"""
Lightweight calibration: nudge scoring weights (and, new as of the
punch-list #81 rewrite below, a per-spot/per-segment location adjustment)
using logged trip outcomes.

Rather than a full regression (which needs a lot of data to be
trustworthy), this compares an outcome metric between trips where a given
factor was "on" vs "off" (or, for location, between one spot/segment and
the rest), and nudges that factor a small, capped amount toward whichever
direction the user's own logged data supports. Requires a minimum sample
size before it touches anything, and always blends toward - never
replaces - the documented default weights.

Punch-list #81 (real angler feedback, live-checked against 143 logged
trips): the outcome metric used to be a bare "did you catch anything"
binary flag (fish_caught > 0), which throws away almost everything a
session actually reports - a single fish in a 4-hour slog and five fish in
a 45-minute blitz both just counted as "1 success." Replaced with
fish-per-hour (see trip_fish_per_hour() below), which is the metric the
angler actually asked for, computed per logged lure entry (each row
already represents one specific lure fished for its own lure_start_time -
lure_end_time window, with fish_caught scoped to just that window - not a
whole-session total, so no session-level aggregation is needed).

That data isn't fully trustworthy, though - a lot of historical sessions
were reconstructed after the fact in a batch during past data-recovery
work (see this file's own git history around punch-list #57/#67-69 in
SESSION_NOTES.md), and there is no field anywhere distinguishing a
live-timed entry from a reconstructed-after-the-fact one (checked directly:
every row's conditions_json says "source": "spot_session" regardless).
Rather than trust every logged duration equally, trip_fish_per_hour()
applies a plausibility filter (5 minutes - 6 hours) and EXCLUDES (returns
None, not 0) anything outside that range or missing a duration at all -
best-effort now against what already exists, per the angler's own explicit
choice, rather than waiting weeks for a "logged live" flag that doesn't
exist yet. calibrate_weights()/location_adjustments() both use the MEDIAN
fish/hour within each bucket rather than the mean, specifically so one
implausibly-productive-but-still-inside-the-filter outlier (a real example
in the live data: 17 fish logged in a 1-hour window) can't single-handedly
swing a whole factor's calibration.
"""
from __future__ import annotations
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from datetime import time as dtime
from typing import Optional

from .astro import SYNODIC_MONTH, moon_phase
from .scoring import DEFAULT_WEIGHTS
from .storage import parse_conditions

MIN_SAMPLES_PER_SIDE = 4
MAX_NUDGE_FRACTION = 0.35  # never move a weight more than 35% from default

# Punch-list #81: how long a single logged lure window has to be before its
# fish-per-hour rate is trusted at all. Picked as a plausibility guardrail,
# not a measured threshold - 5 minutes is short enough to cover a real quick
# lure change, 6 hours long enough to cover fishing one lure all session,
# while still catching the clearest signs of a reconstructed-after-the-fact
# guess (an exact "1.0 hour", a suspiciously round "0.5 hours" repeated
# across many unrelated entries, a multi-day span from a bad AM/PM read).
MIN_TRUSTED_SESSION_HOURS = 5 / 60
MAX_TRUSTED_SESSION_HOURS = 6.0

# Location adjustment (punch-list #81): same min-sample bar as the existing
# weight factors, reused rather than inventing a separate number.
LOCATION_MIN_SAMPLES = MIN_SAMPLES_PER_SIDE
LOCATION_ADJUSTMENT_CAP = 1.0  # points - same additive scale as the other weights
# Empirical-Bayes-style shrinkage: a cell's adjustment is damped by
# n / (n + LOCATION_SHRINKAGE_PRIOR), so a spot/segment right at the
# MIN_SAMPLES_PER_SIDE floor (4) only gets 4/(4+6) = 40% of its raw estimate,
# and one with a much larger sample (Stripe Island Point's Dawn trips, e.g.)
# approaches the full estimate. Prevents a thin-sample spot (an early
# Midnight Point read, say) from swinging the score around on noise the way
# a flat per-location bonus with no shrinkage would.
LOCATION_SHRINKAGE_PRIOR = 6


def _factor_flags(conditions: dict) -> dict:
    pt = conditions.get("pressure_trend_24h", 0) or 0
    return {
        "pressure_falling": pt <= -1.5,
        "pressure_high_stable_post_front": pt >= 2.0,
        "moon_new_full_bonus": bool(conditions.get("moon_near_new_full", False)),
        "cloud_overcast_bonus": (conditions.get("avg_cloud_pct") or 0) >= 60,
        "wind_sweet_spot_bonus": 4 <= (conditions.get("avg_wind_mph") or 0) <= 14,
    }


def trip_fish_per_hour(row: dict) -> Optional[float]:
    """Best-effort fish-caught-per-hour for one logged trip row (one lure
    entry, not a whole session - see this module's docstring). Returns
    None - never 0 - when the duration is missing or fails the
    plausibility filter, so a row we can't trust is EXCLUDED from
    calibration rather than silently scored as a real, terrible rate."""
    conditions = parse_conditions(row)
    start = conditions.get("lure_start_time")
    end = conditions.get("lure_end_time")
    if not start or not end:
        return None
    try:
        t0 = datetime.strptime(start, "%H:%M:%S")
        t1 = datetime.strptime(end, "%H:%M:%S")
    except (ValueError, TypeError):
        return None
    hours = (t1 - t0).total_seconds() / 3600.0
    if not (MIN_TRUSTED_SESSION_HOURS <= hours <= MAX_TRUSTED_SESSION_HOURS):
        return None
    try:
        caught = int(row.get("fish_caught") or 0)
    except (ValueError, TypeError):
        return None
    if caught < 0:
        return None
    return caught / hours


def calibrate_weights(trip_rows: list) -> dict:
    """trip_rows: list of dicts as returned by storage.read_all_trips()."""
    weights = dict(DEFAULT_WEIGHTS)
    if not trip_rows:
        return weights

    rates = [trip_fish_per_hour(r) for r in trip_rows]
    valid_rates = [r for r in rates if r is not None]
    if not valid_rates:
        return weights  # no trustworthy-duration trips yet - stay at defaults

    # Normalizes each factor's lift into a stable, comparable -1..1 range -
    # see this module's docstring for why the median (not mean) of all
    # trustworthy trips is the reference point, not either bucket's own
    # median (which could itself be near-zero and blow the ratio up).
    baseline = statistics.median(valid_rates)
    if baseline <= 0:
        return weights

    buckets = {k: {"on": [], "off": []} for k in _factor_flags({})}
    for row, rate in zip(trip_rows, rates):
        if rate is None:
            continue
        conditions = parse_conditions(row)
        flags = _factor_flags(conditions)
        for factor, is_on in flags.items():
            buckets[factor]["on" if is_on else "off"].append(rate)

    for factor, b in buckets.items():
        if len(b["on"]) < MIN_SAMPLES_PER_SIDE or len(b["off"]) < MIN_SAMPLES_PER_SIDE:
            continue  # not enough trustworthy-duration data yet - keep default
        on_med = statistics.median(b["on"])
        off_med = statistics.median(b["off"])
        relative_lift = max(-1.0, min(1.0, (on_med - off_med) / baseline))
        default_w = DEFAULT_WEIGHTS.get(factor, 0)
        cap = abs(default_w) * MAX_NUDGE_FRACTION if default_w != 0 else 0.5
        nudge = max(-cap, min(cap, relative_lift * cap))
        weights[factor] = round(default_w + nudge, 3)

    return weights


def location_adjustments(trip_rows: list) -> dict:
    """Punch-list #81: how much better or worse a specific spot performs at
    a specific time-of-day segment than that SAME segment does everywhere
    else - i.e. holding time-of-day equal, per the real pattern in the
    angler's own data (Stripe Island Point's best segment isn't Midnight
    Point's best segment - a flat per-spot bonus would blur that away).

    Returns {(spot_id, segment): {"adjustment": float, "n": int,
    "spot_name": str}} for every (spot, segment) cell with enough
    trustworthy-duration trips (see trip_fish_per_hour()) to say anything
    at all. A cell simply being absent means "not enough data yet," not
    "confirmed no difference" - callers should treat a missing lookup as
    0.0/no adjustment, the same as every other optional scoring input."""
    by_segment = defaultdict(list)
    by_cell = defaultdict(list)
    spot_names = {}
    all_rates = []

    for row in trip_rows:
        rate = trip_fish_per_hour(row)
        if rate is None:
            continue
        segment = row.get("segment")
        spot_id = row.get("spot_id")
        if not segment or not spot_id:
            continue
        by_segment[segment].append(rate)
        by_cell[(spot_id, segment)].append(rate)
        spot_names.setdefault(spot_id, row.get("spot_name") or spot_id)
        all_rates.append(rate)

    if not all_rates:
        return {}
    overall_baseline = statistics.median(all_rates)
    if overall_baseline <= 0:
        return {}

    result = {}
    for (spot_id, segment), rates in by_cell.items():
        n = len(rates)
        if n < LOCATION_MIN_SAMPLES:
            continue
        segment_rates = by_segment[segment]
        if len(segment_rates) < LOCATION_MIN_SAMPLES:
            continue  # not enough of a same-segment baseline to compare against yet
        cell_median = statistics.median(rates)
        segment_median = statistics.median(segment_rates)
        relative_lift = max(-1.0, min(1.0, (cell_median - segment_median) / overall_baseline))
        confidence = n / (n + LOCATION_SHRINKAGE_PRIOR)
        adjustment = round(relative_lift * LOCATION_ADJUSTMENT_CAP * confidence, 3)
        if adjustment == 0:
            continue
        result[(spot_id, segment)] = {"adjustment": adjustment, "n": n, "spot_name": spot_names[spot_id]}

    return result


# Punch-list #new: the angler's own hypothesis - a bright full moon lets
# bass see (and feed) better at night, so they feed LESS at dawn/morning,
# with the opposite pattern near a new moon - is about WHEN during the day
# fish bite, not whether total daily catch rate changes with moon phase (the
# 2023 SN Applied Sciences study cited in core/scoring.py's docstring found
# no such 24h-total relationship, which is exactly why this splits by
# time-of-day instead of repeating that same whole-day comparison).
MORNING_SEGMENTS = ("Dawn", "Morning")

# int(SYNODIC_MONTH) + 1 = 30 whole-day buckets (age_days runs 0 up to just
# under 29.53, so int(age_days) is always 0-29) - one bucket per day of the
# lunar cycle, replacing the earlier 8-named-phase version per the angler's
# own follow-up ("let's look at each day of the lunar cycle" - finer detail
# than 8 buckets, and every day gets its own real illumination % instead of
# a shared phase label).
DAYS_IN_LUNAR_CYCLE = int(SYNODIC_MONTH) + 1


def _illumination_pct_for_age(age_days: float) -> float:
    """The exact illumination-% formula astro.moon_phase() uses internally
    (0% at new moon, 100% at full moon), applied directly to a whole day-of-
    cycle number rather than averaged across whatever few real trips happen
    to land in that bucket - so every bucket's label is a fixed, reproducible
    number, not a noisy sample statistic."""
    fraction = age_days / SYNODIC_MONTH
    return (1 - math.cos(2 * math.pi * fraction)) / 2 * 100


def moon_illumination_dawn_rates(trip_rows: list, since: Optional[object] = None) -> list:
    """Median fish-per-hour for Dawn+Morning trips ONLY (punch-list #89,
    revised after the angler saw the first version: dropped the "rest of
    day" comparison - Dawn+Morning is where the large majority of this
    lake's logged trips actually are, so that's the one series worth
    trusting right now), bucketed by whole day of the lunar cycle (0 = new
    moon, ~15 = full moon, 0-29) rather than the 8 named phases the first
    version used.

    `since` (a `datetime.date`, optional): when given, only trips whose
    trip_date is on or after this date are counted - added so home.py can
    show a "just the last 2 weeks" chart alongside the all-time one (the
    angler's own follow-up, wanting to see whether a recent stretch tracks
    or diverges from the full history) without a second, near-duplicate
    function. `None` (the default) keeps every trustworthy-duration trip
    ever logged, unchanged from before this parameter existed.

    Each bucket's moon state is recomputed fresh at 18:00 the evening
    BEFORE trip_date, not read from conditions_json's already-logged
    moon_phase (which core/scoring.py computes at 18:00 on trip_date
    itself - the UPCOMING night, appropriate for an evening/night
    forecast, but a full calendar day too late for a Dawn/Morning session
    that already happened THAT SAME morning, before that night arrives).
    Getting this right matters specifically for this chart, since the
    whole point is checking whether the moonlight that was actually out
    overnight - not tomorrow night - lines up with a quieter or busier
    morning bite.

    Returns a list of 30 dicts, one per day 0-29 in cycle order:
    {"day_of_cycle": int, "illumination_pct": float (0-100, see
    _illumination_pct_for_age() above), "median": float|None, "n": int}.
    Every day appears even with zero logged trips (real state right now:
    most of the 30 buckets are thin or empty - only ~54 Dawn+Morning trips
    exist in total, spread across a whole lunar cycle) - a caller should
    treat "n": 0 as "no data yet," not "confirmed no difference," same
    convention as location_adjustments()/the original moon-phase version
    above. Deliberately does NOT gate on MIN_SAMPLES_PER_SIDE - this is an
    exploratory chart the angler is meant to eyeball sample sizes on
    directly, not a scoring input."""
    buckets = {d: [] for d in range(DAYS_IN_LUNAR_CYCLE)}
    for row in trip_rows:
        if row.get("segment") not in MORNING_SEGMENTS:
            continue
        rate = trip_fish_per_hour(row)
        if rate is None:
            continue
        trip_date_str = row.get("trip_date")
        if not trip_date_str:
            continue
        try:
            trip_date = datetime.strptime(trip_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if since is not None and trip_date < since:
            continue
        night_before = datetime.combine(trip_date - timedelta(days=1), dtime(18, 0))
        day_of_cycle = int(moon_phase(night_before).age_days)
        buckets.setdefault(day_of_cycle, []).append(rate)

    return [
        {
            "day_of_cycle": d,
            "illumination_pct": round(_illumination_pct_for_age(d), 1),
            "median": statistics.median(rates) if rates else None,
            "n": len(rates),
        }
        for d, rates in sorted(buckets.items())
    ]


def calibration_summary(trip_rows: list) -> dict:
    """Human-readable summary of how many trips have been logged and which
    weight factors have enough trustworthy-duration data to influence the
    model yet."""
    rates = {id(r): trip_fish_per_hour(r) for r in trip_rows}
    buckets = {k: {"on_total": 0, "off_total": 0} for k in _factor_flags({})}
    for row in trip_rows:
        if rates[id(row)] is None:
            continue
        conditions = parse_conditions(row)
        flags = _factor_flags(conditions)
        for factor, is_on in flags.items():
            buckets[factor]["on_total" if is_on else "off_total"] += 1
    active = {
        f: b for f, b in buckets.items()
        if b["on_total"] >= MIN_SAMPLES_PER_SIDE and b["off_total"] >= MIN_SAMPLES_PER_SIDE
    }
    trustworthy = sum(1 for r in rates.values() if r is not None)
    return {
        "total_trips": len(trip_rows),
        "trustworthy_duration_trips": trustworthy,
        "factors_calibrated": list(active.keys()),
        "detail": buckets,
    }
