"""
Pre-dam lake-bottom cover classification: for each ~55m cell of the real
lake footprint (data/nolin_shoreline.geojson), what the ground looked like
on the 1953/1954 pre-dam USGS topo sheets before Nolin River Lake was
impounded in 1963 - wooded, cleared/open, or the original stream channel.

Why this instead of depth: two attempts at deriving numeric depth contours
from this same public data (a hand-modeled channel corridor, then a real-
shoreline-clipped version of it) both produced results that didn't hold up
- there's no actual bathymetric survey for this lake, and public sources
can't support smooth, accurate depth isolines at the fidelity anglers need.
Land cover is a different, more tractable question: it only needs the
color/symbol on the source scan, not precise elevation or precise
registration, so it tolerates the same scan noise and georeferencing slop
that broke the depth work. "This cove was wooded before flooding" is a
useful, honest, defensible fact even when "this cove is 14.3 ft deep" isn't.

Cover classes:
  wooded  - green forest symbol pre-flooding. Likely standing timber once
            submerged - classic largemouth cover, but also a snag risk.
  cleared - white/cream cropland or pasture pre-flooding. Likely a cleaner,
            more open bottom.
  water   - the original stream/river channel itself (shown in blue on the
            source sheets). Useful as a rough breakline/channel-edge
            indicator even without a matching depth value.

data/nolin_cover.csv columns: lat, lon, dominant_class, wooded_frac,
cleared_frac, water_frac, n_px (classified source pixels that cell's
majority vote was based on - a rough per-cell confidence signal, since a
cell built from a handful of pixels near a contour-line-dense area is
noisier than one built from hundreds of clean interior pixels).

See core/shoreline.py for how the real lake footprint used to build this
was derived, and SESSION_NOTES.md for the color-threshold methodology.
"""
from __future__ import annotations
import csv
from pathlib import Path
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "data" / "nolin_cover.csv"

METERS_PER_DEG_LAT = 111_320.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    import math
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat_deg))


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
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "dominant_class": row["dominant_class"],
                    "wooded_frac": float(row["wooded_frac"]),
                    "cleared_frac": float(row["cleared_frac"]),
                    "water_frac": float(row["water_frac"]),
                    "n_px": int(row["n_px"]),
                })
            except (KeyError, ValueError):
                continue
    return rows


def load_cover_cells(path: Path = DEFAULT_PATH) -> list:
    """Returns a list of cover-cell dicts (see module docstring for fields).
    Empty list if the file doesn't exist."""
    return _load_cached(str(path))


def cover_cell_count(path: Path = DEFAULT_PATH) -> int:
    return len(load_cover_cells(path))


@lru_cache(maxsize=1)
def _tree(path_str: str):
    cells = _load_cached(path_str)
    if not cells:
        return None, []
    lat0 = float(np.mean([c["lat"] for c in cells]))
    m_per_lon = _meters_per_deg_lon(lat0)
    pts = np.array([
        [c["lat"] * METERS_PER_DEG_LAT, c["lon"] * m_per_lon] for c in cells
    ])
    return cKDTree(pts), cells


def get_cover_at(lat: float, lon: float, max_dist_m: float = 80.0, path: Path = DEFAULT_PATH):
    """
    Nearest pre-dam cover cell within max_dist_m, or None if nothing close
    enough. Returns the cell dict (see module docstring for fields) plus a
    'distance_m' key. max_dist_m defaults to a bit larger than the ~55m
    cell size so a query near a cell boundary still finds its neighbor.
    """
    tree, cells = _tree(str(path))
    if tree is None:
        return None
    lat0 = float(np.mean([c["lat"] for c in cells]))
    m_per_lon = _meters_per_deg_lon(lat0)
    dist, idx = tree.query([lat * METERS_PER_DEG_LAT, lon * m_per_lon])
    if dist > max_dist_m:
        return None
    result = dict(cells[idx])
    result["distance_m"] = round(float(dist), 1)
    return result
