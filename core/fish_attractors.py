"""
Real, GPS-tagged fish attractors placed in Nolin River Lake by the Kentucky
Department of Fish & Wildlife Resources (KDFWR) - brush piles, Christmas
trees, pallet stacks, plastic structures, rock piles, and reef balls.

This is a different kind of source than everything else in the bathymetry/
cover chain: it's not derived from a historical map at all, it's a state
agency's own placement records, published specifically so anglers can load
them into a GPS or depth finder (fw.ky.gov/Fish/Pages/fish_attractor_lakes.aspx,
GPX download at fw.ky.gov/Fish/documents/Nolin_River_Lake.gpx). KDFWR is a
public agency and this data is published for exactly this kind of public
use - the same category of source as the USACE gauge/KY State Parks/Census
TIGER data already used elsewhere in this project, not a proprietary chart
product.

The user downloaded the GPX (my fetch tools could reach the KDFWR page but
not the binary GPX file or its Google My Maps mirror) and it was parsed
into data/nolin_fish_attractors.csv: columns ident, lat, lon, structure_type
(one of: Brush, Christmas Trees, Pallet Stack, Plastic, Spider Hump, Reef
Ball, Rock). 346 total as of the snapshot KDFWR had published (metadata in
the source GPX dated 2023-03-08). Most idents are KDFWR's own NRL### code;
about 40 points (mostly ones whose source entry carried an embedded photo
instead of an ident string) got a synthetic NRL-NOID-### placeholder so
every row has a stable, non-empty identifier.

Note on positions: about a third of these points fall outside (sometimes
several hundred meters outside) data/nolin_shoreline.geojson's real-
shoreline polygons. That's expected, not a data error on either side -
attractors are often placed intentionally close to the bank in shallow
water, and this project's own shoreline digitization has its own
resolution/registration limits (see core/shoreline.py). These are kept
as-is, unfiltered, since they're the most authoritative point data in the
whole project - real placements, not anything derived or modeled.
"""
from __future__ import annotations
import csv
from pathlib import Path
from functools import lru_cache

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "data" / "nolin_fish_attractors.csv"


@lru_cache(maxsize=1)
def _load_cached(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return []
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "ident": row["ident"],
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "structure_type": row["structure_type"],
                })
            except (KeyError, ValueError):
                continue
    return rows


def load_fish_attractors(path: Path = DEFAULT_PATH) -> list:
    """Returns a list of {"ident", "lat", "lon", "structure_type"} dicts.
    Empty list if the file doesn't exist."""
    return _load_cached(str(path))


def fish_attractor_count(path: Path = DEFAULT_PATH) -> int:
    return len(load_fish_attractors(path))


def fish_attractor_type_counts(path: Path = DEFAULT_PATH) -> dict:
    counts: dict = {}
    for a in load_fish_attractors(path):
        counts[a["structure_type"]] = counts.get(a["structure_type"], 0) + 1
    return counts
