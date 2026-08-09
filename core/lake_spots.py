"""
User-created fishing spot pins for Nolin River Lake.

Distinct from core/spots.py's curated data/nolin_spots.json (a handful of
general reference spots anchored to public sources, still used elsewhere
for trip logging on pages/3_Log_a_Trip.py) - this is the angler's own,
personal catalog of specific spots they've found on the water and want to
remember: drop a pin on the Lake Map page and record what kind of spot it
is, what the bottom is made of, how deep the main area and its drop-off
are, and how sharp that drop-off is.

Mirrors core/lure_inventory.py's storage pattern: rows live in
data/lake_spots.csv inside the repo, and when a GITHUB_TOKEN is
configured, changes are committed and pushed back (via
core.storage.commit_and_push) so they survive Streamlit Cloud restarts;
without one, changes still work, just for the current session.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

from .lures import STRUCTURE_TYPES

REPO_ROOT = Path(__file__).resolve().parent.parent
SPOTS_PATH = REPO_ROOT / "data" / "lake_spots.csv"

# What kind of physical spot this is. Deliberately its own vocabulary,
# separate from core.lures.STRUCTURE_TYPES (which describes fishing
# situations for the day/segment recommendation engine, and doesn't
# distinguish e.g. a natural rock bluff from man-made riprap the way an
# angler cataloging real spots would want to) - this is a personal spot
# catalog first. LOCATION_TYPE_TO_STRUCTURE_TYPE below bridges the two
# vocabularies for the one place that needs both: getting lure suggestions
# for a specific saved spot (pages/6_Spot_Session.py).
LOCATION_TYPES = [
    "Main-lake point",
    "Secondary / pocket point",
    "Flat",
    "Creek channel / ledge",
    "Rock face / bluff",
    "Riprap",
    "Boat dock",
    "Bridge piling",
    "Cove / pocket (shallow cover)",
    "Standing timber",
    "Roadbed / old ford",
    "Other",
]

# What the bottom is actually made of at the spot. Multi-select, since a
# real spot is often more than one of these at once (e.g. rocky with some
# laydowns mixed in).
BOTTOM_STRUCTURE_OPTIONS = [
    "Rocky", "Gravel", "Sand", "Clay / hardpan", "Mud / silt",
    "Weeds / grass", "Standing timber", "Laydowns / brush", "Stumps",
    "Boulders", "Riprap",
]

# How sharply the bottom falls away from the main/shallow part of the spot
# toward its transition depth - a steep ("High") break concentrates fish
# along a short stretch, while a gradual ("Low") taper spreads them out
# over a wider area.
TRANSITION_GRADE_OPTIONS = ["High (steep break)", "Medium", "Low (gradual taper)"]

# Bridges a saved spot's location_type to the closest core.lures.STRUCTURE_TYPES
# value, for the one place that needs it: pages/6_Spot_Session.py passes a
# saved spot's structure into core.lures.recommend() to get lure suggestions
# for that exact spot. Every LOCATION_TYPES value has an entry so lookups
# never need a fallback default; several map to the same STRUCTURE_TYPES
# value where the recommendation engine doesn't distinguish further (e.g.
# both point types just mean "Main-lake point" to the lure engine).
LOCATION_TYPE_TO_STRUCTURE_TYPE = {
    "Main-lake point": "Main-lake point",
    "Secondary / pocket point": "Main-lake point",
    "Flat": "Flat",
    "Creek channel / ledge": "Creek channel / ledge",
    "Rock face / bluff": "Riprap / dam face",
    "Riprap": "Riprap / dam face",
    "Boat dock": "Boat dock",
    "Bridge piling": "Bridge piling",
    "Cove / pocket (shallow cover)": "Cove / pocket (shallow cover)",
    "Standing timber": "Standing timber",
    "Roadbed / old ford": "Flat",
    "Other": "Main-lake point",
}

assert set(LOCATION_TYPE_TO_STRUCTURE_TYPE) == set(LOCATION_TYPES)
assert set(LOCATION_TYPE_TO_STRUCTURE_TYPE.values()) <= set(STRUCTURE_TYPES)

FIELDNAMES = [
    "spot_id", "added_at", "updated_at", "name", "lat", "lon",
    "location_type", "bottom_structure", "main_depth_ft", "transition_depth_ft",
    "transition_grade", "notes",
]


@dataclass
class LakeSpot:
    name: str
    lat: float
    lon: float
    location_type: str = ""
    bottom_structure: list = field(default_factory=list)  # stored as a "|"-joined string in the CSV
    main_depth_ft: Optional[float] = None
    transition_depth_ft: Optional[float] = None
    transition_grade: str = ""
    notes: str = ""
    spot_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    added_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_row(self) -> dict:
        d = asdict(self)
        d["bottom_structure"] = "|".join(self.bottom_structure)
        return {k: d.get(k, "") for k in FIELDNAMES}


def split_bottom_structure(value: str) -> list:
    """Turn a CSV row's pipe-joined bottom_structure string back into a list."""
    return [s for s in (value or "").split("|") if s]


def ensure_spots_file_exists(path: Path = SPOTS_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def read_all_spots(path: Path = SPOTS_PATH) -> list:
    ensure_spots_file_exists(path)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append_spot(spot: LakeSpot, path: Path = SPOTS_PATH):
    ensure_spots_file_exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(spot.to_row())


def _write_rows(rows: list, path: Path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})


def update_spot(spot_id: str, path: Path = SPOTS_PATH, **changes) -> bool:
    """Update fields on an existing spot by spot_id. A `bottom_structure`
    change may be passed as a list (joined automatically here) or an
    already-joined string. Returns True if found."""
    rows = read_all_spots(path)
    found = False
    for row in rows:
        if row["spot_id"] == spot_id:
            for k, v in changes.items():
                if k not in FIELDNAMES:
                    continue
                if k == "bottom_structure" and isinstance(v, list):
                    v = "|".join(v)
                row[k] = "" if v is None else v
            row["updated_at"] = datetime.utcnow().isoformat()
            found = True
            break
    if found:
        _write_rows(rows, path)
    return found


def delete_spot(spot_id: str, path: Path = SPOTS_PATH) -> bool:
    rows = read_all_spots(path)
    remaining = [r for r in rows if r["spot_id"] != spot_id]
    deleted = len(remaining) != len(rows)
    if deleted:
        _write_rows(remaining, path)
    return deleted


def nearest_spot_within(lat: float, lon: float, spots: list, max_deg: float = 0.0001):
    """Return the closest saved spot to (lat, lon) if it's within max_deg
    degrees (~9-11m at Nolin's latitude), else None.

    Used to tell "clicked an existing pin" apart from "clicked a new blank
    location" on the map: our own markers are placed exactly at each
    spot's stored coordinates, and a click registered on a marker's icon
    reports that marker's exact location, so a small tolerance (just
    enough to absorb float/CSV round-tripping, not to forgive an
    imprecise click) is all that's needed here."""
    if not spots:
        return None
    best, best_dist = None, None
    for s in spots:
        try:
            d = ((float(s["lat"]) - lat) ** 2 + (float(s["lon"]) - lon) ** 2) ** 0.5
        except (KeyError, TypeError, ValueError):
            continue
        if best_dist is None or d < best_dist:
            best, best_dist = s, d
    if best is not None and best_dist <= max_deg:
        return best
    return None
