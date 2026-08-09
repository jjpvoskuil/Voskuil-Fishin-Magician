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
    LAKE_ZONEINFO,
)

SEGMENTS = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]


def lake_now_naive() -> datetime:
    """Current wall-clock time at the lake (America/Chicago) as a naive
    datetime, matching the convention this module already uses internally -
    score_day() passes naive local-time datetimes (not true UTC, despite
    some parameter names) to astro.moon_phase()/pressure_trend_hpa_per_24h()
    because the weather bundle's own hourly timestamps come back in the
    lake's local timezone (Open-Meteo's `timezone=LAKE_TZ` request param),
    not UTC. Used by manual_segment_score()/realtime_context_from_bundle()
    so "right now" lines up with that same convention."""
    return datetime.now(LAKE_ZONEINFO).replace(tzinfo=None)

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


def effective_season_and_temp(day: "DayForecast", water_temp_override_f: float = None):
    """
    If the angler supplied a real surface-temp reading (from their own
    electronics), use it in place of the estimated water temp for anything
    downstream (lure/season selection) - a measured reading beats our
    air-temp-based estimate. Returns (season, water_temp_f).
    """
    if water_temp_override_f is None:
        return day.season, day.water_temp_f
    day_of_year = day.the_date.timetuple().tm_yday
    return season_stage(day_of_year, water_temp_override_f), water_temp_override_f


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


def _segment_score(
    name: str, p_trend: float, moon: "astro.MoonPhase", overlap: Optional[str],
    avg_cloud: float, avg_wind: float, season: str, total_precip: float,
    max_precip_prob: float, weights: dict,
) -> tuple:
    """The actual 1-10 scoring formula for one time-of-day segment, factored
    out of score_day() so it can be driven either by real hourly/daily
    weather-bundle data (score_day's normal path) or by conditions someone
    reports by hand while standing at the water (core.scoring.
    manual_segment_score(), used by the spot-specific "fish this spot now"
    page) - both paths produce a score using the exact same weights/rules,
    just from different sources for the same handful of inputs. Returns
    (score, notes)."""
    w = weights
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

    return round(_clamp(score), 1), notes


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
        # Solunar overlay (segment-level) - needs this segment's actual start/end,
        # so it's resolved here rather than inside the shared _segment_score() helper.
        overlap = None
        for ms, me in sol.major_periods:
            if _overlaps(start, end, ms, me):
                overlap = "major"
        if overlap is None:
            for ms, me in sol.minor_periods:
                if _overlaps(start, end, ms, me):
                    overlap = "minor"

        score, notes = _segment_score(
            name, p_trend, moon, overlap, avg_cloud, avg_wind, season,
            total_precip, max_precip_prob, w,
        )

        segments.append(
            SegmentForecast(name=name, start=start, end=end, score=score, solunar_overlap=overlap, notes=notes)
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


@dataclass
class ManualScoreResult:
    score: float
    notes: list
    moon: astro.MoonPhase
    warnings: list


def manual_segment_score(
    segment_name: str,
    season: str,
    avg_cloud_pct: float,
    avg_wind_mph: float,
    total_precip_in: float = 0.0,
    max_precip_prob_pct: float = 0.0,
    pressure_trend_24h: float = 0.0,
    moon: Optional["astro.MoonPhase"] = None,
    solunar_overlap: Optional[str] = None,
    weights: dict = None,
    at_time: Optional[datetime] = None,
) -> ManualScoreResult:
    """Same 1-10 activity score as score_day()/score_week(), but driven by
    conditions someone reports by hand while standing at the water (the
    spot-specific "fish this spot now" page) instead of an Open-Meteo
    forecast bundle for a whole day.

    Real moon phase needs only a point in time, not a weather API, so it's
    computed here (via core.astro) unless the caller already has one - as
    of "right now" (lake_now_naive()) by default, or as of `at_time` when
    the caller supplies one. Pass the angler's own entered session-start
    time here (not wall-clock "now") when they're filling this out ahead of
    or after the actual session, so the moon phase reflects the time they
    were actually on the water rather than whenever they happened to type
    it in - the entered time should win over a generic "now" default.
    Everything else the caller must supply - typically approximated from
    the angler's own observations at the water (core.onwater.py's band
    helpers turn "Overcast / Diffuse Day" or "Heavy / Turbulent" wind into
    the same avg_cloud_pct/avg_wind_mph/precip inputs score_day() would
    have extracted from a real bundle) or a real pressure-trend reading if
    a weather bundle happens to be available (core.weather.
    pressure_trend_hpa_per_24h, also against `at_time` when given).
    Solunar major/minor overlap needs today's real sunrise/sunset, which
    also requires a weather bundle - pass None (the default) when one
    isn't available, and this simply skips that bonus rather than
    guessing."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    moon = moon or astro.moon_phase(at_time or lake_now_naive())

    score, notes = _segment_score(
        segment_name, pressure_trend_24h, moon, solunar_overlap, avg_cloud_pct, avg_wind_mph,
        season, total_precip_in, max_precip_prob_pct, w,
    )

    warnings = []
    if total_precip_in > 1.0 or max_precip_prob_pct > 85:
        warnings.append("Storms/heavy rain possible - check local radar and lightning before heading out.")

    return ManualScoreResult(score=score, notes=notes, moon=moon, warnings=warnings)


def segment_time_ranges(bundle: Optional[WeatherBundle], d: date) -> Optional[dict]:
    """Real per-segment (Dawn/Morning/.../Night) start/end datetimes for date
    `d`, derived from the weather bundle's actual sunrise/sunset for that
    date - e.g. for labeling a "time window" picker with the real clock
    range each segment covers today ("Dawn (5:52 AM-7:52 AM)"), same as the
    7-Day Forecast page already shows. Returns None if a bundle isn't
    available or doesn't cover that date, so callers can degrade
    gracefully (just show the segment names with no time range) rather
    than raising."""
    if bundle is None:
        return None
    try:
        daily = daily_row_for_date(bundle, d)
        if not daily or not daily.get("sunrise") or not daily.get("sunset"):
            return None
        return {name: (start, end) for name, start, end in _segment_windows(daily["sunrise"], daily["sunset"], d)}
    except Exception:
        return None


def realtime_context_from_bundle(
    bundle: Optional[WeatherBundle], segment_name: str, d: date,
    lat: float = LAKE_LAT, lon: float = LAKE_LON, tz_offset_hours: float = LAKE_TZ_UTC_OFFSET_HOURS,
    at_time: Optional[datetime] = None,
) -> dict:
    """Best-effort real pressure-trend + solunar-overlap lookup, for
    manual_segment_score() callers that happen to have an already-fetched
    weather bundle handy (e.g. the spot-specific session page also shows
    the 7-Day Forecast elsewhere in the app, so the bundle is usually
    already cached) - a nice-to-have enhancement layered on top of
    otherwise fully hand-entered conditions, not a requirement.

    Pressure trend is computed as of `at_time` if given, else "right now"
    (lake_now_naive()) - pass the angler's own entered session-start time
    so this reflects that specific moment rather than whenever they
    happened to be filling out the page, same reasoning as
    manual_segment_score()'s `at_time`. Solunar overlap is already tied to
    `segment_name` + `d` rather than a specific instant, so it isn't
    affected by `at_time`.

    Returns {"pressure_trend_24h": float, "solunar_overlap": str|None},
    falling back to 0.0/None for anything that can't be resolved (no
    bundle, today's date outside the bundle's coverage, etc.) rather than
    raising."""
    result = {"pressure_trend_24h": 0.0, "solunar_overlap": None}
    if bundle is None:
        return result

    try:
        result["pressure_trend_24h"] = round(pressure_trend_hpa_per_24h(bundle, at_time or lake_now_naive()), 2)
    except Exception:
        pass

    try:
        ranges = segment_time_ranges(bundle, d)
        window = ranges.get(segment_name) if ranges else None
        if window:
            start, end = window
            sol = astro.solunar_times(d, lat, lon, tz_offset_hours)
            overlap = None
            for ms, me in sol.major_periods:
                if _overlaps(start, end, ms, me):
                    overlap = "major"
            if overlap is None:
                for ms, me in sol.minor_periods:
                    if _overlaps(start, end, ms, me):
                        overlap = "minor"
            result["solunar_overlap"] = overlap
    except Exception:
        pass

    return result


def score_week(bundle: WeatherBundle, start: date, days: int = 7, weights: dict = None):
    """Score each day in [start, start+days). Skips (rather than raising for)
    any individual day the weather bundle doesn't cover, instead of letting
    score_day's ValueError abort the whole week - e.g. a cached bundle that
    briefly lags one day behind right at the lake's local-day rollover would
    otherwise take down the entire page for a day it does have data for, just
    because a later day in the requested range is momentarily missing.
    Callers should check len(result) against `days` and let the user know if
    it came back short."""
    results = []
    for i in range(days):
        d = start + timedelta(days=i)
        try:
            results.append(score_day(bundle, d, weights=weights))
        except ValueError:
            continue
    return results
