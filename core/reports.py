"""
Reports page - punch-list #92, first pass ("get the basic framework
together... I am sure this will iterate out a lot").

Angler's ask, verbatim: "Create a dynamic reports page with the initial
primary purpose of running correlations between various session
parameters, session weather conditions, moon illumination (night before),
location, lure used, lure colors, etc. and fishing success (# of fish
caught, fish catching rate, success with certain fish types. I would like
this to be as dynamic as possible so that I can run various analyses
quickly and flexibly over various dates and date ranges. I'd like to also
have the ability for the model to predict success in future days given
forecasted parameter and/or known moon illumination (night before). I
would like the output to generate line or bar graphs to visualize the
data. I would also like the ability to export the output of the analysis
to Excel as appropriate."

This module is the data side of that: turn the raw trip log into two wide,
fully-featured DataFrames (one row per logged lure-use, one row per
individual fish caught - same two-granularity split pages/8_Leaderboard.py
already uses, for the same reason: some questions are per-trip, some are
per-catch), with every "session parameter"/weather/moon/location/lure
factor already computed as a plain column - then one generic
compute_report() that groups any chosen success metric by any chosen
factor, over any date range/angler/segment/species filter. The page
(pages/9_Reports.py) is just UI on top of this - picking a factor, a
metric, and a filter set, then handing compute_report()'s output to a
chart and an Excel export.

Deliberately Streamlit-free (like core/daily_leaderboard.py) so this is
unit-testable without AppTest, and deliberately does NOT reuse
pages/8_Leaderboard.py's private _build_frames()/category builders for the
same reason that module gave: different shape (a wide factor table meant
to be grouped by ANY column, not a fixed list of ranking categories), so
keeping them independent avoids regression risk on that already-shipped
page even though the two share some parsing logic.

Explicitly OUT of scope for this first pass, per the angler's own framing
("I am sure this will iterate out a lot, but let's get the basic framework
together today, at the least"): the predictive piece ("predict success in
future days given forecasted parameters"). Everything below is the
descriptive/correlational half only - see pages/9_Reports.py's own top-of-
page caption for how that's flagged to the angler.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Optional

import pandas as pd

from core.astro import moon_phase
from core.calibration import trip_fish_per_hour, MIN_TRUSTED_SESSION_HOURS, MAX_TRUSTED_SESSION_HOURS
from core.daily_leaderboard import week_bounds
from core.lures import LURE_PROFILES
from core.onwater import water_temp_band, WATER_TEMP_BANDS, LIGHT_CONDITIONS, WIND_BAND_LABELS
from core.scoring import SEGMENTS, season_stage
from core.storage import parse_conditions

# --- Small parsing helpers (mirrors pages/8_Leaderboard.py's own conventions,
# kept local rather than imported since that page's are private) ------------

def _parse_date(s) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _to_float(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # NaN check


def _lure_category_label(cond: dict) -> Optional[str]:
    category = cond.get("lure_category")
    if not category:
        return None
    return LURE_PROFILES.get(category, {}).get("name", category)


# --- Pressure trend banding ---------------------------------------------------
# No existing named band table for this one (unlike wind/sky/water-temp,
# which already have one in core.onwater) - reusing the same two thresholds
# core.calibration._factor_flags() already calibrates against
# (pressure_falling <= -1.5, pressure_high_stable_post_front >= 2.0) so
# "falling/steady/rising" here means the same thing it already means
# elsewhere in this app, not a newly-invented cutoff.
PRESSURE_TREND_BANDS = ["Falling", "Steady", "Rising / High"]


def _pressure_trend_band(pt: Optional[float]) -> Optional[str]:
    if pt is None:
        return None
    if pt <= -1.5:
        return "Falling"
    if pt >= 2.0:
        return "Rising / High"
    return "Steady"


# --- Moon illumination (night before) -----------------------------------------
# Reuses core.astro.moon_phase() directly (not core.calibration's private
# day-of-cycle bucketing) for the actual real illumination % on the evening
# BEFORE trip_date (6pm the prior day - the moon that was actually out
# overnight before this trip's day), same convention
# core.calibration._day_of_cycle_for_date() already uses for its own
# Dawn/Morning-vs-moon chart, just without going through that chart's
# whole-day-of-lunar-cycle bucketing - a continuous 0-100 float here.
MOON_ILLUMINATION_BIN_WIDTH = 10  # fixed-width deciles, not data-driven quantiles
MOON_ILLUMINATION_BIN_ORDER = [f"{lo}-{lo + MOON_ILLUMINATION_BIN_WIDTH}%" for lo in range(0, 100, MOON_ILLUMINATION_BIN_WIDTH)]


def moon_illumination_pct_night_before(trip_date: date) -> float:
    night_before = datetime.combine(trip_date - timedelta(days=1), datetime.min.time().replace(hour=18))
    return round(moon_phase(night_before).illumination_pct, 1)


def _moon_illumination_bin(pct: Optional[float]) -> Optional[str]:
    if pct is None:
        return None
    pct = max(0.0, min(100.0, pct))
    lo = int(pct // MOON_ILLUMINATION_BIN_WIDTH) * MOON_ILLUMINATION_BIN_WIDTH
    lo = min(lo, 100 - MOON_ILLUMINATION_BIN_WIDTH)  # 100.0 falls in the last bucket, not a new "100-100%" one
    hi = lo + MOON_ILLUMINATION_BIN_WIDTH
    return f"{lo}-{hi}%"


# --- Water temp: user-adjustable-width buckets (punch-list #92 follow-up) -----
# Angler's report: "Water Temp Band" (the 5 fixed biological bands right
# below) is too coarse right now - a whole season's worth of trips hasn't
# been logged yet, so the real observed range so far is only ~10-15°F wide,
# meaning nearly every trip lands in just one or two of those five bands.
# "As the seasons change, this will certainly get larger, so maybe we can
# have the app create buckets based on a user inputted range."
#
# Rather than replacing "Water Temp Band" (still the right long-term view,
# and it's the same classification core.scoring/Spot Session already use
# elsewhere), this adds a SECOND, independent water-temp factor with a
# user-chosen bucket width in °F (pages/9_Reports.py's own "Bucket width"
# control, shown only when this factor is picked) - the angler can zoom in
# tight while the logged range is narrow, and widen it back out once a
# full season's spread makes the coarser named bands meaningful again.
#
# Unlike every other factor above, this one can't be precomputed as a
# column in build_reports_dataframe() - the bucket width isn't known until
# query time - so compute_report() computes it on the fly (see the
# WATER_TEMP_BUCKET_FACTOR handling there) instead of _row_factors()
# materializing it up front like every other factor.
#
# Buckets are anchored to absolute 0°F (floor(value / width) * width), NOT
# to whatever the currently-filtered data's own min happens to be, for the
# same reason MOON_ILLUMINATION_BIN_ORDER is anchored to 0% rather than the
# observed minimum illumination: a given bucket's boundaries need to stay
# the SAME (e.g. always "68-70°F" at a 2°F width, never shifting to
# "67.4-69.4°F" because a different date range was picked) so two different
# filter picks stay comparable side by side, and so the label itself is a
# clean round number instead of an arbitrary float.
WATER_TEMP_BUCKET_FACTOR = "water_temp_bucket"
DEFAULT_WATER_TEMP_BUCKET_WIDTH_F = 2.0


def _water_temp_bucket_label(temp_f: Optional[float], width: float) -> Optional[str]:
    # pd.isna(), not "is None" - callers apply() this over a pandas Series,
    # which represents a missing water_temp_f as float NaN, not Python None
    # (math.floor(nan) raises ValueError, not something floor() itself
    # would ever cleanly return, so this has to be caught before that call).
    if temp_f is None or width <= 0 or pd.isna(temp_f):
        return None
    lo = math.floor(temp_f / width) * width
    hi = lo + width
    return f"{lo:g}-{hi:g}°F"


def _water_temp_bucket_axis(observed_temps: pd.Series, width: float) -> list:
    """Every width-wide bucket between the coldest and warmest water-temp
    reading actually present in the currently-filtered trips (not the
    metric's own possibly-narrower subset, and not the app's all-time
    range) - same "show a real zero between two real endpoints, don't just
    skip it" convention _date_axis() already uses for date-based factors,
    just for a continuous numeric range instead of a calendar range."""
    valid = observed_temps.dropna() if observed_temps is not None else pd.Series(dtype=float)
    if valid.empty or width <= 0:
        return []
    lo = math.floor(valid.min() / width) * width
    hi = math.floor(valid.max() / width) * width
    labels = []
    b = lo
    while b <= hi + 1e-9:  # tolerate float drift at the top edge
        labels.append(_water_temp_bucket_label(b, width))
        b += width
    return labels


# --- Factor catalog --------------------------------------------------------
# label -> (column name, ORDER_HINTS key or None). Every column here is
# fully materialized (plain string/None) in both trips_df and fish_df by
# build_reports_dataframe() below - compute_report() never special-cases a
# factor by name, it just groups by whichever column the caller picked. The
# one exception is WATER_TEMP_BUCKET_FACTOR (see its own comment above) -
# its bucket width isn't known until query time, so compute_report()
# computes that one column on the fly instead.
FACTOR_OPTIONS = {
    "Spot": "spot",
    "Structure Type": "structure_type",
    "Water Clarity": "water_clarity",
    "Lure": "lure",
    "Lure Category": "lure_category",
    "Color": "color",
    "Technique": "technique",
    "Time Segment": "segment",
    "Season": "season",
    "Sky Condition": "light_condition",
    "Wind Band": "wind_band",
    "Wind Direction": "wind_direction",
    "Precipitation": "precipitation",
    "Water Temp Band": "water_temp_band",
    "Water Temp (custom range)": WATER_TEMP_BUCKET_FACTOR,
    "Pressure Trend": "pressure_trend_band",
    "Moon Illumination % (night before)": "moon_illumination_bin",
    "Fish Activity (reported)": "fish_activity",
    "Forage Activity (reported)": "forage_activity",
    "Angler": "angler",
    "Day of Week": "day_of_week",
    "Date (daily)": "date",
    "Date (weekly, Sun-Sat)": "week_start",
}

# Columns whose natural order isn't plain alphabetical - used to both (a)
# sort the aggregated report and (b) show every listed value even at n=0,
# so e.g. "Time Segment" always shows all 6 segments in Dawn->Night order
# instead of only whichever ones happen to have data, and a bar chart's
# x-axis stays stable across different filter picks.
_DAY_OF_WEEK_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
ORDER_HINTS = {
    "segment": SEGMENTS,
    "water_temp_band": [b[2] for b in WATER_TEMP_BANDS],
    "pressure_trend_band": PRESSURE_TREND_BANDS,
    "light_condition": LIGHT_CONDITIONS,
    "wind_band": WIND_BAND_LABELS,
    "moon_illumination_bin": MOON_ILLUMINATION_BIN_ORDER,
    "day_of_week": _DAY_OF_WEEK_ORDER,
}

# Factors whose column is a real date/week-start (not a plain label) - these
# always sort chronologically and always get every date/week IN the
# filtered range shown (even at n=0), never just the observed ones, same
# "show a real zero, don't just omit the day" convention
# core.calibration.daily_dawn_morning_catch() already uses.
DATE_FACTOR_COLUMNS = {"date", "week_start"}

METRIC_OPTIONS = {
    "Total Fish Caught": "total_fish",
    "Fish per Hour (rate)": "fish_per_hour",
    "Biggest Fish (lb)": "biggest_fish",
    "# Trips": "trip_count",
}

# Metrics answering "success with certain fish types" - species-filterable,
# since they're computed from fish_df (one row per individual catch).
# fish_per_hour/trip_count are inherently per-TRIP, not per-species, so the
# page disables the species picker for those (mirrors
# pages/8_Leaderboard.py's own disabled-when-not-applicable pattern).
SPECIES_FILTERABLE_METRICS = {"total_fish", "biggest_fish"}


# --- Fish-per-hour: pooled (sum/sum), not a median-of-per-trip-rates ------------
# Punch-list #92 follow-up (angler's live report: "if I pick sky condition and
# total fish caught, there is something in every bucket, but if I do it as a
# fish caught rate, only 3 buckets have a number... something is off").
#
# Root cause, confirmed against the real logged data: core.calibration's own
# calibrate_weights()/location_adjustments() deliberately take the MEDIAN of
# each trip's own fish-per-hour rate within a bucket (see that module's
# docstring - a single wildly-productive-but-still-plausible outlier
# shouldn't single-handedly swing a calibration nudge). This module originally
# mirrored that same convention. But bass fishing produces plenty of
# genuinely-skunked (0 fish, otherwise perfectly trustworthy) trips - real
# live data checked directly: "Clear / Sunny" had 64 trustworthy trips
# totalling 134 fish (a clearly productive condition, per Total Fish Caught),
# yet its MEDIAN per-trip rate was exactly 0.0, because more than half of
# those 64 individual trips happened to be skunked. Calibration only needs
# one outlier-robust NUDGE direction, so that's fine there; a page whose
# whole point is "compare success across conditions at a glance" is actively
# misleading when a condition that clearly produces fish reads as a flat,
# invisible-on-the-chart zero.
#
# Fixed by pooling instead: sum(fish caught) / sum(trustworthy hours) across
# every trustworthy trip in the bucket - the standard "catch per unit
# effort" framing (every logged hour counts toward the denominator, a
# skunked-but-trustworthy trip included, not excluded) - rather than
# averaging each trip's own already-noisy single-trip rate. A bucket only
# reads as 0 now if it genuinely caught zero fish across every trustworthy
# hour logged under it.
#
# _trustworthy_session_hours() duplicates trip_fish_per_hour()'s own
# duration-parsing/plausibility-window check (see that function's docstring
# for the full "why 5min-6hr" reasoning) rather than importing it, because a
# skunked trip's real hours can't be recovered by dividing back out of its
# own 0.0 rate (0 fish / hours = 0.0, and 0.0 doesn't tell you what the
# hours were) - the pooled denominator genuinely needs the raw hours, not
# just the rate. MIN/MAX_TRUSTED_SESSION_HOURS are imported (not
# duplicated) so the plausibility window itself can't drift out of sync
# with calibration's own.
def _trustworthy_session_hours(row: dict) -> Optional[float]:
    conditions = parse_conditions(row)
    start = conditions.get("lure_start_time")
    end = conditions.get("lure_end_time")
    if not start or not end:
        return None
    try:
        t0 = dtime.fromisoformat(start)
        t1 = dtime.fromisoformat(end)
    except (ValueError, TypeError):
        return None
    seconds = lambda t: t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6
    hours = (seconds(t1) - seconds(t0)) / 3600.0
    if not (MIN_TRUSTED_SESSION_HOURS <= hours <= MAX_TRUSTED_SESSION_HOURS):
        return None
    return hours


def _row_factors(row: dict) -> dict:
    """Every derived factor for one trip_log.csv row, computed once and
    shared by both trips_df and fish_df below so the two frames can never
    drift apart on how a factor is derived."""
    cond = parse_conditions(row)
    trip_date = _parse_date(row.get("trip_date"))
    water_temp_f = _to_float(cond.get("water_temp_f"))
    pressure_trend = _to_float(cond.get("pressure_trend_24h"))
    moon_pct = moon_illumination_pct_night_before(trip_date) if trip_date else None
    return {
        "trip_id": row.get("trip_id"),
        "date": trip_date,
        "week_start": week_bounds(trip_date)[0] if trip_date else None,
        "day_of_week": trip_date.strftime("%A") if trip_date else None,
        "angler": (cond.get("angler") or "").strip() or "Unspecified",
        "spot": row.get("spot_name") or "Unknown location",
        "structure_type": row.get("structure_type") or "Unspecified",
        "water_clarity": row.get("water_clarity") or "Unspecified",
        "lure": row.get("lure_used") or _lure_category_label(cond) or "Unspecified",
        "lure_category": _lure_category_label(cond) or "Unspecified",
        "color": row.get("color_used") or "Unspecified",
        "technique": row.get("technique_used") or "Unspecified",
        "segment": row.get("segment") or "Unspecified",
        "water_temp_f": water_temp_f,
        "water_temp_band": water_temp_band(water_temp_f)["label"] if water_temp_f is not None else None,
        "wind_band": cond.get("wind_band") or "Unspecified",
        "wind_direction": cond.get("wind_direction") or "Unspecified",
        "light_condition": cond.get("light_condition") or "Unspecified",
        "precipitation": cond.get("precipitation") or "Unspecified",
        "fish_activity": cond.get("fish_activity") or "Unspecified",
        "forage_activity": cond.get("forage_activity") or "Unspecified",
        "pressure_trend_24h": pressure_trend,
        "pressure_trend_band": _pressure_trend_band(pressure_trend),
        "avg_wind_mph": _to_float(cond.get("avg_wind_mph")),
        "moon_illumination_pct": moon_pct,
        "moon_illumination_bin": _moon_illumination_bin(moon_pct),
        "season": season_stage(trip_date.timetuple().tm_yday, water_temp_f)
                  if (trip_date and water_temp_f is not None) else None,
    }, cond


def build_reports_dataframe(rows: list) -> tuple:
    """Returns (trips_df, fish_df):
    - trips_df: one row per trip_log.csv row (one lure USE), with every
      factor column above plus fish_caught (int), fish_per_hour (float|None,
      via core.calibration.trip_fish_per_hour() - already has its own
      plausibility filter, see that function's docstring), trustworthy_hours
      (float|None, this trip's own raw duration when that same plausibility
      filter passes - see _trustworthy_session_hours() above; needed
      alongside fish_per_hour so compute_report() can pool sum(fish caught)/
      sum(hours) across a bucket instead of averaging each trip's own noisy
      single-trip rate), and biggest_fish_lb (float|None, that trip's own
      column).
    - fish_df: one row per individual fish caught (flattened out of each
      trip's conditions_json["fish"] list, same as
      pages/8_Leaderboard.py's own fish_df), carrying every factor column
      from its PARENT trip plus species/weight_lb/length_in/count.
    A trip logged before the Spot Session redesign (no fish list) falls
    back to its own fish_caught/biggest_fish_lb summary columns for
    trips_df, and contributes nothing to fish_df (no species to attribute
    it to) - same fallback pages/8_Leaderboard.py already uses."""
    trip_records = []
    fish_records = []
    for row in rows:
        factors, cond = _row_factors(row)
        fish_list = cond.get("fish")
        trip_fish_count = 0
        if isinstance(fish_list, list) and fish_list:
            for fish in fish_list:
                if not isinstance(fish, dict):
                    continue
                try:
                    count = int(fish.get("count") or 1)
                except (TypeError, ValueError):
                    count = 1
                trip_fish_count += count
                fish_records.append({
                    **factors,
                    "species": (fish.get("species") or "Unspecified").strip() or "Unspecified",
                    "count": count,
                    "weight_lb": _to_float(fish.get("weight_lb")),
                    "length_in": _to_float(fish.get("length_in")),
                })
        else:
            try:
                trip_fish_count = int(float(row.get("fish_caught") or 0))
            except (TypeError, ValueError):
                trip_fish_count = 0

        try:
            biggest = float(row.get("biggest_fish_lb")) if row.get("biggest_fish_lb") not in (None, "") else None
        except (TypeError, ValueError):
            biggest = None

        trip_records.append({
            **factors,
            "fish_caught": trip_fish_count,
            "fish_per_hour": trip_fish_per_hour(row),
            "trustworthy_hours": _trustworthy_session_hours(row),
            "biggest_fish_lb": biggest,
        })

    trips_df = pd.DataFrame(trip_records)
    fish_df = pd.DataFrame(fish_records)
    return trips_df, fish_df


def _apply_filters(df: pd.DataFrame, date_start=None, date_end=None, anglers=None, segments=None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if date_start is not None:
        out = out[out["date"].notna() & (out["date"] >= date_start)]
    if date_end is not None:
        out = out[out["date"].notna() & (out["date"] <= date_end)]
    if anglers:
        out = out[out["angler"].isin(anglers)]
    if segments:
        out = out[out["segment"].isin(segments)]
    return out


def _date_axis(date_start, date_end, weekly: bool) -> list:
    """Every date/week-start value that SHOULD appear on the x-axis for the
    requested window, even ones with no logged trips at all - matches
    core.calibration.daily_dawn_morning_catch()'s "a day with zero trips
    still appears, with a real 0" convention. Falls back to a 30-day
    window ending today when no explicit range was given, so a date-based
    report always has a concrete, bounded axis rather than trying to
    enumerate "all time" one day at a time."""
    end = date_end or date.today()
    start = date_start or (end - timedelta(days=29))
    if weekly:
        w_start, _ = week_bounds(start)
        _, w_end = week_bounds(end)
        weeks = []
        d = w_start
        while d <= w_end:
            weeks.append(d)
            d += timedelta(days=7)
        return weeks
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def compute_report(trips_df: pd.DataFrame, fish_df: pd.DataFrame, factor_col: str, metric_key: str,
                    species: Optional[str] = None, date_start=None, date_end=None,
                    anglers: Optional[list] = None, segments: Optional[list] = None,
                    water_temp_bucket_width_f: Optional[float] = None) -> pd.DataFrame:
    """The one generic aggregator every Reports page chart/table/export
    reads from: groups `metric_key` by `factor_col`, after applying the
    filters, and returns a DataFrame with columns [factor_col, "value",
    "n"] - "n" is the sample size actually backing "value" (trips for
    fish_per_hour/trip_count, individual fish for total_fish/biggest_fish),
    so a thin bar/point can be told apart from a well-supported one.

    Row set: for a factor in ORDER_HINTS or a date-based factor, EVERY
    known value in that order appears, even at n=0/value=0 - a stable axis
    the angler can compare across different filter picks. Otherwise, only
    values actually observed in the filtered data appear, sorted by value
    descending (the "what's working best" reading most of this app's other
    ranking views already default to).

    species: only applied for a SPECIES_FILTERABLE_METRICS metric; ignored
    (silently) for fish_per_hour/trip_count, since those are inherently
    per-trip, not per-species.

    fish_per_hour is a POOLED rate per bucket - sum(fish caught) /
    sum(trustworthy hours) across every trustworthy trip in it ("catch per
    unit effort," standard fisheries framing) - not an average of each
    trip's own individual rate. See _trustworthy_session_hours()'s own
    comment above for why: bass fishing produces plenty of genuinely
    skunked (0 fish, otherwise trustworthy) trips, and averaging (mean OR
    median) each trip's own rate lets a bucket where most trips happened to
    get skunked read as a flat 0 even when it clearly produced real fish
    overall - confirmed against live data (a condition with 64 trustworthy
    trips totalling 134 fish still had a median per-trip rate of exactly
    0.0). Pooling first means a bucket only reads as 0 if it genuinely
    caught nothing across every trustworthy hour logged under it.

    water_temp_bucket_width_f: only meaningful when factor_col is
    WATER_TEMP_BUCKET_FACTOR - see that constant's own module-level comment
    for why this factor can't be precomputed like every other one. Ignored
    for every other factor_col. Defaults to
    DEFAULT_WATER_TEMP_BUCKET_WIDTH_F when not given."""
    t_df = _apply_filters(trips_df, date_start, date_end, anglers, segments)
    f_df = _apply_filters(fish_df, date_start, date_end, anglers, segments)
    if species and species != "All species" and metric_key in SPECIES_FILTERABLE_METRICS and not f_df.empty:
        f_df = f_df[f_df["species"] == species]

    water_temp_bucket_width = water_temp_bucket_width_f or DEFAULT_WATER_TEMP_BUCKET_WIDTH_F
    if factor_col == WATER_TEMP_BUCKET_FACTOR:
        # Can't be a precomputed column (unlike every other factor) - the
        # bucket width isn't known until query time - so it's added here,
        # on a copy (.assign(), never mutating the caller's own trips_df/
        # fish_df), right before the same groupby-by-factor_col logic every
        # other factor already goes through below.
        if not t_df.empty:
            t_df = t_df.assign(**{factor_col: t_df["water_temp_f"].apply(
                lambda v: _water_temp_bucket_label(v, water_temp_bucket_width)
            )})
        if not f_df.empty:
            f_df = f_df.assign(**{factor_col: f_df["water_temp_f"].apply(
                lambda v: _water_temp_bucket_label(v, water_temp_bucket_width)
            )})

    if metric_key == "fish_per_hour":
        base = t_df.dropna(subset=["trustworthy_hours"]) if not t_df.empty else t_df
        if not base.empty:
            agg = base.groupby(factor_col).agg(
                _fish_sum=("fish_caught", "sum"), _hours_sum=("trustworthy_hours", "sum"), n=("trip_id", "count"),
            ).reset_index()
            agg["value"] = agg["_fish_sum"] / agg["_hours_sum"]
            agg = agg[[factor_col, "value", "n"]]
        else:
            agg = pd.DataFrame(columns=[factor_col, "value", "n"])
    elif metric_key == "trip_count":
        # Punch-list #92 follow-up: an entirely-empty result used to come
        # back with no "value" column at all (only assigned "if not
        # agg.empty"), which every axis-filling branch below unconditionally
        # reads via agg["value"] - a latent bug that a fully-empty ORDER_
        # HINTS/date-factor report never happened to exercise before (their
        # axis always has at least one listed value to merge against), but
        # WATER_TEMP_BUCKET_FACTOR's dynamically-generated axis can
        # legitimately be empty too (no trustworthy water-temp readings at
        # all), which does hit it. Always include "value" so the merge
        # below never KeyErrors on a genuinely empty report.
        agg = t_df.groupby(factor_col)["trip_id"].agg(n="count").reset_index() if not t_df.empty else pd.DataFrame(columns=[factor_col, "n"])
        agg["value"] = agg["n"] if not agg.empty else pd.Series(dtype=float)
    elif metric_key == "biggest_fish":
        base = f_df.dropna(subset=["weight_lb"]) if not f_df.empty else f_df
        agg = base.groupby(factor_col)["weight_lb"].agg(value="max", n="count").reset_index() if not base.empty else pd.DataFrame(columns=[factor_col, "value", "n"])
    else:  # total_fish (default)
        if species and species != "All species":
            agg = f_df.groupby(factor_col)["count"].agg(value="sum", n="count").reset_index() if not f_df.empty else pd.DataFrame(columns=[factor_col, "value", "n"])
        else:
            agg = t_df.groupby(factor_col)["fish_caught"].agg(value="sum", n="count").reset_index() if not t_df.empty else pd.DataFrame(columns=[factor_col, "value", "n"])

    if factor_col in DATE_FACTOR_COLUMNS:
        axis = _date_axis(date_start, date_end, weekly=(factor_col == "week_start"))
        full = pd.DataFrame({factor_col: axis})
        agg = full.merge(agg, on=factor_col, how="left")
        agg["value"] = agg["value"].fillna(0)
        agg["n"] = agg["n"].fillna(0).astype(int)
        return agg.sort_values(factor_col).reset_index(drop=True)

    if factor_col in ORDER_HINTS:
        full = pd.DataFrame({factor_col: ORDER_HINTS[factor_col]})
        agg = full.merge(agg, on=factor_col, how="left")
        agg["value"] = agg["value"].fillna(0)
        agg["n"] = agg["n"].fillna(0).astype(int)
        order = {v: i for i, v in enumerate(ORDER_HINTS[factor_col])}
        return agg.sort_values(by=factor_col, key=lambda s: s.map(order)).reset_index(drop=True)

    if factor_col == WATER_TEMP_BUCKET_FACTOR:
        # Same "every bucket between the two real endpoints, even at n=0"
        # idea as ORDER_HINTS/DATE_FACTOR_COLUMNS above, but the axis itself
        # has to be generated fresh each call (from whatever's actually in
        # the filtered trips_df right now) instead of coming from a fixed
        # table, since the bucket width is chosen at query time.
        axis_labels = _water_temp_bucket_axis(t_df["water_temp_f"] if not t_df.empty else None, water_temp_bucket_width)
        # An empty axis_labels list (no trustworthy water-temp readings at
        # all in the filtered trips) would otherwise default to a float64
        # column here, which can't merge against agg's object-dtype
        # factor_col when agg is ALSO empty (pandas refuses a float64 <->
        # object merge outright) - force object dtype explicitly so the
        # "nothing to show" case merges cleanly instead of raising.
        full = pd.DataFrame({factor_col: pd.Series(axis_labels, dtype=object)})
        agg = full.merge(agg, on=factor_col, how="left")
        agg["value"] = agg["value"].fillna(0)
        agg["n"] = agg["n"].fillna(0).astype(int)
        order = {v: i for i, v in enumerate(axis_labels)}
        return agg.sort_values(by=factor_col, key=lambda s: s.map(order)).reset_index(drop=True)

    if agg.empty:
        return agg
    return agg.sort_values("value", ascending=False).reset_index(drop=True)


def species_options(fish_df: pd.DataFrame) -> list:
    if fish_df.empty:
        return []
    return sorted(fish_df["species"].dropna().unique().tolist())
