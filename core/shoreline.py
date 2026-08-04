"""
Real lake shoreline polygons digitized from the solid-blue water fill on
the 1966 USGS post-dam topo sheets (Nolin Reservoir/Dickeys Mills quad and
Bee Spring quad) at the 515ft summer pool elevation - see
data/nolin_shoreline.geojson and SESSION_NOTES.md for how these were
produced (color-threshold water detection + OpenCV contour extraction,
restricted to the lake's known footprint to drop unrelated ponds picked up
elsewhere on the same map sheets).

core/bathymetry.py uses this as a hard clip on the modeled depth grid:
depth (and therefore every contour line derived from it) is only ever
reported inside these real polygons, regardless of what the simplified
straight-line channel model's own corridor shape would otherwise allow.
Nolin Lake is highly sinuous - the channel model connects only a handful of
anchor points with straight segments - so without this clip, the model's
corridor cuts across necks of land wherever the real lake bends away from
that straight line. This is what keeps contour lines from crossing dry
land.
"""
from __future__ import annotations
import json
from pathlib import Path as FsPath
from functools import lru_cache

import numpy as np
from skimage.measure import points_in_poly

DATA_PATH = FsPath(__file__).resolve().parent.parent / "data" / "nolin_shoreline.geojson"


@lru_cache(maxsize=1)
def _load_polygons(path_str: str = str(DATA_PATH)):
    try:
        with open(path_str) as f:
            geo = json.load(f)
    except FileNotFoundError:
        return []
    polys = []
    for feat in geo.get("features", []):
        coords = feat["geometry"]["coordinates"][0]
        if len(coords) < 3:
            continue
        polys.append(np.array(coords, dtype=float))  # columns: lon, lat
    return polys


def shoreline_polygon_count() -> int:
    return len(_load_polygons())


def shoreline_polygons():
    """Public accessor for the raw digitized polygons (list of (n,2) lon/lat
    arrays) - used by core/lake_map.py to draw the real shoreline as a
    reference layer."""
    return _load_polygons()


def shoreline_mask(lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
    """
    Boolean array, same shape as lat_grid/lon_grid, True where that grid
    cell's center falls inside a real digitized shoreline polygon.

    lat_grid/lon_grid are expected to be the 2D meshgrid arrays used
    elsewhere in core/bathymetry.py (rows = lat_axis, cols = lon_axis).
    Restricts the expensive point-in-polygon test to each polygon's own
    bounding box instead of testing the whole grid against every polygon -
    there are ~1300 small polygons, so this matters.

    Returns an all-False mask if no shoreline data is available, so callers
    should check shoreline_polygon_count() (or just fall back to the
    unclipped model) rather than treating an empty mask as "clip to
    nothing."
    """
    polys = _load_polygons()
    mask = np.zeros(lat_grid.shape, dtype=bool)
    if not polys:
        return mask

    lat_axis = lat_grid[:, 0]
    lon_axis = lon_grid[0, :]

    for poly in polys:
        lon_min, lat_min = poly.min(axis=0)
        lon_max, lat_max = poly.max(axis=0)
        i0 = max(0, np.searchsorted(lat_axis, lat_min, side="left") - 1)
        i1 = min(len(lat_axis), np.searchsorted(lat_axis, lat_max, side="right") + 1)
        j0 = max(0, np.searchsorted(lon_axis, lon_min, side="left") - 1)
        j1 = min(len(lon_axis), np.searchsorted(lon_axis, lon_max, side="right") + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        sub_lat = lat_grid[i0:i1, j0:j1]
        sub_lon = lon_grid[i0:i1, j0:j1]
        pts = np.column_stack([sub_lon.ravel(), sub_lat.ravel()])
        inside = points_in_poly(pts, poly)
        if inside.any():
            mask[i0:i1, j0:j1] |= inside.reshape(sub_lat.shape)

    return mask
