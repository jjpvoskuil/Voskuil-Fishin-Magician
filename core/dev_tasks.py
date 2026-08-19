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
creation, and is never reused - see _next_task_no()/append_task() below.
Editing an item (description/page/status) or deleting it entirely never
changes its number or any other item's number.

Numbering is backed by a small sidecar counter file (dev_tasks_counter.txt,
next to dev_tasks.csv) rather than derived from "highest task_no currently
in the file" - the latter would let a number get reused after the
highest-numbered item is deleted (e.g. items #1-#5 exist, #5 is deleted,
the next new item would become #5 again under a live-max scheme), which
would be actively confusing for a set of ids specifically designed to be
memorized and referenced by number. The counter file only ever increases.
If it doesn't exist yet (a fresh dev_tasks.csv, or one that predates this
counter), it's bootstrapped from the highest task_no already present.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_TASKS_PATH = REPO_ROOT / "data" / "dev_tasks.csv"
DEV_TASKS_COUNTER_PATH = DEV_TASKS_PATH.with_name("dev_tasks_counter.txt")

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
    "Tackle Box",
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


def _counter_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_counter.txt")


def _next_task_no(path: Path = DEV_TASKS_PATH) -> int:
    counter_file = _counter_path(path)
    if counter_file.exists():
        try:
            return int(counter_file.read_text().strip())
        except ValueError:
            pass  # corrupt counter file - fall through to the bootstrap below
    # No counter file yet (a fresh list, or one saved before this counter
    # existed) - bootstrap from whatever's already in the CSV.
    rows = read_all_tasks(path)
    nums = [int(r["task_no"]) for r in rows if str(r.get("task_no", "")).strip().isdigit()]
    return max(nums, default=0) + 1


def _save_next_task_no(path: Path, next_no: int):
    _counter_path(path).write_text(str(next_no))


def append_task(description: str, page: str, path: Path = DEV_TASKS_PATH) -> DevTask:
    """Create and save a new punch-list item, auto-assigning the next
    task_no (see _next_task_no()/module docstring) and advancing the
    counter file so that number is never handed out again."""
    ensure_dev_tasks_exists(path)
    task_no = _next_task_no(path)
    task = DevTask(description=description.strip(), page=page, task_no=task_no)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(task.to_row())
    _save_next_task_no(path, task_no + 1)
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


def delete_task(task_no, path: Path = DEV_TASKS_PATH) -> bool:
    """Remove the item with this task_no entirely. Returns False (no-op,
    file untouched) if no row with that task_no exists. Never touches the
    counter file, so a deleted item's number is never reassigned to a
    later item - see module docstring."""
    rows = read_all_tasks(path)
    remaining = [r for r in rows if str(r["task_no"]) != str(task_no)]
    deleted = len(remaining) != len(rows)
    if deleted:
        _write_rows(remaining, path)
    return deleted


def mark_done(task_no, path: Path = DEV_TASKS_PATH) -> bool:
    return update_task(
        task_no, path, status=STATUS_DONE, completed_at=datetime.utcnow().isoformat(),
    )


def reopen_task(task_no, path: Path = DEV_TASKS_PATH) -> bool:
    return update_task(task_no, path, status=STATUS_OPEN, completed_at="")
