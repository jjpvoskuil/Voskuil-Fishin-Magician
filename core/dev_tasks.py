"""
Development punch list - a running list of things the angler wants adjusted
or fixed in the app itself, tracked inside the app so it survives between
Claude sessions the same way trip logs and inventory do.

Mirrors core/lure_inventory.py's storage pattern: rows live in
data/dev_tasks.csv inside the repo, and when a GITHUB_TOKEN is configured,
changes are committed and pushed back (via core.storage.commit_and_push) so
the list survives Streamlit Cloud restarts; without one, changes still
work, just for the current session.

Each entry gets a small, stable, human-friendly integer `task_no` (not a
uuid, unlike every other data file in this app) - the whole point of this
page is so the angler can say "let's do #7 next session" and a future
Claude session can find it immediately. task_no is assigned once, on
creation, and is never reused or reassigned - see append_task().

Deliberately append-only (no delete_task): a punch-list item is meant to
stay referenceable by its number even after it's done, so "check off when
complete" (status -> "Done") is the only way an item leaves the open list,
not removal. If unwanted items ever pile up, trimming data/dev_tasks.csv by
hand is always an option, but the app itself doesn't offer a delete action.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_TASKS_PATH = REPO_ROOT / "data" / "dev_tasks.csv"

FIELDNAMES = [
    "task_no", "created_at", "description", "page", "status", "completed_at",
]

STATUS_OPEN = "Open"
STATUS_DONE = "Done"

# What page/area an item is mainly associated with. Matches app.py's real
# page titles so a punch-list entry can point straight at the page it's
# about, plus a couple of catch-all options for anything that doesn't fit
# one specific page.
PAGE_OPTIONS = [
    "Today (Home)",
    "7 Day Forecast",
    "Lake Map",
    "Trip History",
    "Lure Inventory",
    "Spot Session",
    "Development",
    "General / whole app",
    "Data / backend (not page-specific)",
]


@dataclass
class DevTask:
    description: str
    page: str
    status: str = STATUS_OPEN
    task_no: int = 0  # real value assigned by append_task(), never left at 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str = ""

    def to_row(self) -> dict:
        d = asdict(self)
        return {k: d.get(k, "") for k in FIELDNAMES}


def ensure_dev_tasks_exists(path: Path = DEV_TASKS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def read_all_tasks(path: Path = DEV_TASKS_PATH) -> list:
    ensure_dev_tasks_exists(path)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _next_task_no(rows: list) -> int:
    nums = [int(r["task_no"]) for r in rows if str(r.get("task_no", "")).strip().isdigit()]
    return max(nums, default=0) + 1


def append_task(description: str, page: str, path: Path = DEV_TASKS_PATH) -> DevTask:
    """Create and save a new punch-list item, auto-assigning the next task_no
    (existing rows' highest task_no + 1, starting at 1 for an empty list)."""
    ensure_dev_tasks_exists(path)
    rows = read_all_tasks(path)
    task = DevTask(description=description.strip(), page=page, task_no=_next_task_no(rows))
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(task.to_row())
    return task


def _write_rows(rows: list, path: Path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def update_task(task_no, path: Path = DEV_TASKS_PATH, **changes) -> bool:
    """Update fields on an existing item by task_no. Returns True if found.
    task_no is compared as a string against the CSV's own string values, so
    callers can pass either an int or a str."""
    rows = read_all_tasks(path)
    found = False
    for row in rows:
        if str(row["task_no"]) == str(task_no):
            row.update({k: v for k, v in changes.items() if k in FIELDNAMES})
            found = True
            break
    if found:
        _write_rows(rows, path)
    return found


def mark_done(task_no, path: Path = DEV_TASKS_PATH) -> bool:
    return update_task(
        task_no, path, status=STATUS_DONE, completed_at=datetime.utcnow().isoformat(),
    )


def reopen_task(task_no, path: Path = DEV_TASKS_PATH) -> bool:
    return update_task(task_no, path, status=STATUS_OPEN, completed_at="")
