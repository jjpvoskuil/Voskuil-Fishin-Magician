"""
Modeled bathymetry for Nolin River Lake.

There is no free, downloadable, full-lake bathymetric survey for Nolin Lake
(checked USACE eHydro - navigation channels only; USGS - only a partial
2016 water-quality study). Commercial charts exist (Navionics, Fishidy,
GPS Nautical Charts) but their compiled depth data is proprietary and
can't be scraped/embedded here.

Instead, this builds a MODELED depth surface from a hand-defined river
channel centerline (data/nolin_channel.json), anchored at verified points
(USACE gauge, KY State Parks GNIS coordinate, Census TIGER geocodes) with
a Gaussian cross-section that tapers from channel depth to the shoreline.
It's clearly a model, not a measurement - labeled as such everywhere it
surfaces in the UI.

It's also designed to improve: points read from pre-dam USGS historical
topo sheets (core/historic_bathymetry.py, data/historic_bathymetry.csv -
public domain, see that module for the full method) blend in the same way,
followed by real depth soundings the angler has recorded themselves (Garmin
Quickdraw Contours, see core/survey_points.py and data/quickdraw/README.md)
on top of that - real data wins near where it was actually recorded
(inverse-distance weighted, fading smoothly back to the model), and both
sources can extend coverage into areas the hand-modeled channel doesn't
reach at all (side coves/arms not represented in nolin_channel.json).
Everywhere neither source has data yet, the modeled surface is unchanged.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree
from skimage import measure

from .survey_points import load_survey_points
from .historic_bathymetry import load_historic_points

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "nolin_channel.json"

GRID_RESOLUTION = 220  # cells across the longer axis - good detail without being slow
METERS_PER_DEG_LAT = 111_320.0

# Within this many meters of a real recorded depth point, that point's
# reading is blended in (fading smoothly from 100% real at 0m to 100%
# modeled at this radius).
REAL_DATA_BLEND_RADIUS_M = 50.0
# How many nearest real points to average (inverse-distance weighted) at
# each grid cell - smooths out single noisy pings without over-smoothing.
REAL_DATA_NEIGHBORS = 6

# Historic-topo-derived points are sparser and cover a small area (see
# core/historic_bathymetry.py) - a wider fade radius lets a handful of
# points blend into a continuous patch rather than staying isolated dots.
HISTORIC_BLEND_RADIUS_M = 60.0
# Fewer neighbors than REAL_DATA_NEIGHBORS: the historic point cloud is small
# and lopsided (many shoreline 0-ft points, few deeper ones per pocket), so
# averaging over too many neighbors washes out the deeper readings.
HISTORIC_NEIGHBORS = 3


def _meters_per_deg_lon(lat_deg: float) -> float:
    return METERS_PER_DEG_LAT * math.cos(math.radians(lat_deg))


def load_channel() -> dict:
    with open(DATA_PATH) as f:
        return json.load(f)


def _densify_branch(points: list, step_m: float = 40.0) -> list:
    """Linearly interpolate extra points along a branch so segments aren't too coarse."""
    if len(points) < 2:
        return points
    lat0 = points[0]["lat"]
    m_per_lon = _meters_per_deg_lon(lat0)
    dense = [points[0]]
    for a, b in zip(points, points[1:]):
        dx = (b["lon"] - a["lon"]) * m_per_lon
        dy = (b["lat"] - a["lat"]) * METERS_PER_DEG_LAT
        seg_len = math.hypot(dx, dy)
        n = max(1, int(seg_len // step_m))
        for i in range(1, n + 1):
            t = i / n
            dense.append({
                "lat": a["lat"] + (b["lat"] - a["lat"]) * t,
                "lon": a["lon"] + (b["lon"] - a["lon"]) * t,
                "depth_ft": a["depth_ft"] + (b["depth_ft"] - a["depth_ft"]) * t,
                "half_width_m": a["half_width_m"] + (b["half_width_m"] - a["half_width_m"]) * t,
            })
    return dense


@lru_cache(maxsize=1)
def _dense_channel_points() -> list:
    data = load_channel()
    pts = []
    for branch in data["branches"].values():
        pts.extend(_densify_branch(branch["points"]))
    return pts


@lru_cache(maxsize=1)
def _bounds():
    """
    Grid extent. Padded around the channel model's own points, but also
    widened to cover any real survey/historic-topo points that fall outside
    that padding - otherwise a trip logged (or a historic point read) in an
    un-modeled cove west/east of the channel model's own footprint could
    sit right at the edge of - or just outside - the grid, where nearest-
    cell lookups and boundary blending get unreliable. See
    core/historic_bathymetry.py and core/survey_points.py.
    """
    pts = _dense_channel_points()
    lats = [p["lat"] for p in pts]
    lons = [p["lon"] for p in pts]
    max_half_width_deg_lat = 700 / METERS_PER_DEG_LAT  # pad by widest plausible half-width + margin
    pad_lat = max_half_width_deg_lat * 1.6
    pad_lon = pad_lat  # close enough near this latitude after lon-scaling below
    lat_min, lat_max = min(lats) - pad_lat, max(lats) + pad_lat
    lon_min, lon_max = min(lons) - pad_lon, max(lons) + pad_lon

    extra_lat, extra_lon = [], []
    hist_lat, hist_lon, _ = load_historic_points()
    extra_lat.extend(hist_lat.tolist())
    extra_lon.extend(hist_lon.tolist())
    real_lat, real_lon, _ = load_survey_points()
    extra_lat.extend(real_lat.tolist())
    extra_lon.extend(real_lon.tolist())

    if extra_lat:
        # small fixed margin (~100m) around any real/historic point outside
        # the channel-model padding, so it's never right at the grid edge
        margin_lat = 100 / METERS_PER_DEG_LAT
        margin_lon = margin_lat
        lat_min = min(lat_min, min(extra_lat) - margin_lat)
        lat_max = max(lat_max, max(extra_lat) + margin_lat)
        lon_min = min(lon_min, min(extra_lon) - margin_lon)
        lon_max = max(lon_max, max(extra_lon) + margin_lon)

    return (lat_min, lat_max, lon_min, lon_max)


def _blend_real_survey_data(lat_axis, lon_axis, depth_grid, lat_pts, lon_pts, depth_pts,
                             blend_radius_m=REAL_DATA_BLEND_RADIUS_M, neighbors=REAL_DATA_NEIGHBORS):
    """
    Blends real recorded depth points into the modeled grid: inverse-
    distance weighted average of the nearest real readings, fully
    replacing the model at 0m and fading back to it by
    REAL_DATA_BLEND_RADIUS_M. Where the model has no coverage at all
    (np.nan) but real data exists nearby, the real reading is used
    directly - this lets logged trips extend the map into un-modeled
    coves/arms, not just refine the existing channel.
    """
    if len(lat_pts) == 0:
        return depth_grid

    lat0 = float(np.mean(lat_axis))
    m_per_lon = _meters_per_deg_lon(lat0)
    lon_grid, lat_grid = np.meshgrid(lon_axis, lat_axis)

    grid_x = (lon_grid - lon_axis[0]) * m_per_lon
    grid_y = (lat_grid - lat_axis[0]) * METERS_PER_DEG_LAT
    pts_x = (lon_pts - lon_axis[0]) * m_per_lon
    pts_y = (lat_pts - lat_axis[0]) * METERS_PER_DEG_LAT

    tree = cKDTree(np.column_stack([pts_x, pts_y]))
    query_pts = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    k = min(neighbors, len(lat_pts))
    dists, idxs = tree.query(query_pts, k=k)
    if k == 1:
        dists = dists[:, None]
        idxs = idxs[:, None]

    weights = 1.0 / np.clip(dists, 1.0, None) ** 2
    real_estimate = np.sum(weights * depth_pts[idxs], axis=1) / np.sum(weights, axis=1)
    real_estimate = real_estimate.reshape(depth_grid.shape)

    nearest_dist = dists[:, 0].reshape(depth_grid.shape)
    blend_w = np.clip(1.0 - nearest_dist / blend_radius_m, 0.0, 1.0)

    result = depth_grid.copy()
    has_real_nearby = blend_w > 0
    mask_blend = has_real_nearby & ~np.isnan(depth_grid)
    result[mask_blend] = (
        blend_w[mask_blend] * real_estimate[mask_blend]
        + (1 - blend_w[mask_blend]) * depth_grid[mask_blend]
    )
    mask_extend = has_real_nearby & np.isnan(depth_grid)
    result[mask_extend] = real_estimate[mask_extend]
    return result


@lru_cache(maxsize=1)
def _depth_grid():
    """
    Returns (lat_axis, lon_axis, depth_grid) where depth_grid[i, j] is the
    modeled depth in feet at (lat_axis[i], lon_axis[j]), or np.nan outside
    the modeled lake polygon. Real recorded depth points (if any have been
    dropped into data/quickdraw/) are blended in - see
    _blend_real_survey_data.
    """
    lat_min, lat_max, lon_min, lon_max = _bounds()
    lat_axis = np.linspace(lat_min, lat_max, GRID_RESOLUTION)
    # Scale lon resolution so grid cells are roughly square in meters
    lon_span_m = (lon_max - lon_min) * _meters_per_deg_lon((lat_min + lat_max) / 2)
    lat_span_m = (lat_max - lat_min) * METERS_PER_DEG_LAT
    n_lon = max(2, int(GRID_RESOLUTION * lon_span_m / max(lat_span_m, 1e-6)))
    lon_axis = np.linspace(lon_min, lon_max, n_lon)

    lon_grid, lat_grid = np.meshgrid(lon_axis, lat_axis)  # shape (len(lat_axis), len(lon_axis))
    m_per_lon = _meters_per_deg_lon(float(np.mean(lat_axis)))

    pts = _dense_channel_points()
    channel_lat = np.array([p["lat"] for p in pts])
    channel_lon = np.array([p["lon"] for p in pts])
    channel_depth = np.array([p["depth_ft"] for p in pts])
    channel_halfw = np.array([p["half_width_m"] for p in pts])

    depth = np.full(lat_grid.shape, np.nan)

    # For performance, process in row chunks
    for i in range(lat_grid.shape[0]):
        row_lat = lat_grid[i, :]
        row_lon = lon_grid[i, :]
        dy = (row_lat[:, None] - channel_lat[None, :]) * METERS_PER_DEG_LAT
        dx = (row_lon[:, None] - channel_lon[None, :]) * m_per_lon
        dist = np.sqrt(dx ** 2 + dy ** 2)  # (n_lon, n_channel_pts)
        nearest_idx = np.argmin(dist, axis=1)
        nearest_dist = dist[np.arange(dist.shape[0]), nearest_idx]
        target_depth = channel_depth[nearest_idx]
        half_w = channel_halfw[nearest_idx]

        # Gaussian cross-section falloff from channel centerline to shoreline.
        # k tuned so depth reaches ~0 close to half_width (shoreline).
        k = 1.4
        row_depth = target_depth * np.exp(-k * (nearest_dist / np.maximum(half_w, 1.0)) ** 2)
        row_depth = np.where(nearest_dist <= half_w * 1.15, row_depth, np.nan)
        depth[i, :] = row_depth

    hist_lat, hist_lon, hist_depth = load_historic_points()
    depth = _blend_real_survey_data(lat_axis, lon_axis, depth, hist_lat, hist_lon, hist_depth,
                                     blend_radius_m=HISTORIC_BLEND_RADIUS_M, neighbors=HISTORIC_NEIGHBORS)

    lat_pts, lon_pts, depth_pts = load_survey_points()
    depth = _blend_real_survey_data(lat_axis, lon_axis, depth, lat_pts, lon_pts, depth_pts)

    return lat_axis, lon_axis, depth


def get_depth_at_ft(lat: float, lon: float):
    """Nearest-cell modeled depth in feet, or None if outside the modeled area."""
    lat_axis, lon_axis, depth = _depth_grid()
    if not (lat_axis[0] <= lat <= lat_axis[-1] and lon_axis[0] <= lon <= lon_axis[-1]):
        return None
    i = int(np.clip(np.searchsorted(lat_axis, lat), 0, len(lat_axis) - 1))
    j = int(np.clip(np.searchsorted(lon_axis, lon), 0, len(lon_axis) - 1))
    val = depth[i, j]
    return None if np.isnan(val) else round(float(val), 1)


def _local_gradient_ft_per_100m(lat: float, lon: float):
    lat_axis, lon_axis, depth = _depth_grid()
    i = int(np.clip(np.searchsorted(lat_axis, lat), 1, len(lat_axis) - 2))
    j = int(np.clip(np.searchsorted(lon_axis, lon), 1, len(lon_axis) - 2))
    window = depth[i - 1:i + 2, j - 1:j + 2]
    if np.all(np.isnan(window)):
        return 0.0
    cell_m_lat = (lat_axis[1] - lat_axis[0]) * METERS_PER_DEG_LAT
    gy, gx = np.gradient(np.nan_to_num(window, nan=np.nanmean(window)))
    grad_mag_per_m = math.hypot(float(gy[1, 1]), float(gx[1, 1])) / max(cell_m_lat, 1.0)
    return grad_mag_per_m * 100  # ft of depth change per 100m


def infer_structure_type(lat: float, lon: float) -> str:
    """
    Heuristic structure-type guess from the modeled depth surface: combines
    local depth with local slope (steepness). This is a starting suggestion
    the user can always override in the UI - it's not a substitute for
    reading your electronics on the water.
    """
    depth = get_depth_at_ft(lat, lon)
    if depth is None:
        return "Flat"
    slope = _local_gradient_ft_per_100m(lat, lon)
    if slope >= 6:
        return "Creek channel / ledge"
    if depth <= 6:
        return "Cove / pocket (shallow cover)"
    if depth <= 12:
        return "Flat"
    if depth <= 25:
        return "Main-lake point"
    return "Creek channel / ledge"  # deep basin / old river channel itself


def contour_lines(levels=(5, 10, 15, 20, 30, 40, 50, 60, 70, 80)):
    """
    Returns [{"depth_ft": d, "paths": [[(lat, lon), ...], ...]}, ...] using
    marching squares (skimage) on the modeled depth grid.
    """
    lat_axis, lon_axis, depth = _depth_grid()
    filled = np.nan_to_num(depth, nan=-1.0)
    results = []
    for level in levels:
        if level >= np.nanmax(depth[~np.isnan(depth)]) if np.any(~np.isnan(depth)) else True:
            if np.isnan(depth).all() or level > np.nanmax(depth):
                continue
        contours = measure.find_contours(filled, level=level)
        paths = []
        for c in contours:
            # c is array of (row, col) float indices into the grid
            rows = np.clip(c[:, 0].astype(int), 0, len(lat_axis) - 1)
            cols = np.clip(c[:, 1].astype(int), 0, len(lon_axis) - 1)
            # sub-cell precision via linear interpolation of axis values
            row_frac = c[:, 0] - np.floor(c[:, 0])
            col_frac = c[:, 1] - np.floor(c[:, 1])
            row_lo = np.clip(np.floor(c[:, 0]).astype(int), 0, len(lat_axis) - 1)
            row_hi = np.clip(row_lo + 1, 0, len(lat_axis) - 1)
            col_lo = np.clip(np.floor(c[:, 1]).astype(int), 0, len(lon_axis) - 1)
            col_hi = np.clip(col_lo + 1, 0, len(lon_axis) - 1)
            lat_vals = lat_axis[row_lo] * (1 - row_frac) + lat_axis[row_hi] * row_frac
            lon_vals = lon_axis[col_lo] * (1 - col_frac) + lon_axis[col_hi] * col_frac
            if len(lat_vals) >= 2:
                paths.append(list(zip(lat_vals.tolist(), lon_vals.tolist())))
        if paths:
            results.append({"depth_ft": level, "paths": paths})
    return results


def lake_center():
    lat_axis, lon_axis, _ = _depth_grid()
    return float(np.mean(lat_axis)), float(np.mean(lon_axis))
