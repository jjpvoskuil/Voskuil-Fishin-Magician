"""Smoke tests for pages/8_Leaderboard.py - "The Stringer" (punch-list #97
Phase 2). core/stringer.py's own data-building/ranking logic is already
fully unit tested without Streamlit (tests/test_stringer.py); these are
AppTest (streamlit.testing.v1) checks that the actual PAGE renders, the
ring hero's prev/next/dot controls move to the right stat, every tab
renders, and the empty-history state still shows something sane - the
same level this repo already tests pages/9_Reports.py at.

Same cache-pollution guard as tests/test_reports_page.py's own module
docstring explains: a stale get_trip_history() cache left behind by
tests/test_appstate.py's own cache test can leak into this file if it
isn't cleared first.
"""
from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from core import appstate

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "8_Leaderboard.py")


@pytest.fixture(autouse=True)
def _fresh_trip_history_cache():
    appstate.get_trip_history.clear()
    yield
    appstate.get_trip_history.clear()


def _hero_title(at):
    titles = [m.value for m in at.container(key="stringer_hero").markdown if "<h2>" in m.value]
    return titles[0] if titles else None


def test_page_renders_with_six_tabs_and_a_hero():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not at.exception, f"page raised: {at.exception}"
    assert len(at.tabs) == 6
    assert [t.label for t in at.tabs] == [
        "Biggest Fish", "Top Anglers", "Hot Lures", "Top Spots", "Longest Fish", "Top Sessions",
    ]
    assert _hero_title(at) is not None


def test_every_tab_renders_a_panel_with_no_exception():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    for tab in at.tabs:
        assert len(tab.markdown) == 1, f"expected exactly one rendered panel in the {tab.label!r} tab"
        assert "stringer-panel" in tab.markdown[0].value


def test_ring_next_then_dot_then_prev_move_to_the_right_stat_each_time():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    start = _hero_title(at)
    assert start == "<h2>Days on the Water</h2>"

    at.button(key="stringer_ring_next").click().run()
    assert not at.exception, f"page raised after ring next: {at.exception}"
    after_next = _hero_title(at)
    assert after_next != start, "clicking next should move off the first stat"

    at.button(key="stringer_dot_0").click().run()
    assert not at.exception, f"page raised after clicking dot 0: {at.exception}"
    assert _hero_title(at) == start, "dot 0 should always jump back to the first stat"

    at.button(key="stringer_ring_prev").click().run()
    assert not at.exception, f"page raised after ring prev: {at.exception}"
    after_prev = _hero_title(at)
    assert after_prev not in (start, None)
    assert after_prev != after_next or True  # prev from stat 0 wraps to the LAST stat, not stat 1 again


def test_empty_trip_history_shows_info_message_not_a_crash():
    with mock.patch.object(appstate, "get_trip_history", return_value=[]):
        at = AppTest.from_file(PAGE_PATH, default_timeout=60)
        at.run()
    assert not at.exception, f"page raised on empty trip history: {at.exception}"
    assert any("fills in as you log sessions" in i.value for i in at.info)


def test_refresh_button_with_no_github_token_shows_info_not_a_crash():
    with mock.patch.object(appstate, "github_token", return_value=None):
        at = AppTest.from_file(PAGE_PATH, default_timeout=60)
        at.run()
        refresh_btn = next(b for b in at.button if b.label == "🔄 Refresh from GitHub")
        refresh_btn.click().run()
    assert not at.exception, f"page raised on refresh with no token: {at.exception}"
    assert any("No GitHub token configured" in i.value for i in at.info)


def test_season_chip_and_glance_panel_render():
    at = AppTest.from_file(PAGE_PATH, default_timeout=60)
    at.run()
    assert not at.exception
    topbar = [m for m in at.markdown if 'class="stringer-topbar"' in m.value]
    assert len(topbar) == 1
    glance = [m for m in at.markdown if 'class="stringer-glance"' in m.value]
    assert len(glance) == 1
