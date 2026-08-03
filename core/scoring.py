"""
Largemouth bass activity scoring: 1 (least active) - 10 (most active).

This is an explainable, rule-based heuristic (not a black box) so results
can be reasoned about and tuned. It combines:

  - Barometric pressure trend (falling pressure ahead of a front = more
    active feeding; high, stable pressure right after a front = tougher bite)
  - Moon phase (new/full moon windows historically correlate with
    increased feeding activity - classic solunar theory)
  - Solunar major/minor windows (time-of-day overlay)
  - Cloud cover (overcast = more active, especially shallow/aggressive bite)
  - Wind (light-moderate wind stirs baitfish/oxygenates - a mild positive;
    dead calm or very strong wind is a mild negative)
  - Season / estimated water temperature (drives depth & aggression pattern)
  - Precipitation (light/steady rain before a front can be good; the app
    flags heavy storms as unsafe rather than scoring them favorably)

Weights are documented inline. `core/calibration.py` can nudge these
weights over time using logged trip outcomes.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timedelta, time as dtime
from typing import Optional

from . import astro
from .weather import (
    WeatherBundle,
    hourly_rows_for_date,
    daily_row_for_date,
    pressure_trend_hpa_per_24h,
    estimate_water_temp_f,
    LAKE_LAT,
    LAKE_LON,
    LAKE_TZ_UTC_OFFSET_HOURS,
)

SEGMENTS = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]

DEFAULT_WEIGHTS = {
    "pressure_falling": 2.5,
    "pressure_high_stable_post_front": -2.0,
    "pressure_rising_slow": -0.5,
    "moon_new_full_bonus": 1.5,
    "cloud_overcast_bonus": 1.2,
    "wind_sweet_spot_bonus": 0.8,
    "wind_calm_or_high_penalty": -0.8,
    "season_spring_fall_bonus": 1.3,
    "season_summer_midday_penalty": -1.5,
    "season_winter_penalty": -1.0,
    "storm_penalty": -3.0,
    "solunar_major_bonus": 2.0,
    "solunar_minor_bonus": 1.0,
}


def season_stage(day_of_year: int, water_temp_f: float) -> str:
    if water_temp_f < 50:
        return "winter"
    if 50 <= water_temp_f < 60:
        return "pre_spawn"
    if 60 <= water_temp_f < 75 and 60 <= day_of_year <= 150:
        return "spawn"
    if water_temp_f >= 80:
        return "summer_peak"
    if 75 <= water_temp_f < 80:
        return "post_spawn_summer"
    if water_temp_f < 65 and day_of_year > 250:
        return "fall_turnover"
    return "fall_feed_up"


@dataclass
class SegmentForecast:
    name: str
    start: datetime
    end: datetime
    score: float
    solunar_overlap: Optional[str]  # "major" | "minor" | None
    notes: list


@dataclass
class DayForecast:
    the_date: date
    overall_score: float
    water_temp_f: float
    season: str
    moon: astro.MoonPhase
    pressure_trend_24h: float
    sunrise: Optional[datetime]
    sunset: Optional[datetime]
    segments: list  # list[SegmentForecast]
    weather_summary: dict
    warnings: list


def _segment_windows(sunrise: datetime, sunset: datetime, d: date):
    dawn_start = sunrise - timedelta(hours=1)
    dawn_end = sunrise + timedelta(hours=1)
    dusk_start = sunset - timedelta(hours=1)
    dusk_end = sunset + timedelta(hours=1)
    morning_end = max(dawn_end, sunrise.replace(hour=11, minute=0))
    midday_end = sunrise.replace(hour=14, minute=0)
    afternoon_end = dusk_start
    night_start = dusk_end
    next_dawn = dawn_start + timedelta(days=1)

    return [
        ("Dawn", dawn_start, dawn_end),
        ("Morning", dawn_end, morning_end),
        ("Midday", morning_end, midday_end),
        ("Afternoon", midday_end, afternoon_end),
        ("Dusk", dusk_start, dusk_end),
        ("Night", night_start, next_dawn),
    ]


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def _clamp(v, lo=1.0, hi=10.0):
    return max(lo, min(hi, v))


def score_day(
    bundle: WeatherBundle,
    d: date,
    weights: dict = None,
    lat: float = LAKE_LAT,
    lon: float = LAKE_LON,
) -> DayForecast:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    warnings = []

    daily = daily_row_for_date(bundle, d)
    hourly = hourly_rows_for_date(bundle, d)
    if not daily or not hourly:
        raise ValueError(f"No weather data available for {d}")

    sunrise = daily["sunrise"]
    sunset = daily["sunset"]
    day_of_year = d.timetuple().tm_yday

    water_temp = estimate_water_temp_f(bundle, d, day_of_year)
    season = season_stage(day_of_year, water_temp)

    noon = datetime.combine(d, dtime(12, 0))
    p_trend = pressure_trend_hpa_per_24h(bundle, noon)

    moon = astro.moon_phase(datetime.combine(d, dtime(18, 0)))
    sol = astro.solunar_times(d, lat, lon, LAKE_TZ_UTC_OFFSET_HOURS)

    avg_cloud = sum(r["cloudcover"] for r in hourly if r["cloudcover"] is not None) / max(len(hourly), 1)
    avg_wind = sum(r["windspeed_10m"] for r in hourly if r["windspeed_10m"] is not None) / max(len(hourly), 1)
    max_precip_prob = max((r["precipitation_probability"] or 0) for r in hourly)
    total_precip = sum((r["precipitation"] or 0) for r in hourly)

    if total_precip > 1.0 or max_precip_prob > 85:
        warnings.append("Storms/heavy rain possible - check local radar and lightning before heading out.")

    windows = _segment_windows(sunrise, sunset, d)
    segments = []
    for name, start, end in windows:
        score = 5.0
        notes = []

        # Pressure
        if p_trend <= -1.5:
            score += w["pressure_falling"]
            notes.append("Falling pressure ahead of a front - bite often turns on.")
        elif p_trend >= 2.0:
            score += w["pressure_high_stable_post_front"]
            notes.append("High, rising pressure post-front - expect a tougher, slower bite.")
        elif 0.3 < p_trend < 2.0:
            score += w["pressure_rising_slow"]

        # Moon
        if moon.is_new_or_full_window:
            score += w["moon_new_full_bonus"]
            notes.append(f"{moon.name} - near new/full moon, historically more active feeding.")

        # Solunar overlay (segment-level)
        overlap = None
        for ms, me in sol.major_periods:
            if _overlaps(start, end, ms, me):
                overlap = "major"
        if overlap is None:
            for ms, me in sol.minor_periods:
                if _overlaps(start, end, ms, me):
                    overlap = "minor"
        if overlap == "major":
            score += w["solunar_major_bonus"]
            notes.append("Overlaps a solunar major period.")
        elif overlap == "minor":
            score += w["solunar_minor_bonus"]
            notes.append("Overlaps a solunar minor period.")

        # Cloud cover
        if avg_cloud >= 60:
            score += w["cloud_overcast_bonus"]
            notes.append("Overcast skies - fish often roam and feed more actively/shallow.")

        # Wind
        if 4 <= avg_wind <= 14:
            score += w["wind_sweet_spot_bonus"]
            notes.append("Light-moderate wind/chop - good for reaction baits and windblown banks.")
        elif avg_wind < 2 or avg_wind > 20:
            score += w["wind_calm_or_high_penalty"]

        # Season / segment interplay
        if season in ("spawn", "pre_spawn", "fall_feed_up"):
            score += w["season_spring_fall_bonus"]
        if season == "summer_peak" and name in ("Midday", "Afternoon"):
            score += w["season_summer_midday_penalty"]
            notes.append("Summer heat - fish likely pushed to deeper, cooler structure midday.")
        if season == "winter":
            score += w["season_winter_penalty"]

        # Storm penalty applies lake-wide regardless of other bonuses
        if total_precip > 1.0 or max_precip_prob > 85:
            score += w["storm_penalty"]

        segments.append(
            SegmentForecast(
                name=name, start=start, end=end, score=round(_clamp(score), 1),
                solunar_overlap=overlap, notes=notes,
            )
        )

    overall = round(_clamp(sum(s.score for s in segments) / len(segments)), 1)

    return DayForecast(
        the_date=d,
        overall_score=overall,
        water_temp_f=water_temp,
        season=season,
        moon=moon,
        pressure_trend_24h=round(p_trend, 2),
        sunrise=sunrise,
        sunset=sunset,
        segments=segments,
        weather_summary={
            "avg_cloud_pct": round(avg_cloud, 0),
            "avg_wind_mph": round(avg_wind, 1),
            "max_precip_prob_pct": max_precip_prob,
            "total_precip_in": round(total_precip, 2),
            "temp_hi_f": daily.get("temperature_2m_max"),
            "temp_lo_f": daily.get("temperature_2m_min"),
        },
        warnings=warnings,
    )


def score_week(bundle: WeatherBundle, start: date, days: int = 7, weights: dict = None):
    return [score_day(bundle, start + timedelta(days=i), weights=weights) for i in range(days)]
