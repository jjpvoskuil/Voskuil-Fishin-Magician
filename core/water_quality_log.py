"""
Local, git-backed historical log of USACE surface water-quality readings -
punch-list #13's "longer trend" chart for the Corps of Engineers data on
the Today page.

core/lake_water_quality.py's fetch_surface_water_quality() only ever
returns the CURRENT reading - the live report page itself has no history,
just whatever the most recent manual survey found (see that module's
docstring, and SESSION_NOTES.md's punch-list #69 entry, for the exhaustive
search that confirmed no external source publishes a real historical time
series for this lake's water temp/DO). There's no way to backfill genuine
past readings, so this app starts recording its own archive going forward
instead: every time home.py successfully fetches a fresh reading,
append_if_new() saves it here unless that exact survey has already been
logged - same git-committed-CSV persistence pattern data/trip_log.csv
(core/storage.py) and data/lure_inventory.csv (core/lure_inventory.py)
already use, so the log survives Streamlit Cloud restarts/redeploys via
core.storage.commit_and_push().

Because USACE only republishes this survey roughly every 1-2 weeks, the
resulting trend chart starts sparse (as little as a single point, the day
this feature ships) and fills in gradually over subsequent weeks - by
design, never fabricated or backfilled with synthetic history.
"""
from __future__ import annotations
import csv
from datetime import datetime
from pathlib import Path

from .lake_water_quality import SurfaceWaterQuality
from .storage import data_write_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
WATER_QUALITY_LOG_PATH = REPO_ROOT / "data" / "water_quality_log.csv"

FIELDNAMES = ["observed_at", "water_temp_f", "do_mg_l", "do_saturation_pct"]


def ensure_log_exists(path: Path = WATER_QUALITY_LOG_PATH):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def read_log(path: Path = WATER_QUALITY_LOG_PATH) -> list:
    """Returns every logged reading, oldest first (the order rows were
    appended in, which is always chronological since append_if_new() only
    ever adds the current live reading)."""
    ensure_log_exists(path)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append_if_new(reading: SurfaceWaterQuality, path: Path = WATER_QUALITY_LOG_PATH) -> bool:
    """Appends `reading` unless a row for the same observed_at timestamp is
    already logged. get_surface_water_quality() (core/appstate.py) is
    cached for 6 hours but still gets re-fetched many times across days/
    weeks of app usage while the underlying USACE survey itself hasn't
    actually changed - only a genuinely NEW survey date should ever add a
    row, so every call here is a cheap no-op except roughly once every 1-2
    weeks when USACE actually republishes. Returns True if a row was
    actually appended (i.e. this is a reading not seen before)."""
    # Punch-list #68: exists-check-then-append guarded by data_write_lock()
    # (see core.storage's docstring) so two near-simultaneous fetches of a
    # genuinely new reading can't both pass the exists-check and both append.
    with data_write_lock():
        ensure_log_exists(path)
        observed_at_iso = reading.observed_at.isoformat()
        if any(row["observed_at"] == observed_at_iso for row in read_log(path)):
            return False
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow({
                "observed_at": observed_at_iso,
                "water_temp_f": reading.water_temp_f,
                "do_mg_l": reading.do_mg_l,
                "do_saturation_pct": reading.do_saturation_pct,
            })
        return True


def parsed_log(path: Path = WATER_QUALITY_LOG_PATH) -> list:
    """Same rows as read_log(), but with observed_at parsed to a real
    datetime and the numeric fields parsed to float - what home.py's chart
    code actually wants, kept separate from read_log() so a corrupted/
    partially-written row (e.g. an interrupted write) degrades to being
    skipped here rather than raising and taking the whole Today page down
    with it."""
    rows = []
    for row in read_log(path):
        try:
            rows.append({
                "observed_at": datetime.fromisoformat(row["observed_at"]),
                "water_temp_f": float(row["water_temp_f"]),
                "do_mg_l": float(row["do_mg_l"]),
                "do_saturation_pct": float(row["do_saturation_pct"]),
            })
        except (KeyError, ValueError):
            continue
    return rows
