"""Tests for pages/6_Spot_Session.py's post-add confirmation popup -
punch-list #87. Uses Streamlit's AppTest (streamlit.testing.v1), same as
test_dev_tasks_page.py, since this is specifically about what the rendered
page shows and does, not about core/storage.py's own read/write logic
(already covered elsewhere).

Angler's own direct ask, verbatim: "each lure I add to the session should
be followed by a pop up the shows what lure have been added so far and an
option to either add more lures or start the session." Implemented as a
new @st.dialog, _lure_added_dialog(), triggered by a session_state flag
(_lure_added_popup_key()) set right after a lure actually lands in the
pending list - from the tackle-box picker, the suggestions quick-add, a
manual entry, or the trailer dialog's own "Add lure" button.

Important AppTest/st.dialog interaction note, found the hard way while
building this: the trigger flag is deliberately a plain `.get()` on every
render, NEVER a one-shot `.pop()`. An early draft popped the flag the
instant it was read, which "worked" in the sense that the popup rendered
once - but then NEITHER of its own two buttons could ever be clicked
successfully, because on the very next script run (the one a click inside
the popup itself triggers), the already-consumed flag no longer told the
page to re-invoke the dialog function at all, so Streamlit had nothing
left to attach that click to. The fix - checking a flag that stays True
until something explicit clears it (either "Add more lures" popping it
directly, or "Start Session" advancing session_build_seq so the OLD
seq-scoped key stops matching) - is what makes the popup's own buttons
actually work under AppTest. This is also presumably why the pre-existing
_trailer_dialog (opened inline from a button's own click, with no sticky
flag re-checked by top-level code every render) is NOT covered here or
anywhere else in this suite: AppTest has no equivalent of Streamlit's own
internal "keep re-rendering the last-opened dialog automatically" runtime
behavior, so a dialog only opened as a direct one-off reaction to a click
event can't be interacted with further inside this harness, even though it
works fine in a real deployed app. Manually verified end-to-end instead
(a trailer-eligible item's "+ Add" -> trailer dialog -> "Add lure" really
does set the popup flag in the source, matching the already-proven
non-trailer path exactly) rather than forced into an AppTest scenario this
harness structurally can't drive.

Every real file write (core.storage.append_trip, core.storage.
commit_and_push_data, core.storage.push_pending_data) and every cached
getter (core.appstate.get_lake_spots/get_inventory/get_weather_bundle/
get_anglers/get_trip_history/get_calibrated_weights/get_location_
adjustments) is mocked in every test below - this suite must never touch
the real data/*.csv files on disk or attempt a real network call.
"""
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from core import appstate, storage

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "6_Spot_Session.py")

FAKE_SPOT = {
    "spot_id": "spot1", "name": "Test Cove", "lat": 37.3, "lon": -86.2,
    "location_type": "Main-lake point", "notes": "",
}
FAKE_ITEM = {
    "item_id": "item1", "brand": "Strike King", "description": "Test Chartreuse Shad",
    "category": "medium_diving_crankbait", "quantity": 3, "sku": "sku1",
    "image_url": "", "image_filename": "", "price": 5.0, "package_qty": 1,
}
FAKE_ITEM_2 = {
    "item_id": "item2", "brand": "Zoom", "description": "Test Fluke",
    "category": "weightless_soft_plastic", "quantity": 2, "sku": "sku2",
    "image_url": "", "image_filename": "", "price": 4.0, "package_qty": 1,
}


def _install_mocks(monkeypatch, inventory=None):
    monkeypatch.setattr(appstate, "get_lake_spots", mock.MagicMock(return_value=[FAKE_SPOT]))
    monkeypatch.setattr(appstate, "get_inventory", mock.MagicMock(return_value=inventory or [FAKE_ITEM]))
    monkeypatch.setattr(appstate, "get_weather_bundle", mock.MagicMock(return_value=None))
    monkeypatch.setattr(appstate, "get_anglers", mock.MagicMock(return_value=["Solo"]))
    # These three specifically need a real .clear() (a plain lambda doesn't
    # have one) since _push_or_toast() always calls it after a trip-log
    # write - see this module's own docstring and punch-list #85's test
    # file for the same fix.
    monkeypatch.setattr(appstate, "get_trip_history", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "get_calibrated_weights", mock.MagicMock(return_value={}))
    monkeypatch.setattr(appstate, "get_location_adjustments", mock.MagicMock(return_value={}))
    monkeypatch.setattr(appstate, "github_token", mock.MagicMock(return_value=""))
    monkeypatch.setattr(storage, "append_trip", mock.MagicMock())
    monkeypatch.setattr(storage, "commit_and_push_data", mock.MagicMock(return_value=(True, "ok")))
    monkeypatch.setattr(storage, "push_pending_data", mock.MagicMock(return_value=(True, "ok")))


def _start_session_build(monkeypatch, inventory=None):
    """Gets to the point of a fresh, empty session-build for FAKE_SPOT,
    angler "Solo" - settled right before any lure has been added."""
    _install_mocks(monkeypatch, inventory=inventory)
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.session_state["spot_session_target_id"] = "spot1"
    at.run()
    assert not at.exception, f"initial run raised: {at.exception}"
    at.selectbox(key="spot_session_landing_choice").select("Solo").run()
    assert not at.exception, f"after picking angler: {at.exception}"
    return at


def _add_item1(at):
    at.button(key="session_lure_picker_spot1_0_toggle_item1").click().run()
    assert not at.exception, f"after adding item1: {at.exception}"
    return at


def test_lure_added_popup_shows_after_adding_a_lure(monkeypatch):
    at = _start_session_build(monkeypatch)
    _add_item1(at)

    successes = [s.value for s in at.success]
    assert any("Added!" in s and "1 lure queued" in s for s in successes), (
        f"expected the post-add confirmation popup, got: {successes}"
    )
    lure_lines = [m.value for m in at.markdown if "Test Chartreuse Shad" in m.value]
    assert any(l.startswith("🎣") for l in lure_lines), (
        "popup should list the lure that was just added"
    )
    button_keys = {b.key for b in at.button}
    assert "lure_added_popup_more_spot1_0" in button_keys
    assert "lure_added_popup_start_spot1_0" in button_keys


def test_start_session_from_popup_starts_the_session(monkeypatch):
    at = _start_session_build(monkeypatch)
    _add_item1(at)

    at.button(key="lure_added_popup_start_spot1_0").click().run()
    assert not at.exception, f"after Start Session from popup: {at.exception}"
    headers = [h.value for h in at.header]
    assert any("Session in progress" in h for h in headers), (
        f"expected the popup's own Start Session button to start the session, got headers: {headers}"
    )
    storage.append_trip.assert_called_once()


def test_add_more_lures_from_popup_closes_it_and_a_second_add_still_works(monkeypatch):
    at = _start_session_build(monkeypatch, inventory=[FAKE_ITEM, FAKE_ITEM_2])
    _add_item1(at)

    at.button(key="lure_added_popup_more_spot1_0").click().run()
    assert not at.exception, f"after Add more lures: {at.exception}"
    remaining_keys = {b.key for b in at.button}
    assert "lure_added_popup_more_spot1_0" not in remaining_keys, "popup should be closed"
    assert "lure_added_popup_start_spot1_0" not in remaining_keys, "popup should be closed"

    at.button(key="session_lure_picker_spot1_0_toggle_item2").click().run()
    assert not at.exception, f"after adding a second lure: {at.exception}"
    successes = [s.value for s in at.success]
    assert any("Added!" in s and "2 lures queued" in s for s in successes), (
        f"popup should reopen for the second add, listing both lures now, got: {successes}"
    )
    lure_lines = [m.value for m in at.markdown if m.value.startswith("🎣")]
    assert any("Test Chartreuse Shad" in l for l in lure_lines)
    assert any("Test Fluke" in l for l in lure_lines)
