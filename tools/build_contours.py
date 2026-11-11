"""Builds Nolin River Lake bottom contours for the web app's Lake Map (John 11-10/11-11).

Runs in GitHub Actions (.github/workflows/build-contours.yml) because the sandbox can't reach the data:
  python tools/build_contours.py OUTDIR

Source: KyFromAbove Phase 2 lidar DEM (public, Kentucky Division of Geographic Information; STAC collection
dem-phase2; 2-ft cloud-optimized GeoTIFF tiles in EPSG:3089, US survey feet). It was flown Dec 2022 - Apr 2023 with
the lake drawn down (~495.8-498.8 ft depending on the flight day), so everything above that water line is real
measured bottom. Lidar can't see through water, so the DEM is flat at the water surface there.

Below the lidar water line the bottom is ESTIMATED and every line from it is flagged est=1:
  * from each edge of the unseen area, the bottom keeps falling at the slope the lidar measured at that edge,
    leveling off smoothly toward a floor;
  * floor = 480 ft (John: "most areas don't get much deeper than 35 ft at summer pool" = 515 - 35), deepening only
    along the old river channel (data/nolin_channel.json centerline) toward 455 ft (55-60 ft at summer pool near
    the dam and in a few holes - John's numbers).
Output stores bottom ELEVATION (ft above sea level), so the app shows depth = live USGS lake level - elevation and
the contours follow the lake as it rises and falls (John 11-10).

Writes OUTDIR/contours.json: {generated, source, levels, lines: [{e: elevation_ft, est: 0|1, c: [[lon, lat], ...]}]}
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from scipy import ndimage
from shapely.geometry import LineString
from skimage import measure

ROOT = Path(__file__).resolve().parents[1]
STAC = "https://spved5ihrl.execute-api.us-west-2.amazonaws.com/"
COLLECTION = "dem-phase2"
PIX = 8.0                      # ft per pixel we work at (lidar is 2 ft; 8 ft is plenty for 2-ft contours, ~16x less data)
SUMMER_POOL = 515.0
TOP = 516.0                    # lake footprint = connected ground at or below this
GENERAL_FLOOR = 480.0          # John: most of the lake <= 35 ft at summer pool
CHANNEL_FLOOR = 455.0          # John: a few areas 55-60 ft at summer pool
LEVELS = np.arange(456, 516, 2.0)
DAM = (37.2783, -86.2475)


def lake_bbox_wgs84():
    gj = json.loads((ROOT / "data" / "nolin_shoreline.geojson").read_text())
    xs, ys = [], []
    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for k in c:
                walk(k)
    for f in gj["features"]:
        walk(f["geometry"]["coordinates"])
    m = 0.01
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def flat_water_level(a):
    """The lidar's flat water surface in a tile: the most common elevation between 480 and 505 ft (0.1-ft bins)."""
    v = a[(a > 480) & (a < 505)]
    if v.size < 2000:
        return None
    vals, counts = np.unique(np.round(v, 1), return_counts=True)
    i = int(np.argmax(counts))
    return float(vals[i]) if counts[i] > 0.15 * v.size and counts[i] > 2000 else None


def main(out):
    t0 = time.time()
    lon0, lat0, lon1, lat1 = lake_bbox_wgs84()
    print(f"lake bbox {lon0:.4f},{lat0:.4f} .. {lon1:.4f},{lat1:.4f}")
    cat = pystac_client.Client.open(STAC)
    items = list(cat.search(collections=[COLLECTION], bbox=[lon0, lat0, lon1, lat1], max_items=2000).items())
    print(f"{len(items)} lidar tiles")

    # --- read every tile at 8 ft (COG overviews) into one mosaic
    tiles = []
    for it in items:
        href = next(a.href for a in it.assets.values() if a.href.endswith(".tif"))
        with rasterio.open(href) as src:
            f = int(round(PIX / src.res[0]))
            h, w = src.height // f, src.width // f
            a = src.read(1, out_shape=(h, w), resampling=Resampling.average, masked=True).astype("float32").filled(np.nan)
            tiles.append((src.bounds, a, it.properties.get("start_datetime", "")))
    x0 = min(b.left for b, _, _ in tiles); x1 = max(b.right for b, _, _ in tiles)
    y0 = min(b.bottom for b, _, _ in tiles); y1 = max(b.top for b, _, _ in tiles)
    W, H = int(math.ceil((x1 - x0) / PIX)), int(math.ceil((y1 - y0) / PIX))
    Z = np.full((H, W), np.nan, "float32")
    WL = np.full((H, W), np.nan, "float32")   # lidar water-surface level, where the tile has one
    for b, a, when in tiles:
        r0, c0 = int(round((y1 - b.top) / PIX)), int(round((b.left - x0) / PIX))
        hh, ww = min(a.shape[0], H - r0), min(a.shape[1], W - c0)
        sub = a[:hh, :ww]
        Z[r0:r0 + hh, c0:c0 + ww] = np.where(np.isnan(sub), Z[r0:r0 + hh, c0:c0 + ww], sub)
        wl = flat_water_level(sub)
        if wl is not None:
            WL[r0:r0 + hh, c0:c0 + ww] = np.where(np.isnan(sub), WL[r0:r0 + hh, c0:c0 + ww], wl)
    print(f"mosaic {W}x{H} px at {PIX} ft ({time.time() - t0:.0f}s); water levels seen: "
          f"{sorted(set(np.round(WL[~np.isnan(WL)], 1).tolist()))[:12]}")

    to_ky = Transformer.from_crs("EPSG:4326", "EPSG:3089", always_xy=True)
    to_ll = Transformer.from_crs("EPSG:3089", "EPSG:4326", always_xy=True)
    def px(lat, lon):
        x, y = to_ky.transform(lon, lat)
        return int((y1 - y) / PIX), int((x - x0) / PIX)

    # --- the lake: ground at/below TOP connected to the dam; unseen = lidar's flat water inside it
    water = ~np.isnan(WL) & (np.abs(Z - WL) < 0.2)
    low = (Z <= TOP) | water
    lab, n = ndimage.label(low, structure=np.ones((3, 3)))
    dr, dc = px(*DAM)
    # the dam pixel may sit on the embankment: take the biggest component with water near it
    near = lab[max(0, dr - 60):dr + 60, max(0, dc - 60):dc + 60]
    ids, cnt = np.unique(near[near > 0], return_counts=True)
    lake_id = int(ids[np.argmax(cnt)])
    lake = lab == lake_id
    unseen = lake & water
    seen = lake & ~unseen
    print(f"lake {lake.sum() * PIX * PIX / 43560:.0f} acres at <= {TOP} ft; unseen (estimated) {unseen.sum() * PIX * PIX / 43560:.0f} acres")

    # --- estimate the bottom under the lidar water line
    gy, gx = np.gradient(np.where(seen, Z, np.nan), PIX)
    slope = np.hypot(gx, gy)
    slope = np.where(seen & np.isfinite(slope), slope, np.nan)
    # slope near the edge, smoothed so one odd pixel doesn't steer a whole flat
    s_ok = np.isfinite(slope)
    s_med = ndimage.median_filter(np.where(s_ok, slope, 0), size=5)
    d_ft, (ir, ic) = ndimage.distance_transform_edt(~seen | ~s_ok, sampling=PIX, return_indices=True)
    edge_slope = np.clip(s_med[ir, ic], 0.03, 0.6)
    edge_wl = np.where(np.isnan(WL), 496.0, WL)
    d_unseen = ndimage.distance_transform_edt(unseen, sampling=PIX)  # ft from the lidar water line

    # floor: 480 ft everywhere, sinking toward 455 ft along the old river channel (corridor from nolin_channel.json)
    floor = np.full((H, W), GENERAL_FLOOR, "float32")
    ch = json.loads((ROOT / "data" / "nolin_channel.json").read_text())
    chan_mask = np.zeros((H, W), bool)
    chan_floor = np.full((H, W), GENERAL_FLOOR, "float32")
    for br in ch["branches"].values():
        pts = br["points"]
        for a, b in zip(pts, pts[1:]):
            n_steps = 60
            for k in range(n_steps + 1):
                t = k / n_steps
                lat = a["lat"] + t * (b["lat"] - a["lat"]); lon = a["lon"] + t * (b["lon"] - a["lon"])
                depth = min(60.0, a["depth_ft"] + t * (b["depth_ft"] - a["depth_ft"]))
                r, c = px(lat, lon)
                if 0 <= r < H and 0 <= c < W:
                    chan_mask[r, c] = True
                    chan_floor[r, c] = min(chan_floor[r, c], max(CHANNEL_FLOOR, SUMMER_POOL - depth))
    d_ch, (cr, cc) = ndimage.distance_transform_edt(~chan_mask, sampling=PIX, return_indices=True)
    halfw = 350.0  # ft: channel influence fades over ~ a long cast or two each side
    floor = GENERAL_FLOOR - (GENERAL_FLOOR - chan_floor[cr, cc]) * np.exp(-(d_ch / halfw) ** 2)

    cap = np.maximum(edge_wl - floor, 1.0)
    depth_below = cap * (1 - np.exp(-edge_slope * d_unseen / cap))
    est = edge_wl - depth_below
    est = ndimage.gaussian_filter(np.where(unseen, est, np.where(seen, Z, TOP)), 2.0)
    surface = np.where(unseen, est, np.where(seen, Z, TOP + 10))   # outside the lake: high, so shore lines close
    print(f"estimated bottom: min {np.nanmin(np.where(unseen, est, np.nan)):.1f} ft, "
          f"deepest at summer pool {SUMMER_POOL - np.nanmin(np.where(unseen, est, np.nan)):.0f} ft ({time.time() - t0:.0f}s)")

    # --- contour lines, split where they cross between measured and estimated bottom
    unseen_d = ndimage.binary_dilation(unseen, iterations=1)
    lines, kept_pts = [], 0
    for e in LEVELS:
        for cs in measure.find_contours(np.nan_to_num(surface, nan=TOP + 10), e):
            rr = np.clip(cs[:, 0].round().astype(int), 0, H - 1); ccx = np.clip(cs[:, 1].round().astype(int), 0, W - 1)
            if not lake[rr, ccx].any():
                continue
            flag = unseen_d[rr, ccx]
            start = 0
            for i in range(1, len(cs) + 1):
                if i == len(cs) or flag[i] != flag[start]:
                    seg = cs[start:i + 1] if i < len(cs) else cs[start:i]
                    if len(seg) >= 3:
                        xs = x0 + seg[:, 1] * PIX; ys = y1 - seg[:, 0] * PIX
                        ls = LineString(np.column_stack([xs, ys])).simplify(PIX * 0.75)
                        if ls.length >= 80:
                            lon, lat = to_ll.transform(*np.array(ls.coords).T)
                            coords = [[round(a, 5), round(b, 5)] for a, b in zip(lon, lat)]
                            kept_pts += len(coords)
                            lines.append({"e": int(e), "est": int(bool(flag[start])), "c": coords})
                    start = i
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    doc = {"generated": time.strftime("%Y-%m-%d"), "levels": LEVELS.astype(int).tolist(),
           "source": "KyFromAbove Phase 2 lidar (Kentucky Division of Geographic Information), flown winter 2022-23 at "
                     "~496 ft; below that the bottom is estimated (est=1).",
           "lines": lines}
    p = out / "contours.json"
    p.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"wrote {p}: {len(lines)} lines, {kept_pts} points, {p.stat().st_size / 1e6:.1f} MB "
          f"(measured {sum(1 for l in lines if not l['est'])}, estimated {sum(1 for l in lines if l['est'])}) "
          f"in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
