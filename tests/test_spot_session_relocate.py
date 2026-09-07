"""Tests for punch-list #93: mid-session relocation on Spot Session.

The angler's own verbatim ask: "during a session I can now change
conditions mid session. Lets modify this so that I can change both the
conditions and location without ending the session or having to re enter
any lures that I am using. All fishing activity will still be kept under
the same session but with potential new location(s) and conditions. Any
fish caught prior to a change should be associated with the original
location and conditions and any new fish caught will be associated with
the cooresponding new locaation and/or conditions."

This extends the existing "🔄 Conditions changed?" panel (punch-list #49)
with a location picker, and replaces its old "just overwrite
active['base_conditions'] in place" save behavior with
_relocate_active_session(): every currently-active (non-retired) lure's
row is end-stamped/retired exactly like "🔄 Change" already does, and a
fresh continuation row is appended for that same lure under the new
spot/conditions - so the angler never has to re-pick a lure, the session
never ends (same session_id throughout), and fish logged before the
change stay on the closed-out row while anything landed after lands on
the new one.

Uses AppTest (streamlit.testing.v1), same convention as
test_spot_session_page.py - see that file's own docstring for the
AppTest/st.dialog limitations this suite also respects (nothing here
opens _fish_entry_dialog via a button click; a fish caught before a
relocation is instead simulated by writing directly into session_state,
mirroring exactly what _record_fish() itself would have produced).
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
FAKE_SPOT_2 = {
    "spot_id": "spot2", "name": "Second Cove", "lat": 37.4, "lon": -86.3,
    "location_type": "Main-lake point", "notes": "",
}
FAKE_ITEM = {
    "item_id": "item1", "brand": "Strike King", "description": "Test Chartreuse Shad",
    "category": "medium_diving_crankbait", "quantity": 3, "sku": "sku1",
    "image_url": "", "image_filename": "", "price": 5.0, "package_qty": 1,
}


def _install_mocks(monkeypatch, spots=None):
    monkeypatch.setattr(appstate, "get_lake_spots", mock.MagicMock(return_value=spots or [FAKE_SPOT, FAKE_SPOT_2]))
    monkeypatch.setattr(appstate, "get_inventory", mock.MagicMock(return_value=[FAKE_ITEM]))
    monkeypatch.setattr(appstate, "get_weather_bundle", mock.MagicMock(return_value=None))
    monkeypatch.setattr(appstate, "get_anglers", mock.MagicMock(return_value=["Solo"]))
    monkeypatch.setattr(appstate, "get_trip_history", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "get_calibrated_weights", mock.MagicMock(return_value={}))
    monkeypatch.setattr(appstate, "get_location_adjustments", mock.MagicMock(return_value={}))
    monkeypatch.setattr(appstate, "github_token", mock.MagicMock(return_value=""))
    monkeypatch.setattr(storage, "append_trip", mock.MagicMock())
    monkeypatch.setattr(storage, "update_trip", mock.MagicMock())
    monkeypatch.setattr(storage, "commit_and_push_data", mock.MagicMock(return_value=(True, "ok")))
    monkeypatch.setattr(storage, "push_pending_data", mock.MagicMock(return_value=(True, "ok")))


def _started_session(monkeypatch):
    """Gets to an in-progress session at FAKE_SPOT (spot1) for angler
    "Solo", with one lure (item1) already active - mirrors
    test_spot_session_page.py's own _start_session_build()/_add_item1(),
    just also starting the session itself so "Session in progress" is on
    screen and the mid-session relocation panel is reachable."""
    _install_mocks(monkeypatch)
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.session_state["spot_session_target_id"] = "spot1"
    at.run()
    assert not at.exception, f"initial run raised: {at.exception}"
    at.selectbox(key="spot_session_landing_choice").select("Solo").run()
    assert not at.exception, f"after picking angler: {at.exception}"
    at.button(key="session_lure_picker_spot1_0_toggle_item1").click().run()
    assert not at.exception, f"after adding item1: {at.exception}"
    at.button(key="lure_added_popup_start_spot1_0_1").click().run()
    assert not at.exception, f"after Start Session: {at.exception}"
    headers = [h.value for h in at.header]
    assert any("Session in progress" in h for h in headers), (
        f"expected the session to already be in progress, got headers: {headers}"
    )
    return at


def _active(at):
    return at.session_state["active_session_spot1_solo"]


def test_relocate_panel_defaults_to_current_location(monkeypatch):
    """The location picker inside the mid-session panel should default to
    wherever the session is CURRENTLY at (spot1, "Test Cove") - not just
    whatever spot the page happens to be showing, though those are the
    same thing before any relocation ever happens."""
    at = _started_session(monkeypatch)
    loc_select = at.selectbox(key="midsession_spot1_solo_spot_idx")
    assert loc_select.options[loc_select.value] == "Test Cove"


def test_relocate_moves_session_without_ending_it_or_re_adding_lure(monkeypatch):
    """The core ask: change location AND conditions mid-session, without
    ending the session or re-picking the lure already in use."""
    at = _started_session(monkeypatch)
    original_session_id = _active(at)["session_id"]

    at.selectbox(key="midsession_spot1_solo_spot_idx").select("Second Cove")
    at.button(key="midsession_spot1_solo_apply").click().run()
    assert not at.exception, f"after Update conditions & location: {at.exception}"

    headers = [h.value for h in at.header]
    assert any("Session in progress" in h for h in headers), (
        "the session must still be in progress - relocating must never end it"
    )
    toasts = [t.value for t in at.toast]
    assert any("Moved to Second Cove" in t for t in toasts), (
        f"expected a 'moved' confirmation toast, got: {toasts}"
    )

    active = _active(at)
    assert active["spot_id"] == "spot2"
    assert active["spot_name"] == "Second Cove"
    assert active["session_id"] == original_session_id, "relocating must never change the session_id"

    lures = active["lures"]
    assert len(lures) == 2, f"expected the original lure's row closed + a fresh continuation row, got {lures}"
    old_lure, new_lure = lures[0], lures[1]
    assert old_lure["retired"] is True
    assert old_lure["entry_kwargs"]["spot_id"] == "spot1"
    assert old_lure["entry_kwargs"]["conditions"]["lure_end_time"] is not None
    assert new_lure["retired"] is False
    assert new_lure["label"] == old_lure["label"]
    assert "Test Chartreuse Shad" in new_lure["label"]
    assert new_lure["item_id"] == old_lure["item_id"]
    assert new_lure["entry_kwargs"]["spot_id"] == "spot2"
    assert new_lure["entry_kwargs"]["session_id"] == original_session_id
    assert new_lure["fish"] == []

    # No re-pick needed - the (new) active lure is directly tappable.
    button_keys = {b.key for b in at.button}
    assert "open_fish_dialog_spot1_1" in button_keys, (
        "the carried-forward lure should be immediately usable without "
        "re-adding it from the tackle box"
    )
    assert storage.append_trip.call_count == 2, (
        "one append for the original Start Session lure, one for the new "
        "continuation row - never a re-add through the normal add-lure path"
    )
    assert storage.update_trip.call_count == 1, "the old row should be closed out via update_trip, exactly once"


def test_fish_caught_before_relocation_stays_on_the_old_row(monkeypatch):
    """Punch-list #93's explicit requirement: "Any fish caught prior to a
    change should be associated with the original location and
    conditions." Simulates a fish already logged on the active lure
    (writing directly into session_state, mirroring exactly what
    _record_fish() itself produces - see this module's docstring for why
    the real fish-logging dialog can't be driven through AppTest), then
    relocates, and checks that fish stayed on the closed-out row while the
    new row starts empty."""
    at = _started_session(monkeypatch)
    active = _active(at)
    fish_record = {"species": "Largemouth", "weight_lb": 2.5, "count": 1}
    active["lures"][0]["fish"].append(fish_record)
    entry_kwargs = dict(active["lures"][0]["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["fish"] = active["lures"][0]["fish"]
    entry_kwargs["conditions"] = conditions
    entry_kwargs["fish_caught"] = 1
    active["lures"][0]["entry_kwargs"] = entry_kwargs
    at.session_state["active_session_spot1_solo"] = active
    at.run()
    assert not at.exception, f"after simulating a logged fish: {at.exception}"

    at.selectbox(key="midsession_spot1_solo_spot_idx").select("Second Cove")
    at.button(key="midsession_spot1_solo_apply").click().run()
    assert not at.exception, f"after Update conditions & location: {at.exception}"

    lures = _active(at)["lures"]
    assert len(lures) == 2
    old_lure, new_lure = lures[0], lures[1]
    assert old_lure["fish"] == [fish_record], "the fish caught before relocating must stay on the old row"
    assert old_lure["entry_kwargs"]["spot_id"] == "spot1"
    assert old_lure["entry_kwargs"]["fish_caught"] == 1
    assert new_lure["fish"] == [], "the new row must start with no fish carried over"
    assert new_lure["entry_kwargs"]["spot_id"] == "spot2"
    assert new_lure["entry_kwargs"]["fish_caught"] == 0


def test_relocating_without_changing_spot_still_splits_the_lure(monkeypatch):
    """A plain conditions-only update (angler leaves the location picker on
    the current spot) must still close out the old row and open a fresh
    one - the same "fish before vs. after stay attributed correctly" rule
    applies to a conditions-only change too, not just an actual move."""
    at = _started_session(monkeypatch)
    at.button(key="midsession_spot1_solo_apply").click().run()
    assert not at.exception, f"after Update conditions & location: {at.exception}"

    toasts = [t.value for t in at.toast]
    assert any("Conditions updated" in t for t in toasts), f"expected a plain update toast, got: {toasts}"
    active = _active(at)
    assert active["spot_id"] == "spot1"
    lures = active["lures"]
    assert len(lures) == 2
    assert lures[0]["retired"] is True
    assert lures[1]["retired"] is False


def test_retired_lures_expander_shows_spot_per_lure(monkeypatch):
    """Once a session has touched more than one location, the "Retired
    lures" expander should say which spot each closed-out row was actually
    fished at, since they can now legitimately differ."""
    at = _started_session(monkeypatch)
    at.selectbox(key="midsession_spot1_solo_spot_idx").select("Second Cove")
    at.button(key="midsession_spot1_solo_apply").click().run()
    assert not at.exception, f"after Update conditions & location: {at.exception}"

    captions = [c.value for c in at.caption]
    assert any("Test Cove" in c and "Test Chartreuse Shad" in c for c in captions), (
        f"expected the retired (old) row's caption to name its own spot, got: {captions}"
    )
    assert any("currently at 📍 Second Cove" in c for c in captions), (
        f"expected the session header caption to show the NEW current location, got: {captions}"
    )
