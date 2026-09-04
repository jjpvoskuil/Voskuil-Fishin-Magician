import json

from core.calibration import (
    calibrate_weights, calibration_summary, location_adjustments, trip_fish_per_hour,
    MIN_SAMPLES_PER_SIDE, LOCATION_MIN_SAMPLES,
)
from core.scoring import DEFAULT_WEIGHTS


def _row(pressure_trend_24h=0.0, fish_caught=1, conditions_json=None):
    if conditions_json is None:
        conditions_json = json.dumps({"pressure_trend_24h": pressure_trend_24h})
    return {"conditions_json": conditions_json, "fish_caught": fish_caught}


def _timed_row(
    pressure_trend_24h=0.0, fish_caught=1, hours=1.0,
    spot_id=None, spot_name=None, segment=None, extra_conditions=None,
):
    """A row with a real lure_start_time/lure_end_time window (punch-list
    #81) - the shape trip_fish_per_hour()/calibrate_weights()/
    location_adjustments() all actually key off of, unlike _row() above
    (which predates fish-per-hour and has no timing at all - kept as-is for
    the pre-#81 tests that only care about the JSON-shape edge cases)."""
    start = "06:00:00"
    end_seconds = int(hours * 3600)
    end_h, rem = divmod(end_seconds, 3600)
    end_m, end_s = divmod(rem, 60)
    end = f"{6 + end_h:02d}:{end_m:02d}:{end_s:02d}"
    cond = {"pressure_trend_24h": pressure_trend_24h, "lure_start_time": start, "lure_end_time": end}
    if extra_conditions:
        cond.update(extra_conditions)
    row = {"conditions_json": json.dumps(cond), "fish_caught": fish_caught}
    if spot_id is not None:
        row["spot_id"] = spot_id
    if spot_name is not None:
        row["spot_name"] = spot_name
    if segment is not None:
        row["segment"] = segment
    return row


def test_calibrate_weights_ignores_rows_where_conditions_json_is_not_an_object():
    # Same latent bug class as core.lure_history: conditions_json can be
    # valid JSON that isn't a dict (a bare number/string/list/null) - this
    # used to crash _factor_flags()'s conditions.get(...) call with an
    # uncaught AttributeError instead of just skipping the row.
    rows = [_row(conditions_json="7"), _row(conditions_json='"oops"'), _row(conditions_json="[1]")]
    rows += [_row(pressure_trend_24h=-2.0, fish_caught=1) for _ in range(MIN_SAMPLES_PER_SIDE)]
    rows += [_row(pressure_trend_24h=0.0, fish_caught=0) for _ in range(MIN_SAMPLES_PER_SIDE)]
    weights = calibrate_weights(rows)  # must not raise
    assert isinstance(weights, dict)


def test_calibration_summary_ignores_rows_where_conditions_json_is_not_an_object():
    rows = [_row(conditions_json="null"), _row(conditions_json="24")]
    summary = calibration_summary(rows)  # must not raise
    assert isinstance(summary, dict)


# --- Punch-list #81: fish-per-hour replaces the old binary success flag ----

def test_trip_fish_per_hour_computes_rate_from_lure_start_and_end_time():
    row = _timed_row(fish_caught=2, hours=1.0)
    assert trip_fish_per_hour(row) == 2.0


def test_trip_fish_per_hour_a_scoreless_but_validly_timed_trip_is_zero_not_excluded():
    # Fishing for a real hour and catching nothing is a real, informative
    # data point - distinct from "we don't know how long this took" (None).
    row = _timed_row(fish_caught=0, hours=1.0)
    assert trip_fish_per_hour(row) == 0.0


def test_trip_fish_per_hour_excludes_missing_timing():
    row = _row(fish_caught=1)  # no lure_start_time/lure_end_time at all
    assert trip_fish_per_hour(row) is None


def test_trip_fish_per_hour_excludes_implausibly_short_or_long_durations():
    # A punch-list #81 guardrail against the "sketchy" batch-reconstructed
    # sessions the angler flagged - see core/calibration.py's module
    # docstring for why there's no way to positively identify those rows,
    # only filter out the most implausible-looking durations.
    too_short = _timed_row(fish_caught=1, hours=1 / 120)  # 30 seconds
    too_long = _timed_row(fish_caught=1, hours=9.0)
    assert trip_fish_per_hour(too_short) is None
    assert trip_fish_per_hour(too_long) is None


def test_calibrate_weights_stays_at_defaults_with_no_trustworthy_duration_data():
    # Every row here has a real pressure signal but NO timing at all (the
    # pre-#81 _row() helper) - the old binary-success calibration would have
    # happily nudged pressure_falling from this; the rewrite must not, since
    # none of it can be trusted as a real rate.
    rows = [_row(pressure_trend_24h=-2.0, fish_caught=1) for _ in range(10)]
    rows += [_row(pressure_trend_24h=0.0, fish_caught=0) for _ in range(10)]
    weights = calibrate_weights(rows)
    assert weights == DEFAULT_WEIGHTS


def test_calibrate_weights_moves_on_fish_per_hour_even_when_binary_success_is_identical():
    # The core punch-list #81 behavior change: "on" and "off" here both hit
    # fish_caught >= 1 on every single row (100% success either way, which
    # is what the OLD calibration compared) - only the rate differs. If
    # calibration were still binary-success-based, this would produce zero
    # lift and leave pressure_falling untouched.
    on_rows = [_timed_row(pressure_trend_24h=-2.0, fish_caught=1, hours=0.25) for _ in range(4)]   # 4.0 fish/hr
    off_rows = [_timed_row(pressure_trend_24h=0.0, fish_caught=1, hours=2.0) for _ in range(4)]    # 0.5 fish/hr
    weights = calibrate_weights(on_rows + off_rows)
    assert weights["pressure_falling"] > DEFAULT_WEIGHTS["pressure_falling"]


def test_calibration_summary_reports_trustworthy_duration_count():
    rows = [_timed_row(fish_caught=1, hours=1.0) for _ in range(3)]
    rows += [_row(fish_caught=1)]  # no timing - not trustworthy
    summary = calibration_summary(rows)
    assert summary["total_trips"] == 4
    assert summary["trustworthy_duration_trips"] == 3


# --- Punch-list #81: location_adjustments() ---------------------------------

def test_location_adjustments_rewards_a_spot_segment_that_outperforms_its_segment_baseline():
    # Spot A crushes it at Dawn; Spot B is ordinary at Dawn - enough samples
    # at both to compare, and enough total Dawn samples to have a baseline.
    rows = []
    rows += [_timed_row(fish_caught=3, hours=1.0, spot_id="A", spot_name="Spot A", segment="Dawn") for _ in range(6)]
    rows += [_timed_row(fish_caught=1, hours=1.0, spot_id="B", spot_name="Spot B", segment="Dawn") for _ in range(6)]
    adjustments = location_adjustments(rows)
    assert ("A", "Dawn") in adjustments
    assert adjustments[("A", "Dawn")]["adjustment"] > 0
    assert adjustments[("A", "Dawn")]["n"] == 6
    assert adjustments[("A", "Dawn")]["spot_name"] == "Spot A"
    assert ("B", "Dawn") in adjustments
    assert adjustments[("B", "Dawn")]["adjustment"] < 0


def test_location_adjustments_requires_minimum_samples_per_cell():
    rows = [_timed_row(fish_caught=5, hours=1.0, spot_id="A", spot_name="Spot A", segment="Dawn")
            for _ in range(LOCATION_MIN_SAMPLES - 1)]
    rows += [_timed_row(fish_caught=1, hours=1.0, spot_id="B", spot_name="Spot B", segment="Dawn")
             for _ in range(LOCATION_MIN_SAMPLES)]
    adjustments = location_adjustments(rows)
    assert ("A", "Dawn") not in adjustments  # too few trips at A itself


def test_location_adjustments_shrinks_small_samples_toward_zero():
    # Same relative outperformance at both spots (1.5x the segment baseline
    # rate), but Spot Big has far more logged trips than Spot Small - the
    # small sample's adjustment should be damped harder (n / (n + K)
    # shrinkage), not treated as equally confident. The baseline population
    # is deliberately large (50) so it isn't itself swamped by "big"'s own
    # 30 rows - if the baseline sample were small, the segment median would
    # just track "big" and wash out its own relative lift to zero.
    rows = []
    rows += [_timed_row(fish_caught=2, hours=1.0, spot_id="baseline", spot_name="Baseline", segment="Dawn")
             for _ in range(50)]
    rows += [_timed_row(fish_caught=3, hours=1.0, spot_id="big", spot_name="Big", segment="Dawn") for _ in range(30)]
    rows += [_timed_row(fish_caught=3, hours=1.0, spot_id="small", spot_name="Small", segment="Dawn")
             for _ in range(LOCATION_MIN_SAMPLES)]
    adjustments = location_adjustments(rows)
    assert adjustments[("big", "Dawn")]["adjustment"] > adjustments[("small", "Dawn")]["adjustment"] > 0
