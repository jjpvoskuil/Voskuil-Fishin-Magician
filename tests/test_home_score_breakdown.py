"""Tests for punch-list #94: "In any area that shows a fishing predicted
score for the day or period, add a collapsable box or similar next to the
score that details how the score was derived" - plus its two follow-up
asks, "Lets maybe just have a small box with the 'i' icon instead of that
and the txt" (an icon-only st.popover, no visible text label) and "for the
full day score in the 7 day forecast, maybe average the individual
scoring elements across all periods of the day instead of averaging the
period of the day scores" (core.scoring.aggregate_day_overall()).

Home page ("Today at a glance") shows a predicted score in two places:
the "Activity score" tile (today.overall_score - now the day's own
factor-averaged breakdown, not a plain average of its 6 segment scores)
and the "Best window today" info box (best_segment.score - one segment's
own factor-weighted breakdown). Both now get the identical icon-only "ℹ️"
st.popover right next to them (core.ui.render_score_breakdown(), the same
function for both - a day-level score has its own real breakdown now, so
no separate "day" helper is needed) - a popover rather than st.expander
so this can be dropped in anywhere a score is shown without fighting for
layout width, including compact metric-tile columns like this page's
"today_at_a_glance_metrics" row.

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

    popovers = at.get("popover")
    activity_popover = next((p for p in popovers if p.key == "home_activity_score_breakdown"), None)
    assert activity_popover is not None, (
        f"expected an icon-only score-breakdown popover next to the Activity score tile, got keys: "
        f"{[p.key for p in popovers]}"
    )
    # Punch-list #94 follow-up: icon-only now ("Lets maybe just have a
    # small box with the 'i' icon instead of that and the txt") - no
    # visible text label, just the ℹ️ icon.
    assert activity_popover.proto.popover.label == ""
    assert activity_popover.proto.popover.icon == "ℹ️"

    all_markdown = [m.value for m in at.markdown]
    # Punch-list #94 follow-up: the day-level score now averages each
    # scoring FACTOR's own delta across the day's segments (core.scoring.
    # aggregate_day_overall()), not the segments' own scores - so its
    # popover shows the same factor-breakdown shape (starting with the
    # shared "Base" line) as any single segment's own breakdown, not a
    # per-segment score list.
    assert any("**How this score was derived:**" in t and "- Base:" in t for t in all_markdown), (
        f"expected factor-breakdown content for the day-level score, got: {all_markdown}"
    )


def test_best_window_info_box_has_a_factor_breakdown_popover(monkeypatch):
    at = _run_home(monkeypatch)
    infos = [i.value for i in at.info]
    assert any("Best window today" in i for i in infos), f"expected the best-window info box, got: {infos}"

    popovers = at.get("popover")
    best_window_popover = next((p for p in popovers if p.key == "home_best_window_score_breakdown"), None)
    assert best_window_popover is not None, (
        f"expected an icon-only score-breakdown popover next to the best-window box, got keys: "
        f"{[p.key for p in popovers]}"
    )
    assert best_window_popover.proto.popover.label == ""
    assert best_window_popover.proto.popover.icon == "ℹ️"

    breakdown_texts = [m.value for m in at.markdown if "How this score was derived" in m.value]
    assert any("- Base:" in t for t in breakdown_texts), (
        f"expected a factor-level breakdown (starting with the 'Base' line) for the best window, got: {breakdown_texts}"
    )
