from datetime import date
from core.thermocline import (
    estimate_thermocline_band_ft, estimate_thermocline_ft,
    default_thermocline_input_ft, thermocline_caveat, NO_STRATIFICATION_DEFAULT_FT,
)


def test_no_thermocline_in_winter():
    assert estimate_thermocline_band_ft(date(2026, 1, 15)) is None
    assert estimate_thermocline_band_ft(date(2026, 12, 1)) is None
    assert estimate_thermocline_ft(date(2026, 1, 15)) is None


def test_no_thermocline_after_fall_turnover():
    assert estimate_thermocline_band_ft(date(2026, 10, 20)) is None


def test_thermocline_present_and_deepest_in_july():
    band = estimate_thermocline_band_ft(date(2026, 7, 15))
    assert band is not None
    lo, hi = band
    assert lo < hi
    # Anchored to the KDFWR-reported ~15 ft mid/late-July reading for Nolin.
    assert lo <= 15.0 <= hi
    midpoint = estimate_thermocline_ft(date(2026, 7, 15))
    assert lo <= midpoint <= hi


def test_thermocline_deepens_from_may_to_september():
    may_band = estimate_thermocline_band_ft(date(2026, 5, 10))
    sept_band = estimate_thermocline_band_ft(date(2026, 9, 10))
    assert may_band[1] < sept_band[1]


def test_default_input_falls_back_to_safe_value_off_season():
    assert default_thermocline_input_ft(date(2026, 1, 15)) == NO_STRATIFICATION_DEFAULT_FT


def test_default_input_matches_model_in_season():
    assert default_thermocline_input_ft(date(2026, 7, 15)) == estimate_thermocline_ft(date(2026, 7, 15))


def test_caveat_none_without_value_or_depth():
    assert thermocline_caveat(None, 20) is None
    assert thermocline_caveat(15.0, None) is None


def test_caveat_triggers_below_set_depth():
    msg = thermocline_caveat(15.0, 25)
    assert msg is not None
    assert "below the thermocline depth you've set" in msg
    assert "15 ft" in msg


def test_caveat_silent_at_or_above_set_depth():
    assert thermocline_caveat(15.0, 15) is None
    assert thermocline_caveat(15.0, 5) is None
