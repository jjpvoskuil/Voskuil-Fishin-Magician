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

Real-app follow-up bug, reported directly by the angler after this popup
first shipped: "after I add 2 lures, it doesn't toggle to let me add
more." The FIRST "Add more lures" click (going from 1 lure to picking a
2nd) worked; the SECOND one (after the 2nd lure landed, trying to go pick
a 3rd) silently did nothing. Root cause: _lure_added_dialog()'s own two
button keys were originally scoped only to (spot_id, session_build_seq) -
constant across every reopening of this popup within one session build,
so the 2nd (and every later) occurrence of this exact dialog reused the
exact same widget keys as the 1st. That reuse worked fine under THIS
harness (see the AppTest-vs-real-Streamlit gap noted above - this is
another instance of it, just in the opposite direction: AppTest's
simulation is apparently more forgiving of key reuse across separate
dialog open/close cycles than a real browser session is), but a real
deployed app's own dialog-widget bookkeeping got stuck the second time
the identical key was reused. Fixed by folding len(pending_lures) - which
increases by exactly 1 every single time this popup opens, since it only
ever opens right after an add - into both button keys, giving every
occurrence of the popup a genuinely fresh key.
test_add_more_lures_can_be_used_twice_in_a_row() below is the regression
guard for this specific report - even though the underlying real-app
symptom couldn't be reproduced under AppTest either (the ORIGINAL,
buggy key scheme also passed this exact same two-cycle sequence when
tried against this harness beforehand), asserting the concrete key
format directly (rather than only asserting behavior) at least catches a
future regression back to a key that fails to vary per popup occurrence.

Real-app follow-up #2, found by the angler watching a live screen-shared
reproduction of the sequence above: the popup itself WAS reopening
correctly for every add (the len(pending_lures) key fix above really did
fix the original report), but "Add more lures" was dumping the angler
back onto a page where the "Add from tackle box" expander had silently
collapsed shut again - so every add after the first needed an extra
manual click just to reopen it before the next lure could even be picked,
exactly backwards from the "keep adding lure after lure with no extra
navigation" the whole popup was built for in the first place. Root cause:
st.expander's `expanded=` argument only sets its INITIAL state on first
mount - a manual open/close toggle lives purely in the frontend and does
not survive a script rerun, so without something re-asserting
`expanded=True` on the next render, it snaps back to its `expanded=False`
default on every single st.rerun() (which every add and every popup
button here triggers). Fixed with a new session_state flag,
_tackle_box_expander_open_key(spot_id, seq), set True the moment a lure
actually lands in the pending list (covers the tackle-box picker, manual
entry, quick-add, and the trailer dialog's own "Add lure" confirm - all
of them funnel through _handle_lure_add_click()/_trailer_dialog(), where
the flag is set) and read back as this expander's own `expanded=`
argument, so it stays open for the rest of this session build once used,
no matter how many more st.rerun()s happen in between.
test_tackle_box_expander_stays_open_across_add_more_lures_cycles() below
is the regression guard for this specific report.

First draft of that fix also drove the sibling "Suggestions for right
now" expander from the same flag (it has the identical quick-add-
triggered collapse bug), but the angler explicitly asked for that one to
be left alone: "the suggestions for right now should stay collapsed.
That section should only open if I deliberately uncollapse it." Reverted
- "Suggestions for right now" is back to a bare `expanded=False` (punch-
list #33's own original intent) and does NOT track the tackle-box flag.
test_suggestions_expander_stays_collapsed_even_after_adding_lures() below
guards specifically against that regression.

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
    # Key now folds in len(pending_lures) (== 1 after this first add) so
    # that every popup occurrence gets a genuinely fresh key - see this
    # module's docstring for the real-app bug this fixes.
    assert "lure_added_popup_more_spot1_0_1" in button_keys
    assert "lure_added_popup_start_spot1_0_1" in button_keys


def test_start_session_from_popup_starts_the_session(monkeypatch):
    at = _start_session_build(monkeypatch)
    _add_item1(at)

    at.button(key="lure_added_popup_start_spot1_0_1").click().run()
    assert not at.exception, f"after Start Session from popup: {at.exception}"
    headers = [h.value for h in at.header]
    assert any("Session in progress" in h for h in headers), (
        f"expected the popup's own Start Session button to start the session, got headers: {headers}"
    )
    storage.append_trip.assert_called_once()


def test_add_more_lures_from_popup_closes_it_and_a_second_add_still_works(monkeypatch):
    at = _start_session_build(monkeypatch, inventory=[FAKE_ITEM, FAKE_ITEM_2])
    _add_item1(at)

    at.button(key="lure_added_popup_more_spot1_0_1").click().run()
    assert not at.exception, f"after Add more lures: {at.exception}"
    remaining_keys = {b.key for b in at.button}
    assert "lure_added_popup_more_spot1_0_1" not in remaining_keys, "popup should be closed"
    assert "lure_added_popup_start_spot1_0_1" not in remaining_keys, "popup should be closed"

    at.button(key="session_lure_picker_spot1_0_toggle_item2").click().run()
    assert not at.exception, f"after adding a second lure: {at.exception}"
    successes = [s.value for s in at.success]
    assert any("Added!" in s and "2 lures queued" in s for s in successes), (
        f"popup should reopen for the second add, listing both lures now, got: {successes}"
    )
    lure_lines = [m.value for m in at.markdown if m.value.startswith("🎣")]
    assert any("Test Chartreuse Shad" in l for l in lure_lines)
    assert any("Test Fluke" in l for l in lure_lines)


def test_add_more_lures_can_be_used_twice_in_a_row(monkeypatch):
    """Regression guard for the angler's real-app bug report: "after I add
    2 lures, it doesn't toggle to let me add more." Drives the exact
    sequence that broke live - add1, Add more lures, add2, Add more lures
    again, add3 - and asserts the SECOND "Add more lures" click uses a
    genuinely different widget key than the first (the fix folds
    len(pending_lures) into the key), so this popup can be reopened and
    dismissed repeatedly within one session build rather than only once.
    """
    at = _start_session_build(
        monkeypatch,
        inventory=[FAKE_ITEM, FAKE_ITEM_2, {**FAKE_ITEM, "item_id": "item3", "sku": "sku3", "description": "Test Third Lure"}],
    )
    _add_item1(at)

    first_more_key = "lure_added_popup_more_spot1_0_1"
    button_keys = {b.key for b in at.button}
    assert first_more_key in button_keys
    at.button(key=first_more_key).click().run()
    assert not at.exception, f"after first Add more lures: {at.exception}"

    at.button(key="session_lure_picker_spot1_0_toggle_item2").click().run()
    assert not at.exception, f"after adding a second lure: {at.exception}"

    second_more_key = "lure_added_popup_more_spot1_0_2"
    assert second_more_key != first_more_key, (
        "the second popup occurrence must use a different key than the "
        "first, or a real browser's dialog-widget bookkeeping gets stuck "
        "reusing the identical key (this was the actual reported bug)"
    )
    button_keys = {b.key for b in at.button}
    assert second_more_key in button_keys, (
        f"expected the second 'Add more lures' click to still work, got button keys: {button_keys}"
    )
    at.button(key=second_more_key).click().run()
    assert not at.exception, f"after second Add more lures: {at.exception}"

    at.button(key="session_lure_picker_spot1_0_toggle_item3").click().run()
    assert not at.exception, f"after adding a third lure: {at.exception}"
    successes = [s.value for s in at.success]
    assert any("Added!" in s and "3 lures queued" in s for s in successes), (
        f"popup should reopen a third time, listing all three lures, got: {successes}"
    )


def _tackle_box_expander(at):
    matches = [e for e in at.expander if e.label == "➕ Add from tackle box"]
    assert matches, "expected an 'Add from tackle box' expander on the page"
    return matches[0]


def test_tackle_box_expander_stays_open_across_add_more_lures_cycles(monkeypatch):
    """Regression guard for the angler's real-app follow-up #2, found while
    watching a live screen-shared reproduction of the add-3-lures sequence:
    the popup itself reopened correctly every time (the len(pending_lures)
    key fix works), but "Add more lures" kept dumping the angler back onto
    a page where the "Add from tackle box" expander had silently collapsed
    shut again, needing an extra manual click to reopen it before the next
    lure could even be picked. Before this fix, the expander's own
    `expanded=` argument was a bare `False` with nothing keeping it open
    across the st.rerun() every add/popup button triggers - so it snapped
    shut every single cycle. This test drives add1 -> Add more lures ->
    add2 -> Add more lures again and asserts the expander is still
    reporting expanded=True immediately after each "Add more lures" click,
    with no extra click of its own required to reopen it."""
    at = _start_session_build(monkeypatch, inventory=[FAKE_ITEM, FAKE_ITEM_2])

    # Starts collapsed on a fresh page load - unchanged from before this fix,
    # and matches punch-list #33's own explicit "don't take up screen space
    # on every page load" intent for the sibling suggestions expander.
    assert _tackle_box_expander(at).proto.expanded is False

    _add_item1(at)
    # Adding the very first lure (from inside this same expander) should
    # already flip it open for the rest of this session build.
    assert _tackle_box_expander(at).proto.expanded is True

    at.button(key="lure_added_popup_more_spot1_0_1").click().run()
    assert not at.exception, f"after first Add more lures: {at.exception}"
    assert _tackle_box_expander(at).proto.expanded is True, (
        "the tackle-box picker should still be open immediately after "
        "'Add more lures', with no extra click needed to reopen it - this "
        "is the exact behavior the angler reported as broken"
    )

    at.button(key="session_lure_picker_spot1_0_toggle_item2").click().run()
    assert not at.exception, f"after adding a second lure: {at.exception}"
    at.button(key="lure_added_popup_more_spot1_0_2").click().run()
    assert not at.exception, f"after second Add more lures: {at.exception}"
    assert _tackle_box_expander(at).proto.expanded is True, (
        "the tackle-box picker should stay open across every 'Add more "
        "lures' cycle in this session build, not just the first one"
    )


def _suggestions_expander(at):
    matches = [e for e in at.expander if e.label == "Suggestions for right now"]
    assert matches, "expected a 'Suggestions for right now' expander on the page"
    return matches[0]


def test_suggestions_expander_stays_collapsed_even_after_adding_lures(monkeypatch):
    """Regression guard for the angler's explicit correction after the
    tackle-box-expander fix shipped: "Better, but the suggestions for
    right now should stay collapsed. That section should only open if I
    deliberately uncollapse it." Unlike "Add from tackle box" (which
    SHOULD stay open once used - see the test above), this sibling
    expander must stay collapsed through the exact same add/Add-more-
    lures cycle, matching punch-list #33's original "don't take up screen
    space on every page load" intent with no exception for an in-progress
    session build."""
    at = _start_session_build(monkeypatch, inventory=[FAKE_ITEM, FAKE_ITEM_2])
    assert _suggestions_expander(at).proto.expanded is False

    _add_item1(at)
    assert _suggestions_expander(at).proto.expanded is False, (
        "adding a lure should not auto-expand 'Suggestions for right now'"
    )

    at.button(key="lure_added_popup_more_spot1_0_1").click().run()
    assert not at.exception, f"after Add more lures: {at.exception}"
    assert _suggestions_expander(at).proto.expanded is False, (
        "'Suggestions for right now' must stay collapsed across an "
        "'Add more lures' cycle too - the angler asked for this one to "
        "only ever open when they deliberately click it themselves"
    )
