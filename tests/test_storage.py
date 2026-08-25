"""Tests for core/storage.py, focused on commit_and_push()'s punch-list #26
retry hardening (a rejected/non-fast-forward push should fetch+rebase+retry
instead of silently failing when two devices save at nearly the same time).

Most cases here use a real local bare git repo (not GitHub) so the actual
git plumbing (fetch/rebase/push) is exercised end to end, not just mocked -
this is the one part of this change where "does a real rebase actually
resolve a real concurrent push" matters more than unit-testing branch logic
in isolation. A few edge cases (auth failure, a genuine rebase conflict,
retries exhausted) use a monkeypatched subprocess.run instead, since forcing
those specific situations through real git is either not meaningfully
different from mocking or (for a real conflict) flaky to engineer reliably.
"""
import subprocess
from pathlib import Path

import pytest

from core import storage


def _run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"{args} failed: {result.stderr}"
    return result


def _init_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", "main"], cwd=path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=path)
    _run(["git", "config", "user.name", "Test"], cwd=path)


@pytest.fixture
def bare_and_seed(tmp_path):
    """A bare 'remote' repo plus one already-pushed commit (a small
    trip_log-like CSV with a header and one row), so both clones below start
    from a real shared history rather than an empty repo."""
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _run(["git", "init", "--bare", "-b", "main"], cwd=bare)

    seed = tmp_path / "seed"
    _init_repo(seed)
    data_dir = seed / "data"
    data_dir.mkdir()
    (data_dir / "trip_log.csv").write_text("trip_id,notes\n")
    # Mirrors the real repo's root .gitattributes (data/*.csv merge=union) -
    # it has to be present from this shared common ancestor, not added
    # later, since git reads it from the commit(s) actually being merged.
    (seed / ".gitattributes").write_text("data/*.csv merge=union\n")
    _run(["git", "add", "data/trip_log.csv", ".gitattributes"], cwd=seed)
    _run(["git", "commit", "-m", "seed"], cwd=seed)
    _run(["git", "push", str(bare), "HEAD:main"], cwd=seed)
    return bare


def _clone(bare: Path, dest: Path):
    _run(["git", "clone", str(bare), str(dest)], cwd=dest.parent)
    _run(["git", "config", "user.email", "test@example.com"], cwd=dest)
    _run(["git", "config", "user.name", "Test"], cwd=dest)
    return dest


def test_commit_and_push_no_token():
    ok, msg = storage.commit_and_push(["data/x.csv"], github_token="", repo_slug="a/b", commit_message="m")
    assert ok is False
    assert "No GITHUB_TOKEN" in msg


def test_commit_and_push_no_changes(tmp_path, bare_and_seed):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="no-op", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True
    assert "No changes" in msg


def test_commit_and_push_simple_success(tmp_path, bare_and_seed):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n")
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="add trip", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True
    assert "Saved and pushed" in msg


def test_session_id_round_trips_through_append_and_read(tmp_path, monkeypatch):
    """Punch-list #55: session_id is a real column now (see FIELDNAMES),
    stamped by pages/6_Spot_Session.py's Start Session handler and read back
    by Trip History to group a session's lures into one record. Confirms
    the field survives append_trip -> read_all_trips unchanged, and that a
    row saved before this field existed (no session_id key at all) doesn't
    break reading/rewriting the file."""
    monkeypatch.setattr(storage, "TRIP_LOG_PATH", tmp_path / "trip_log.csv")

    entry = storage.TripEntry(
        trip_date="2026-08-24", segment="Morning", spot_id="s1", spot_name="Test Spot",
        structure_type="Main-lake point", water_clarity="Green stained", lure_used="Fluke",
        color_used="", technique_used="", fish_caught=0, biggest_fish_lb=None,
        predicted_score=5.0, conditions={}, session_id="abc12345",
    )
    storage.append_trip(entry)

    rows = storage.read_all_trips()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "abc12345"
    assert rows[0]["trip_id"] == entry.trip_id


def test_update_trip_preserves_legacy_rows_missing_session_id_column(tmp_path, monkeypatch):
    """A row written before session_id existed has no such key in its dict
    (its file's header predates the column) - update_trip rewriting the
    whole file (with the new header) shouldn't choke on that row missing a
    key, and should leave it with a blank session_id rather than erroring."""
    log_path = tmp_path / "trip_log.csv"
    monkeypatch.setattr(storage, "TRIP_LOG_PATH", log_path)
    # Simulate a pre-#55 file: header/row with no session_id column at all.
    old_fieldnames = [f for f in storage.FIELDNAMES if f != "session_id"]
    import csv
    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fieldnames)
        writer.writeheader()
        writer.writerow({
            "trip_id": "legacy01", "logged_at": "2026-01-01T00:00:00", "trip_date": "2026-01-01",
            "segment": "Dawn", "spot_id": "s1", "spot_name": "Test Spot",
            "structure_type": "Flat", "water_clarity": "Clear", "lure_used": "Worm",
            "color_used": "", "technique_used": "", "fish_caught": "0", "biggest_fish_lb": "",
            "predicted_score": "4.0", "conditions_json": "{}", "notes": "",
        })

    new_entry = storage.TripEntry(
        trip_date="2026-08-24", segment="Morning", spot_id="s2", spot_name="Another Spot",
        structure_type="Flat", water_clarity="Clear", lure_used="Jig", color_used="",
        technique_used="", fish_caught=1, biggest_fish_lb=2.5, predicted_score=6.0,
        conditions={}, session_id="new123",
    )
    storage.append_trip(new_entry)
    # update_trip on the NEW row rewrites the whole file (including the old
    # legacy row, which is missing session_id entirely) - shouldn't raise.
    new_entry.notes = "edited"
    assert storage.update_trip(new_entry) is True

    rows = storage.read_all_trips()
    by_id = {r["trip_id"]: r for r in rows}
    assert by_id["legacy01"]["session_id"] == ""
    assert by_id[new_entry.trip_id]["session_id"] == "new123"
    assert by_id[new_entry.trip_id]["notes"] == "edited"


def test_commit_and_push_retries_and_succeeds_on_real_concurrent_push(tmp_path, bare_and_seed):
    """The real punch-list #26 scenario: two anglers' devices (repoA, repoB)
    both cloned the same starting point and both append a trip row before
    either has pushed. repoA pushes first (trivially succeeds, advancing the
    shared 'remote'); repoB's first push attempt should then be rejected as
    non-fast-forward, and commit_and_push should recover on its own (fetch +
    rebase + retry) rather than reporting failure."""
    repo_a = _clone(bare_and_seed, tmp_path / "repoA")
    repo_b = _clone(bare_and_seed, tmp_path / "repoB")

    (repo_a / "data" / "trip_log.csv").write_text("trip_id,notes\n1,from A\n")
    ok_a, msg_a = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="A's trip", repo_root=repo_a, remote_url=str(bare_and_seed),
    )
    assert ok_a is True and "Saved and pushed" in msg_a

    # repoB never fetched A's push - its own push below will be rejected at
    # least once before the retry logic catches it up and retries.
    (repo_b / "data" / "trip_log.csv").write_text("trip_id,notes\n2,from B\n")
    ok_b, msg_b = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="B's trip", repo_root=repo_b, remote_url=str(bare_and_seed),
        max_push_retries=3,
    )
    assert ok_b is True, msg_b
    assert "Saved and pushed" in msg_b

    # The shared remote must now carry BOTH trips - the whole point of the
    # retry is that B's save isn't silently dropped by A's earlier push.
    show = _run(["git", "show", "main:data/trip_log.csv"], cwd=bare_and_seed)
    assert "from A" in show.stdout
    assert "from B" in show.stdout

    # And repoB's own working tree (now rebased onto A's commit) reflects
    # both rows too, not just its own.
    local_content = (repo_b / "data" / "trip_log.csv").read_text()
    assert "from A" in local_content
    assert "from B" in local_content


def test_commit_and_push_non_retryable_failure_does_not_retry(tmp_path, bare_and_seed, monkeypatch):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n")

    calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            calls.append(args)
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="fatal: Authentication failed")
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="add trip", repo_root=repo, remote_url=str(bare_and_seed),
        max_push_retries=3,
    )
    assert ok is False
    assert "Authentication failed" in msg
    assert len(calls) == 1  # never retried a non-rejection failure


def test_commit_and_push_gives_up_after_max_retries(tmp_path, bare_and_seed, monkeypatch):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n")

    push_calls = []
    fetch_calls = []
    rebase_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            push_calls.append(args)
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="! [rejected] main -> main (non-fast-forward)")
        if args[:2] == ["git", "fetch"]:
            fetch_calls.append(args)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        if args[:2] == ["git", "rebase"] and args[2] != "--abort":
            rebase_calls.append(args)
            return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="add trip", repo_root=repo, remote_url=str(bare_and_seed),
        max_push_retries=3, retry_backoff_seconds=0,
    )
    assert ok is False
    assert "after 3 attempts" in msg
    assert len(push_calls) == 3
    assert len(fetch_calls) == 2  # fetched before each retry, not after the final failed attempt


def test_commit_and_push_aborts_on_real_rebase_conflict(tmp_path, bare_and_seed):
    """A genuine conflict should abort the rebase and report a clear
    message, not loop or crash. Uses a plain .txt file (not one of the
    data/*.csv files the repo's .gitattributes routes through the
    union-merge driver, see that file's own comment) - both sides edit the
    exact same line, which is a real, unavoidable conflict once rebased."""
    repo_a = _clone(bare_and_seed, tmp_path / "repoA")
    repo_b = _clone(bare_and_seed, tmp_path / "repoB")

    (repo_a / "data" / "notes.txt").write_text("A's version\n")
    ok_a, _ = storage.commit_and_push(
        ["data/notes.txt"], github_token="x", repo_slug="unused/unused",
        commit_message="A edits notes", repo_root=repo_a, remote_url=str(bare_and_seed),
    )
    assert ok_a is True

    # repoB edits the SAME line differently, based on the original (pre-A)
    # content - a real conflict once rebased onto A, since data/notes.txt
    # isn't covered by the union-merge .gitattributes rule.
    (repo_b / "data" / "notes.txt").write_text("B's version\n")
    ok_b, msg_b = storage.commit_and_push(
        ["data/notes.txt"], github_token="x", repo_slug="unused/unused",
        commit_message="B edits notes", repo_root=repo_b, remote_url=str(bare_and_seed),
        max_push_retries=3,
    )
    assert ok_b is False
    assert "conflicted" in msg_b

    # The rebase must have been aborted cleanly - repo left in a usable
    # state, not stuck mid-rebase.
    status = _run(["git", "status"], cwd=repo_b)
    assert "rebase in progress" not in status.stdout.lower()


# --- Punch-list #52: data/main branch split ----------------------------------
# commit_and_push_data() and sync_data_from_data_branch() together are what
# keep routine angler saves from triggering a Streamlit Cloud redeploy (which
# used to wipe every connected user's session_state at once - see
# SESSION_NOTES.md punch-list #51/#52 and core/storage.py's module docstring
# for the full investigation). These tests use the same real-bare-repo
# pattern as the rest of this file, specifically so a genuine "push lands on
# the right branch" / "sync pulls from the right branch without moving HEAD"
# claim is verified against real git plumbing, not just mocked calls.

def test_commit_and_push_data_lands_on_data_branch_not_main(tmp_path, bare_and_seed):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,angler save\n")
    ok, msg = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="angler save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg
    assert "Saved and pushed" in msg

    on_data = _run(["git", "show", f"{storage.DATA_BRANCH}:data/trip_log.csv"], cwd=bare_and_seed)
    assert "angler save" in on_data.stdout

    on_main = _run(["git", "show", "main:data/trip_log.csv"], cwd=bare_and_seed)
    assert "angler save" not in on_main.stdout, (
        "a data save must never land on main - main is the branch Streamlit "
        "Cloud watches for redeploys"
    )


def test_sync_data_from_data_branch_no_data_branch_yet_is_a_soft_noop(tmp_path, bare_and_seed):
    """Before the one-time cutover (or on a brand new repo), the data branch
    doesn't exist at all - the sync must not crash or touch anything."""
    repo = _clone(bare_and_seed, tmp_path / "app_repo")
    before = (repo / "data" / "trip_log.csv").read_text()
    ok, msg = storage.sync_data_from_data_branch(
        github_token="x", repo_slug="unused/unused", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is False
    assert "may not exist yet" in msg
    assert (repo / "data" / "trip_log.csv").read_text() == before


def test_sync_data_from_data_branch_pulls_latest_without_switching_branch(tmp_path, bare_and_seed):
    """The core of punch-list #52's fix for a fresh boot: a repo checked out
    on main, with stale data/, should pick up the data branch's latest
    content - without its HEAD moving off main."""
    # Cut the data branch over from main's current state.
    cutover = _clone(bare_and_seed, tmp_path / "cutover")
    _run(["git", "checkout", "-b", storage.DATA_BRANCH], cwd=cutover)
    _run(["git", "push", str(bare_and_seed), f"HEAD:{storage.DATA_BRANCH}"], cwd=cutover)

    # A save lands on the data branch, same as a real angler action would.
    saver = _clone(bare_and_seed, tmp_path / "saver")
    (saver / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,new catch\n")
    ok, _ = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="new catch", repo_root=saver, remote_url=str(bare_and_seed),
    )
    assert ok is True

    # A freshly booted "app" repo, still on main with main's now-stale data/,
    # syncs and should pick up the new catch, while staying on main.
    app_repo = _clone(bare_and_seed, tmp_path / "app_repo")
    assert "new catch" not in (app_repo / "data" / "trip_log.csv").read_text()
    ok, msg = storage.sync_data_from_data_branch(
        github_token="x", repo_slug="unused/unused", repo_root=app_repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg
    assert "new catch" in (app_repo / "data" / "trip_log.csv").read_text()
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=app_repo).stdout.strip()
    assert branch == "main"

    # main itself must remain untouched by the sync (it only touches the
    # working tree/index, never commits or pushes anything).
    on_main = _run(["git", "show", "main:data/trip_log.csv"], cwd=bare_and_seed)
    assert "new catch" not in on_main.stdout


def test_sync_data_from_data_branch_no_token(tmp_path, bare_and_seed):
    repo = _clone(bare_and_seed, tmp_path / "app_repo")
    ok, msg = storage.sync_data_from_data_branch(github_token="", repo_slug="a/b", repo_root=repo)
    assert ok is False
    assert "No GITHUB_TOKEN" in msg


# --- Punch-list #58: transient-network retry + push_pending() ---------------
# The session-loss investigation: a save that fails to push for a plain
# transient reason (dropped connection, DNS hiccup, a GitHub 5xx - all
# expected sometimes when this app is used standing at the lake on spotty
# cell signal) used to behave exactly like a hard failure - one attempt, then
# give up, leaving the commit sitting locally-only until some LATER save
# happens to succeed and carry it along. These tests cover the two-part fix:
# commit_and_push() now retries a transient failure the same way it already
# retried a rejected push, and push_pending() gives autosave a way to retry
# an already-committed-but-unpushed save on its own, without needing a new
# change to trigger it.

def test_commit_and_push_retries_transient_network_error_then_succeeds(tmp_path, bare_and_seed, monkeypatch):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n")

    push_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            push_calls.append(args)
            if len(push_calls) < 3:
                return subprocess.CompletedProcess(
                    args, returncode=128, stdout="",
                    stderr="fatal: unable to access 'https://github.com/...': Could not resolve host: github.com",
                )
            return real_run(args, **kwargs)
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="add trip", repo_root=repo, remote_url=str(bare_and_seed),
        max_push_retries=5, retry_backoff_seconds=0,
    )
    assert ok is True, msg
    assert "Saved and pushed" in msg
    assert len(push_calls) == 3  # two transient failures, then a real (unpatched) push succeeds


def test_commit_and_push_gives_up_after_max_retries_on_persistent_transient_error(tmp_path, bare_and_seed, monkeypatch):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n")

    push_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            push_calls.append(args)
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="fatal: Connection timed out")
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="add trip", repo_root=repo, remote_url=str(bare_and_seed),
        max_push_retries=3, retry_backoff_seconds=0,
    )
    assert ok is False
    assert "after 3 attempts" in msg
    assert len(push_calls) == 3


def test_push_pending_retries_and_eventually_pushes_an_already_committed_change(tmp_path, bare_and_seed):
    """The core punch-list #58 scenario: a prior commit_and_push_data() call
    committed locally but its push kept failing (simulated here by just
    never calling push at all the first time - i.e. the commit sits
    unpushed) - a LATER, independent push_pending_data() call (autosave's
    heartbeat/manual retry, with no new file changes at all) should still
    get that commit onto the remote."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,caught while offline\n")
    subprocess.run(["git", "add", "data/trip_log.csv"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "committed locally, never pushed"], cwd=repo, check=True)

    # Nothing new to add/commit - push_pending must still find and push the
    # already-committed change above.
    ok, msg = storage.push_pending(
        github_token="x", repo_slug="unused/unused", branch="main",
        repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg
    assert "Saved and pushed" in msg

    on_remote = subprocess.run(
        ["git", "show", "main:data/trip_log.csv"], cwd=bare_and_seed, capture_output=True, text=True, check=True,
    )
    assert "caught while offline" in on_remote.stdout


def test_push_pending_is_a_harmless_noop_when_nothing_is_pending(tmp_path, bare_and_seed):
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    ok, msg = storage.push_pending(
        github_token="x", repo_slug="unused/unused", branch="main",
        repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg


def test_push_pending_no_token():
    ok, msg = storage.push_pending(github_token="", repo_slug="a/b")
    assert ok is False
    assert "No GITHUB_TOKEN" in msg


def test_push_pending_data_lands_on_data_branch(tmp_path, bare_and_seed):
    """push_pending_data (the DATA_BRANCH-hardcoded sibling autosave should
    actually call) must retry against 'data', never 'main' - same
    redeploy-storm concern commit_and_push_data() itself exists for."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,pending save\n")
    ok, _ = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="pending save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True

    ok2, msg2 = storage.push_pending_data(
        github_token="x", repo_slug="unused/unused", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok2 is True, msg2  # already pushed above - this should be a harmless no-op, not an error

    on_data = subprocess.run(
        ["git", "show", f"{storage.DATA_BRANCH}:data/trip_log.csv"], cwd=bare_and_seed,
        capture_output=True, text=True, check=True,
    )
    assert "pending save" in on_data.stdout
    on_main = subprocess.run(
        ["git", "show", "main:data/trip_log.csv"], cwd=bare_and_seed, capture_output=True, text=True, check=True,
    )
    assert "pending save" not in on_main.stdout


def test_is_transient_network_error_matches_common_flaky_connection_phrasing():
    assert storage._is_transient_network_error("fatal: unable to access 'https://...': Could not resolve host: github.com")
    assert storage._is_transient_network_error("error: RPC failed; curl 56 Recv failure: Connection reset by peer")
    assert storage._is_transient_network_error("fatal: The requested URL returned error: 503")
    assert not storage._is_transient_network_error("fatal: Authentication failed for 'https://...'")
    assert not storage._is_transient_network_error("! [rejected] main -> main (non-fast-forward)")
