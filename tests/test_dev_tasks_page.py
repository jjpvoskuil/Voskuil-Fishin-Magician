"""Tests for pages/7_Development.py's action-result reporting - punch-list
#85. Uses Streamlit's AppTest (streamlit.testing.v1), same as
test_trip_history_page.py, since the bug is specifically about what the
rendered page shows (or fails to show), not about core/dev_tasks.py's own
read/write logic (already covered by test_dev_tasks.py).

Root cause (angler report): added a punch-list item twice on the live
Development page, saw nothing that looked like an error either time, then
a "Reboot app" showed neither had actually landed on GitHub. Two distinct
bugs, both fixed here:

1. "Add an item" called st.success()/st.warning()/st.info() immediately
   before st.rerun() in the same script run - Streamlit wipes anything
   shown that way the instant a real rerun starts, so an angler on the
   real deployed app never actually saw it (the same class of bug already
   fixed elsewhere via punch-list #71). Fixed with the same
   persisted-banner pattern (stash in session_state, render on the next
   pass) already used on Tackle Box/Spot Session.
2. The Done-toggle/Edit-save/Delete handlers threw away _push()'s real
   (ok, msg) result entirely and always showed an unconditional
   st.toast("...saved.") - so even a genuine GitHub push failure looked
   identical to success. Fixed so every handler now reports what _push()
   actually returned.

Every real file write (core.dev_tasks.append_task, core.appstate.
get_dev_tasks) and every GitHub call (core.appstate.github_token,
core.storage.commit_and_push_data) is mocked in every test below - this
suite must never touch the real data/dev_tasks.csv on disk or attempt a
real network call.

Note on AppTest and st.rerun(): AppTest.run() runs a script to a fully
settled state, silently following any st.rerun() the script issues itself
until nothing is left queued - so the persisted-banner mechanism can't be
told apart from the old immediate-message-then-rerun bug by "which run it
shows up in" (both show up in the same at.run() call from this harness's
point of view; the old bug was only ever visible against a real running
Streamlit server, which is exactly why it was fixed by inspection/manual
verification rather than a test, both here and originally for #71). What
these tests actually guard against is the SECOND, definitely-automatable
bug: that the banner's content honestly reflects _push()'s real (ok, msg)
result instead of a hardcoded/blind success.
"""
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from core import appstate, dev_tasks, storage

PAGE_PATH = str(Path(__file__).resolve().parent.parent / "pages" / "7_Development.py")


class _FakeTask:
    def __init__(self, task_no=85, description="Test item"):
        self.task_no = task_no
        self.description = description


def _run_add_flow(monkeypatch, github_token_value, push_return):
    """Drives the "Add an item" form exactly the way the live page's own
    st.form does, with every file-touching/network-touching dependency
    mocked, and returns the AppTest instance settled at its post-submit
    state."""
    monkeypatch.setattr(dev_tasks, "append_task", lambda description, page: _FakeTask())
    monkeypatch.setattr(appstate, "get_dev_tasks", mock.MagicMock(return_value=[]))
    monkeypatch.setattr(appstate, "github_token", lambda: github_token_value)
    monkeypatch.setattr(storage, "commit_and_push_data", mock.MagicMock(return_value=push_return))

    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"initial run raised: {at.exception}"

    # get_dev_tasks() is mocked to return [] above, so the only text_area on
    # the page at this point is the "Add an item" form's own description
    # field - address it by position rather than guessing its widget key.
    at.text_area[0].set_value("Some new punch-list item")
    add_buttons = [b for b in at.button if b.label == "Add to punch list"]
    assert add_buttons, "could not find the 'Add to punch list' submit button"
    add_buttons[0].click().run()
    assert not at.exception, f"after submitting Add: {at.exception}"
    return at


def test_add_item_push_failure_is_reported_as_a_warning_not_success(monkeypatch):
    """The actual live bug: a real GitHub push failure used to be
    indistinguishable from success, since the Done-toggle/Edit/Delete
    handlers discarded _push()'s (ok, msg) result outright and the Add
    handler's own message was never actually visible on a real server
    (see module docstring). Regression guard here: with a token
    configured and commit_and_push_data() mocked to fail, the settled page
    must show a warning containing the real failure text, and must NOT
    show a plain "#N added." success for this same action."""
    push_error = "Saved locally, but push failed after 3 attempts: fatal: could not resolve host"
    at = _run_add_flow(monkeypatch, github_token_value="fake-token", push_return=(False, push_error))

    warnings = [w.value for w in at.warning]
    assert any(push_error in w for w in warnings), (
        f"expected a warning naming the real push failure, got: {warnings}"
    )
    assert not any(s.value.startswith("#85 added.") for s in at.success), (
        "a failed push must never render as a plain success message"
    )


def test_add_item_push_success_is_reported_honestly(monkeypatch):
    """Mirror of the failure case: a genuine successful push must show up
    as a real success banner naming the actual push result - not a
    generic/blind success shown regardless of what _push() returned."""
    at = _run_add_flow(
        monkeypatch, github_token_value="fake-token",
        push_return=(True, "Saved and pushed to GitHub."),
    )
    successes = [s.value for s in at.success]
    assert any(s.startswith("#85 added.") and "pushed to GitHub" in s for s in successes), (
        f"expected a success banner confirming the real push result, got: {successes}"
    )


def test_add_item_with_no_token_configured_is_flagged_as_local_only(monkeypatch):
    """No GITHUB_TOKEN configured must be reported as a warning (not a
    plain success) so an angler adding an item on a mis-configured deploy
    knows it won't survive a restart or reboot - the exact scenario that
    triggered the original bug report (twice added, nothing survived a
    reboot, and no error was ever shown explaining why)."""
    at = _run_add_flow(monkeypatch, github_token_value="", push_return=(True, None))
    warnings = [w.value for w in at.warning]
    assert any("no GITHUB_TOKEN configured" in w and "won't survive" in w for w in warnings), (
        f"expected a local-only warning, got: {warnings}"
    )
    assert not any(s.value.startswith("#85 added.") for s in at.success), (
        "a local-only (unpushed) add must never render as a plain success message"
    )


def test_mark_done_reports_a_real_push_failure_instead_of_a_blind_toast(monkeypatch):
    """The Done-toggle handler used to call _push() and throw away its
    result entirely, always showing st.toast("... marked Done.") - so a
    genuine push failure while marking an item Done looked identical to
    success, with no way for an angler to ever notice their change didn't
    survive a restart. Regression guard: with the push mocked to fail,
    the settled page must show a warning naming the real failure."""
    # get_dev_tasks() must reflect mark_done()'s effect on the next call the
    # same way the real CSV-backed version would (row.status flips to
    # Done) - otherwise the checkbox's new "checked" state never matches
    # what the row itself says, and the page's own `if new_done != is_done`
    # re-triggers the handler (and its st.rerun()) forever.
    row = {
        "task_no": "7", "description": "Some existing item", "page": "Tackle Box",
        "status": dev_tasks.STATUS_OPEN, "completed_at": "",
    }
    monkeypatch.setattr(appstate, "get_dev_tasks", mock.MagicMock(side_effect=lambda: [row]))
    monkeypatch.setattr(appstate, "github_token", lambda: "fake-token")
    push_error = "Saved locally, but push failed after 3 attempts: fatal: could not resolve host"
    monkeypatch.setattr(storage, "commit_and_push_data", mock.MagicMock(return_value=(False, push_error)))

    def _fake_mark_done(task_no):
        row["status"] = dev_tasks.STATUS_DONE
        return True

    monkeypatch.setattr(dev_tasks, "mark_done", _fake_mark_done)

    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.run()
    assert not at.exception, f"initial run raised: {at.exception}"

    done_checkboxes = [cb for cb in at.checkbox if cb.key == "done_7"]
    assert done_checkboxes, "could not find item #7's Done checkbox"
    done_checkboxes[0].check().run()
    assert not at.exception, f"after checking Done: {at.exception}"

    warnings = [w.value for w in at.warning]
    assert any(push_error in w for w in warnings), (
        f"expected a warning naming the real push failure after marking Done, got: {warnings}"
    )
