"""
Largemouth bass activity scoring: 1 (least active) - 10 (most active).

This is an explainable, rule-based heuristic (not a black box) so results
can be reasoned about and tuned. It combines:

  - Barometric pressure trend (falling pressure ahead of a front = more
    active feeding; high, stable pressure right after a front = tougher bite) -
    a believable proxy for a front's real, better-evidenced side effects
    (cloud/wind/temp shift) rather than a strongly-evidenced factor on its
    own, so it's weighted accordingly rather than as the single biggest lever.
  - Moon phase and solunar major/minor windows - classic solunar theory,
    kept as small, genuinely two-sided nudges (a matching penalty near the
    quarter moons/no-overlap, not just a one-way bonus) rather than dropped,
    but weighted as a token acknowledgment: a 2023 peer-reviewed study (SN
    Applied Sciences) found no significant relationship between solunar
    predictions and real freshwater catch rates.
  - Cloud cover (overcast = more active, especially shallow/aggressive bite;
    clear/bright "bluebird" skies = the classic tough-bite pattern - genuinely
    two-sided, not bonus-only)
  - Wind (light-moderate wind stirs baitfish/oxygenates - a mild positive;
    dead calm or very strong wind is a mild negative)
  - Season / estimated water temperature (drives depth & aggression pattern,
    and - since a real study found temperature to be the one environmental
    factor that actually predicted catch rate - also scores its own
    metabolic-band bonus/penalty directly, the same way manual on-the-water
    readings always have)
  - Precipitation (light/steady rain before a front can be good; the app
    flags heavy storms as unsafe rather than scoring them favorably)

See SESSION_NOTES.md's development log for the sources behind the 2026
weight rebalance (which factors have real evidence vs. which are kept as a
small nod to popular belief) and the before/after distribution check.

Weights are documented inline. `core/calibration.py` can nudge some of
these weights over time using logged trip outcomes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, time as dtime
from typing import Optional

from . import astro
from . import onwater
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
    # Pressure trend is a believable PROXY for an approaching/departing front
    # (which brings real, better-evidenced changes - cloud cover, wind shift,
    # temperature) rather than a well-established direct mechanism on its own -
    # a controlled single-lure study (see SESSION_NOTES.md entry on the 2026
    # rebalance) found no significant catch-rate difference by pressure alone.
    # Trimmed down from this model's old single biggest lever to something more
    # proportionate to that mixed evidence, while keeping the direction (still
    # widely used as a practical proxy by working guides/tournament anglers).
    "pressure_falling": 1.5,
    "pressure_high_stable_post_front": -1.5,
    "pressure_rising_slow": -0.4,
    # Moon phase: solunar theory's underlying claim. A 2023 peer-reviewed study
    # (SN Applied Sciences) tested 7 commercial solunar services against 361
    # real freshwater fishing trips and found no significant relationship to
    # catch rate at all. Kept as a small, now genuinely two-sided nudge (a
    # matching penalty near the quarter moons, not just a one-way bonus near
    # new/full) rather than dropped outright, since it's a near-universal
    # angler belief worth a token acknowledgment - but the magnitude is cut by
    # more than half from before to reflect how weak the evidence actually is.
    "moon_new_full_bonus": 0.6,
    "moon_quarter_penalty": -0.5,
    # Cloud cover: bass are light-sensitive sight predators, and "bluebird
    # skies = tough bite" is near-universal in professional bass-fishing
    # sources (e.g. Bassmaster's cold-front coverage) - genuinely two-sided
    # now instead of only ever rewarding overcast.
    "cloud_overcast_bonus": 1.0,
    "cloud_clear_sky_penalty": -0.8,
    # Wind: kept two-sided (it already was), but trimmed slightly further -
    # the same 2023 peer-reviewed freshwater study that debunked solunar
    # tables also found wind speed had no measurable effect on catch rate at
    # all, the weakest evidence of any factor still in this model.
    "wind_sweet_spot_bonus": 0.5,
    "wind_calm_or_high_penalty": -0.5,
    "season_spring_fall_bonus": 1.3,
    "season_summer_midday_penalty": -1.5,
    "season_winter_penalty": -1.0,
    "storm_penalty": -3.0,
    # Solunar major/minor windows: same weak evidence as moon phase above (it's
    # the same underlying theory) - cut to a small fraction of their old
    # weight rather than dropped, for the same "token acknowledgment of a
    # popular belief, not a load-bearing factor" reasoning.
    "solunar_major_bonus": 0.6,
    "solunar_minor_bonus": 0.3,
    # Light/steady rain (short of storm level) is a well-documented feeding
    # trigger (reduced light penetration, surface disturbance, less wary fish) -
    # this applies to both score_day() and manual_segment_score(), unlike the
    # manual-only weights below, since total_precip/max_precip_prob are already
    # available from a real forecast bundle too.
    "precip_light_rain_bonus": 0.6,
    # Water-temperature metabolic bands (core.onwater.water_temp_band) - the
    # one factor a real peer-reviewed study actually found to matter (catch
    # rate rose with temperature). score_day()/score_week() now pass their own
    # estimated water temp through, same as manual_segment_score() always has -
    # water_clarity/forage_present below remain manual-entry-only, since
    # there's no way to estimate either from a weather forecast.
    "water_temp_cold_penalty": -1.0,
    "water_temp_prespawn_bonus": 0.3,
    "water_temp_prime_bonus": 1.0,
    "water_temp_extreme_penalty": -1.2,
    # Water clarity - manual-entry-only, same reasoning as the water-temp weights.
    "water_clarity_stained_bonus": 0.4,
    "water_clarity_muddy_penalty": -0.3,
    # Forage observed nearby - manual-entry-only, same reasoning.
    "forage_present_bonus": 0.3,
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
    breakdown: list = field(default_factory=list)  # [(label, delta, detail), ...] - see _segment_score()
    pressure_trend_24h: float = 0.0  # this segment's own 24h trend - see score_day()


@dataclass
class DayForecast:
    the_date: date
    overall_score: float
    water_temp_f: float
    season: str
    moon: astro.MoonPhase
    pressure_trend_24h: float  # day-level, noon-anchored "at a glance" number - see
    # each segment's OWN pressure_trend_24h (SegmentForecast) for the value
    # actually driving that segment's score/lure pick.
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

    # Morning/Midday/Afternoon used to end at fixed 11:00 AM/2:00 PM clock
    # cutoffs - so on a long summer day Midday still stayed a flat 3 hours
    # while Afternoon absorbed all the extra daylight, and on a short winter
    # day Morning got squeezed down to barely 2 hours. Splitting the actual
    # "daytime interior" - the stretch between Dawn's end and Dusk's start -
    # into three equal proportional thirds instead means all three windows
    # genuinely grow and shrink with the season, the same way Dawn/Dusk
    # (always a real ±1h around sunrise/sunset) and Night (whatever's left)
    # already did - every segment now tracks the actual sunrise/sunset for
    # date `d`, not a mix of real astronomy and fixed clock time.
    interior = dusk_start - dawn_end
    third = interior / 3
    morning_end = dawn_end + third
    midday_end = dawn_end + 2 * third
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
    water_temp_f: Optional[float] = None, water_clarity: Optional[str] = None,
    forage_present: Optional[bool] = None,
) -> tuple:
    """The actual 1-10 scoring formula for one time-of-day segment, factored
    out of score_day() so it can be driven either by real hourly/daily
    weather-bundle data (score_day's normal path) or by conditions someone
    reports by hand while standing at the water (core.scoring.
    manual_segment_score(), used by the spot-specific "fish this spot now"
    page) - both paths produce a score using the exact same weights/rules,
    just from different sources for the same handful of inputs.

    `water_temp_f` is a shared enhancement (like the light-rain bonus below) -
    score_day()/score_week() pass their own estimated water temp through here
    too, since a real peer-reviewed study found temperature to be the one
    environmental factor that actually predicted catch rate (see SESSION_NOTES.md).
    `water_clarity` and `forage_present`, by contrast, stay manual-entry-only -
    a real Secchi-depth reading or "did you actually see forage" only exist
    when someone is standing at the water, with no equivalent forecast-API
    estimate to fall back on. Both still default to None, so a caller that
    doesn't pass them behaves exactly as if they didn't exist.

    Returns (score, notes, breakdown) - `notes` is the existing plain-
    language bullet list used elsewhere in the app; `breakdown` is a new
    list of (label, delta, detail) tuples for every factor that actually
    moved the score (base included), meant for a "how was this derived"
    explainer - see pages/6_Spot_Session.py's score `help=` tooltip."""
    w = weights
    score = 5.0
    notes = []
    breakdown = [("Base", 5.0, "Starting point before any factors below.")]

    # Pressure
    if p_trend <= -1.5:
        d = w["pressure_falling"]
        note = "Falling pressure ahead of a front - bite often turns on."
        score += d; notes.append(note); breakdown.append(("Pressure trend", d, note))
    elif p_trend >= 2.0:
        d = w["pressure_high_stable_post_front"]
        note = "High, rising pressure post-front - expect a tougher, slower bite."
        score += d; notes.append(note); breakdown.append(("Pressure trend", d, note))
    elif 0.3 < p_trend < 2.0:
        d = w["pressure_rising_slow"]
        score += d; breakdown.append(("Pressure trend", d, "Slowly rising pressure."))

    # Moon - a small, genuinely two-sided nudge (see DEFAULT_WEIGHTS comment on
    # why this is deliberately a token amount, not a load-bearing factor).
    if moon.is_new_or_full_window:
        d = w["moon_new_full_bonus"]
        note = f"{moon.name} - near new/full moon, per solunar lore (mixed real-world evidence)."
        score += d; notes.append(note); breakdown.append(("Moon phase", d, note))
    elif moon.is_quarter_window:
        d = w["moon_quarter_penalty"]
        note = f"{moon.name} - near a quarter moon, traditionally the slowest solunar window."
        score += d; notes.append(note); breakdown.append(("Moon phase", d, note))

    # Solunar overlay (segment-level) - same "small token amount" reasoning as moon phase.
    if overlap == "major":
        d = w["solunar_major_bonus"]
        note = "Overlaps a solunar major period."
        score += d; notes.append(note); breakdown.append(("Solunar", d, note))
    elif overlap == "minor":
        d = w["solunar_minor_bonus"]
        note = "Overlaps a solunar minor period."
        score += d; notes.append(note); breakdown.append(("Solunar", d, note))

    # Cloud cover - genuinely two-sided: bass are light-sensitive sight
    # predators, and bright/clear ("bluebird") skies are a well-documented
    # tough-bite pattern, not just "no bonus."
    if avg_cloud >= 60:
        d = w["cloud_overcast_bonus"]
        note = "Overcast skies - fish often roam and feed more actively/shallow."
        score += d; notes.append(note); breakdown.append(("Cloud cover", d, note))
    elif avg_cloud <= 25:
        d = w["cloud_clear_sky_penalty"]
        note = "Clear/bright ('bluebird') skies - classic tough-bite pattern, especially midday."
        score += d; notes.append(note); breakdown.append(("Cloud cover", d, note))

    # Wind
    if 4 <= avg_wind <= 14:
        d = w["wind_sweet_spot_bonus"]
        note = "Light-moderate wind/chop - good for reaction baits and windblown banks."
        score += d; notes.append(note); breakdown.append(("Wind", d, note))
    elif avg_wind < 2 or avg_wind > 20:
        d = w["wind_calm_or_high_penalty"]
        score += d; breakdown.append(("Wind", d, "Dead calm or very strong wind."))

    # Season / segment interplay
    if season in ("spawn", "pre_spawn", "fall_feed_up"):
        d = w["season_spring_fall_bonus"]
        score += d
        breakdown.append(("Season", d, f"{season.replace('_', ' ').title()} - typically more active feeding."))
    if season == "summer_peak" and name in ("Midday", "Afternoon"):
        d = w["season_summer_midday_penalty"]
        note = "Summer heat - fish likely pushed to deeper, cooler structure midday."
        score += d; notes.append(note); breakdown.append(("Season", d, note))
    if season == "winter":
        d = w["season_winter_penalty"]
        score += d; breakdown.append(("Season", d, "Winter - slower metabolism."))

    # Precipitation: a storm penalty applies lake-wide regardless of other bonuses;
    # short of a storm, light/steady rain is a well-documented feeding trigger.
    if total_precip > 1.0 or max_precip_prob > 85:
        d = w["storm_penalty"]
        score += d; breakdown.append(("Precipitation", d, "Storm-level rain - unfavorable, and unsafe to be out in."))
    elif 0 < total_precip <= 0.5 and max_precip_prob <= 70:
        d = w["precip_light_rain_bonus"]
        note = "Light rain - often triggers more active, less wary feeding."
        score += d; notes.append(note); breakdown.append(("Precipitation", d, note))

    # Water temperature (metabolic band, core.onwater.water_temp_band) - manual-
    # entry-only, see docstring above.
    if water_temp_f is not None:
        band = onwater.water_temp_band(water_temp_f)["label"]
        temp_weight_key = {
            "Cold / Lethargic": "water_temp_cold_penalty",
            "Pre-Spawn Transition": "water_temp_prespawn_bonus",
            "Peak Optimal Prime": "water_temp_prime_bonus",
            "Extreme Thermal Load": "water_temp_extreme_penalty",
        }.get(band)
        if temp_weight_key:
            d = w[temp_weight_key]
            note = f"Water temp is in the {band} range."
            score += d; notes.append(note); breakdown.append(("Water temperature", d, note))

    # Water clarity - manual-entry-only, see docstring above.
    if water_clarity is not None:
        if water_clarity in ("Green stained", "Brown stained"):
            d = w["water_clarity_stained_bonus"]
            note = "Stained water - the classic power-fishing window."
            score += d; notes.append(note); breakdown.append(("Water clarity", d, note))
        elif water_clarity == "Muddy":
            d = w["water_clarity_muddy_penalty"]
            note = "Muddy water - tougher to trigger reaction strikes on sight alone."
            score += d; notes.append(note); breakdown.append(("Water clarity", d, note))

    # Forage presence - manual-entry-only, see docstring above. Absence isn't
    # scored as a penalty - not seeing forage doesn't mean it isn't there.
    if forage_present:
        d = w["forage_present_bonus"]
        note = "Forage observed nearby - active bait often means active predators."
        score += d; notes.append(note); breakdown.append(("Forage", d, note))

    return round(_clamp(score), 1), notes, breakdown


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

    # Pressure trend used to be computed ONCE per day, anchored at noon, and
    # that single value got reused for every one of the day's six segments -
    # so a front sliding through overnight (falling pressure at Dawn/Night)
    # or in the afternoon never showed up as a falling-pressure bonus for
    # those segments unless it also happened to be falling at noon. Real
    # Open-Meteo hourly pressure data for Nolin Lake confirms a genuine
    # ~12h semidiurnal atmospheric "pressure tide" is layered under the real
    # frontal signal (see SESSION_NOTES.md) - which is exactly why the
    # underlying comparison stays a same-hour-24h-ago window (that cancels
    # the tide) rather than a shorter one; what changes here is only WHICH
    # hour each segment anchors that 24h-ago comparison to, so a segment
    # happening well before/after noon reflects the trend at ITS own time of
    # day instead of borrowing noon's. `noon`/day-level `p_trend` stay in
    # DayForecast.pressure_trend_24h below as the at-a-glance "today" headline
    # number (what's shown on Home/7-Day Forecast's summary line), unchanged
    # from before - only the per-segment scoring/lure-recommendation inputs
    # now use their own segment's anchor.
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

        # Anchor this segment's own 24h pressure trend at its midpoint, not
        # the day's shared noon value - see the comment above `noon` for why.
        segment_midpoint = start + (end - start) / 2
        segment_p_trend = pressure_trend_hpa_per_24h(bundle, segment_midpoint)

        score, notes, breakdown = _segment_score(
            name, segment_p_trend, moon, overlap, avg_cloud, avg_wind, season,
            total_precip, max_precip_prob, w, water_temp_f=water_temp,
        )

        segments.append(
            SegmentForecast(
                name=name, start=start, end=end, score=score, solunar_overlap=overlap,
                notes=notes, breakdown=breakdown, pressure_trend_24h=round(segment_p_trend, 2),
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


@dataclass
class ManualScoreResult:
    score: float
    notes: list
    moon: astro.MoonPhase
    warnings: list
    breakdown: list = field(default_factory=list)  # [(label, delta, detail), ...] - see _segment_score()


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
    water_temp_f: Optional[float] = None,
    water_clarity: Optional[str] = None,
    forage_present: Optional[bool] = None,
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
    helpers turn "Mostly Cloudy" sky or "Heavy / Turbulent" wind into
    the same avg_cloud_pct/avg_wind_mph/precip inputs score_day() would
    have extracted from a real bundle) or a real pressure-trend reading if
    a weather bundle happens to be available (core.weather.
    pressure_trend_hpa_per_24h, also against `at_time` when given).
    Solunar major/minor overlap needs today's real sunrise/sunset, which
    also requires a weather bundle - pass None (the default) when one
    isn't available, and this simply skips that bonus rather than
    guessing.

    `water_temp_f`, `water_clarity` (one of core.lures.WATER_CLARITY_OPTIONS),
    and `forage_present` (whether the angler reported seeing any forage) are
    additional factors score_day()/score_week() have no equivalent input
    for - passing them in lets this manual path go "beyond pressure trend
    and moon phase" and actually use the rest of what the angler entered
    (see _segment_score()'s docstring for exactly how each one scores)."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    moon = moon or astro.moon_phase(at_time or lake_now_naive())

    score, notes, breakdown = _segment_score(
        segment_name, pressure_trend_24h, moon, solunar_overlap, avg_cloud_pct, avg_wind_mph,
        season, total_precip_in, max_precip_prob_pct, w,
        water_temp_f=water_temp_f, water_clarity=water_clarity, forage_present=forage_present,
    )

    warnings = []
    if total_precip_in > 1.0 or max_precip_prob_pct > 85:
        warnings.append("Storms/heavy rain possible - check local radar and lightning before heading out.")

    return ManualScoreResult(score=score, notes=notes, moon=moon, warnings=warnings, breakdown=breakdown)


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
