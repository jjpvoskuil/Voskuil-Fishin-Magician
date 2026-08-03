"""
Lightweight calibration: nudge scoring weights using logged trip outcomes.

Rather than a full regression (which needs a lot of data to be trustworthy),
this compares catch success (fish_caught > 0) between trips where a given
factor was "on" vs "off", and nudges that factor's weight a small, capped
amount toward whichever direction the user's own logged data supports.
Requires a minimum sample size per factor before it touches anything, and
always blends toward - never replaces - the documented default weights.
"""
from __future__ import annotations
import json
from .scoring import DEFAULT_WEIGHTS

MIN_SAMPLES_PER_SIDE = 4
MAX_NUDGE_FRACTION = 0.35  # never move a weight more than 35% from default


def _factor_flags(conditions: dict) -> dict:
    pt = conditions.get("pressure_trend_24h", 0) or 0
    return {
        "pressure_falling": pt <= -1.5,
        "pressure_high_stable_post_front": pt >= 2.0,
        "moon_new_full_bonus": bool(conditions.get("moon_near_new_full", False)),
        "cloud_overcast_bonus": (conditions.get("avg_cloud_pct") or 0) >= 60,
        "wind_sweet_spot_bonus": 4 <= (conditions.get("avg_wind_mph") or 0) <= 14,
    }


def calibrate_weights(trip_rows: list) -> dict:
    """trip_rows: list of dicts as returned by storage.read_all_trips()."""
    weights = dict(DEFAULT_WEIGHTS)
    if not trip_rows:
        return weights

    buckets = {k: {"on_success": 0, "on_total": 0, "off_success": 0, "off_total": 0} for k in _factor_flags({})}

    for row in trip_rows:
        try:
            conditions = json.loads(row.get("conditions_json") or "{}")
            caught = int(row.get("fish_caught") or 0)
        except (ValueError, json.JSONDecodeError):
            continue
        success = 1 if caught > 0 else 0
        flags = _factor_flags(conditions)
        for factor, is_on in flags.items():
            b = buckets[factor]
            if is_on:
                b["on_total"] += 1
                b["on_success"] += success
            else:
                b["off_total"] += 1
                b["off_success"] += success

    for factor, b in buckets.items():
        if b["on_total"] < MIN_SAMPLES_PER_SIDE or b["off_total"] < MIN_SAMPLES_PER_SIDE:
            continue  # not enough data yet - keep default
        on_rate = b["on_success"] / b["on_total"]
        off_rate = b["off_success"] / b["off_total"]
        lift = on_rate - off_rate  # -1..1, positive means factor correlates with more success
        default_w = DEFAULT_WEIGHTS.get(factor, 0)
        cap = abs(default_w) * MAX_NUDGE_FRACTION if default_w != 0 else 0.5
        nudge = max(-cap, min(cap, lift * cap))
        weights[factor] = round(default_w + nudge, 3)

    return weights


def calibration_summary(trip_rows: list) -> dict:
    """Human-readable summary of how many trips have been logged and which
    factors have enough data to influence the model yet."""
    buckets = {k: {"on_total": 0, "off_total": 0} for k in _factor_flags({})}
    for row in trip_rows:
        try:
            conditions = json.loads(row.get("conditions_json") or "{}")
        except json.JSONDecodeError:
            continue
        flags = _factor_flags(conditions)
        for factor, is_on in flags.items():
            buckets[factor]["on_total" if is_on else "off_total"] += 1
    active = {
        f: b for f, b in buckets.items()
        if b["on_total"] >= MIN_SAMPLES_PER_SIDE and b["off_total"] >= MIN_SAMPLES_PER_SIDE
    }
    return {"total_trips": len(trip_rows), "factors_calibrated": list(active.keys()), "detail": buckets}
