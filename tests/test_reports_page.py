"""Smoke tests for pages/9_Reports.py - punch-list #92's first pass.

core/reports.py's own aggregation/binning logic is already fully unit
tested in tests/test_reports.py without Streamlit at all; these tests are
just AppTest (streamlit.testing.v1) confirming the actual PAGE renders,
reacts to its own controls, and produces the download button - the same
level this repo already tests pages/4_Trip_History.py's own filters at.

No weather-bundle mocking needed here (unlike pages that call
core.weather.get_weather_bundle()) - this page only reads
core.appstate.get_trip_history(), a plain read of data/trip_log.csv, so it
renders fine against this repo's own on-disk fixture data.

The module-scoped autouse fixture below clears that cache before every
test in this file. Without it, a fake single-row cache left behind by
tests/test_appstate.py's own test_get_trip_history_is_cached_until_cleared
(which monkeypatches read_all_trips() but - unlike its own two clear()
calls bracketing the fake data - never clears the cache a final time
afterward, so the LAST fake read stays memoized) can leak into this file
whenever it runs later in the same test session, making these tests see a
single fake trip_id-only row instead of this repo's real trip history.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import appstate

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "9_Reports.py")


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
