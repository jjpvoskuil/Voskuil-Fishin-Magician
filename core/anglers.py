"""
Angler roster - punch-list #26's lightweight multi-user support.

The angler asked whether two people (now: the angler, his son, and anyone
else who joins) could each log their own activity under their own name,
while still keeping everything combined in one shared trip log for Trip
History/analytics. Two designs were discussed: (1) a simple, password-free
"who's fishing" name picker that just tags each trip with a name, vs. (2)
real separate logins via Streamlit's native st.login()/OIDC (actual
identity, but needs an OAuth app + secrets.toml wiring). Given this is a
small, private deployment among family/friends, not a multi-tenant public
app, option (1) was the clear fit - no accounts, no passwords, small lift.

This module only stores the ROSTER of names the "Who's fishing" dropdown on
pages/6_Spot_Session.py offers - not per-trip attribution itself, which
lives in core.storage.TripEntry.conditions["angler"] (the flexible
conditions dict, same as most other fields that page logs - see
core/storage.py's FIELDNAMES for why a new top-level CSV column was
deliberately avoided: it would need a one-time migration of the existing,
already-committed data/trip_log.csv header, where the conditions dict just
works with the file exactly as it already is).

Starts seeded with the angler's three named anglers; picking "Other" on the
Spot Session page and typing a new name calls add_angler() to permanently
add it here (git-committed like every other small list in this app -
data/dev_tasks.csv, data/lure_inventory.csv, data/lake_spots.csv, ...) so
it shows up as a real dropdown choice on every future visit, not just this
one session - see pages/6_Spot_Session.py for where that save actually
happens (only at the point a trip is actually logged, not just for typing
into the field, so idly trying the "Other" box doesn't itself commit
anything).
"""
from __future__ import annotations
import csv
from pathlib import Path

from core.storage import data_write_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
ANGLERS_PATH = REPO_ROOT / "data" / "anglers.csv"

FIELDNAMES = ["name"]

# The angler's own named anglers - seeded once, the first time this file is
# created. After that, this constant is never consulted again; the CSV file
# is the sole source of truth (including for these three original names -
# any of them could be edited or removed by hand-editing the CSV, same as
# anything else in data/).
DEFAULT_ANGLERS = ["John", "Matthew", "Alex"]

# The dropdown's own "type in a new name" sentinel - imported by
# pages/6_Spot_Session.py rather than hand-typing the string a second time.
OTHER_LABEL = "Other (type in a name)"


def ensure_anglers_exists(path: Path = ANGLERS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for name in DEFAULT_ANGLERS:
                writer.writerow({"name": name})


def read_anglers(path: Path = ANGLERS_PATH) -> list:
    """Returns the roster as a plain list of names, in file order, with
    accidental exact-duplicate rows (e.g. from a hand-edit) collapsed -
    case-insensitively, keeping the first-seen spelling/capitalization."""
    ensure_anglers_exists(path)
    with open(path, newline="") as f:
        names = [row["name"].strip() for row in csv.DictReader(f) if row.get("name", "").strip()]
    seen = set()
    unique = []
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
    return unique


def add_angler(name: str, path: Path = ANGLERS_PATH) -> bool:
    """Appends a new name to the roster if it isn't already on it
    (case-insensitive) and isn't blank. Returns True only when a row was
    actually added, so a caller can tell "this really is a brand-new name,
    worth a git commit" apart from "blank" or "already a dropdown choice" -
    see pages/6_Spot_Session.py's save handlers, which only push
    data/anglers.csv to GitHub when this returns True."""
    # Punch-list #68: the exists-check-then-append below is guarded by
    # data_write_lock() (see core.storage's docstring) so two concurrent
    # "Other" adds of the same new name can't both pass the exists-check
    # and both append a duplicate row.
    name = (name or "").strip()
    if not name:
        return False
    with data_write_lock():
        existing = read_anglers(path)
        if any(existing_name.lower() == name.lower() for existing_name in existing):
            return False
        ensure_anglers_exists(path)
        with open(path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writerow({"name": name})
        return True
