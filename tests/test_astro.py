from datetime import datetime, date, timezone
from core.astro import moon_phase, solunar_times, PHASE_NAMES


def test_moon_phase_bounds():
    mp = moon_phase(datetime.now(timezone.utc))
    assert 0 <= mp.fraction <= 1
    assert 0 <= mp.illumination_pct <= 100
    assert mp.name in {n for _, _, n in PHASE_NAMES}


def test_moon_phase_cycle_advances():
    a = moon_phase(datetime(2026, 1, 1, tzinfo=timezone.utc))
    b = moon_phase(datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert a.age_days != b.age_days


def test_solunar_times_returns_naive_local_datetimes():
    st = solunar_times(date(2026, 8, 3), 37.2783, -86.2475, -5)
    for t in [st.moonrise, st.moon_transit, st.moonset, st.moon_underfoot]:
        if t is not None:
            assert t.tzinfo is None
    assert len(st.major_periods) <= 2
    assert len(st.minor_periods) <= 2
