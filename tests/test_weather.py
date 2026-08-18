from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from core.weather import (
    lake_today, LAKE_TZ, LAKE_ZONEINFO, WeatherBundle, fetch_forecast,
    estimate_water_temp_f, WATER_TEMP_TREND_PAST_DAYS, HOME_TREND_CHART_PAST_DAYS,
)


def test_lake_today_returns_a_date():
    assert isinstance(lake_today(), date)


def test_lake_zoneinfo_matches_lake_tz_constant():
    assert LAKE_TZ == "America/Chicago"
    assert LAKE_ZONEINFO.key == "America/Chicago"


def test_lake_today_matches_independently_computed_chicago_date():
    # Not a tautology on the implementation - re-derives the value via a fresh
    # ZoneInfo lookup rather than importing LAKE_ZONEINFO, so it'd catch
    # lake_today() drifting to the wrong zone (e.g. back to server-local time).
    assert lake_today() == datetime.now(ZoneInfo("America/Chicago")).date()


def test_fetch_forecast_requests_past_days_for_the_water_temp_trend(monkeypatch):
    # Punch-list #7: without this, estimate_water_temp_f()'s "trailing
    # average" has nothing real to average for TODAY specifically, since
    # Open-Meteo's response otherwise starts exactly at today's local
    # midnight with zero days before it. Confirms the actual HTTP request
    # asks for it, rather than just trusting the estimate function alone.
    #
    # Punch-list #15: the request now asks for max(WATER_TEMP_TREND_PAST_DAYS,
    # HOME_TREND_CHART_PAST_DAYS) so home.py's 14-day trend charts have real
    # data too, without changing WATER_TEMP_TREND_PAST_DAYS itself - that's a
    # tuned model parameter (estimate_water_temp_f()'s trailing-average
    # window), not a chart-length knob, so it must stay independent.
    import core.weather as mod

    captured = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"hourly": {"time": []}, "daily": {"time": []}}

    def _fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResp()

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    fetch_forecast(days=7)
    assert captured["params"]["past_days"] == max(WATER_TEMP_TREND_PAST_DAYS, HOME_TREND_CHART_PAST_DAYS)
    # The chart window is the larger of the two in this app today, but the
    # assertion above is written to stay correct even if that ever flips -
    # confirm that explicitly so a future reader doesn't have to re-derive it.
    assert HOME_TREND_CHART_PAST_DAYS >= WATER_TEMP_TREND_PAST_DAYS
    assert captured["params"]["past_days"] == HOME_TREND_CHART_PAST_DAYS


def _bundle_with_daily_highs(d: date, highs_by_offset: dict) -> WeatherBundle:
    """Build a minimal WeatherBundle whose `daily` covers exactly the dates
    in `highs_by_offset` (day offset from `d` -> that day's high, e.g.
    {-2: 90.0, -1: 92.0} for two real days before `d`), with no hourly data
    at all - isolates estimate_water_temp_f()'s daily-high averaging from
    everything else (hourly used to matter for the old all-hours-average
    formula; it doesn't anymore, so this deliberately leaves it empty to
    prove that)."""
    offsets = sorted(highs_by_offset)
    times = [(d + timedelta(days=off)).isoformat() for off in offsets]
    highs = [highs_by_offset[off] for off in offsets]
    daily = {"time": times, "temperature_2m_max": highs, "temperature_2m_min": [h - 15 for h in highs]}
    return WeatherBundle(hourly={"time": []}, daily=daily)


def test_estimate_water_temp_f_falls_back_to_seasonal_with_no_daily_data():
    d = date(2026, 8, 13)  # day_of_year 225, well into the summer peak
    bundle = WeatherBundle(hourly={"time": []}, daily={"time": []})
    result = estimate_water_temp_f(bundle, d, d.timetuple().tm_yday)
    assert 83.0 <= result <= 89.0  # matches the real logged range for this stretch


def test_estimate_water_temp_f_only_averages_days_strictly_before_d():
    d = date(2026, 8, 13)
    # A day AT d and a day AFTER d, both absurdly hot - if either leaked
    # into the trailing average, the result would spike far past any
    # plausible reading.
    bundle = _bundle_with_daily_highs(d, {0: 130.0, 1: 130.0})
    result = estimate_water_temp_f(bundle, d, d.timetuple().tm_yday)
    assert result < 100.0


def test_estimate_water_temp_f_only_averages_within_the_trailing_window():
    d = date(2026, 8, 13)
    # One day just inside the WATER_TEMP_TREND_PAST_DAYS window (moves the
    # result), one day just outside it (must not move the result at all).
    inside_offset = -WATER_TEMP_TREND_PAST_DAYS
    outside_offset = -(WATER_TEMP_TREND_PAST_DAYS + 1)
    baseline = estimate_water_temp_f(
        _bundle_with_daily_highs(d, {inside_offset: 90.0}), d, d.timetuple().tm_yday,
    )
    with_outside_day_too = estimate_water_temp_f(
        _bundle_with_daily_highs(d, {inside_offset: 90.0, outside_offset: 40.0}), d, d.timetuple().tm_yday,
    )
    assert with_outside_day_too == baseline


def test_estimate_water_temp_f_tracks_a_real_recent_hot_or_cold_spell():
    d = date(2026, 8, 13)
    day_of_year = d.timetuple().tm_yday
    trailing_offsets = range(1, WATER_TEMP_TREND_PAST_DAYS + 1)
    hot = estimate_water_temp_f(
        _bundle_with_daily_highs(d, {-i: 98.0 for i in trailing_offsets}), d, day_of_year,
    )
    cold_snap = estimate_water_temp_f(
        _bundle_with_daily_highs(d, {-i: 70.0 for i in trailing_offsets}), d, day_of_year,
    )
    assert hot > cold_snap


def test_estimate_water_temp_f_matches_real_logged_nolin_readings_in_mid_august():
    # Ground truth: the angler's own real, hand-logged Spot Session surface
    # readings for 2026-08-09 through 2026-08-17 ran 83.0-88.9F (see
    # SESSION_NOTES.md's punch-list #7 entry). A representative recent-highs
    # trend in the low 90s (typical for a KY August) should land the
    # estimate inside that same real range, not several degrees below it
    # like the pre-fix formula did.
    d = date(2026, 8, 13)
    day_of_year = d.timetuple().tm_yday
    trailing_offsets = range(1, WATER_TEMP_TREND_PAST_DAYS + 1)
    result = estimate_water_temp_f(
        _bundle_with_daily_highs(d, {-i: 92.0 for i in trailing_offsets}), d, day_of_year,
    )
    assert 82.0 <= result <= 90.0
