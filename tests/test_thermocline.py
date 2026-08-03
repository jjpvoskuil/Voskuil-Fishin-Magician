from datetime import date
from core.thermocline import estimate_thermocline_band_ft, thermocline_caveat


def test_no_thermocline_in_winter():
    assert estimate_thermocline_band_ft(date(2026, 1, 15)) is None
    assert estimate_thermocline_band_ft(date(2026, 12, 1)) is None


def test_no_thermocline_after_fall_turnover():
    assert estimate_thermocline_band_ft(date(2026, 10, 20)) is None


def test_thermocline_present_and_deepest_in_july():
    band = estimate_thermocline_band_ft(date(2026, 7, 15))
    assert band is not None
    lo, hi = band
    assert lo < hi
    # Anchored to the KDFWR-reported ~15 ft mid/late-July reading for Nolin.
    assert lo <= 15.0 <= hi


def test_thermocline_deepens_from_may_to_september():
    may_band = estimate_thermocline_band_ft(date(2026, 5, 10))
    sept_band = estimate_thermocline_band_ft(date(2026, 9, 10))
    assert may_band[1] < sept_band[1]


def test_caveat_none_without_band_or_depth():
    assert thermocline_caveat(None, 20) is None
    assert thermocline_caveat((13.0, 17.0), None) is None


def test_caveat_triggers_below_band():
    msg = thermocline_caveat((13.0, 17.0), 25)
    assert msg is not None
    assert "below the modeled thermocline" in msg
    assert "13-17 ft" in msg


def test_caveat_silent_within_or_above_band():
    assert thermocline_caveat((13.0, 17.0), 15) is None
    assert thermocline_caveat((13.0, 17.0), 5) is None
