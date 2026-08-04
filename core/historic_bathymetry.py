"""
Loads depth points derived from historical (pre-dam) USGS topographic maps,
blended into the modeled depth surface in core/bathymetry.py the same way
Quickdraw survey points are - real elevation data wins near where it was
actually read, fading back to the model further out.

Where this data comes from: Nolin River Lake was impounded in 1963. USGS's
Historical Topographic Map Collection (public domain, free via TopoView/
The National Map) has 7.5' quadrangle sheets surveyed just before the dam
(e.g. Bee Spring, KY 1953; Dickeys Mills, KY 1954 - the cell later re-
surveyed and renamed Nolin Lake/Nolin Reservoir once the lake existed) that
show the original ground contours for what's now lake bed, at a 20 ft
contour interval. The 1966 post-dam revision of the same sheets shows the
515' summer pool shoreline directly (it's printed on the map). Depth points
here were built by reading pre-dam ground elevation at specific locations
against that 515' shoreline (515 - elevation = depth), then converting to
lat/lon.

This is a slower, smaller-scale source than a full survey - each point is
either a directly-read contour/benchmark elevation or, further from the
shoreline, an extrapolation along the general valley gradient. It's
intentionally NOT a full contour digitization: automated contour-line
tracing was tried and abandoned (see SESSION_NOTES.md) because gaps in the
historical scans (text labels, roads crossing contour lines) caused
flood-fill region tracing to leak across elevation bands at anything past
a small, clean area. What's here is real, public-domain USGS data, just
modest in extent - data/historic_bathymetry.csv documents confidence per
batch of points, and more can be added the same way as additional
historical quads are digitized.

This is a different provenance than data/quickdraw/ (the angler's own
sonar) and is kept as a separate file/loader so that distinction stays
clear, even though both blend into the model the same way.
"""
from __future__ import annotations
import csv
from pathlib import Path
from functools import lru_cache

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "data" / "historic_bathymetry.csv"


@lru_cache(maxsize=1)
def _load_cached(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return np.array([]), np.array([]), np.array([])
    lats, lons, depths = [], [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lats.append(float(row["lat"]))
                lons.append(float(row["lon"]))
                depths.append(float(row["depth_ft"]))
            except (KeyError, ValueError):
                continue
    return np.array(lats), np.array(lons), np.array(depths)


def load_historic_points(path: Path = DEFAULT_PATH):
    """Returns (lat_array, lon_array, depth_ft_array) of depth points read
    from pre-dam USGS historical topo sheets. Empty arrays if the file
    doesn't exist."""
    return _load_cached(str(path))


def historic_point_count(path: Path = DEFAULT_PATH) -> int:
    lats, _, _ = load_historic_points(path)
    return len(lats)
