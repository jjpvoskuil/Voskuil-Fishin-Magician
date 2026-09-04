"""Tests for app.py's boot-time data sync (_sync_data_once()) - the home of
punch-list #52/#73/#77. Uses Streamlit's AppTest (streamlit.testing.v1)
rather than a plain `import app`, since app.py's own st.navigation()/
pg.run() calls at module level need a real Streamlit script-run context to
execute at all - the same tool already used (as a one-off, uncommitted
scratch script) to verify punch-list #73's fix. Committing it here gives
this exact class of bug (a boot-time sync going stale - whether because
the sync itself never retries, #73, or because a downstream cache never
learns the sync succeeded, #77) durable regression coverage instead of
relying on a scratch script someone has to remember to re-run by hand.
"""
from pathlib import Path
from unittest import mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from core import appstate

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _reset_resource_cache():
    # _sync_data_once() is an @st.cache_resource function - a process-wide
    # cache that outlives any single test. Without this, an earlier test
    # (in this file or, since it's process-wide, any other) that already
    # ran app.py once could leave _sync_data_once() cached as "done",
    # silently making this test's own fake sync never get called at all.
    # get_trip_history() is a SEPARATE cache type (st.cache_data) that's
    # just as process-wide and just as easy to leave dirty between tests -
    # cleared here too so one test's fresh read can't leak into the next
    # test's "stale" assertion (or vice versa).
    st.cache_resource.clear()
    appstate.get_trip_history.clear()
    yield
    st.cache_resource.clear()
    appstate.get_trip_history.clear()


def test_sync_data_once_clears_stale_trip_history_cache_once_it_succeeds(monkeypatch):
    """Punch-list #77 - the actual live bug: a page render that happens to
    call get_trip_history() BEFORE this process's sync has succeeded (very
    plausible right at cold boot, or during a still-in-progress retry) must
    NOT keep serving that stale read for its own 5-minute TTL once the sync
    DOES succeed on a later rerun - closing that gap is the whole point of
    _sync_data_once() clearing these caches on success."""
    sync_calls = {"n": 0}

    def fake_sync(token, slug):
        sync_calls["n"] += 1
        if sync_calls["n"] < 2:
            # 1st attempt "fails" - the app keeps running on whatever's
            # already on disk (main's frozen snapshot, in the real bug).
            return False, "Data branch sync skipped: fatal: Connection timed out"
        return True, "Synced data/ from the 'data' branch."

    def fake_read_all_trips():
        # Row count only changes once the sync has actually succeeded -
        # before that, this always represents the stale/frozen data a real
        # cold boot would still have on disk.
        row_count = 1 if sync_calls["n"] < 2 else 2
        return [{"trip_id": f"row-{i}"} for i in range(row_count)]

    monkeypatch.setattr(appstate, "read_all_trips", fake_read_all_trips)

    with mock.patch("core.appstate.github_token", return_value="fake-token"), \
         mock.patch("core.storage.sync_data_from_data_branch", side_effect=fake_sync):
        at = AppTest.from_file(APP_PATH, default_timeout=30)

        at.run()  # 1st boot: sync fails, app runs on today's "frozen" data
        assert not at.exception, f"1st run raised: {at.exception}"

        # A page rendering during this window (Leaderboard, 7-Day Forecast,
        # Spot Session's own recommendation panels) would call this exact
        # getter - simulate that directly, the same way test_appstate.py's
        # own cache tests already do.
        stale = appstate.get_trip_history()
        assert len(stale) == 1, "expected the pre-sync-success (stale) row count"

        at.run()  # 2nd rerun: sync succeeds this time
        assert not at.exception, f"2nd run raised: {at.exception}"

        fresh = appstate.get_trip_history()
        assert len(fresh) == 2, (
            "get_trip_history() kept serving its stale pre-sync-success cached "
            "read instead of being cleared the moment the sync actually succeeded"
        )


def test_sync_data_once_does_not_clear_caches_on_a_failed_attempt(monkeypatch):
    """The clear must be gated on success, not run unconditionally on every
    attempt - clearing on a FAILED attempt would just throw away a
    perfectly good cached read for no reason, right when the sync itself is
    having trouble and a fresh read would just re-serve the same stale
    file anyway."""
    read_calls = {"n": 0}

    def fake_sync(token, slug):
        return False, "Data branch sync skipped: fatal: Connection timed out"

    def fake_read_all_trips():
        read_calls["n"] += 1
        return [{"trip_id": "row-1"}]

    monkeypatch.setattr(appstate, "read_all_trips", fake_read_all_trips)

    with mock.patch("core.appstate.github_token", return_value="fake-token"), \
         mock.patch("core.storage.sync_data_from_data_branch", side_effect=fake_sync):
        at = AppTest.from_file(APP_PATH, default_timeout=30)

        at.run()
        assert not at.exception, f"1st run raised: {at.exception}"
        appstate.get_trip_history()
        assert read_calls["n"] == 1

        at.run()  # sync fails again
        assert not at.exception, f"2nd run raised: {at.exception}"
        # Still cached from before - a failed sync must not have cleared it.
        appstate.get_trip_history()
        assert read_calls["n"] == 1, "a failed sync attempt cleared the cache anyway"
