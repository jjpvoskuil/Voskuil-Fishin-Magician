"""Tests for punch-list #94 on Spot Session: every predicted score shown
gets an "ℹ️ How this score was derived" st.popover right next to it -
the pre-session "Suggestions for right now" preview, the mid-session
"🔄 Conditions changed?" panel's live preview, and the "Session in
progress" caption once a session is actually running.

Uses AppTest, same conventions as tests/test_spot_session_page.py and
tests/test_spot_session_relocate.py (see those files' own docstrings for
the AppTest/st.dialog limitations this suite also respects).
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


def _install_mocks(monkeypatch):
    monkeypatch.setattr(appstate, "get_lake_spots", mock.MagicMock(return_value=[FAKE_SPOT]))
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


def _pending_build(monkeypatch):
    """Angler picked, still on the pre-Start-Session Conditions/preview
    screen - mirrors test_spot_session_page.py's own
    _start_session_build()."""
    _install_mocks(monkeypatch)
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.session_state["spot_session_target_id"] = "spot1"
    at.run()
    assert not at.exception, f"initial run raised: {at.exception}"
    at.selectbox(key="spot_session_landing_choice").select("Solo").run()
    assert not at.exception, f"after picking angler: {at.exception}"
    return at


def _started_session(monkeypatch):
    at = _pending_build(monkeypatch)
    at.button(key="session_lure_picker_spot1_0_toggle_item1").click().run()
    assert not at.exception, f"after adding item1: {at.exception}"
    at.button(key="lure_added_popup_start_spot1_0_1").click().run()
    assert not at.exception, f"after Start Session: {at.exception}"
    return at


def test_pre_session_preview_has_a_score_breakdown_popover(monkeypatch):
    at = _pending_build(monkeypatch)
    popover_keys = [p.key for p in at.get("popover")]
    assert "preview_score_breakdown_spot1" in popover_keys, (
        f"expected the 'Suggestions for right now' preview score to have a breakdown popover, got: {popover_keys}"
    )
    all_markdown = [m.value for m in at.markdown]
    assert any("**How this score was derived:**" in t and "- Base:" in t for t in all_markdown), (
        f"expected factor-breakdown content, got: {all_markdown}"
    )


def test_mid_session_panel_has_a_score_breakdown_popover(monkeypatch):
    at = _started_session(monkeypatch)
    popover_keys = [p.key for p in at.get("popover")]
    assert "midsession_spot1_solo_score_breakdown" in popover_keys, (
        f"expected the mid-session panel's live-preview score to have a breakdown popover, got: {popover_keys}"
    )


def test_session_in_progress_caption_has_a_score_breakdown_popover(monkeypatch):
    at = _started_session(monkeypatch)
    popover_keys = [p.key for p in at.get("popover")]
    assert "active_session_score_breakdown_spot1" in popover_keys, (
        f"expected the 'Session in progress' predicted score to have a breakdown popover right after Start "
        f"Session (predicted_score_breakdown is set in-memory then), got: {popover_keys}"
    )
    all_markdown = [m.value for m in at.markdown]
    assert any("**How this score was derived:**" in t and "- Base:" in t for t in all_markdown), (
        f"expected factor-breakdown content, got: {all_markdown}"
    )
