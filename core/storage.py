"""
Trip log storage + optional git commit-back.

Trip logs are stored as data/trip_log.csv inside the repo itself, so the
log travels with the code (no extra database/service to set up). When
running on Streamlit Cloud with a GitHub token configured in
st.secrets["GITHUB_TOKEN"], each new log entry is also committed and
pushed back to the repo so it survives app restarts/redeploys. If no
token is configured (e.g. local development), the app still works - it
just writes to the local CSV for that session and shows a note that the
entry wasn't pushed upstream.

commit_and_push() is intentionally generic (takes a list of paths) so
other modules that follow the same git-backed-persistence pattern - e.g.
core/lure_inventory.py - can reuse it instead of re-implementing the git
plumbing.

--- Two branches: `main` (code) vs DATA_BRANCH (data) - punch-list #52 ---
Streamlit Community Cloud auto-redeploys the whole app on every push to
`main` (see README.md's Deployment section). Every data-mutating action in
this app - logging a trip, adding a lure, editing the punch list, adding an
angler or a lake spot, freezing a forecast segment - used to call
commit_and_push() with its old default of branch="main", which meant ANY
angler's routine save could trigger a full process restart, wiping
st.session_state for every currently-connected browser at once. Confirmed
via real usage logs: dozens of commits in a single afternoon of concurrent
fishing, several clusters of 2-3 within one minute - see SESSION_NOTES.md
punch-list #51/#52 for the full investigation.

The fix: all in-app data writes now go through commit_and_push_data() below
instead of calling commit_and_push() directly - it's the exact same
function, just hardcoded to push to DATA_BRANCH ("data") instead of
"main". Streamlit Cloud only watches "main" for redeploys, so a data save
no longer triggers one. `main` still gets pushed to directly (by a Claude
coding session, via a raw `git push ... main:main`, same as always) for
real code changes, which SHOULD still redeploy - that's the one kind of
restart that's still expected and fine.

Because of this split, main's own data/*.csv files stop advancing after
the punch-list #52 cutover - they're frozen at whatever they were the
moment DATA_BRANCH was created. The actual, current data only lives on
DATA_BRANCH. sync_data_from_data_branch() (below) is what closes that gap
for the RUNNING APP: app.py calls it once per process boot (guarded by
st.cache_resource, so it's not re-run on every page click) to overlay the
working tree's data/ directory with DATA_BRANCH's latest content before
serving any page, so a freshly restarted process picks up every real save
since the last boot instead of silently serving stale (or, for a brand
new deploy, potentially very old) data.

**This matters for a future Claude coding session too**: if you `git
clone` this repo (which checks out `main` by default), the data/*.csv
files you see are FROZEN at the punch-list #52 cutover point, not current.
To see or work with real current data, fetch and inspect DATA_BRANCH
specifically (`git fetch origin data && git show origin/data:data/trip_log.csv`,
or check it out into a scratch worktree) - don't assume main's data/ folder
reflects what anglers have actually logged since. See SESSION_NOTES.md's
Architecture section for the full picture.

--- Why commit_and_push_data() commits in an isolated worktree, not
`repo_root` itself - punch-list #67 ---
Punch-list #52's split (above) only ever protected the REMOTE `main`
branch - pushing to DATA_BRANCH instead of `main` stops the push itself
from reaching the branch Streamlit Cloud redeploys on. It did NOT protect
`repo_root`'s own LOCAL git state on the live, currently-running deployment
- every real save still ran `git commit` directly inside repo_root (the
exact directory the deployed app's Python process is running from and
Streamlit Cloud is actively watching), even though that commit's content
only ever gets pushed to DATA_BRANCH afterward. Confirmed via Streamlit
Cloud's own server logs (a live angler-provided log, not guesswork) that
this local commit ALONE - regardless of which remote branch it's pushed
to - is enough to make Streamlit Cloud think new code arrived and kick off
a real redeploy cycle ("Pulling code changes from Github... Processing
dependencies... Updated app!") in the middle of the still-running script's
own execution. That redeploy swaps files on disk out from under the live
Python interpreter mid-import (a cascade of KeyError/AttributeError/
ImportError, all different symptoms of the same "the file changed while
this was importing it" race - see SESSION_NOTES.md entry 133/134 for the
full log excerpt) and, worse, appears to reset repo_root back to match
`origin/main` as part of resyncing - discarding the very commit that
triggered it before its push to DATA_BRANCH necessarily finished. That's
why a trip logged (or a punch-list item added) could look saved for a
minute and then silently vanish, never having reached GitHub at all.

The fix: commit_and_push_data() and push_pending_data() now do their
actual `git add`/`git commit`/`git push` inside a SEPARATE git worktree
(see _ensure_data_worktree() below) - a second, independent working
directory backed by the same .git object database, checked out to
DATA_BRANCH, living outside repo_root entirely (under the system temp
directory, keyed by repo_root's own path) so nothing under the live app's
own directory tree - and critically, repo_root's own HEAD/branch ref -
ever changes when a data save happens. The file(s) being saved are copied
into the worktree's mirrored path immediately before committing there;
repo_root's own working copy of those files (what the running app
actually reads from) is untouched by this - it already has the new
content, since that's what triggered the save in the first place.
sync_data_from_data_branch() (below) was already safe by this same
standard before this fix existed - it only ever does a scoped `git
checkout FETCH_HEAD -- data`, which updates working-tree files without
moving repo_root's HEAD or creating any commit, so it was left as-is.

--- Every git subprocess call has a timeout now - punch-list #76 ---
Live incident: an angler mid-Spot-Session tapped a lure to log a catch and
got no response at all - the whole app appeared frozen, not just that one
click. Root cause: every single `subprocess.run(["git", ...])` call in this
file - fetch, push, commit, add, worktree setup, all of it - had NO
timeout. This app is used standing at a lake, often on weak or dropping
cell signal, which is exactly the condition that makes a network call
stall (not fail - just never come back) rather than error out cleanly. A
stalled `git fetch`/`git push` subprocess call blocks whatever Python
thread called `subprocess.run()`, and since every interaction in this app
is a live, synchronous round trip through one Streamlit script run (no
background/async work exists here), that one stalled call froze the
ENTIRE page - any button, not just the one that happened to trigger the
network call - for as long as the connection stayed down, which could be
indefinitely.

The fix: every git subprocess call now passes `timeout=` (see
`_GIT_LOCAL_TIMEOUT_SECONDS`/`_GIT_NETWORK_TIMEOUT_SECONDS` below, right
after `_is_transient_network_error()`) so a hang always resolves into an
ordinary failure within a bounded number of seconds instead of never
resolving at all. Two ways that failure gets folded back into logic this
file already had, so nothing else needed to change: (1) for the manually-
returncode-checked calls (push, fetch, rebase - the ones inspected by
`_is_transient_network_error()`), `_run_git_or_timeout()` turns a timeout
into a synthetic failed result whose stderr contains "operation timed
out", already one of that function's recognized markers - so a timed-out
push/fetch is automatically retried exactly like any other flaky-
connection failure, zero changes to the retry logic itself; (2) for the
check=True calls (`git config`/`git add`/`git commit` in
commit_and_push()) and `sync_data_from_data_branch()`'s own fetch/checkout
(already inside a `try/except Exception` retry loop from punch-list #73),
a raised `subprocess.TimeoutExpired` is caught by widening the existing
except clauses from `subprocess.CalledProcessError` to its parent
`subprocess.SubprocessError` (which TimeoutExpired is also a subclass of)
- or, for #73's loop, needed no change at all, since it already caught
every exception generically. This app still can't do anything about a
connection that's ACTUALLY down for the whole timeout window - the fix
isn't "always succeed on bad signal," it's "never just sit there with no
feedback and no way for anything else on the page to respond."
"""
from __future__ import annotations
import csv
import fcntl
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIP_LOG_PATH = REPO_ROOT / "data" / "trip_log.csv"


def _data_lock_path(repo_root: Path = REPO_ROOT) -> Path:
    """Same keying scheme as _data_worktree_dir() below (a hash of
    repo_root's resolved path, under the system temp dir) so each real
    deployment - and each test pointing at its own throwaway repo_root -
    gets its own independent lock file rather than colliding with unrelated
    ones. Deliberately NOT under repo_root itself: nothing here should ever
    be a trackable file a `git add` could accidentally pick up."""
    key = hashlib.sha1(str(Path(repo_root).resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"fishin-magician-data-lock-{key}"


@contextmanager
def data_write_lock(repo_root: Path = REPO_ROOT):
    """Punch-list #68 (trip-history data-loss investigation): every real
    data-mutating action in this app - append/update/delete on
    trip_log.csv, lure_inventory.csv, dev_tasks.csv, anglers.csv,
    lake_spots.csv, water_quality_log.csv - reads a local CSV, rewrites it
    whole (or appends a row), and separately copies that same file into the
    commit_and_push_data() worktree to commit+push it. None of that was ever
    guarded against two of these sequences overlapping in time - two
    concurrent Streamlit sessions (or, worse, an old pre-redeploy process
    and a freshly booted one briefly alive at the same moment, sharing the
    same repo_root and the same /tmp) each reading/writing/copying the same
    file with no coordination at all.

    Confirmed as the real mechanism behind a live incident: trip_log.csv
    briefly ballooned from 76 to 152 rows with column-shifted garbage (real
    segment names like "Dawn"/"Afternoon" landing in the trip_date column -
    the unmistakable signature of two writes interleaving mid-row) right
    around a manual app reboot, before the very next write collapsed it back
    down and discarded several real, already-logged 8/24-8/26 sessions in
    the process (recovered from earlier git history afterward - see
    SESSION_NOTES.md punch-list #68).

    The fix: an OS-level advisory lock (`fcntl.flock`, exclusive, blocking -
    works across threads AND across separate processes on the same
    filesystem, which a plain Python `threading.Lock` would not) that every
    local-file read-modify-write AND the commit_and_push_data()/
    push_pending_data() worktree section below both acquire for their full
    duration. Whichever save gets there first now runs to completion (local
    write, or worktree copy+commit+push) before any other save's critical
    section can start, so two overlapping saves are serialized instead of
    interleaved - eliminating this exact class of corruption regardless of
    which two operations happen to race. Reentrant-safe is NOT needed here
    (and not provided) - every real call site acquires this once per
    top-level call, never while already holding it."""
    lock_path = _data_lock_path(repo_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as lockfile:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)

# Punch-list #52: the branch every in-app data save pushes to - see the
# module docstring above. Streamlit Cloud never watches this branch, so
# pushing here never triggers a redeploy.
DATA_BRANCH = "data"

FIELDNAMES = [
    "trip_id", "session_id", "logged_at", "trip_date", "segment", "spot_id", "spot_name",
    "structure_type", "water_clarity", "lure_used", "color_used", "technique_used",
    "fish_caught", "biggest_fish_lb", "predicted_score", "conditions_json", "notes",
]


@dataclass
class TripEntry:
    trip_date: str
    segment: str
    spot_id: str
    spot_name: str
    structure_type: str
    water_clarity: str
    lure_used: str
    color_used: str
    technique_used: str
    fish_caught: int
    biggest_fish_lb: Optional[float]
    # None when a session was logged via "Add results" without ever filling in
    # "Conditions right now" first (no live reading means no score to compute) -
    # see pages/6_Spot_Session.py.
    predicted_score: Optional[float]
    conditions: dict
    notes: str = ""
    trip_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    logged_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # Punch-list #55: groups every lure/fish logged in one Spot Session run
    # (▶ Start Session through ⏹ End Session, including any lure added
    # mid-session) so Trip History can show one record per outing instead of
    # one per lure. Blank ("") for any row written before this field
    # existed and for anything that isn't a Spot Session row - Trip History
    # treats a blank session_id as its own single-lure "session" rather than
    # guessing at grouping from date/spot/timestamp proximity. See
    # pages/6_Spot_Session.py's Start Session handler for where a real value
    # gets stamped.
    session_id: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        d["conditions_json"] = json.dumps(d.pop("conditions"))
        return {k: d.get(k, "") for k in FIELDNAMES}


def ensure_log_exists():
    if not TRIP_LOG_PATH.exists():
        TRIP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRIP_LOG_PATH, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def read_all_trips() -> list:
    ensure_log_exists()
    with open(TRIP_LOG_PATH, newline="") as f:
        return list(csv.DictReader(f))


def parse_conditions(row: dict) -> dict:
    """Every caller that reads a trip_log.csv row's conditions_json column
    needs this - several places used to each roll their own
    `json.loads(row.get("conditions_json") or "{}")`, checking only for a
    JSON *parse* error, not for the parsed value actually being a dict.
    conditions_json is JSON-encoded free text, not schema-validated - a
    hand-edited CSV, an old row from before some field existed, or any
    other origin that isn't this app's own json.dumps(conditions) call
    could in principle leave a bare number/string/list/null in that
    column, which parses just fine but then crashes the very next line
    every one of these callers had (`conditions.get(...)`) with an
    uncaught AttributeError - a real bug, confirmed while investigating a
    "brief error, didn't stop anything" report during a live Spot Session
    (the current data never actually had a row like this, so the crash
    couldn't be reproduced end-to-end, but the defect itself is real and
    would show exactly that way: a one-off exception on whichever rerun
    happened to touch the bad row, self-clearing on the next). Always
    returns a dict - {} for missing/unparseable/non-dict conditions_json,
    the parsed dict otherwise - so every caller can keep calling
    .get(...) on the result without checking anything itself."""
    try:
        parsed = json.loads(row.get("conditions_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def append_trip(entry: TripEntry):
    # Punch-list #68: the read-implicit-in-"a" (append position) through the
    # actual write must be atomic against any other process/thread doing the
    # same - see data_write_lock()'s docstring for the corruption this
    # prevents.
    with data_write_lock():
        ensure_log_exists()
        with open(TRIP_LOG_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow(entry.to_row())


def update_trip(entry: TripEntry) -> bool:
    """Replace the existing row whose trip_id matches entry.trip_id with this
    entry's data - an in-place edit rather than a new appended row. Used by
    Spot Session's edit mode (see pages/6_Spot_Session.py) so a previously
    logged session can be corrected and re-saved without leaving a duplicate
    behind. Returns False (no-op, file untouched) if no row with that
    trip_id exists anymore - e.g. it was deleted from trip_log.csv by
    something else while an edit was in progress.

    Punch-list #68: the read-modify-write below now runs under
    data_write_lock() - see its docstring - so this can't interleave with
    another process's concurrent append/update/delete on the same file."""
    with data_write_lock():
        ensure_log_exists()
        rows = read_all_trips()
        for i, row in enumerate(rows):
            if row.get("trip_id") == entry.trip_id:
                rows[i] = entry.to_row()
                break
        else:
            return False
        with open(TRIP_LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        return True


def delete_trip(trip_id: str) -> bool:
    """Remove the row with this trip_id entirely. Used by Trip History's
    per-trip "Delete" action. Returns False (no-op, file untouched) if no
    row with that trip_id exists.

    Punch-list #68: same data_write_lock()-guarded read-modify-write as
    update_trip() above, for the same reason."""
    with data_write_lock():
        ensure_log_exists()
        rows = read_all_trips()
        remaining = [r for r in rows if r.get("trip_id") != trip_id]
        if len(remaining) == len(rows):
            return False
        with open(TRIP_LOG_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(remaining)
        return True


def _resolve_remote_url(github_token: str, repo_slug: str, remote_url: Optional[str]) -> str:
    """Shared by commit_and_push()/sync_data_from_data_branch(): the real
    authenticated github.com URL, built from the token/slug, unless a
    caller (only ever a test) supplies its own remote_url to point at a
    throwaway local repo instead."""
    return remote_url or f"https://x-access-token:{github_token}@github.com/{repo_slug}.git"


# Punch-list #58 (session-loss investigation): substrings seen in real git
# push failures caused by a flaky/dropped connection rather than something
# that retrying won't fix (bad auth, a real conflict). This app is used
# standing at the lake on spotty cell signal, so "the push itself timed out
# or the socket dropped" is expected to happen sometimes - worth a few
# automatic retries, unlike e.g. "Authentication failed" which will just
# fail again instantly. Deliberately conservative (matches only known
# transient-network phrasing) so a real auth/permissions problem still
# fails fast instead of burning through retries pointlessly.
_TRANSIENT_ERROR_MARKERS = (
    "could not resolve host",
    "connection timed out",
    "connection reset",
    "connection refused",
    "operation timed out",
    "network is unreachable",
    "temporarily unavailable",
    "empty reply from server",
    "recv failure",
    "ssl_read",
    "the requested url returned error: 5",  # 502/503/504 from GitHub's edge
    "unable to access",
)


def _is_transient_network_error(stderr: str) -> bool:
    lowered = (stderr or "").lower()
    return any(marker in lowered for marker in _TRANSIENT_ERROR_MARKERS)


# Punch-list #76 (live incident - the whole app froze mid-Spot-Session; an
# angler tapped a lure to log a catch and got no response at all): every
# git subprocess call in this module used to have NO timeout whatsoever. A
# stalled network call - a weak or dropped connection, exactly the
# conditions this app is actually used in, standing at a lake on cell
# signal - could make the underlying `git` process hang indefinitely, and
# with it the ENTIRE Streamlit script run that called it: this app has no
# background/async work, every click is a live, synchronous round trip
# through the Python server, so one hung subprocess call froze the whole
# page, not just the action that triggered it. Confirmed by inspecting
# every subprocess.run() call site in this file - none passed timeout=.
#
# Two timeouts: a short one for git operations that never touch the
# network (config/add/commit/diff/status/rev-parse/worktree bookkeeping/
# rebase) - generous for even a slow disk, short enough that a stuck local
# git lock still fails fast rather than hanging just as badly as a network
# call would; a longer one for the two operations that actually reach
# GitHub (fetch, push) - generous enough for a genuinely slow-but-working
# connection to still succeed, short enough that a dead one gives up well
# within what an angler would sit and wait for mid-session.
_GIT_LOCAL_TIMEOUT_SECONDS = 15
_GIT_NETWORK_TIMEOUT_SECONDS = 20


def _run_git_or_timeout(args: list, cwd, timeout: float) -> subprocess.CompletedProcess:
    """subprocess.run() wrapper for every git call below that inspects
    .returncode/.stderr itself rather than using check=True (see
    commit_and_push()'s own timeout= additions for the check=True call
    sites, which don't need this - a raised subprocess.TimeoutExpired
    there just propagates to that function's own except clause, widened to
    catch it, same as any other git failure).

    A subprocess.TimeoutExpired here is turned into an ordinary FAILED
    CompletedProcess (returncode 1, an explanatory message in stderr)
    instead of being allowed to propagate as an exception - critically,
    that message contains "operation timed out", already one of
    _is_transient_network_error()'s recognized markers above, so a
    push/fetch that times out is automatically retried exactly like any
    other flaky-connection failure (a dropped connection, a DNS hiccup) -
    zero changes needed to any of the retry/rebase/fallback logic that
    already inspects .returncode/.stderr, just a guarantee that a hang
    always resolves into an ordinary, already-handled failure within
    `timeout` seconds instead of never resolving at all."""
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="",
            stderr=(
                f"git operation timed out after {timeout:g}s with no response "
                "(usually a weak/dropped connection, not a real git error)"
            ),
        )


def _push_with_retries(
    remote: str,
    branch: str,
    repo_root: Path,
    max_push_retries: int,
    retry_backoff_seconds: float,
) -> tuple:
    """Shared push-and-recover loop used by both commit_and_push() (right
    after it commits something new) and push_pending() (retrying whatever
    was already committed locally by a PRIOR call that failed to reach the
    remote). Never adds/commits anything itself - purely "try to get
    whatever's on HEAD onto `branch`."

    Two distinct failure modes get an automatic retry, each handled
    differently, same split as before this was extracted into its own
    function:
    - A rejected/non-fast-forward push (someone else's save landed first) -
      fetch + rebase onto the latest remote commit, then retry the push.
    - A transient network error (dropped connection, DNS hiccup, GitHub's
      edge returning a 5xx) - just retry the push itself after a short
      backoff, no fetch/rebase needed since nothing about the remote
      actually changed.
    Anything else (auth failure, a real rebase conflict) returns
    immediately - retrying those just burns time for a result that won't
    change.
    """
    last_error = ""
    for attempt in range(1, max_push_retries + 1):
        push = _run_git_or_timeout(
            ["git", "push", remote, f"HEAD:{branch}"], repo_root, _GIT_NETWORK_TIMEOUT_SECONDS,
        )
        if push.returncode == 0:
            return True, "Saved and pushed to GitHub."

        stderr = push.stderr or ""
        last_error = stderr.strip() or push.stdout.strip()
        rejected = (
            "[rejected]" in stderr
            or "non-fast-forward" in stderr
            or "fetch first" in stderr
        )
        transient = _is_transient_network_error(stderr)
        if not (rejected or transient):
            return False, f"Saved locally, but push failed: {last_error}"
        if attempt == max_push_retries:
            break

        if rejected:
            fetch = _run_git_or_timeout(
                ["git", "fetch", remote, branch], repo_root, _GIT_NETWORK_TIMEOUT_SECONDS,
            )
            if fetch.returncode != 0:
                if _is_transient_network_error(fetch.stderr or ""):
                    # The fetch itself hit the same kind of flaky-connection
                    # error the push did - worth another full loop rather
                    # than giving up on the whole retry chain over one
                    # dropped fetch.
                    time.sleep(retry_backoff_seconds * attempt)
                    continue
                return False, f"Saved locally, but push failed and the retry fetch also failed: {fetch.stderr.strip()}"

            rebase = _run_git_or_timeout(
                ["git", "rebase", "FETCH_HEAD"], repo_root, _GIT_LOCAL_TIMEOUT_SECONDS,
            )
            if rebase.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=repo_root, timeout=_GIT_LOCAL_TIMEOUT_SECONDS)
                return False, (
                    "Saved locally, but another device's save conflicted with this one "
                    "and couldn't be auto-merged - please retry the save."
                )
            # Rebased onto the latest remote branch - loop around and retry the push.
        else:
            # Transient network failure, not a rejection - nothing about the
            # remote branch changed, so just wait a beat and try the exact
            # same push again (a dropped cell signal often recovers within
            # a few seconds).
            time.sleep(retry_backoff_seconds * attempt)

    return False, (
        f"Saved locally, but push failed after {max_push_retries} attempts: {last_error}"
    )


def commit_and_push(
    paths: list,
    github_token: str,
    repo_slug: str,
    commit_message: str,
    branch: str = "main",
    repo_root: Path = REPO_ROOT,
    max_push_retries: int = 3,
    remote_url: Optional[str] = None,
    retry_backoff_seconds: float = 1.0,
) -> tuple:
    """
    Commit the given paths (files or directories, repo-relative or absolute)
    and push using a fine-grained PAT. Returns (success: bool, message: str).
    Never raises - designed to be called from Streamlit and surface a
    friendly warning on failure.

    Punch-list #26: if two anglers log a catch from separate devices at
    nearly the same moment, the second process's push here can get rejected
    as non-fast-forward - the first push already moved the remote branch
    ahead of what this process last fetched. Rather than surface that as a
    silently lost save, a rejected push is retried up to max_push_retries
    times: fetch the remote branch, rebase this commit on top of it (a
    same-file, append-only CSV change essentially never conflicts in
    practice), and push again.

    Punch-list #58: a plain transient network failure (dropped connection,
    DNS hiccup, a GitHub 5xx) now gets the same kind of automatic retry
    (with a short backoff between attempts - see _push_with_retries()),
    instead of giving up on the first try the way this used to. Only a
    genuine non-retryable failure (bad auth, a real rebase conflict) still
    returns immediately. This matters a lot in practice for this app: it's
    used standing at the lake on spotty cell signal, and a save that "fails
    once, quietly" used to just sit committed-but-unpushed on this process's
    local disk - fine as long as the process keeps running, but gone for
    good if it ever restarts before a later save happens to succeed and
    carry it along. See push_pending() below for the other half of this
    fix - retrying an already-committed, still-unpushed save on its own,
    without needing a brand new change to trigger it.

    repo_root defaults to the real repo checkout (REPO_ROOT) so every real
    caller behaves exactly as before; tests point it at a throwaway git repo
    instead of touching the real one - same "optional path parameter,
    defaults to the real constant" pattern already used by
    core/forecast_freeze.py/core/lure_inventory.py. remote_url similarly
    defaults to None (the real github.com PAT URL, built from github_token/
    repo_slug exactly as before); tests pass a local file:// bare-repo URL
    instead, so the retry/rebase logic below can be exercised against real
    git plumbing (a genuine concurrent-push race) rather than only mocked
    subprocess calls. retry_backoff_seconds defaults to a real (if short)
    delay for production use; tests pass 0 so the retry-exhaustion cases
    don't slow the suite down.
    """
    if not github_token:
        return False, "No GITHUB_TOKEN configured - saved locally only for this session."
    try:
        remote = _resolve_remote_url(github_token, repo_slug, remote_url)
        subprocess.run(
            ["git", "config", "user.email", "fishin-magician@bot.local"],
            cwd=repo_root, check=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
        subprocess.run(
            ["git", "config", "user.name", "Fishin' Magician Bot"],
            cwd=repo_root, check=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
        subprocess.run(
            ["git", "add"] + [str(p) for p in paths],
            cwd=repo_root, check=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=repo_root, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
        if diff.returncode == 0:
            # Punch-list #64 (live-app investigation): this exact message,
            # with nothing more, is what an angler has been seeing on every
            # single Start Session/Cancel Session/fish log this whole time -
            # even for a brand-new row that unquestionably differs from
            # whatever's on disk. A plain "no changes" with no further
            # detail was a dead end to debug from outside the running
            # container (no shell access, no server log tailing), so this
            # appends a live snapshot of exactly what git itself thinks is
            # going on for these specific paths right now - which of them
            # git sees as modified/untracked (should never be empty right
            # after a real write - if it IS empty, the write never reached
            # the file git is diffing at all), and whether HEAD even points
            # at a real branch (a detached HEAD, from some prior operation
            # leaving the checkout mid-rebase or on a raw commit SHA, would
            # look exactly like this - "add" and "commit" both still
            # nominally succeed, but nothing meaningful is actually
            # advancing). Purely diagnostic - never raises, doesn't change
            # the (ok, message) contract any caller/test relies on (still
            # `True`, still starts with "No changes to commit.", see
            # tests/test_storage.py's `"No changes" in msg` check), and
            # costs two more `git` calls only on this already-rare no-op
            # path, not on every save.
            status = subprocess.run(
                ["git", "status", "--porcelain"] + [str(p) for p in paths],
                cwd=repo_root, capture_output=True, text=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
            )
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_root, capture_output=True, text=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
            )
            status_bit = status.stdout.strip() or "(git sees these path(s) as completely unmodified)"
            branch_bit = branch.stdout.strip() or "unknown"
            return True, f"No changes to commit. [diag: HEAD={branch_bit!r}, git status={status_bit!r}]"
        subprocess.run(
            ["git", "commit", "-m", commit_message], cwd=repo_root, check=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
        return _push_with_retries(remote, branch, repo_root, max_push_retries, retry_backoff_seconds)
    except subprocess.SubprocessError as e:
        # Punch-list #76: widened from subprocess.CalledProcessError (a
        # non-zero exit) to its parent class, which also covers
        # subprocess.TimeoutExpired (a git call above that hung past its
        # timeout=) - both are "couldn't run this git command" failures,
        # and this message reads fine for either (TimeoutExpired's own
        # str() already says plainly that it timed out).
        return False, f"Saved locally, but push failed: {e}"


def push_pending(
    github_token: str,
    repo_slug: str,
    branch: str = "main",
    repo_root: Path = REPO_ROOT,
    max_push_retries: int = 3,
    remote_url: Optional[str] = None,
    retry_backoff_seconds: float = 1.0,
) -> tuple:
    """Punch-list #58: retries pushing whatever's ALREADY committed locally
    on `branch`'s ref, without adding or committing anything new. This is
    the piece commit_and_push() alone can't provide: if a prior
    commit_and_push()/commit_and_push_data() call committed a change locally
    but failed to push it (a dropped connection, GitHub having a bad
    moment), that commit just sits on local disk - fine as long as this
    process keeps running (the next real save's own commit_and_push() call
    will happily carry it along, since a git push always sends everything
    HEAD is ahead of the remote by, not just the newest commit), but gone
    for good if the process restarts first. Calling this on a timer (see
    pages/6_Spot_Session.py's autosave heartbeat) closes that window by
    retrying on its own, without waiting for the next real change.

    Safe to call anytime, including when there's nothing pending - `git
    push` on a branch that's already up to date is a fast, harmless no-op
    (returns success)."""
    if not github_token:
        return False, "No GITHUB_TOKEN configured - saved locally only for this session."
    try:
        remote = _resolve_remote_url(github_token, repo_slug, remote_url)
        return _push_with_retries(remote, branch, repo_root, max_push_retries, retry_backoff_seconds)
    except subprocess.SubprocessError as e:
        # Punch-list #76: see commit_and_push()'s matching except clause -
        # widened the same way, for the same reason.
        return False, f"Push failed: {e}"


def _data_worktree_dir(repo_root: Path) -> Path:
    """Where commit_and_push_data()/push_pending_data() actually run their
    git commands - see the module docstring's punch-list #67 section for
    why this has to be a separate directory from repo_root. Deliberately
    under the system temp directory (never inside repo_root, and never
    anywhere Streamlit Cloud's own deployment tooling has any reason to
    look), keyed by repo_root's own resolved path so tests pointing at a
    throwaway repo each get their own isolated worktree instead of
    colliding with each other or with a real deployment's."""
    key = hashlib.sha1(str(Path(repo_root).resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"fishin-magician-data-worktree-{key}"


def _ensure_data_worktree(repo_root: Path, remote: str, branch: str) -> tuple:
    """Creates (if it doesn't already exist on disk) and returns the
    isolated worktree directory commit_and_push_data()/push_pending_data()
    commit and push from, checked out to `branch`. Returns
    (worktree_path, None) on success, (None, error_message) on failure.

    Idempotent and cheap to call on every save: a worktree already present
    on disk (the common case - every save after the first one in a given
    process) is reused as-is, just a single Path.exists() check, no git
    calls at all. Only the first call in a fresh process (or the first
    call after a container restart wiped /tmp) actually runs `git
    worktree add`.

    Handles both a repo that already has `branch` fetched/known and one
    that's never heard of it yet (a brand new machine's very first save,
    or a fresh clone that's never pushed to DATA_BRANCH before): fetches
    `branch` from `remote` first and creates the worktree detached at
    FETCH_HEAD if that succeeds, or falls back to a fresh local branch
    (`-B branch`, based on repo_root's current HEAD) if the fetch fails
    because the branch doesn't exist on the remote at all yet - the first
    successful push from that worktree is what actually creates it there."""
    worktree = _data_worktree_dir(repo_root)
    if (worktree / ".git").exists():
        return worktree, None
    # Not on disk (fresh process, or a fresh container whose /tmp doesn't
    # survive restarts) - prune any stale registration left behind in
    # repo_root/.git by a PREVIOUS process's worktree at this same path
    # before trying to create a new one there, so a leftover registration
    # from an already-deleted worktree directory can't make `git worktree
    # add` fail with a spurious "already exists".
    subprocess.run(
        ["git", "worktree", "prune"], cwd=repo_root, capture_output=True, text=True,
        timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
    )
    worktree.parent.mkdir(parents=True, exist_ok=True)
    # Punch-list #76: routed through _run_git_or_timeout() rather than a
    # bare subprocess.run() specifically so a fetch that TIMES OUT (a weak/
    # dropped connection right when a save is trying to set up the
    # worktree for the very first time this process) falls through to the
    # exact same "-B branch, based on local HEAD" fallback below that an
    # ordinary fetch failure already used - the save can still commit
    # locally and be pushed later by the autosave retry heartbeat, instead
    # of failing outright just because the network happened to be down at
    # that moment.
    fetch = _run_git_or_timeout(
        ["git", "fetch", remote, branch], repo_root, _GIT_NETWORK_TIMEOUT_SECONDS,
    )
    if fetch.returncode == 0:
        add = subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "FETCH_HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
    else:
        add = subprocess.run(
            ["git", "worktree", "add", "-B", branch, str(worktree), "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
        )
    if add.returncode != 0:
        return None, (add.stderr or add.stdout).strip()
    return worktree, None


def _copy_into_worktree(src: Path, dest: Path) -> None:
    """Mirrors one `paths` entry (commit_and_push_data()'s copy-into-
    worktree step) from repo_root's own copy at `src` to the worktree's
    matching location at `dest`. `dest`'s own parent is assumed to already
    exist (the caller creates it) - this only ever touches `dest` itself.

    Punch-list #71: `src` can genuinely be a directory - both of the Tackle
    Box page's photo-touching saves (adding a lure with a photo, deleting
    one) pass core.lure_inventory.IMAGES_DIR whole, not a single file, and
    commit_and_push()'s own docstring above has always promised "files or
    directories" - this just never actually implemented that for the
    worktree-copy step `commit_and_push_data()` added on top. Before this
    fix, `shutil.copy2(a_directory, dest)` raised a bare `IsADirectoryError`
    the instant a save touched IMAGES_DIR (confirmed live - see
    SESSION_NOTES.md punch-list #71) - caught by commit_and_push_data()'s
    own outer `except Exception`, so the WHOLE save (not just the photo)
    silently failed to push: `data/lure_inventory.csv`'s new row usually
    still made it to GitHub eventually (any later, unrelated save that
    didn't happen to touch IMAGES_DIR - e.g. editing another item's
    quantity - carries every locally-written row along, images or not), but
    the actual photo file never did, since only these two call sites ever
    reference IMAGES_DIR at all. A restart re-syncing data/ from the `data`
    branch (core.storage.sync_data_from_data_branch()) would then show the
    row with its `image_filename` intact but no matching file on disk -
    exactly "the rest of the information was there but no picture."

    A directory is mirrored as a full, fresh copy (delete-then-copytree)
    rather than a merge, so a file removed from `src` since the last save
    (e.g. delete_item() removing one lure's photo) is correctly reflected
    as removed in the worktree copy too, not left behind as an orphan the
    next `git add` on that same directory would never notice.
    """
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    elif src.exists():
        shutil.copy2(src, dest)
    elif dest.exists():
        dest.unlink()


def commit_and_push_data(
    paths: list,
    github_token: str,
    repo_slug: str,
    commit_message: str,
    repo_root: Path = REPO_ROOT,
    max_push_retries: int = 3,
    remote_url: Optional[str] = None,
    retry_backoff_seconds: float = 1.0,
) -> tuple:
    """Punch-list #52: the function every real in-app data save should call
    instead of commit_and_push() directly - hardcoded to DATA_BRANCH rather
    than accepting a branch argument, deliberately, so a future call site
    can't accidentally reintroduce the redeploy-storm bug by omitting a
    branch= kwarg. See the module docstring above for the full "why".

    Punch-list #67: the actual `git add`/`git commit`/`git push` this does
    now run inside an isolated worktree (_ensure_data_worktree() above),
    never inside repo_root itself - each path in `paths` (absolute, like
    every real call site's TRIP_LOG_PATH-style constant, or repo_root-
    relative, like this module's own tests use) is copied into the
    worktree's mirrored location immediately before committing there, so
    the worktree always reflects exactly the same file content repo_root's
    own copy just got written with. Falls back to a "saved locally"-style
    failure message (matching commit_and_push()'s own failure shape) if
    the worktree itself can't be created - the caller's own file write to
    repo_root already succeeded by the time this runs either way, so
    nothing about the local save is lost even if this fails.

    Punch-list #68: the worktree-copy-then-commit-then-push sequence below
    now runs under data_write_lock() - see its docstring. The same worktree
    directory is shared by every data file this app ever saves, so without
    this, two overlapping calls (from two concurrent sessions, or an old and
    a freshly-booted process briefly alive together across a redeploy) could
    copy into and `git commit` the same worktree at the same time - exactly
    the mechanism confirmed behind a real corruption incident (see
    SESSION_NOTES.md punch-list #68).

    Punch-list #71: the copy step genuinely supports "files or directories"
    now, matching what commit_and_push()'s own docstring above always
    promised - it silently didn't for a whole directory (e.g.
    core.lure_inventory.IMAGES_DIR, passed whole by both of the Tackle Box
    page's "Add a lure with a photo" and "Delete" call sites) until this
    fix. See _copy_into_worktree() below."""
    if not github_token:
        return False, "No GITHUB_TOKEN configured - saved locally only for this session."
    try:
        with data_write_lock(repo_root):
            remote = _resolve_remote_url(github_token, repo_slug, remote_url)
            worktree, err = _ensure_data_worktree(repo_root, remote, DATA_BRANCH)
            if worktree is None:
                return False, f"Saved locally, but couldn't prepare the data worktree: {err}"

            resolved_root = Path(repo_root).resolve()
            dest_paths = []
            for p in paths:
                p = Path(p)
                src = p if p.is_absolute() else (resolved_root / p)
                try:
                    rel = src.resolve().relative_to(resolved_root)
                except ValueError:
                    # Not under repo_root at all - shouldn't happen for any
                    # real call site, but use it as-is rather than failing the
                    # whole save over a path that doesn't fit the usual shape.
                    rel = p
                dest = worktree / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                _copy_into_worktree(src, dest)
                dest_paths.append(str(rel))

            return commit_and_push(
                dest_paths, github_token, repo_slug, commit_message, branch=DATA_BRANCH,
                repo_root=worktree, max_push_retries=max_push_retries, remote_url=remote_url,
                retry_backoff_seconds=retry_backoff_seconds,
            )
    except Exception as e:
        return False, f"Saved locally, but push failed: {e}"


def push_pending_data(
    github_token: str,
    repo_slug: str,
    repo_root: Path = REPO_ROOT,
    max_push_retries: int = 3,
    remote_url: Optional[str] = None,
    retry_backoff_seconds: float = 1.0,
) -> tuple:
    """The DATA_BRANCH-hardcoded sibling of push_pending(), matching how
    commit_and_push_data() relates to commit_and_push() - see push_pending()
    for what this actually does and why. This is the one every in-app
    autosave-retry call site should use (pages/6_Spot_Session.py), for the
    same "never let a call site accidentally target main" reason
    commit_and_push_data() itself exists.

    Punch-list #67: retries against the SAME isolated worktree
    commit_and_push_data() committed into (_ensure_data_worktree() reuses
    whatever's already on disk at that path), never against repo_root -
    whatever's sitting committed-but-unpushed after a prior failed push is
    in the worktree, not repo_root, now that commit_and_push_data() never
    commits there. If no worktree exists yet at all (nothing has ever been
    committed this way in this process), there's nothing pending by
    definition - returns the same harmless-success shape push_pending()
    itself returns for a no-op push, rather than treating "no worktree
    yet" as an error.

    Punch-list #68: also runs under data_write_lock() - see
    commit_and_push_data()'s docstring - so a retry here can't race a
    concurrent commit_and_push_data() call touching the same worktree."""
    if not github_token:
        return False, "No GITHUB_TOKEN configured - saved locally only for this session."
    with data_write_lock(repo_root):
        worktree = _data_worktree_dir(repo_root)
        if not (worktree / ".git").exists():
            return True, "Nothing pending - no local data save has happened yet this process."
        return push_pending(
            github_token, repo_slug, branch=DATA_BRANCH, repo_root=worktree,
            max_push_retries=max_push_retries, remote_url=remote_url,
            retry_backoff_seconds=retry_backoff_seconds,
        )


def sync_data_from_data_branch(
    github_token: str,
    repo_slug: str,
    repo_root: Path = REPO_ROOT,
    remote_url: Optional[str] = None,
    branch: str = DATA_BRANCH,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
) -> tuple:
    """Punch-list #52: overlays repo_root's data/ directory with DATA_BRANCH's
    latest content, WITHOUT switching repo_root off of whatever branch it's
    actually checked out on (main, in every real deployment). Meant to be
    called once per process boot - see app.py's st.cache_resource-guarded
    call - so a freshly started process picks up every real save since the
    last boot instead of serving whatever data/ happened to be frozen into
    main at the punch-list #52 cutover (or, for a brand new machine, an
    even older snapshot).

    Works by fetching `branch` and then `git checkout FETCH_HEAD -- data`,
    which restores/updates every tracked path under data/ to match that
    commit's tree without touching HEAD or any other file in the repo.
    Note this only ever adds/updates files - if a file were ever deleted on
    the data branch, a copy left over locally under data/ wouldn't be
    removed by this alone. That's never happened in this app's history and
    isn't handled here; worth a `git clean`-style follow-up if it ever does.

    Never raises, and treats every failure as a soft no-op rather than
    something that should block the app from booting: no token configured,
    the data branch not existing yet (the very first boot before the
    one-time cutover), a persistent network/auth error - any of these just
    means the app keeps running on whatever's already on disk, exactly as
    it did before this function existed.

    Punch-list #73 (live incident - Trip History reverted to a last entry
    date of 8/23, matching `main`'s own frozen data/trip_log.csv snapshot
    to the row): the fetch step now retries a transient network failure
    (dropped connection, DNS hiccup, GitHub's edge returning a 5xx - the
    exact same `_is_transient_network_error()` check commit_and_push()'s own
    retry loop already uses, punch-list #58) up to `max_retries` times with
    a short backoff, instead of giving up after one attempt. This matters
    specifically for this function because of HOW it's called: app.py's
    `_sync_data_once()` wraps it in `st.cache_resource`, which runs it
    exactly ONCE per process and permanently remembers that it ran - it does
    NOT check whether the call actually succeeded. A single flaky moment
    (very plausible right at cold boot, when a freshly started container's
    outbound network may not be fully warmed up yet) used to mean that
    process would serve `main`'s frozen data/ for its ENTIRE remaining
    lifetime, with no automatic retry and nothing visibly wrong - exactly
    what happened live after this session's own run of back-to-back
    redeploys (#69/#70/#71/#72) made a boot-time fluke more likely to
    actually land on one of them. A non-network failure (bad auth, the data
    branch not existing yet) still returns immediately without retrying,
    same as before - retrying those just burns the retry budget for a
    result that won't change. See app.py's `_sync_data_once()` for the
    other half of this fix: it now re-raises on a still-unsuccessful result
    so `st.cache_resource` doesn't memoize the failure either, letting the
    very next page interaction try again rather than being stuck forever.

    **A future coding session should know:** because app.py only calls this
    ONCE per process boot (now: once per process boot that ends in success -
    see punch-list #73 above), a change pushed straight to DATA_BRANCH from
    OUTSIDE a live running app - a hand-run data migration/backfill script,
    a manual CSV edit, anything committed and pushed the way a Claude
    coding session does it - will NOT be visible in the already-running
    live app until that process next restarts (a `main` push triggers one;
    Streamlit Cloud's own idle-reboot cycle is the other). Confirmed via a
    real case: the punch-list #55 session_id backfill (SESSION_NOTES.md
    entries 117/118) was pushed to `data` correctly, but the user reported
    seeing stale (ungrouped) sessions in the live app afterward - the data
    was right, the running process just hadn't re-synced yet. Two ways to
    close that gap for a user waiting right now: (1) push any real commit
    to `main` (triggers a redeploy, which reboots and re-syncs), or (2) use
    the manual "🔄 Refresh from GitHub" button on Trip History (entry 119),
    which calls this function directly, bypassing the once-per-boot guard.
    """
    if not github_token:
        return False, "No GITHUB_TOKEN configured - using whatever data/ already has locally."
    remote = _resolve_remote_url(github_token, repo_slug, remote_url)
    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            fetch = subprocess.run(
                ["git", "fetch", remote, branch], cwd=repo_root, capture_output=True, text=True,
                timeout=_GIT_NETWORK_TIMEOUT_SECONDS,
            )
            if fetch.returncode != 0:
                stderr = fetch.stderr.strip()
                last_error = stderr
                transient = _is_transient_network_error(stderr)
                if transient and attempt < max_retries:
                    time.sleep(retry_backoff_seconds * attempt)
                    continue
                if transient:
                    # Retries exhausted on a genuinely transient error - say
                    # so plainly (matches commit_and_push()'s own
                    # "after N attempts" retry-exhaustion phrasing) rather
                    # than the misleading "may not exist yet" wording below,
                    # which is meant for a real one-shot failure (bad auth,
                    # the branch genuinely missing), not "kept timing out."
                    return False, (
                        f"Data branch sync skipped after {max_retries} attempts: {stderr}"
                    )
                return False, (
                    f"Data branch sync skipped (fetch of '{branch}' failed - it may not exist yet): "
                    f"{stderr}"
                )
            checkout = subprocess.run(
                ["git", "checkout", "FETCH_HEAD", "--", "data"], cwd=repo_root, capture_output=True, text=True,
                timeout=_GIT_LOCAL_TIMEOUT_SECONDS,
            )
            if checkout.returncode != 0:
                # A checkout failure isn't a network hiccup - retrying the
                # exact same checkout wouldn't change the outcome.
                return False, f"Data branch sync skipped (checkout failed): {checkout.stderr.strip()}"
            return True, f"Synced data/ from the '{branch}' branch."
        except Exception as e:
            # Punch-list #76: this already-broad except (existed before that
            # fix) also catches subprocess.TimeoutExpired now that both git
            # calls above pass timeout= - a fetch/checkout that hangs past
            # its timeout retries with backoff exactly like any other
            # exception here always has, no changes needed to this clause.
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * attempt)
                continue
            return False, f"Data branch sync skipped: {e}"
    return False, f"Data branch sync skipped after {max_retries} attempts: {last_error}"
