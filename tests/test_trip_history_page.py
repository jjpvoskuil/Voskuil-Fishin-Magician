"""Tests for pages/4_Trip_History.py's "Date range" filter - punch-list
#77/#78. Uses Streamlit's AppTest (streamlit.testing.v1) since both bugs
were reported and confirmed against the real rendered page, not just the
pure grouping/filtering logic already covered elsewhere (core.appstate).

Both were confirmed live against the real deployed app, in a mobile
viewport, via direct DOM inspection (see the "Punch-list #77/#78" section
of this page's own module docstring for the full root-cause writeup):

- #77: "Date range" used to share a 3-column row with "Time of day" and
  "Location", which left it squeezed to ~120px wide on a phone - nowhere
  near enough for a full "YYYY/MM/DD - YYYY/MM/DD" range. Fixed by giving
  it its own full-width row.
- #78: picking "just today" required two clicks on the same calendar date
  (standard range-picker behavior, but easy to miss, and an easy target for
  a phone's own double-tap-to-zoom gesture to swallow the second tap). Fixed
  by adding a one-tap "📅 Today only" button that jumps the filter straight
  to a single-day range on today.
"""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from core.weather import lake_today

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "4_Trip_History.py")


def test_date_range_is_not_squeezed_into_the_three_column_filter_grid():
    """Punch-list #77 - the actual live bug: "Date range" sharing a row with
    two other filters left it far too narrow to show a full range on a
    phone. Regression guard: the date_input must not live inside any
    st.columns() split at all (so it always gets the block's full width),
    and the row it used to share with "Time of day"/"Location" must now
    hold only those two (2 columns, not 3)."""
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"

    assert len(at.date_input) == 1, "expected exactly one Date range widget"

    # Pre-fix, the date_input lived inside one of a 3-column row's columns
    # alongside the Time-of-day and Location multiselects. Post-fix it's a
    # direct child of the page (no column), so no Column's own element list
    # should contain it.
    for column in at.columns:
        assert "DateInput" not in [type(el).__name__ for el in column], (
            "Date range is still squeezed inside a multi-column row instead "
            "of getting its own full-width row"
        )

    # Time of day + Location used to be 2 of that same 3-column row; now
    # that Date range has its own row, neither of their columns should have
    # anything else (like the old date_input) sharing space with them.
    for label in ("Time of day", "Location"):
        col = next(
            c for c in at.columns if any(getattr(el, "label", None) == label for el in c)
        )
        kinds = [type(el).__name__ for el in col if type(el).__name__ != "Column"]
        assert kinds == ["Multiselect"], (
            f"expected the '{label}' column to hold only its own multiselect, found {kinds}"
        )


def test_today_only_button_jumps_the_filter_to_a_single_day_on_today():
    """Punch-list #78 - the actual live ask: "just pick a single date,
    include today's date" without fighting the calendar's own two-click
    same-day range mechanic. Confirmed to fail pre-fix (no such button
    exists) and pass post-fix."""
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"

    today_only_buttons = [b for b in at.button if b.label == "📅 Today only"]
    assert len(today_only_buttons) == 1, "expected a single 'Today only' button"

    # Sanity check this isn't a no-op: with real historical trips on disk,
    # the filter should NOT already default to a single day on today before
    # the button is pressed.
    before = at.date_input[0].value
    assert before != (lake_today(), lake_today()), (
        "test fixture's real trip data already defaults to today-only - "
        "this test needs a range that spans more than one day to be meaningful"
    )

    today_only_buttons[0].click().run()
    assert not at.exception, f"page raised after clicking Today only: {at.exception}"

    after = at.date_input[0].value
    assert after == (lake_today(), lake_today()), (
        "Today only did not jump the date range to a single day on today"
    )
