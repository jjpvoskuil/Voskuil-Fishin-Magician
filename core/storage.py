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
"""
from __future__ import annotations
import csv
import io
import json
import subprocess
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIP_LOG_PATH = REPO_ROOT / "data" / "trip_log.csv"

# Punch-list #52: the branch every in-app data save pushes to - see the
# module docstring above. Streamlit Cloud never watches this branch, so
# pushing here never triggers a redeploy.
DATA_BRANCH = "data"

FIELDNAMES = [
    "trip_id", "logged_at", "trip_date", "segment", "spot_id", "spot_name",
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


def append_trip(entry: TripEntry):
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
    something else while an edit was in progress."""
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
    row with that trip_id exists."""
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


def commit_and_push(
    paths: list,
    github_token: str,
    repo_slug: str,
    commit_message: str,
    branch: str = "main",
    repo_root: Path = REPO_ROOT,
    max_push_retries: int = 3,
    remote_url: Optional[str] = None,
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
    practice), and push again. Only a genuine non-fast-forward rejection is
    retried this way - any other failure (auth, network, a real rebase
    conflict) returns immediately with a message describing what happened,
    same as before this retry loop existed.

    repo_root defaults to the real repo checkout (REPO_ROOT) so every real
    caller behaves exactly as before; tests point it at a throwaway git repo
    instead of touching the real one - same "optional path parameter,
    defaults to the real constant" pattern already used by
    core/forecast_freeze.py/core/lure_inventory.py. remote_url similarly
    defaults to None (the real github.com PAT URL, built from github_token/
    repo_slug exactly as before); tests pass a local file:// bare-repo URL
    instead, so the retry/rebase logic below can be exercised against real
    git plumbing (a genuine concurrent-push race) rather than only mocked
    subprocess calls.
    """
    if not github_token:
        return False, "No GITHUB_TOKEN configured - saved locally only for this session."
    try:
        remote = _resolve_remote_url(github_token, repo_slug, remote_url)
        subprocess.run(["git", "config", "user.email", "fishin-magician@bot.local"], cwd=repo_root, check=True)
        subprocess.run(["git", "config", "user.name", "Fishin' Magician Bot"], cwd=repo_root, check=True)
        subprocess.run(["git", "add"] + [str(p) for p in paths], cwd=repo_root, check=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
        if diff.returncode == 0:
            return True, "No changes to commit."
        subprocess.run(["git", "commit", "-m", commit_message], cwd=repo_root, check=True)

        last_error = ""
        for attempt in range(1, max_push_retries + 1):
            push = subprocess.run(
                ["git", "push", remote, f"HEAD:{branch}"],
                cwd=repo_root, capture_output=True, text=True,
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
            if not rejected:
                return False, f"Saved locally, but push failed: {last_error}"
            if attempt == max_push_retries:
                break

            fetch = subprocess.run(
                ["git", "fetch", remote, branch], cwd=repo_root, capture_output=True, text=True,
            )
            if fetch.returncode != 0:
                return False, f"Saved locally, but push failed and the retry fetch also failed: {fetch.stderr.strip()}"

            rebase = subprocess.run(
                ["git", "rebase", "FETCH_HEAD"], cwd=repo_root, capture_output=True, text=True,
            )
            if rebase.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], cwd=repo_root)
                return False, (
                    "Saved locally, but another device's save conflicted with this one "
                    "and couldn't be auto-merged - please retry the save."
                )
            # Rebased onto the latest remote branch - loop around and retry the push.

        return False, (
            f"Saved locally, but push failed after {max_push_retries} attempts "
            f"(another device kept saving at the same time): {last_error}"
        )
    except subprocess.CalledProcessError as e:
        return False, f"Saved locally, but push failed: {e}"


def commit_and_push_data(
    paths: list,
    github_token: str,
    repo_slug: str,
    commit_message: str,
    repo_root: Path = REPO_ROOT,
    max_push_retries: int = 3,
    remote_url: Optional[str] = None,
) -> tuple:
    """Punch-list #52: the function every real in-app data save should call
    instead of commit_and_push() directly. Identical to commit_and_push()
    in every way except it's hardcoded to DATA_BRANCH rather than accepting
    a branch argument - deliberately, so a future call site can't
    accidentally reintroduce the redeploy-storm bug by omitting a branch=
    kwarg. See the module docstring above for the full "why"."""
    return commit_and_push(
        paths, github_token, repo_slug, commit_message, branch=DATA_BRANCH,
        repo_root=repo_root, max_push_retries=max_push_retries, remote_url=remote_url,
    )


def sync_data_from_data_branch(
    github_token: str,
    repo_slug: str,
    repo_root: Path = REPO_ROOT,
    remote_url: Optional[str] = None,
    branch: str = DATA_BRANCH,
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
    one-time cutover), a transient network/auth error - any of these just
    means the app keeps running on whatever's already on disk, exactly as
    it did before this function existed.
    """
    if not github_token:
        return False, "No GITHUB_TOKEN configured - using whatever data/ already has locally."
    try:
        remote = _resolve_remote_url(github_token, repo_slug, remote_url)
        fetch = subprocess.run(
            ["git", "fetch", remote, branch], cwd=repo_root, capture_output=True, text=True,
        )
        if fetch.returncode != 0:
            return False, (
                f"Data branch sync skipped (fetch of '{branch}' failed - it may not exist yet): "
                f"{fetch.stderr.strip()}"
            )
        checkout = subprocess.run(
            ["git", "checkout", "FETCH_HEAD", "--", "data"], cwd=repo_root, capture_output=True, text=True,
        )
        if checkout.returncode != 0:
            return False, f"Data branch sync skipped (checkout failed): {checkout.stderr.strip()}"
        return True, f"Synced data/ from the '{branch}' branch."
    except Exception as e:
        return False, f"Data branch sync skipped: {e}"
