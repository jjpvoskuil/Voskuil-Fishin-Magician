import json

from core.calibration import calibrate_weights, calibration_summary, MIN_SAMPLES_PER_SIDE


def _row(pressure_trend_24h=0.0, fish_caught=1, conditions_json=None):
    if conditions_json is None:
        conditions_json = json.dumps({"pressure_trend_24h": pressure_trend_24h})
    return {"conditions_json": conditions_json, "fish_caught": fish_caught}


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
