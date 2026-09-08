"""Tests for punch-list #94 on the 7-Day Forecast page: every predicted
score shown (each day's overall_score summary tile, and each time-of-day
segment's own score inside a day's detail expander) gets an icon-only "ℹ️"
st.popover right next to it that details how the score was derived.

Plus its two same-session follow-ups: (1) "Lets maybe just have a small
box with the 'i' icon instead of that and the txt" - the popover has no
visible text label, just the ℹ️ icon (help="How this score was derived"
is set instead, for the hover tooltip). (2) "for the full day score in
the 7 day forecast, maybe average the individual scoring elements across
all periods of the day instead of averaging the period of the day
scores" - each day's overall_score/overall_breakdown now come from
core.scoring.aggregate_day_overall(), which averages each scoring
factor's own delta across the day's 6 segments, so the day-level popover
shows a real factor breakdown (starting with "Base") just like a single
segment's own breakdown, not a per-segment score list.

The per-segment popover is deliberately a popover, not another
st.expander: it renders nested inside each day's own st.expander (the
per-day detail panel), and core.ui.render_score_breakdown()'s own
docstring explains why a popover (not a second expander) is used there.

Uses AppTest. See tests/test_home_score_breakdown.py for the shared
_fake_bundle() approach (identical here, duplicated rather than imported
across test files per this suite's existing convention of each test file
building its own fixtures).
"""
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from core import appstate, forecast_freeze, storage
from core.weather import WeatherBundle, WATER_TEMP_TREND_PAST_DAYS, lake_today

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "1_7_Day_Forecast.py")


def _fake_bundle(d, days=16, air_temp_f=80.0):
    times, temps, pres, cloud, wind, wdir, pprob, precip = [], [], [], [], [], [], [], []
    t0 = datetime(d.year, d.month, d.day) - timedelta(days=6)
    for h in range(24 * days):
        dt = t0 + timedelta(hours=h)
        times.append(dt.isoformat())
        temps.append(air_temp_f)
        pres.append(1015 - 0.05 * h)
        cloud.append(40)
        wind.append(7)
        wdir.append(180)
        pprob.append(10)
        precip.append(0)
    hourly = {
        "time": times, "temperature_2m": temps, "surface_pressure": pres, "cloudcover": cloud,
        "windspeed_10m": wind, "winddirection_10m": wdir, "precipitation_probability": pprob,
        "precipitation": precip,
    }
    daily_start = d - timedelta(days=WATER_TEMP_TREND_PAST_DAYS)
    daily_days = WATER_TEMP_TREND_PAST_DAYS + days
    daily = {
        "time": [(daily_start + timedelta(days=i)).isoformat() for i in range(daily_days)],
        "sunrise": [
            (datetime(d.year, d.month, d.day) + timedelta(days=i - WATER_TEMP_TREND_PAST_DAYS, hours=6, minutes=20)).isoformat()
            for i in range(daily_days)
        ],
        "sunset": [
            (datetime(d.year, d.month, d.day) + timedelta(days=i - WATER_TEMP_TREND_PAST_DAYS, hours=20, minutes=15)).isoformat()
            for i in range(daily_days)
        ],
        "temperature_2m_max": [air_temp_f + 10] * daily_days,
        "temperature_2m_min": [air_temp_f - 10] * daily_days,
    }
    return WeatherBundle(hourly=hourly, daily=daily)


def _run_forecast(monkeypatch):
    today = lake_today()
    monkeypatch.setattr(appstate, "get_weather_bundle", mock.MagicMock(return_value=_fake_bundle(today)))
    monkeypatch.setattr(appstate, "get_calibrated_weights", mock.MagicMock(return_value=({}, 0)))
    monkeypatch.setattr(appstate, "get_spots", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "get_lake_spots", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "get_inventory", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "get_trip_history", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "github_token", mock.MagicMock(return_value=""))
    monkeypatch.setattr(forecast_freeze, "apply_freeze", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(storage, "commit_and_push_data", mock.MagicMock(return_value=(True, "ok")))
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"7-Day Forecast raised: {at.exception}"
    return at


def test_each_day_summary_tile_has_a_breakdown_popover(monkeypatch):
    at = _run_forecast(monkeypatch)
    popovers = at.get("popover")
    day_popovers = [p for p in popovers if p.key and p.key.startswith("week_day_score_breakdown_")]
    assert day_popovers, (
        f"expected one day-level breakdown popover per day in the top summary row, got keys: "
        f"{[p.key for p in popovers]}"
    )
    # Punch-list #94 follow-up: icon-only, no visible text label.
    assert all(p.proto.popover.label == "" and p.proto.popover.icon == "ℹ️" for p in day_popovers)

    all_markdown = [m.value for m in at.markdown]
    # Punch-list #94 follow-up: the day-level score now averages each
    # scoring FACTOR's own delta across the day's segments (core.scoring.
    # aggregate_day_overall()), not the segments' own scores - so it
    # shows the same factor-breakdown shape (starting with "Base") as any
    # single segment's own breakdown.
    assert any("**How this score was derived:**" in t and "- Base:" in t for t in all_markdown), (
        f"expected factor-breakdown content for the day-level score, got: {all_markdown}"
    )


def test_each_segment_metric_has_a_factor_breakdown_popover(monkeypatch):
    at = _run_forecast(monkeypatch)
    popover_keys = [p.key for p in at.get("popover")]
    assert any(k and k.startswith("week_segment_score_breakdown_") for k in popover_keys), (
        f"expected one factor-breakdown popover per time-of-day segment, got keys: {popover_keys}"
    )
    all_markdown = [m.value for m in at.markdown]
    assert any("**How this score was derived:**" in t and "- Base:" in t for t in all_markdown), (
        f"expected the shared factor-breakdown content (starting with the 'Base' line), got: {all_markdown}"
    )
