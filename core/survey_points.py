"""
Loads the angler's own recorded depth soundings (Garmin Quickdraw Contours,
exported via qdc-converter to CSV - see data/quickdraw/README.md) so
core/bathymetry.py can blend real data into the modeled depth surface.

This is intentionally separate from the proprietary-chart problem discussed
elsewhere in this app: these are the angler's own sonar readings from their
own boat, not a scraped/reproduced commercial chart, so there's no copyright
concern using them directly.

Any number of CSV files can sit in the quickdraw folder - they're all loaded
and combined, so new exploration trips just mean dropping in another file.
"""
from __future__ import annotations
import csv
from pathlib import Path
from functools import lru_cache

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUICKDRAW_DIR = REPO_ROOT / "data" / "quickdraw"

METERS_TO_FEET = 3.28084

# Real points within ~1m of each other (repeated passes over the same spot)
# get averaged together rather than treated as separate readings.
DEDUPE_PRECISION_DEG = 5  # ~1.1m at this latitude when rounding lat/lon


def _parse_csv_file(path: Path):
    """Yields (lon, lat, depth_m) tuples from one qdc-converter CSV export.
    Tolerant of the default 'X,Y,Depth(m)' header (case-insensitive) and of
    files exported without a header (assumes X,Y,Depth(m) column order)."""
    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return
    header = [c.strip().lower() for c in rows[0]]
    start = 0
    col_order = (0, 1, 2)  # (lon_idx, lat_idx, depth_idx)
    if any("x" == h or "depth" in h or "y" == h for h in header):
        start = 1
        try:
            lon_idx = next(i for i, h in enumerate(header) if h == "x")
            lat_idx = next(i for i, h in enumerate(header) if h == "y")
            depth_idx = next(i for i, h in enumerate(header) if "depth" in h)
            col_order = (lon_idx, lat_idx, depth_idx)
        except StopIteration:
            col_order = (0, 1, 2)
    for row in rows[start:]:
        if len(row) < 3:
            continue
        try:
            lon = float(row[col_order[0]])
            lat = float(row[col_order[1]])
            depth_m = float(row[col_order[2]])
        except (ValueError, IndexError):
            continue
        yield lon, lat, depth_m


@lru_cache(maxsize=1)
def _load_all_points_cached(quickdraw_dir_str: str):
    quickdraw_dir = Path(quickdraw_dir_str)
    if not quickdraw_dir.exists():
        return np.array([]), np.array([]), np.array([])

    by_key = {}  # (rounded_lat, rounded_lon) -> [depth_ft, count]
    for csv_path in sorted(quickdraw_dir.glob("*.csv")):
        for lon, lat, depth_m in _parse_csv_file(csv_path):
            depth_ft = depth_m * METERS_TO_FEET
            key = (round(lat, DEDUPE_PRECISION_DEG), round(lon, DEDUPE_PRECISION_DEG))
            if key in by_key:
                by_key[key][0] += depth_ft
                by_key[key][1] += 1
            else:
                by_key[key] = [depth_ft, 1]

    if not by_key:
        return np.array([]), np.array([]), np.array([])

    lats = np.array([k[0] for k in by_key.keys()])
    lons = np.array([k[1] for k in by_key.keys()])
    depths_ft = np.array([v[0] / v[1] for v in by_key.values()])
    return lats, lons, depths_ft


def load_survey_points(quickdraw_dir: Path = DEFAULT_QUICKDRAW_DIR):
    """Returns (lat_array, lon_array, depth_ft_array) of the angler's own
    recorded depth soundings, deduplicated to ~1m buckets. Empty arrays if
    no CSVs have been dropped in yet."""
    return _load_all_points_cached(str(quickdraw_dir))


def survey_point_count(quickdraw_dir: Path = DEFAULT_QUICKDRAW_DIR) -> int:
    lats, _, _ = load_survey_points(quickdraw_dir)
    return len(lats)


def survey_file_count(quickdraw_dir: Path = DEFAULT_QUICKDRAW_DIR) -> int:
    if not quickdraw_dir.exists():
        return 0
    return len(list(quickdraw_dir.glob("*.csv")))


def clear_survey_cache():
    """Call after adding/removing CSV files so the next load picks them up
    (matters within a single long-running process; a fresh deploy doesn't
    need this since the cache starts empty)."""
    _load_all_points_cached.cache_clear()
