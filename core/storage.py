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
    predicted_score: float
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


def commit_and_push(paths: list, github_token: str, repo_slug: str, commit_message: str, branch: str = "main") -> tuple:
    """
    Commit the given paths (files or directories, repo-relative or absolute)
    and push using a fine-grained PAT. Returns (success: bool, message: str).
    Never raises - designed to be called from Streamlit and surface a
    friendly warning on failure.
    """
    if not github_token:
        return False, "No GITHUB_TOKEN configured - saved locally only for this session."
    try:
        remote = f"https://x-access-token:{github_token}@github.com/{repo_slug}.git"
        subprocess.run(["git", "config", "user.email", "fishin-magician@bot.local"], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "config", "user.name", "Fishin' Magician Bot"], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "add"] + [str(p) for p in paths], cwd=REPO_ROOT, check=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
        if diff.returncode == 0:
            return True, "No changes to commit."
        subprocess.run(["git", "commit", "-m", commit_message], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "push", remote, f"HEAD:{branch}"], cwd=REPO_ROOT, check=True, capture_output=True)
        return True, "Saved and pushed to GitHub."
    except subprocess.CalledProcessError as e:
        return False, f"Saved locally, but push failed: {e}"
