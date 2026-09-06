"""Smoke tests for pages/9_Reports.py - punch-list #92's first pass.

core/reports.py's own aggregation/binning logic is already fully unit
tested in tests/test_reports.py without Streamlit at all; these tests are
just AppTest (streamlit.testing.v1) confirming the actual PAGE renders,
reacts to its own controls, and produces the download button - the same
level this repo already tests pages/4_Trip_History.py's own filters at.

Most of this page needs no weather-bundle mocking - it mainly reads
core.appstate.get_trip_history(), a plain read of data/trip_log.csv, so it
renders fine against this repo's own on-disk fixture data. The one
exception is the barometric-pressure predictor section added for punch-list
#92's 2nd predictive pass, which genuinely depends on core.appstate.
get_weather_bundle(16) - those tests mock it explicitly (see the "Barometric
pressure trend predictor" section below) for a deterministic result, rather
than relying on this sandbox's own network access (which fails here,
incidentally exercising the "no live weather" path in every OTHER test in
this file that never mocks it).

The module-scoped autouse fixture below clears that cache before every
test in this file. Without it, a fake single-row cache left behind by
tests/test_appstate.py's own test_get_trip_history_is_cached_until_cleared
(which monkeypatches read_all_trips() but - unlike its own two clear()
calls bracketing the fake data - never clears the cache a final time
afterward, so the LAST fake read stays memoized) can leak into this file
whenever it runs later in the same test session, making these tests see a
single fake trip_id-only row instead of this repo's real trip history.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from core import appstate
from core.weather import WeatherBundle

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "9_Reports.py")


def _pressure_bundle(start_date: date, num_days: int, hpa_change_per_24h: float,
                      base_pressure: float = 1015.0) -> WeatherBundle:
    """A minimal WeatherBundle with a perfectly linear surface_pressure
    trend, covering `num_days` days of hourly data from local midnight of
    `start_date` - same idea as tests/test_reports.py's own helper of the
    same name (kept local rather than shared, matching this repo's existing
    convention of not importing helpers across test files), just enough to
    give the page's own get_weather_bundle() mock a real, in-range forecast
    to compute a pressure-trend prediction from."""
    start = datetime.combine(start_date, datetime.min.time())
    total_hours = num_days * 24
    hourly_change = hpa_change_per_24h / 24.0
    times = [(start + timedelta(hours=h)).isoformat() for h in range(total_hours)]
    pressures = [base_pressure + hourly_change * h for h in range(total_hours)]
    return WeatherBundle(hourly={"time": times, "surface_pressure": pressures}, daily={})


@pytest.fixture(autouse=True)
def _fresh_trip_history_cache():
    appstate.get_trip_history.clear()
    yield
    appstate.get_trip_history.clear()


def test_page_renders_with_default_controls():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"

    labels = [s.label for s in at.selectbox]
    assert "Factor (x-axis)" in labels
    assert "Success metric" in labels
    assert "Species" in labels
    assert len(at.dataframe) == 1, "expected exactly one report table"
    assert any(b.label == "⬇️ Export to Excel" for b in at.download_button), (
        "expected an Export to Excel download button once a report has data"
    )


def test_switching_to_a_date_factor_still_renders_and_uses_a_line_chart():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    at.selectbox(key="rpt_factor").set_value("Date (daily)").run()
    assert not at.exception, f"page raised after switching to a date factor: {at.exception}"
    assert len(at.dataframe) == 1


def test_switching_to_a_non_species_filterable_metric_disables_species_picker():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    at.selectbox(key="rpt_metric").set_value("Fish per Hour (rate)").run()
    assert not at.exception, f"page raised after switching metric: {at.exception}"

    species_box = next(s for s in at.selectbox if s.label == "Species")
    assert species_box.disabled, (
        "fish_per_hour is inherently per-trip, not per-catch - the Species filter should be "
        "disabled for it, mirroring Leaderboard's own disabled-when-not-applicable pattern"
    )


def test_swapping_an_inverted_date_range_does_not_raise():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    date_inputs = {d.label: d for d in at.date_input}
    from_value = date_inputs["From"].value
    to_value = date_inputs["To"].value
    # Deliberately invert From/To - the page should swap them, not crash.
    date_inputs["From"].set_value(to_value).run()
    date_inputs["To"].set_value(from_value).run()
    assert not at.exception, f"page raised on an inverted date range: {at.exception}"


def test_water_temp_bucket_width_control_only_appears_for_that_factor():
    # Punch-list #92 follow-up: "Water Temp Band" (the 5 fixed biological
    # stages) was too coarse for this repo's real on-disk trip data (an
    # ~83-89°F range, so nearly every trip lands in one or two of the five
    # named bands) - "Water Temp (custom range)" lets the angler pick a
    # tighter bucket width instead. The width control should be invisible
    # for every other factor.
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not any(n.label == "Bucket width (°F)" for n in at.number_input), (
        "the bucket-width control should not appear for the default factor"
    )

    at.selectbox(key="rpt_factor").set_value("Water Temp (custom range)").run()
    assert not at.exception, f"page raised after switching to the water-temp-bucket factor: {at.exception}"
    width_inputs = [n for n in at.number_input if n.label == "Bucket width (°F)"]
    assert len(width_inputs) == 1, "expected exactly one bucket-width control once this factor is picked"
    assert len(at.dataframe) == 1


def test_narrowing_the_water_temp_bucket_width_produces_more_rows():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    at.selectbox(key="rpt_factor").set_value("Water Temp (custom range)").run()
    wide_row_count = len(at.dataframe[0].value)

    at.number_input(key="rpt_water_temp_bucket_width").set_value(1.0).run()
    assert not at.exception, f"page raised after narrowing the bucket width: {at.exception}"
    narrow_row_count = len(at.dataframe[0].value)

    assert narrow_row_count > wide_row_count, (
        "a narrower bucket width over the same real data should produce MORE, not fewer, rows"
    )


def test_predict_section_renders_with_default_controls():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"

    date_inputs = {d.label: d for d in at.date_input}
    assert "Predict for date" in date_inputs
    assert any(m.label.startswith("Predicted ") for m in at.metric), (
        "expected a 'Predicted <metric>' st.metric in the predict section"
    )


def test_predict_section_still_renders_when_the_historical_report_above_is_empty():
    # Regression guard: the predict section must NOT be gated behind the
    # historical chart/table/export block above it (an early st.stop() used
    # to do exactly that) - it reads directly from trips_df/fish_df, not
    # from the (possibly empty, under the CURRENT Factor/filters) `report`
    # variable, so an empty historical report must not take it down too.
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    # A date range with no real trips in it at all forces `report` empty.
    at.date_input(key="rpt_date_start").set_value(date(2020, 1, 1)).run()
    at.date_input(key="rpt_date_end").set_value(date(2020, 1, 2)).run()
    assert not at.exception, f"page raised with an empty historical report: {at.exception}"
    assert any(m.label.startswith("Predicted ") for m in at.metric), (
        "the predict section should still render its metric even when the historical report above is empty"
    )


def test_predicting_for_a_date_with_no_matching_bucket_data_shows_a_dash_not_a_crash():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    # An empty date range (via the historical filters) starves every
    # moon-illumination bucket of data, so whatever date is predicted for
    # should come back as "no data" (a dash), not raise.
    at.date_input(key="rpt_date_start").set_value(date(2020, 1, 1)).run()
    at.date_input(key="rpt_date_end").set_value(date(2020, 1, 2)).run()
    assert not at.exception, f"page raised: {at.exception}"
    predicted_metric = next(m for m in at.metric if m.label.startswith("Predicted "))
    assert predicted_metric.value == "—"


# --- Barometric pressure trend predictor (punch-list #92's 2nd predictor) -------
# Unlike moon illumination, this predictor genuinely depends on a live
# weather fetch (core.appstate.get_weather_bundle(16)) - every test below
# mocks it explicitly for a deterministic result, rather than relying on
# whatever this sandbox's own network access happens to do (the other
# predict-section tests above run against the REAL get_weather_bundle,
# which fails in this sandbox - see this module's own top-of-file
# docstring - and so incidentally exercise the "no live weather" path,
# but that's not something a portable test should depend on).

def test_pressure_predict_section_renders_a_prediction_when_the_forecast_covers_the_target_date():
    target = date.today() + timedelta(days=1)  # the page's own default "Predict for date"
    bundle = _pressure_bundle(target - timedelta(days=2), num_days=5, hpa_change_per_24h=-3.0)
    with mock.patch.object(appstate, "get_weather_bundle", return_value=bundle):
        at = AppTest.from_file(PAGE_PATH, default_timeout=60)
        at.run()
    assert not at.exception, f"page raised: {at.exception}"
    predicted_metrics = [m for m in at.metric if m.label.startswith("Predicted ")]
    assert len(predicted_metrics) == 2, "expected one 'Predicted' metric each for moon and pressure"
    assert any(c.value.startswith("📉 Forecast:") for c in at.caption), (
        "expected a pressure-trend forecast caption once the bundle covers the target date"
    )


def test_pressure_predict_section_shows_an_unavailable_message_when_the_weather_fetch_fails():
    with mock.patch.object(appstate, "get_weather_bundle", return_value=None):
        at = AppTest.from_file(PAGE_PATH, default_timeout=60)
        at.run()
    assert not at.exception, f"page raised when the weather bundle was None: {at.exception}"
    predicted_metrics = [m for m in at.metric if m.label.startswith("Predicted ")]
    assert len(predicted_metrics) == 1, "only moon illumination's metric should render, not pressure's"
    assert any("No live weather forecast available" in c.value for c in at.caption)


def test_pressure_predict_section_shows_an_out_of_range_message_when_the_target_date_is_outside_the_forecast():
    target = date.today() + timedelta(days=1)
    # A bundle that covers dates nowhere near the (default) target date.
    bundle = _pressure_bundle(target - timedelta(days=100), num_days=3, hpa_change_per_24h=-3.0)
    with mock.patch.object(appstate, "get_weather_bundle", return_value=bundle):
        at = AppTest.from_file(PAGE_PATH, default_timeout=60)
        at.run()
    assert not at.exception, f"page raised: {at.exception}"
    predicted_metrics = [m for m in at.metric if m.label.startswith("Predicted ")]
    assert len(predicted_metrics) == 1, "only moon illumination's metric should render, not pressure's"
    assert any("outside the fetched weather forecast's window" in c.value for c in at.caption)


def test_pressure_predict_section_still_renders_when_the_historical_report_above_is_empty():
    target = date.today() + timedelta(days=1)
    bundle = _pressure_bundle(target - timedelta(days=2), num_days=5, hpa_change_per_24h=-3.0)
    with mock.patch.object(appstate, "get_weather_bundle", return_value=bundle):
        at = AppTest.from_file(PAGE_PATH, default_timeout=60)
        at.run()
        # Same "empty historical report above" regression guard as the moon
        # predictor's own test above - a date range with no real trips at all.
        at.date_input(key="rpt_date_start").set_value(date(2020, 1, 1)).run()
        at.date_input(key="rpt_date_end").set_value(date(2020, 1, 2)).run()
    assert not at.exception, f"page raised with an empty historical report: {at.exception}"
    predicted_metrics = [m for m in at.metric if m.label.startswith("Predicted ")]
    assert len(predicted_metrics) == 2
    assert predicted_metrics[1].value == "—", "starved of matching historical trips, pressure's own prediction should be a dash"
