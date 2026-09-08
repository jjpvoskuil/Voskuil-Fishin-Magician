"""Tests for punch-list #94: "In any area that shows a fishing predicted
score for the day or period, add a collapsable box or similar next to the
score that details how the score was derived."

Home page ("Today at a glance") shows a predicted score in two places:
the "Activity score" tile (today.overall_score - a plain average of the
day's 6 time-of-day segment scores) and the "Best window today" info box
(best_segment.score - one segment's own factor-weighted breakdown). Both
now get an "ℹ️ How this score was derived" st.popover right next to them
(core.ui.render_day_score_breakdown() / render_score_breakdown()) - a
popover rather than st.expander so this can be dropped in anywhere a
score is shown without fighting for layout width, including compact
metric-tile columns like this page's "today_at_a_glance_metrics" row.

Uses AppTest (streamlit.testing.v1). Every real file write/network call
(core.storage.commit_and_push_data, core.water_quality_log.append_if_new
indirectly via get_surface_water_quality returning None, every cached
appstate getter) is mocked - this suite must never touch real data/*.csv
files or attempt a real network call.
"""
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from core import appstate
from core.weather import WeatherBundle, WATER_TEMP_TREND_PAST_DAYS, lake_today

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "home.py")


def _fake_bundle(d, days=9, air_temp_f=80.0):
    """Same shape/approach as tests/test_scoring.py's own
    _fake_bundle_with_air_temp() - anchored at `d` so score_day(bundle, d)
    (home.py calls this for lake_today()) has real hourly/daily coverage
    to compute from, rather than raising "No weather data available"."""
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
    daily_days = WATER_TEMP_TREND_PAST_DAYS + 7
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


def _run_home(monkeypatch):
    today = lake_today()
    monkeypatch.setattr(appstate, "get_calibrated_weights", mock.MagicMock(return_value=({}, 0)))
    monkeypatch.setattr(appstate, "get_weather_bundle", mock.MagicMock(return_value=_fake_bundle(today)))
    monkeypatch.setattr(appstate, "get_lake_level", mock.MagicMock(return_value=None))
    monkeypatch.setattr(appstate, "get_surface_water_quality", mock.MagicMock(return_value=None))
    monkeypatch.setattr(appstate, "get_water_quality_log", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "get_trip_history", mock.MagicMock(return_value=[]))
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"home.py raised: {at.exception}"
    return at


def test_activity_score_tile_has_a_breakdown_popover(monkeypatch):
    at = _run_home(monkeypatch)
    metrics = {m.label: m for m in at.metric}
    assert "Activity score" in metrics

    popover_labels = [p.proto.popover.label for p in at.get("popover")]
    assert "ℹ️ How this score was derived" in popover_labels, (
        f"expected a score-breakdown popover next to the Activity score tile, got: {popover_labels}"
    )
    all_markdown = [m.value for m in at.markdown]
    assert any("Average of this day's" in t and "time-of-day windows" in t for t in all_markdown), (
        f"expected the day-level (segment-average) breakdown content, got: {all_markdown}"
    )


def test_best_window_info_box_has_a_factor_breakdown_popover(monkeypatch):
    at = _run_home(monkeypatch)
    infos = [i.value for i in at.info]
    assert any("Best window today" in i for i in infos), f"expected the best-window info box, got: {infos}"

    breakdown_texts = [m.value for m in at.markdown if "How this score was derived" in m.value]
    # The Activity score tile's own day-level breakdown is one of these;
    # the best-window one is the OTHER, factor-level breakdown (starts
    # with the shared "Base" line every core.scoring._segment_score()
    # breakdown always opens with).
    assert any("- Base:" in t for t in breakdown_texts), (
        f"expected a factor-level breakdown (starting with the 'Base' line) for the best window, got: {breakdown_texts}"
    )
