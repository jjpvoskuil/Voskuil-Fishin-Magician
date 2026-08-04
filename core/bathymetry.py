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

Because the channel model is only a handful of anchor points joined by
straight lines, its corridor doesn't follow Nolin Lake's real winding
shoreline - left alone it would show depth (and contour lines) cutting
across necks of land. core/shoreline.py holds real shoreline polygons
digitized from the same USGS topo sheets (data/nolin_shoreline.geojson),
and every stage below is clipped to them so nothing is ever reported
outside the lake's actual footprint.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt
from skimage import measure

from .survey_points import load_survey_points
from .historic_bathymetry import load_historic_points
from .shoreline import shoreline_mask, shoreline_polygon_count

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
                             blend_radius_m=REAL_DATA_BLEND_RADIUS_M, neighbors=REAL_DATA_NEIGHBORS,
                             allowed_mask=None):
    """
    Blends real recorded depth points into the modeled grid: inverse-
    distance weighted average of the nearest real readings, fully
    replacing the model at 0m and fading back to it by
    REAL_DATA_BLEND_RADIUS_M. Where the model has no coverage at all
    (np.nan) but real data exists nearby, the real reading is used
    directly - this lets logged trips extend the map into un-modeled
    coves/arms, not just refine the existing channel. If allowed_mask is
given (True = inside the real shoreline, see core/shoreline.py), that
extension is only allowed where allowed_mask is True - real data can
still refine existing modeled cells anywhere, but can't paint new depth
onto dry land.
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
    if allowed_mask is not None:
        mask_extend = mask_extend & allowed_mask
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

    # Nearest-channel-anchor lookup for every grid cell. The channel anchors
    # (data/nolin_channel.json) now only supply depth *values* and a rough
    # corridor *fallback* - not the primary water/land boundary, since the
    # anchors are hand-placed and their straight-line centerline doesn't
    # reliably run through the real lake everywhere (checked: off by 50m to
    # over 1km in places). half_w is each cell's nearest anchor's
    # half_width_m, used below as the distance over which depth ramps up
    # from shore to full target depth.
    tree = cKDTree(np.column_stack([channel_lat * METERS_PER_DEG_LAT, channel_lon * m_per_lon]))
    query_pts = np.column_stack([lat_grid.ravel() * METERS_PER_DEG_LAT, lon_grid.ravel() * m_per_lon])
    nearest_channel_dist, nearest_idx = tree.query(query_pts)
    nearest_channel_dist = nearest_channel_dist.reshape(lat_grid.shape)
    nearest_idx = nearest_idx.reshape(lat_grid.shape)
    target_depth = channel_depth[nearest_idx]
    half_w = np.maximum(channel_halfw[nearest_idx], 1.0)
    corridor_mask = nearest_channel_dist <= half_w * 1.15
    # Cap how far from the real shoreline depth has to ramp before reaching
    # the nearest anchor's full target depth. channel_halfw values were
    # tuned for the old hand-drawn corridor's assumed cross-section, not the
    # real (and locally variable) width of the digitized lake - using them
    # directly here made most of the lake read as shallow because the real
    # water body is often narrower than that assumed half-width at any given
    # point. Capping keeps the ramp reaching full depth within a plausible
    # distance regardless.
    ramp_dist_m = np.minimum(half_w, 180.0)

    shore = None
    if shoreline_polygon_count():
        shore = shoreline_mask(lat_grid, lon_grid)

    if shore is not None and shore.any():
        # Real digitized shoreline (core/shoreline.py) is the water extent -
        # the channel-anchor corridor is only used as a fallback for the rare
        # spot the digitized shoreline has zero coverage anywhere nearby
        # (e.g. a small scan gap), so a verified anchor point is never
        # dropped entirely just because of a local extraction blind spot.
        # This is deliberately NOT a blanket union: the corridor's own
        # straight-line shape is what originally produced contours crossing
        # dry land, so it should only fill in where the real shoreline is
        # silent, not override it.
        cell_lat_m0 = METERS_PER_DEG_LAT * abs(lat_axis[1] - lat_axis[0]) if len(lat_axis) > 1 else 1.0
        cell_lon_m0 = m_per_lon * abs(lon_axis[1] - lon_axis[0]) if len(lon_axis) > 1 else 1.0
        dist_to_shore0 = distance_transform_edt(~shore, sampling=(cell_lat_m0, cell_lon_m0))
        far_from_shore = dist_to_shore0 > 250.0  # meters
        water_mask = shore | (corridor_mask & far_from_shore)
    else:
        water_mask = corridor_mask

    # Depth ramps from 0 at the water/land boundary up to the nearest
    # anchor's target depth, reached over roughly that anchor's half-width,
    # then holds at target depth further from shore/in wider open water.
    cell_lat_m = METERS_PER_DEG_LAT * abs(lat_axis[1] - lat_axis[0]) if len(lat_axis) > 1 else 1.0
    cell_lon_m = m_per_lon * abs(lon_axis[1] - lon_axis[0]) if len(lon_axis) > 1 else 1.0
    dist_to_boundary_m = distance_transform_edt(water_mask, sampling=(cell_lat_m, cell_lon_m))
    t = np.clip(dist_to_boundary_m / ramp_dist_m, 0.0, 1.0)
    smooth_t = 3 * t ** 2 - 2 * t ** 3  # smoothstep: eases in at the edge, eases out at full depth
    depth = np.where(water_mask, target_depth * smooth_t, np.nan)

    # Verified anchor points (data/nolin_channel.json labels containing
    # "verified anchor") are real surveyed/read depths - a USACE benchmark
    # elevation, a contour read, etc - not shore-ramp estimates. Pin the
    # small neighborhood of grid cells nearest each one directly to its
    # known depth so point lookups there are exact and match what's
    # documented as "verified," and include those cells in water_mask so
    # they connect smoothly into the surrounding contours instead of
    # sitting as an isolated island if the shore ramp alone would have
    # made that spot read shallower (e.g. an anchor near the edge of the
    # digitized shoreline rather than dead center of the deepest water).
    raw_points = []
    for branch in load_channel()["branches"].values():
        raw_points.extend(branch["points"])
    for p in raw_points:
        if "verified anchor" not in p.get("label", "").lower():
            continue
        i = int(np.clip(np.searchsorted(lat_axis, p["lat"]), 0, len(lat_axis) - 1))
        j = int(np.clip(np.searchsorted(lon_axis, p["lon"]), 0, len(lon_axis) - 1))
        if i > 0 and abs(lat_axis[i - 1] - p["lat"]) < abs(lat_axis[i] - p["lat"]):
            i -= 1
        if j > 0 and abs(lon_axis[j - 1] - p["lon"]) < abs(lon_axis[j] - p["lon"]):
            j -= 1
        i0, i1 = max(0, i - 1), min(len(lat_axis), i + 2)
        j0, j1 = max(0, j - 1), min(len(lon_axis), j + 2)
        depth[i0:i1, j0:j1] = p["depth_ft"]
        water_mask[i0:i1, j0:j1] = True

    hist_lat, hist_lon, hist_depth = load_historic_points()
    depth = _blend_real_survey_data(lat_axis, lon_axis, depth, hist_lat, hist_lon, hist_depth,
                                     blend_radius_m=HISTORIC_BLEND_RADIUS_M, neighbors=HISTORIC_NEIGHBORS,
                                     allowed_mask=water_mask)

    lat_pts, lon_pts, depth_pts = load_survey_points()
    depth = _blend_real_survey_data(lat_axis, lon_axis, depth, lat_pts, lon_pts, depth_pts,
                                     allowed_mask=water_mask)

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
