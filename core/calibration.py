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
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Optional

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
