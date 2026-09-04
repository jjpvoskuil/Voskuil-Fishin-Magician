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


@pytest.fixture(autouse=True)
def _isolate_worktree_tempdir(tmp_path_factory, monkeypatch):
    """commit_and_push_data()/push_pending_data() (punch-list #67) create a
    real worktree directory under the system temp dir, keyed by a hash of
    repo_root's path, and deliberately never delete it (mirroring
    production, where repo_root - and so the worktree - is stable for the
    whole life of the deployed container). Left alone here, every test run
    that exercises those two functions would leave a fresh, never-cleaned
    directory behind in the real /tmp forever. Redirect it into pytest's own
    managed tmp tree instead, which pytest prunes automatically.
    """
    fake_tmp_root = tmp_path_factory.mktemp("worktree-root")
    monkeypatch.setattr(storage.tempfile, "gettempdir", lambda: str(fake_tmp_root))


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


# --- Punch-list #73: sync_data_from_data_branch() must retry a transient ----
# fetch failure instead of giving up after one attempt. Root-caused from a
# real live incident: Trip History reverted to a last entry date of 8/23/2026
# - exactly main's own frozen data/trip_log.csv snapshot, row for row -
# because app.py's _sync_data_once() wraps this in st.cache_resource (runs
# ONCE per process, remembers only that it ran, never whether it actually
# succeeded) and the old version here gave up on the very first fetch
# failure. A single flaky moment at cold boot (very plausible - a freshly
# started container's outbound network may not be fully warmed up yet) used
# to strand that process on stale/frozen data for its entire remaining
# lifetime. These two tests cover the fix: a transient fetch failure now
# gets retried (mirroring commit_and_push()'s own punch-list #58 transient-
# retry tests just above/below this block), and a persistent one still gives
# up cleanly (no crash, no infinite loop) after max_retries.

def test_sync_data_from_data_branch_retries_transient_network_error_then_succeeds(
    tmp_path, bare_and_seed, monkeypatch,
):
    cutover = _clone(bare_and_seed, tmp_path / "cutover")
    _run(["git", "checkout", "-b", storage.DATA_BRANCH], cwd=cutover)
    _run(["git", "push", str(bare_and_seed), f"HEAD:{storage.DATA_BRANCH}"], cwd=cutover)

    saver = _clone(bare_and_seed, tmp_path / "saver")
    (saver / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,new catch\n")
    ok, _ = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="new catch", repo_root=saver, remote_url=str(bare_and_seed),
    )
    assert ok is True

    app_repo = _clone(bare_and_seed, tmp_path / "app_repo")
    fetch_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            fetch_calls.append(args)
            if len(fetch_calls) < 3:
                return subprocess.CompletedProcess(
                    args, returncode=128, stdout="",
                    stderr="fatal: unable to access 'https://github.com/...': Could not resolve host: github.com",
                )
            return real_run(args, **kwargs)
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.sync_data_from_data_branch(
        github_token="x", repo_slug="unused/unused", repo_root=app_repo, remote_url=str(bare_and_seed),
        max_retries=5, retry_backoff_seconds=0,
    )
    assert ok is True, msg
    assert "new catch" in (app_repo / "data" / "trip_log.csv").read_text()
    assert len(fetch_calls) == 3  # two transient failures, then a real (unpatched) fetch succeeds


def test_sync_data_from_data_branch_gives_up_after_max_retries_on_persistent_transient_error(
    tmp_path, bare_and_seed, monkeypatch,
):
    cutover = _clone(bare_and_seed, tmp_path / "cutover")
    _run(["git", "checkout", "-b", storage.DATA_BRANCH], cwd=cutover)
    _run(["git", "push", str(bare_and_seed), f"HEAD:{storage.DATA_BRANCH}"], cwd=cutover)

    app_repo = _clone(bare_and_seed, tmp_path / "app_repo")
    before = (app_repo / "data" / "trip_log.csv").read_text()
    fetch_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            fetch_calls.append(args)
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="fatal: Connection timed out")
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.sync_data_from_data_branch(
        github_token="x", repo_slug="unused/unused", repo_root=app_repo, remote_url=str(bare_and_seed),
        max_retries=3, retry_backoff_seconds=0,
    )
    assert ok is False
    assert "after 3 attempts" in msg
    assert len(fetch_calls) == 3
    # Never touched the working tree - a failed sync must be a pure no-op,
    # same guarantee the pre-existing "no data branch yet" soft-noop test
    # above already covers for a different failure reason.
    assert (app_repo / "data" / "trip_log.csv").read_text() == before


# --- Punch-list #80: the DEFAULT retry budget itself was too short for a ----
# real cold-boot cold-start - a third live occurrence of the 8/23 reversion,
# right after a redeploy, with the manual "Refresh from GitHub" button (same
# function, same arguments) succeeding immediately moments later. That
# proved the network/auth/repo path was fine and the automatic boot sync
# just wasn't retrying long enough to survive it. This test pins the actual
# defaults (unlike the #73 tests above, which all pass explicit
# max_retries=/retry_backoff_seconds= overrides and would stay green no
# matter what the real defaults were) - confirmed to fail against the
# pre-fix defaults (max_retries=3) and pass against the fix (max_retries=6).
def test_sync_data_from_data_branch_default_retry_budget_survives_five_transient_failures(
    tmp_path, bare_and_seed, monkeypatch,
):
    cutover = _clone(bare_and_seed, tmp_path / "cutover")
    _run(["git", "checkout", "-b", storage.DATA_BRANCH], cwd=cutover)
    _run(["git", "push", str(bare_and_seed), f"HEAD:{storage.DATA_BRANCH}"], cwd=cutover)

    saver = _clone(bare_and_seed, tmp_path / "saver")
    (saver / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,new catch\n")
    ok, _ = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="new catch", repo_root=saver, remote_url=str(bare_and_seed),
    )
    assert ok is True

    app_repo = _clone(bare_and_seed, tmp_path / "app_repo")
    fetch_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            fetch_calls.append(args)
            if len(fetch_calls) < 6:
                return subprocess.CompletedProcess(
                    args, returncode=128, stdout="",
                    stderr="fatal: unable to access 'https://github.com/...': Could not resolve host: github.com",
                )
            return real_run(args, **kwargs)
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    monkeypatch.setattr(storage.time, "sleep", lambda seconds: None)  # keep the test fast
    # Deliberately NOT passing max_retries=/retry_backoff_seconds= - this is
    # the whole point: it exercises whatever this function's real defaults
    # are, the same way app.py's actual boot-time call does.
    ok, msg = storage.sync_data_from_data_branch(
        github_token="x", repo_slug="unused/unused", repo_root=app_repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg
    assert "new catch" in (app_repo / "data" / "trip_log.csv").read_text()
    assert len(fetch_calls) == 6  # five transient failures, then a real (unpatched) fetch succeeds


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


# --- Punch-list #67: commit_and_push_data() must never touch repo_root's
# own HEAD ---------------------------------------------------------------
# The confirmed root cause of the live Start-Session crash and real data
# loss: repo_root is the SAME live checkout Streamlit Community Cloud has
# deployed `main` from and watches for changes. Creating a local `git
# commit` there - even one that only ever gets pushed to `data`, never
# `main` - is enough on its own to trigger Streamlit Cloud's redeploy
# detection mid-request, which corrupts the running process and can wipe
# the very commit that was just made before its push completes. The fix
# moves the actual add/commit/push into an isolated git worktree; these
# tests assert the guarantee that fix exists to provide.

def test_commit_and_push_data_never_touches_repo_roots_own_head(tmp_path, bare_and_seed):
    """The core guarantee: after a successful data save, repo_root's own
    HEAD, branch, and git history are byte-for-byte unchanged - the only
    new commit exists in the isolated worktree, never in repo_root."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    head_before = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    branch_before = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()

    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,angler save\n")
    ok, msg = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="angler save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg

    head_after = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    branch_after = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()
    assert head_after == head_before, (
        "repo_root got a new local commit - this is exactly what used to "
        "trigger a Streamlit Cloud redeploy mid-save"
    )
    assert branch_after == branch_before

    # The working-tree edit above (the same in-place edit a real save makes
    # before calling commit_and_push_data) is still there, untouched and
    # uncommitted - repo_root's index/working tree were never staged either.
    status = _run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    assert status == "M data/trip_log.csv"


def test_commit_and_push_data_accepts_absolute_paths_like_production_does(tmp_path, bare_and_seed):
    """Production call sites pass absolute-path constants (e.g.
    storage.TRIP_LOG_PATH), not repo-root-relative strings like most tests
    in this file use - the worktree copy step must resolve an absolute
    source path against repo_root correctly, not just relative ones."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    absolute_path = (repo / "data" / "trip_log.csv").resolve()
    absolute_path.write_text("trip_id,notes\n1,first\n2,absolute path save\n")

    ok, msg = storage.commit_and_push_data(
        [absolute_path], github_token="x", repo_slug="unused/unused",
        commit_message="absolute path save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg

    on_data = _run(["git", "show", f"{storage.DATA_BRANCH}:data/trip_log.csv"], cwd=bare_and_seed)
    assert "absolute path save" in on_data.stdout


def test_commit_and_push_data_handles_a_whole_directory_in_paths(tmp_path, bare_and_seed):
    """Punch-list #71: the real bug behind "pictures of lures disappearing
    from the tackle box." Both of the Tackle Box page's photo-touching
    saves (adding a lure with a photo, deleting one) pass
    core.lure_inventory.IMAGES_DIR whole in `paths`, not a single file -
    commit_and_push()'s own docstring has always promised "files or
    directories" for exactly this reason. Before the fix, the worktree-copy
    step used `shutil.copy2()` unconditionally, which raises a bare
    IsADirectoryError the instant a directory shows up in `paths` -
    confirmed live against this exact fixture shape before the fix existed.
    That crash was caught by commit_and_push_data()'s own outer `except
    Exception`, so the WHOLE save (not just the photo) silently came back
    False - the new inventory row usually still made it to GitHub
    eventually (a later, unrelated save with different `paths` carries
    every locally-written row along regardless), but the actual photo file
    never did, since nothing else ever references IMAGES_DIR - exactly "the
    rest of the information was there but no picture" after a restart
    re-synced data/ from the real committed history."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    images_dir = repo / "data" / "images"
    images_dir.mkdir()
    (images_dir / "existing.jpg").write_bytes(b"already-there photo")
    _run(["git", "add", "data/images/existing.jpg"], cwd=repo)
    _run(["git", "commit", "-m", "seed an existing photo"], cwd=repo)
    _run(["git", "push", str(bare_and_seed), "HEAD:main"], cwd=repo)
    _run(["git", "push", str(bare_and_seed), "HEAD:data"], cwd=repo)

    # A new save: a new row in the CSV, plus a brand new photo file - the
    # exact shape of a real "Add a lure" with a photo attached.
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,new lure added\n")
    (images_dir / "new_photo.jpg").write_bytes(b"brand new photo bytes")

    ok, msg = storage.commit_and_push_data(
        [repo / "data" / "trip_log.csv", images_dir],
        github_token="x", repo_slug="unused/unused",
        commit_message="Add lure to inventory: Test Lure", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg

    check = tmp_path / "check"
    _run(["git", "clone", "--branch", storage.DATA_BRANCH, str(bare_and_seed), str(check)], cwd=tmp_path)
    assert (check / "data" / "images" / "new_photo.jpg").read_bytes() == b"brand new photo bytes"
    # The pre-existing photo must survive untouched, not just the new one.
    assert (check / "data" / "images" / "existing.jpg").read_bytes() == b"already-there photo"
    assert "new lure added" in (check / "data" / "trip_log.csv").read_text()


def test_commit_and_push_data_directory_mirror_reflects_a_local_deletion(tmp_path, bare_and_seed):
    """The delete_item() side of punch-list #71: a file removed from
    IMAGES_DIR locally (e.g. deleting a tackle box item that had a photo)
    must actually disappear from the pushed data too, not linger as an
    orphan because the worktree copy only ever adds, never removes."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    images_dir = repo / "data" / "images"
    images_dir.mkdir()
    (images_dir / "keep.jpg").write_bytes(b"keep me")
    (images_dir / "remove_me.jpg").write_bytes(b"delete me")
    _run(["git", "add", "data/images"], cwd=repo)
    _run(["git", "commit", "-m", "seed two photos"], cwd=repo)
    _run(["git", "push", str(bare_and_seed), "HEAD:main"], cwd=repo)
    _run(["git", "push", str(bare_and_seed), "HEAD:data"], cwd=repo)

    (images_dir / "remove_me.jpg").unlink()

    ok, msg = storage.commit_and_push_data(
        [images_dir], github_token="x", repo_slug="unused/unused",
        commit_message="Remove lure inventory item", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg

    check = tmp_path / "check"
    _run(["git", "clone", "--branch", storage.DATA_BRANCH, str(bare_and_seed), str(check)], cwd=tmp_path)
    remaining = sorted(p.name for p in (check / "data" / "images").iterdir())
    assert remaining == ["keep.jpg"]


def test_push_pending_data_reuses_the_worktree_commit_and_push_data_created(tmp_path, bare_and_seed):
    """push_pending_data() must retry against the SAME worktree a prior
    commit_and_push_data() call committed into, not create a second one -
    a fresh worktree per call would defeat the point of a stable, reusable
    isolation layer."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,first save\n")
    ok, msg = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="first save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg

    worktree = storage._data_worktree_dir(repo)
    assert worktree.exists()
    worktrees_before = _run(["git", "worktree", "list"], cwd=repo).stdout

    ok2, msg2 = storage.push_pending_data(
        github_token="x", repo_slug="unused/unused", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok2 is True, msg2

    worktrees_after = _run(["git", "worktree", "list"], cwd=repo).stdout
    assert worktrees_before == worktrees_after, (
        "push_pending_data() created a second worktree instead of reusing "
        "the one commit_and_push_data() already made"
    )


def test_commit_and_push_data_retries_when_the_shared_worktree_falls_behind(tmp_path, bare_and_seed):
    """Realistic punch-list #67 concurrency case: repo_root's own worktree
    can still fall behind the remote `data` branch (e.g. a stale or
    overlapping container pushing during a Streamlit Cloud redeploy). The
    existing fetch+rebase+retry logic in commit_and_push() must keep
    working when it's the WORKTREE's push that gets rejected, and
    repo_root's own HEAD must still never move."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,first save\n")
    ok, msg = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="first save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is True, msg

    # Something else pushes to `data` behind repo_root's worktree's back -
    # e.g. a different/stale container during a redeploy.
    outsider = _clone(bare_and_seed, tmp_path / "outsider")
    _run(["git", "fetch", str(bare_and_seed), storage.DATA_BRANCH], cwd=outsider)
    _run(["git", "checkout", "FETCH_HEAD"], cwd=outsider)
    (outsider / "data" / "trip_log.csv").write_text(
        "trip_id,notes\n1,first\n2,first save\n3,outsider save\n"
    )
    _run(["git", "add", "data/trip_log.csv"], cwd=outsider)
    _run(["git", "commit", "-m", "outsider save"], cwd=outsider)
    _run(["git", "push", str(bare_and_seed), f"HEAD:{storage.DATA_BRANCH}"], cwd=outsider)

    head_before = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    (repo / "data" / "trip_log.csv").write_text(
        "trip_id,notes\n1,first\n2,first save\n4,second save\n"
    )
    ok2, msg2 = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="second save", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok2 is True, msg2
    assert _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip() == head_before, (
        "repo_root's HEAD must stay put even when the worktree needs a "
        "fetch+rebase retry"
    )

    on_data = _run(["git", "show", f"{storage.DATA_BRANCH}:data/trip_log.csv"], cwd=bare_and_seed).stdout
    assert "outsider save" in on_data
    assert "second save" in on_data


def test_is_transient_network_error_matches_common_flaky_connection_phrasing():
    assert storage._is_transient_network_error("fatal: unable to access 'https://...': Could not resolve host: github.com")
    assert storage._is_transient_network_error("error: RPC failed; curl 56 Recv failure: Connection reset by peer")
    assert storage._is_transient_network_error("fatal: The requested URL returned error: 503")
    assert not storage._is_transient_network_error("fatal: Authentication failed for 'https://...'")
    assert not storage._is_transient_network_error("! [rejected] main -> main (non-fast-forward)")


# --- Punch-list #76: no git subprocess call had a timeout, so a stalled ---
# network call (weak/dropped cell signal - real, expected conditions for an
# app used standing at a lake) could hang the underlying `git` process, and
# with it the entire synchronous Streamlit script run that called it,
# indefinitely. Live report: an angler mid-Spot-Session tapped a lure to log
# a catch and got no response at all. These simulate a hang by making a
# mocked subprocess.run() raise subprocess.TimeoutExpired directly (the same
# thing a real timeout= produces once it fires) rather than actually waiting
# out a real timeout, which would make the suite painfully slow.

def test_run_git_or_timeout_converts_a_hang_into_an_already_recognized_transient_failure(monkeypatch):
    """The core mechanism _push_with_retries()'s push/fetch/rebase calls all
    go through now: a raised TimeoutExpired must come back as an ordinary
    failed result (never propagate as an exception) whose stderr is already
    recognized by _is_transient_network_error() - that's what makes a timed-
    out push/fetch automatically retry with zero changes to the retry logic
    itself."""
    args = ["git", "push", "origin", "HEAD:data"]

    def fake_run(a, **kwargs):
        raise subprocess.TimeoutExpired(cmd=a, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    result = storage._run_git_or_timeout(args, "/tmp", timeout=20)
    assert result.returncode != 0
    assert storage._is_transient_network_error(result.stderr)


def test_commit_and_push_retries_when_push_hangs_then_succeeds(tmp_path, bare_and_seed, monkeypatch):
    """Same scenario as test_commit_and_push_retries_transient_network_error_
    then_succeeds above, but the failure is a genuine hang (subprocess.run
    raising TimeoutExpired) instead of a fast error response - proving a
    stalled push gets the same automatic retry a fast-failing one already
    did, not a frozen/uncaught-exception app."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    (repo / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n")

    push_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "push"]:
            push_calls.append(args)
            if len(push_calls) < 3:
                raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))
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
    assert len(push_calls) == 3  # two hangs, then a real (unpatched) push succeeds


def test_commit_and_push_config_call_hanging_is_a_clean_failure_not_an_uncaught_crash(
    tmp_path, bare_and_seed, monkeypatch,
):
    """Before this fix, `git config` (a check=True call) had no timeout= at
    all, and commit_and_push()'s except clause only caught
    subprocess.CalledProcessError - a raised TimeoutExpired from a hang would
    propagate straight out of commit_and_push() uncaught, crashing whatever
    Streamlit script run called it instead of returning the normal (False,
    message) failure shape every other error here produces."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "config"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.commit_and_push(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="add trip", repo_root=repo, remote_url=str(bare_and_seed),
    )
    assert ok is False
    assert "push failed" in msg.lower()


def test_sync_data_from_data_branch_retries_when_fetch_hangs_then_succeeds(tmp_path, bare_and_seed, monkeypatch):
    """Mirrors test_sync_data_from_data_branch_retries_transient_network_
    error_then_succeeds, but with a genuine hang (TimeoutExpired) instead of
    a fast error - this function's existing try/except Exception retry loop
    (punch-list #73) needed no changes at all to handle this correctly, once
    the fetch call itself passes timeout=."""
    cutover = _clone(bare_and_seed, tmp_path / "cutover")
    _run(["git", "checkout", "-b", storage.DATA_BRANCH], cwd=cutover)
    _run(["git", "push", str(bare_and_seed), f"HEAD:{storage.DATA_BRANCH}"], cwd=cutover)

    saver = _clone(bare_and_seed, tmp_path / "saver")
    (saver / "data" / "trip_log.csv").write_text("trip_id,notes\n1,first\n2,new catch\n")
    ok, _ = storage.commit_and_push_data(
        ["data/trip_log.csv"], github_token="x", repo_slug="unused/unused",
        commit_message="new catch", repo_root=saver, remote_url=str(bare_and_seed),
    )
    assert ok is True

    app_repo = _clone(bare_and_seed, tmp_path / "app_repo")
    fetch_calls = []
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            fetch_calls.append(args)
            if len(fetch_calls) < 3:
                raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))
            return real_run(args, **kwargs)
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)
    ok, msg = storage.sync_data_from_data_branch(
        github_token="x", repo_slug="unused/unused", repo_root=app_repo, remote_url=str(bare_and_seed),
        max_retries=5, retry_backoff_seconds=0,
    )
    assert ok is True, msg
    assert "new catch" in (app_repo / "data" / "trip_log.csv").read_text()
    assert len(fetch_calls) == 3  # two hangs, then a real (unpatched) fetch succeeds


def test_ensure_data_worktree_falls_back_to_local_branch_when_fetch_hangs(tmp_path, bare_and_seed, monkeypatch):
    """A fetch that HANGS while setting up the data worktree for the first
    time in a process must fall back to creating a local branch (same as an
    ordinary fast fetch failure already did), not fail the whole save
    outright - a local commit can still happen and be pushed later by the
    autosave retry heartbeat."""
    repo = _clone(bare_and_seed, tmp_path / "repoA")
    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "fetch"]:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout"))
        return real_run(args, **kwargs)

    monkeypatch.setattr(storage.subprocess, "run", fake_run)

    worktree, err = storage._ensure_data_worktree(repo, str(bare_and_seed), storage.DATA_BRANCH)
    assert worktree is not None, f"expected a local-branch fallback, got error: {err}"
    assert (worktree / ".git").exists()


def test_parse_conditions_returns_the_dict_for_a_normal_row():
    row = {"conditions_json": '{"lure_category": "football_jig", "avg_wind_mph": 6}'}
    assert storage.parse_conditions(row) == {"lure_category": "football_jig", "avg_wind_mph": 6}


def test_parse_conditions_is_a_dict_for_missing_or_blank_conditions_json():
    assert storage.parse_conditions({}) == {}
    assert storage.parse_conditions({"conditions_json": ""}) == {}
    assert storage.parse_conditions({"conditions_json": None}) == {}


def test_parse_conditions_is_a_dict_for_malformed_json():
    assert storage.parse_conditions({"conditions_json": "not json"}) == {}


def test_parse_conditions_is_a_dict_when_json_parses_to_a_non_dict():
    # The real bug this was added for: conditions_json is JSON-encoded free
    # text, not schema-validated - a bare number/string/list/null is valid
    # JSON (json.loads succeeds) but isn't a dict. Every caller immediately
    # calls .get(...) on the result, so this used to be an uncaught
    # AttributeError rather than just an empty/unusable row.
    assert storage.parse_conditions({"conditions_json": "24"}) == {}
    assert storage.parse_conditions({"conditions_json": '"a string"'}) == {}
    assert storage.parse_conditions({"conditions_json": "[1, 2, 3]"}) == {}
    assert storage.parse_conditions({"conditions_json": "null"}) == {}
