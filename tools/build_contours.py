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
import os
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
    # slope of the measured bottom near the lidar water line, spread smoothly over the unseen water (normalized
    # convolution, ~300 ft): a nearest-bank lookup jumps mid-channel and drew cross-channel ticks (11-11)
    band = seen & np.isfinite(slope) & (ndimage.distance_transform_edt(~unseen, sampling=PIX) < 120)
    num = ndimage.gaussian_filter(np.where(band, np.clip(slope, 0.02, 0.8), 0), 38)
    den = ndimage.gaussian_filter(band.astype("float32"), 38)
    edge_slope = np.clip(np.where(den > 1e-4, num / np.maximum(den, 1e-4), 0.12), 0.03, 0.6)
    wl_known = ~np.isnan(WL)
    wl_num = ndimage.gaussian_filter(np.where(wl_known, WL, 0), 60); wl_den = ndimage.gaussian_filter(wl_known.astype("float32"), 60)
    edge_wl = np.where(wl_known, WL, np.where(wl_den > 1e-4, wl_num / np.maximum(wl_den, 1e-4), 496.0))
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

    # option B (John 11-14, TOPO=1): the bottom below the water line from the pre-dam 1953/54 USGS sheets where they
    # reach; the edge-slope estimate below stays as the fallback (and is what the holdout check compares against)
    topo_E = None
    if os.environ.get("TOPO") == "1":
        from topo_bottom import topo_surface
        ground = np.isfinite(Z) & ~water
        topo_E, topo_skel, _ = topo_surface(Z, WL, lake, seen, unseen, ground, x0, y1, PIX, (lon0, lat0, lon1, lat1), (dr, dc), out)
        if topo_skel.any():   # the real old river (and creeks) for the channel-swing suggestions
            d_ch = np.minimum(d_ch, ndimage.distance_transform_edt(~topo_skel, sampling=PIX))

    cap = np.maximum(edge_wl - floor, 1.0)
    depth_below = cap * (1 - np.exp(-edge_slope * d_unseen / cap))
    est = edge_wl - depth_below
    from_topo = np.zeros((H, W), bool)
    if topo_E is not None:
        from_topo = unseen & np.isfinite(topo_E)
        est = np.where(from_topo, topo_E, est)
    est = ndimage.gaussian_filter(np.where(unseen, est, np.where(seen, Z, TOP)), 3.0)
    surface = np.where(unseen, est, np.where(seen, Z, TOP + 10))   # outside the lake: high, so shore lines close
    print(f"estimated bottom: min {np.nanmin(np.where(unseen, est, np.nan)):.1f} ft, "
          f"deepest at summer pool {SUMMER_POOL - np.nanmin(np.where(unseen, est, np.nan)):.0f} ft ({time.time() - t0:.0f}s)")

    # --- contour lines, split where they cross between measured and estimated bottom
    lines, kept_pts = [], 0
    for e in LEVELS:
        for cs in measure.find_contours(np.nan_to_num(surface, nan=TOP + 10), e):
            rr = np.clip(cs[:, 0].round().astype(int), 0, H - 1); ccx = np.clip(cs[:, 1].round().astype(int), 0, W - 1)
            if not lake[rr, ccx].any():
                continue
            # 0 = lidar, 1 = edge-slope estimate, 2 = read from the pre-dam USGS map
            flag = np.where(e < edge_wl[rr, ccx] - 0.3, np.where(from_topo[rr, ccx], 2, 1), 0)
            # merge flicker: runs shorter than 8 vertices take their neighbors' value
            runs = np.flatnonzero(np.diff(flag.astype(int))) + 1
            bounds = np.concatenate([[0], runs, [len(flag)]])
            for a, b in zip(bounds[:-1], bounds[1:]):
                if b - a < 8 and a > 0:
                    flag[a:b] = flag[a - 1]
            start = 0
            for i in range(1, len(cs) + 1):
                if i == len(cs) or flag[i] != flag[start]:
                    seg = cs[start:i + 1] if i < len(cs) else cs[start:i]
                    if len(seg) >= 3:
                        xs = x0 + seg[:, 1] * PIX; ys = y1 - seg[:, 0] * PIX
                        ls = LineString(np.column_stack([xs, ys])).simplify(PIX * 0.75)
                        closed = np.hypot(*(seg[0] - seg[-1])) < 2
                        if ls.length >= (400 if closed else 150):
                            lon, lat = to_ll.transform(*np.array(ls.coords).T)
                            coords = [[round(a, 5), round(b, 5)] for a, b in zip(lon, lat)]
                            kept_pts += len(coords)
                            lines.append({"e": int(e), "est": int(flag[start]), "c": coords})
                    start = i
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    (out / "suggestions.json").write_text(json.dumps(suggest(surface, lake, seen, unseen, d_ch, slope, edge_wl, x0, y1, to_ll),
                                                     separators=(",", ":")))
    doc = {"generated": time.strftime("%Y-%m-%d"), "levels": LEVELS.astype(int).tolist(),
           "source": "KyFromAbove Phase 2 lidar (Kentucky Division of Geographic Information), flown winter 2022-23 at "
                     "~496 ft; below that the bottom is estimated (est=1).",
           "lines": lines}
    p = out / "contours.json"
    p.write_text(json.dumps(doc, separators=(",", ":")))
    if topo_E is not None:
        doc["source"] += " Where the 1953/54 pre-dam USGS 1:24,000 topo maps reach, the bottom below it is read from them (est=2)."
        p.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"wrote {p}: {len(lines)} lines, {kept_pts} points, {p.stat().st_size / 1e6:.1f} MB "
          f"(measured {sum(1 for l in lines if not l['est'])}, estimated {sum(1 for l in lines if l['est'])}) "
          f"in {time.time() - t0:.0f}s")


def suggest(surface, lake, seen, unseen, d_ch, slope, edge_wl, x0, y1, to_ll):
    """'Spots to try' (John 11-10/11-11): structure bass relate to, found in the lake's shape and the measured bottom.
    Judged at summer pool (515 ft); each entry keeps bottom elevations so the app shows depths at today's level."""
    H, W = lake.shape
    land = ~lake
    d_land = ndimage.distance_transform_edt(lake, sampling=PIX)          # ft from shore (in the lake)
    d_lake = ndimage.distance_transform_edt(land, sampling=PIX)          # ft from water (on land)
    water_around = ndimage.gaussian_filter(lake.astype("float32"), 30)  # ~250 ft neighborhood
    depth_sp = SUMMER_POOL - surface
    cands = []
    def clusters(mask, kind, why, min_px, weight):
        lab, n = ndimage.label(ndimage.binary_dilation(mask, iterations=2))
        if not n:
            return
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        for i, sz in enumerate(sizes, start=1):
            if sz < min_px:
                continue
            rr, cc = np.nonzero((lab == i) & mask)
            k = len(rr) // 2
            r, c = int(np.median(rr)), int(np.median(cc))
            if not mask[r, c]:
                r, c = int(rr[k]), int(cc[k])
            # depth range around it (within ~150 ft), at summer pool
            win = (slice(max(0, r - 19), r + 20), slice(max(0, c - 19), c + 20))
            el = surface[win][lake[win]]
            if el.size == 0:
                continue
            cands.append({"r": r, "c": c, "kind": kind, "why": why, "score": weight * math.log1p(sz),
                          "emin": float(np.percentile(el, 5)), "emax": float(np.percentile(el, 95)),
                          "est": bool(unseen[win].mean() > 0.5)})
    # 1. points: land sticking out into the lake (lots of water around a shoreline pixel)
    tips = land & (d_lake <= PIX * 2) & (water_around > 0.66)
    clusters(tips, "point", "Point sticking out into the lake — bass use the tip and the sides where it tapers into deeper water.", 6, 1.3)
    # 2. steep breaks / bluff walls in the measured band (6-19 ft at summer pool)
    steep = seen & (depth_sp > 6) & (depth_sp < 19) & (slope > 0.5)
    clusters(steep, "break", "Steep break or bluff wall — fast drop from shallow to deep, good for jerkbaits, cranks and jigs down the face.", 25, 1.0)
    # 3. old channel swinging in against the bank
    swing = lake & (d_ch < 120) & (d_land < 200) & (depth_sp > 10)
    clusters(swing, "swing", "Old river channel swings close to the bank — deep water right next to shallow; fish hold on the edge.", 15, 1.1)
    # 4. shallow flat next to deep water (measured flat 3-12 ft, deep water within ~250 ft)
    deep_near = ndimage.maximum_filter(np.where(lake, depth_sp, 0), size=63) > 25
    flat = seen & (depth_sp > 3) & (depth_sp < 12) & (np.nan_to_num(slope, nan=1) < 0.05) & deep_near
    clusters(flat, "flat", "Shallow flat next to deep water — a feeding area in low light and spring/fall; work the edge where it drops.", 120, 0.9)
    # keep the best, spread out (>= ~250 m apart), up to 70
    cands.sort(key=lambda d: -d["score"])
    kept = []
    for cnd in cands:
        if all(math.hypot(cnd["r"] - k["r"], cnd["c"] - k["c"]) * PIX > 820 for k in kept):
            kept.append(cnd)
        if len(kept) >= 70:
            break
    outl = []
    for k in kept:
        lon, lat = to_ll.transform(x0 + (k["c"] + 0.5) * PIX, y1 - (k["r"] + 0.5) * PIX)
        outl.append({"lat": round(lat, 5), "lon": round(lon, 5), "kind": k["kind"], "why": k["why"], "emin": round(k["emin"], 1),
                     "emax": round(k["emax"], 1), "est": int(k["est"]), "score": round(k["score"], 2)})
    counts = {x: sum(1 for o in outl if o["kind"] == x) for x in ("point", "break", "swing", "flat")}
    print(f"spots to try: {len(outl)} {counts}")
    return {"generated": time.strftime("%Y-%m-%d"), "spots": outl}


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
