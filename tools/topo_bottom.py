"""Bottom of Nolin below the lidar water line, read from the pre-dam USGS 1:24,000 topo sheets (John 11-14, option B
for punch-list #100). Called by tools/build_contours.py when TOPO=1; runs in GitHub Actions only.

Why this can work now when the Streamlit-era attempt (SESSION_NOTES entry 13) didn't: that attempt had to label every
contour line by flood-filling between lines, and text/road gaps let the fill leak. Here the lidar already gives the
real bottom down to ~496 ft, so below it there are only a couple of 20-ft contour levels (480, 460, maybe 440) plus
the old riverbed, and each line piece is labeled on its own against a first-guess surface — no flood fill.

Steps, all on build_contours' 8-ft EPSG:3089 grid:
  1. each sheet → masks at full resolution: contour pixels (orange-brown: red clearly above green and blue) and
     water pixels (blue), clipped to the sheet's own 7.5' quad (no collar text), warped with max-resampling;
  2. registration: shift each sheet's contour mask (±80 ft) to where its contour pixels sit on lidar elevations that
     are multiples of 20 ft; the vertical offset (NGVD29 vs NAVD88) comes out of the same fit;
  3. the old river (+ creeks): blue pixels near the lake, skeletonized; elevation along that network = piecewise
     linear between fixed points (lidar where the network is above the water line, the 446-ft pre-dam benchmark at the
     dam, and later the labeled contour crossings);
  4. first-guess bottom = the 11-11 edge-slope estimate, pulled to the riverbed near the river (a plain harmonic fill
     between rim and river was ~19 ft too high in the holdout and labeled almost nothing — run 11-14);
  5. each contour piece under the water line gets the 20-ft level nearest the first guess, if it fits well (median
     within 8 ft, little spread); then the fill is solved again with those pieces held at their level (twice);
  6. HOLDOUT CHECK: the same method is run as if the water line were at 536 ft, on lidar-measured ground between the
     real water line and 536 ft, and compared with the lidar there — alongside the old edge-slope estimate on the same
     ground. That is the "is it garbage?" number.
"""
import json
import math
import os
import time

import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import Resampling, reproject
from scipy import ndimage, sparse
from scipy.sparse import csgraph
from scipy.sparse.linalg import spsolve
from shapely.geometry import box as sbox
from shapely.ops import transform as stransform
from pyproj import Transformer
from skimage.morphology import skeletonize

S3 = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Maps/HistoricalTopo/GeoTIFF/KY/"
# pre-dam 1:24,000 sheets (the lake was impounded in 1963) and their 7.5' quads (west, south)
SHEETS = [
    ("Dickeys Mills 1954", "KY_Dickeys%20Mills_708534_1954_24000_geo.tif", (-86.25, 37.25)),
    ("Bee Spring 1953", "KY_Bee%20Spring_803316_1953_24000_geo.tif", (-86.375, 37.25)),
    ("Cub Run 1954", "KY_Cub%20Run_803441_1954_24000_geo.tif", (-86.125, 37.25)),
    ("Clarkson 1954", "KY_Clarkson_708385_1954_24000_geo.tif", (-86.25, 37.375)),
    ("Leitchfield 1954", "KY_Leitchfield_709087_1954_24000_geo.tif", (-86.375, 37.375)),
    ("Millerstown 1954", "KY_Millerstown_709298_1954_24000_geo.tif", (-86.125, 37.375)),
]
QUAD = 0.125
INTERVAL = 20.0
DAM_BENCHMARK = 446.0   # USGS benchmark at Kyrock / Dismal Rock, at the dam gorge (data/nolin_channel.json)
HOLDOUT_LINE = 536.0


def log(*a):
    print("[topo]", *a, flush=True)


# ---------------------------------------------------------------- 1. sheets → masks on the grid
def sheet_masks(H, W, x0, y1, pix, lake_bbox):
    """Returns (contour, water, cover) uint8 arrays on the grid + per-sheet contour masks for registration."""
    dst_tf = rasterio.transform.from_origin(x0, y1, pix, pix)
    to_ky = Transformer.from_crs("EPSG:4326", "EPSG:3089", always_xy=True).transform
    contour = np.zeros((H, W), np.uint8); water = np.zeros((H, W), np.uint8); cover = np.zeros((H, W), bool)
    per = []
    lon0, lat0, lon1, lat1 = lake_bbox
    for name, fn, (qw, qs) in SHEETS:
        if qw > lon1 or qw + QUAD < lon0 or qs > lat1 or qs + QUAD < lat0:
            continue
        t = time.time()
        with rasterio.open(f"/vsicurl/{S3}{fn}") as ds:
            a = ds.read()
            if ds.count == 1 and ds.colormap(1):
                cm = ds.colormap(1); lut = np.array([cm.get(i, (0, 0, 0, 0))[:3] for i in range(256)], np.uint8)
                rgb = lut[a[0]].astype(np.int16)
            else:
                rgb = a[:3].transpose(1, 2, 0).astype(np.int16)
            R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            cmask = ((R - G > 22) & (R - B > 45) & (R > 120)).astype(np.uint8)
            wmask = ((B - R > 30) & (B > 120)).astype(np.uint8)
            del rgb, R, G, B, a
            cg = np.zeros((H, W), np.uint8); wg = np.zeros((H, W), np.uint8)
            for src, dst in ((cmask, cg), (wmask, wg)):
                reproject(src, dst, src_transform=ds.transform, src_crs=ds.crs, dst_transform=dst_tf, dst_crs="EPSG:3089",
                          resampling=Resampling.max)
        quad = stransform(to_ky, sbox(qw, qs, qw + QUAD, qs + QUAD).segmentize(0.002))
        inq = features.rasterize([(quad, 1)], out_shape=(H, W), transform=dst_tf).astype(bool)
        # a few px in from the neatline (it's drawn in black, and the collar ticks are brown)
        inq = ndimage.binary_erosion(inq, iterations=4)
        cg[~inq] = 0; wg[~inq] = 0
        per.append((name, cg, inq))
        water |= wg; cover |= inq
        log(f"{name}: contour px {int(cg.sum())}, water px {int(wg.sum())} ({time.time() - t:.0f}s)")
    return per, water.astype(bool), cover


# ---------------------------------------------------------------- 2. registration against the lidar
def register(per, Z, ground, pix):
    """Shift each sheet's contour mask to best fit lidar multiples of 20 ft. Returns (contour mask, report)."""
    H, W = Z.shape
    ok_ground = ground & (Z > 500) & (Z < 760)
    resid = np.abs(Z - np.round(Z / INTERVAL) * INTERVAL)
    out = np.zeros((H, W), bool); report = []
    for name, cg, inq in per:
        rr, cc = np.nonzero(cg)
        best = None
        for dr in range(-10, 11):       # ±80 ft: also absorbs the NAD27→NAD83 shift (no datum grids on the runner)
            for dc in range(-10, 11):
                r2, c2 = rr + dr, cc + dc
                k = (r2 >= 0) & (r2 < H) & (c2 >= 0) & (c2 < W)
                r2, c2 = r2[k], c2[k]
                g = ok_ground[r2, c2]
                if g.sum() < 2000:
                    continue
                score = float((resid[r2[g], c2[g]] < 3.0).mean())
                if not best or score > best[0]:
                    best = (score, dr, dc)
        if not best:
            report.append({"sheet": name, "skipped": "too little lidar ground"}); continue
        score, dr, dc = best
        shifted = np.zeros((H, W), bool)
        r2, c2 = rr + dr, cc + dc; k = (r2 >= 0) & (r2 < H) & (c2 >= 0) & (c2 < W)
        shifted[r2[k], c2[k]] = True
        g = shifted & ok_ground
        dz = (Z - np.round(Z / INTERVAL) * INTERVAL)[g]
        near = dz[np.abs(dz) < 6]
        chance = 6.0 / INTERVAL  # fraction within ±3 ft if contour pixels sat on random elevations
        rep = {"sheet": name, "shift_ft": [dc * pix, -dr * pix], "within_3ft": round(score, 3), "chance": round(chance, 3),
               "vertical_offset_ft": round(float(np.median(near)), 2) if near.size else None, "px": int(g.sum())}
        report.append(rep); log("register", rep)
        out |= shifted
    return out, report


# ---------------------------------------------------------------- harmonic fill helpers
def laplace(domain, fixed, k=4):
    """Harmonic interpolation over `domain` (bool, grid) with `fixed` values (nan = free), solved on a k× coarser grid,
    returned upsampled to the grid (nan outside domain or where no fixed value is reachable)."""
    H, W = domain.shape
    h, w = math.ceil(H / k), math.ceil(W / k)
    pad = lambda a, v: np.pad(a, ((0, h * k - H), (0, w * k - W)), constant_values=v)
    D = pad(domain, False).reshape(h, k, w, k).any(axis=(1, 3))
    F = pad(np.where(np.isfinite(fixed), fixed, 0.0), 0.0).reshape(h, k, w, k).sum(axis=(1, 3))
    N = pad(np.isfinite(fixed), False).reshape(h, k, w, k).sum(axis=(1, 3))
    Fc = np.where(N > 0, F / np.maximum(N, 1), np.nan)
    node = D | (N > 0)
    idx = -np.ones((h, w), int); free = node & ~(N > 0)
    idx[free] = np.arange(free.sum())
    n = int(free.sum())
    rows, cols, vals = [], [], []
    rhs = np.zeros(n)
    deg = np.zeros(n)
    fr, fc = np.nonzero(free)
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        r2, c2 = fr + dr, fc + dc
        k_ = (r2 >= 0) & (r2 < h) & (c2 >= 0) & (c2 < w)
        i = idx[fr[k_], fc[k_]]; r2, c2 = r2[k_], c2[k_]
        isfree = free[r2, c2]; isfix = (N[r2, c2] > 0)
        deg_add = isfree | isfix
        np.add.at(deg, i[deg_add], 1)
        rows.append(i[isfree]); cols.append(idx[r2[isfree], c2[isfree]]); vals.append(-np.ones(isfree.sum()))
        np.add.at(rhs, i[isfix], Fc[r2[isfix], c2[isfix]])
    rows.append(np.arange(n)); cols.append(np.arange(n)); vals.append(deg + 1e-9)
    A = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    # free cells with no path to a fixed value: drop them
    adj = A.copy(); adj.setdiag(0); adj.eliminate_zeros()
    ncomp, lab = csgraph.connected_components(adj, directed=False)
    anchored = np.zeros(ncomp, bool); np.logical_or.at(anchored, lab, rhs != 0)
    keep = anchored[lab]
    sol = np.full(n, np.nan)
    if keep.any():
        ki = np.flatnonzero(keep); sub = A[ki][:, ki]
        sol[ki] = spsolve(sub.tocsc(), rhs[ki])
    out = np.where(N > 0, Fc, np.nan)
    out[free] = sol
    up = np.repeat(np.repeat(out, k, 0), k, 1)[:H, :W]
    # smooth the blockiness a little (nan-aware)
    v = np.isfinite(up)
    num = ndimage.gaussian_filter(np.where(v, up, 0), k * 0.6); den = ndimage.gaussian_filter(v.astype(float), k * 0.6)
    sm = np.where(den > 0.2, num / np.maximum(den, 1e-6), np.nan)
    return np.where(domain & v, sm, np.nan)


def network_profile(skel, fixed_pts):
    """1-D harmonic (piecewise linear) elevation along a skeleton network. fixed_pts: {(r, c): elev}."""
    rr, cc = np.nonzero(skel)
    id_ = -np.ones(skel.shape, int); id_[rr, cc] = np.arange(len(rr))
    rows, cols = [], []
    for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
        r2, c2 = rr + dr, cc + dc
        k = (r2 >= 0) & (r2 < skel.shape[0]) & (c2 >= 0) & (c2 < skel.shape[1])
        j = id_[r2[k], c2[k]]; m = j >= 0
        rows.append(np.arange(len(rr))[k][m]); cols.append(j[m])
    r_ = np.concatenate(rows); c_ = np.concatenate(cols)
    n = len(rr)
    Adj = sparse.coo_matrix((np.ones(len(r_)), (r_, c_)), shape=(n, n)).tocsr(); Adj = Adj + Adj.T
    deg = np.asarray(Adj.sum(1)).ravel()
    fixed = np.full(n, np.nan)
    for (r, c), e in fixed_pts.items():
        if id_[r, c] >= 0:
            fixed[id_[r, c]] = e
    isf = np.isfinite(fixed); free = ~isf
    L = sparse.diags(deg) - Adj
    fi = np.flatnonzero(free); xi = np.flatnonzero(isf)
    out = fixed.copy()
    if len(fi) and len(xi):
        Lff = L[fi][:, fi]; Lfx = L[fi][:, xi]
        ncomp, lab = csgraph.connected_components(Adj[fi][:, fi], directed=False)
        rhs = -Lfx @ fixed[xi]
        touched = np.zeros(ncomp, bool); np.logical_or.at(touched, lab, np.asarray(np.abs(Lfx).sum(1)).ravel() > 0)
        keep = touched[lab]
        kk = np.flatnonzero(keep)
        sol = spsolve((Lff[kk][:, kk] + sparse.eye(len(kk)) * 1e-9).tocsc(), rhs[kk])
        out[fi[kk]] = sol
    prof = np.full(skel.shape, np.nan, "float32"); prof[rr, cc] = out
    return prof


# ---------------------------------------------------------------- 3–5. the method (used for real and for the holdout)
def solve_bottom(Z, known, unknown, contour, skel, dam_rc, line_level, levels, pix, tag, offset=0.0):
    """known: lidar ground used as boundary; unknown: cells to fill. Returns (surface over unknown, stats)."""
    H, W = Z.shape
    # riverbed fixed points: lidar where the network is on known ground (min within 3 px: the channel, not the bank)
    zmin = ndimage.minimum_filter(np.where(known, Z, np.inf), size=7)
    fixed = {}
    kr, kc = np.nonzero(skel & known & np.isfinite(zmin) & (zmin < line_level + 40))
    for r, c in zip(kr, kc):
        fixed[(r, c)] = float(zmin[r, c])
    if dam_rc is not None:
        fixed[dam_rc] = DAM_BENCHMARK
    prof = network_profile(skel, fixed)
    river_fix = np.where(skel & unknown & np.isfinite(prof), np.minimum(prof, line_level), np.nan)

    boundary = np.where(known & ndimage.binary_dilation(unknown, iterations=2), Z, np.nan)
    # first guess = the 11-11 edge-slope estimate (holdout: ~4 ft median error), pulled down to the riverbed near the
    # river; a plain harmonic fill between rim and river came out ~19 ft too high and labeled almost nothing
    E = np.where(unknown, old_estimate(Z, known, unknown, line_level, pix), np.nan)
    rv = np.isfinite(river_fix)
    if rv.any():
        d_r, (ir, ic) = ndimage.distance_transform_edt(~rv, sampling=pix, return_indices=True)
        w = np.exp(-(d_r / 150.0) ** 2)
        E = np.where(unknown, np.minimum(E, (1 - w) * E + w * river_fix[ir, ic]), np.nan)
    stats = {"tag": tag, "river_fixed_points": len(fixed)}
    # contour pieces under the line
    pieces, n = ndimage.label(contour & unknown, structure=np.ones((3, 3)))
    for it in range(2):
        idx = np.arange(1, n + 1)
        med = ndimage.median(np.where(np.isfinite(E), E, -9999), pieces, idx)
        q1 = ndimage.labeled_comprehension(E, pieces, idx, lambda v: np.nanpercentile(v, 25) if np.isfinite(v).any() else np.nan, float, np.nan)
        q3 = ndimage.labeled_comprehension(E, pieces, idx, lambda v: np.nanpercentile(v, 75) if np.isfinite(v).any() else np.nan, float, np.nan)
        size = ndimage.sum(np.ones_like(pieces), pieces, idx)
        lv = np.array(levels, float) + offset   # map datum (NGVD29) → lidar datum
        nearest = lv[np.argmin(np.abs(med[:, None] - lv[None, :]), axis=1)]
        good = (size >= 12) & (med > 0) & (np.abs(med - nearest) <= 8) & ((q3 - q1) <= 14)
        lab_val = np.full(n + 1, np.nan); lab_val[idx[good]] = nearest[good]
        cfix = lab_val[pieces]; cfix[pieces == 0] = np.nan
        stats[f"pass{it + 1}"] = {"pieces": int(n), "labeled": int(good.sum()),
                                  "by_level": {str(int(l)): int((good & (nearest == l)).sum()) for l in lv}}
        # contour crossings of the river feed back into the riverbed profile
        near_r = ndimage.binary_dilation(skel, iterations=3)
        cr, cc = np.nonzero(near_r & np.isfinite(cfix))
        if len(cr):
            _, (ir, ic) = ndimage.distance_transform_edt(~skel, return_indices=True)
            for r, c in zip(cr, cc):
                fixed[(int(ir[r, c]), int(ic[r, c]))] = float(cfix[r, c])
            prof = network_profile(skel, fixed)
            river_fix = np.where(skel & unknown & np.isfinite(prof), np.minimum(prof, line_level), np.nan)
        fixed2d = np.where(np.isfinite(cfix), cfix, np.where(np.isfinite(river_fix), river_fix, boundary))
        E = laplace(unknown | np.isfinite(boundary), fixed2d)
    E = np.minimum(E, line_level)
    log(tag, json.dumps(stats))
    return E, stats


def old_estimate(Z, known, unknown, line_level, pix):
    """The 11-11 edge-slope estimate (build_contours.py), re-run from a given water line, for the holdout comparison."""
    gy, gx = np.gradient(np.where(known, Z, np.nan), pix)
    slope = np.hypot(gx, gy)
    band = known & np.isfinite(slope) & (ndimage.distance_transform_edt(~unknown, sampling=pix) < 120)
    num = ndimage.gaussian_filter(np.where(band, np.clip(slope, 0.02, 0.8), 0), 38)
    den = ndimage.gaussian_filter(band.astype("float32"), 38)
    es = np.clip(np.where(den > 1e-4, num / np.maximum(den, 1e-4), 0.12), 0.03, 0.6)
    d = ndimage.distance_transform_edt(unknown, sampling=pix)
    cap = max(line_level - 480.0, 1.0)
    return line_level - cap * (1 - np.exp(-es * d / cap))



def debug_overlays(per, Z, ground, x0, y1, pix, outdir):
    """Red = 1950s map contour pixels, blue = lidar 20-ft contours, purple = both. A few public lake places."""
    from PIL import Image
    to_ky = Transformer.from_crs("EPSG:4326", "EPSG:3089", always_xy=True)
    allc = np.zeros(Z.shape, bool)
    for _, cg, _ in per:
        allc |= cg.astype(bool)
    lid = ground & (np.abs(Z - np.round(Z / INTERVAL) * INTERVAL) < 1.0) & (Z > 500)
    os.makedirs(outdir, exist_ok=True)
    for name, (lat, lon) in {"midlake": (37.33, -86.17), "dam": (37.280, -86.247), "statepark": (37.300, -86.210), "upper": (37.36, -86.13)}.items():
        x, y = to_ky.transform(lon, lat); r, c = int((y1 - y) / pix), int((x - x0) / pix)
        h = 300
        sl = (slice(max(0, r - h), r + h), slice(max(0, c - h), c + h))
        im = np.full(allc[sl].shape + (3,), 255, np.uint8)
        im[lid[sl]] = (60, 110, 255); im[allc[sl]] = (230, 60, 50); im[allc[sl] & lid[sl]] = (130, 0, 160)
        Image.fromarray(im).save(os.path.join(outdir, f"debug_{name}.png"))
    log("debug overlays written")


def debug_overlay(Z, ground, per, water, x0, y1, pix, outdir):
    """Alignment diagnostics: wide shift search (±800 ft) per sheet + an overlay PNG (lidar 20-ft contours red, map
    contour pixels black, map water blue) around mid-lake."""
    from PIL import Image
    H, W = Z.shape
    resid = np.abs(Z - np.round(Z / INTERVAL) * INTERVAL)
    okg = ground & (Z > 500) & (Z < 760)
    rep = []
    for name, cg, inq in per:
        rr, cc = np.nonzero(cg)
        if len(rr) > 400000:
            sel = np.random.default_rng(0).choice(len(rr), 400000, replace=False); rr, cc = rr[sel], cc[sel]
        best = []
        for dr in range(-100, 101, 4):
            for dc in range(-100, 101, 4):
                r2, c2 = rr + dr, cc + dc
                k = (r2 >= 0) & (r2 < H) & (c2 >= 0) & (c2 < W); r2, c2 = r2[k], c2[k]
                g = okg[r2, c2]
                if g.sum() < 2000:
                    continue
                best.append(((resid[r2[g], c2[g]] < 3).mean(), dr, dc))
        best.sort(reverse=True)
        rep.append({"sheet": name, "best": [(round(float(a), 3), int(b * pix), int(c * pix)) for a, b, c in best[:3]]})
        log("wide-search", rep[-1])
    to_ky = Transformer.from_crs("EPSG:4326", "EPSG:3089", always_xy=True)
    x, y = to_ky.transform(-86.17, 37.33)   # the app's generic lake center (public); never a saved spot here
    r0, c0 = int((y1 - y) / pix), int((x - x0) / pix)
    h = 380
    sl = (slice(max(0, r0 - h), r0 + h), slice(max(0, c0 - h), c0 + h))
    z = Z[sl]
    img = np.full(z.shape + (3,), 255, np.uint8)
    shade = np.clip(128 + 40 * np.gradient(np.nan_to_num(z, nan=500))[1], 60, 230).astype(np.uint8)
    img[..., 0] = img[..., 1] = img[..., 2] = np.where(np.isfinite(z), shade, 255)
    lid = np.zeros(z.shape, bool)
    for lv in range(440, 760, 20):
        lid |= (np.nan_to_num(z) >= lv) & (np.roll(np.nan_to_num(z), 1, 1) < lv)
        lid |= (np.nan_to_num(z) >= lv) & (np.roll(np.nan_to_num(z), 1, 0) < lv)
    img[lid] = (230, 40, 40)
    cm = np.zeros(z.shape, bool)
    for _, cg, _ in per:
        cm |= cg[sl].astype(bool)
    img[cm] = (0, 0, 0)
    img[water[sl]] = (40, 90, 255)
    Image.fromarray(img).save(os.path.join(outdir, "overlay_midlake.png"))
    return rep


def topo_surface(Z, WL, lake, seen, unseen, ground, x0, y1, pix, lake_bbox, dam_rc, outdir):
    t0 = time.time()
    H, W = Z.shape
    per, water, cover = sheet_masks(H, W, x0, y1, pix, lake_bbox)
    os.makedirs(outdir, exist_ok=True)
    wide = debug_overlay(Z, ground, per, water, x0, y1, pix, outdir)
    if os.environ.get("TOPO_DEBUG") == "1":
        debug_overlays(per, Z, ground, x0, y1, pix, outdir)
        if os.environ.get("TOPO_STOP") == "1":
            raise SystemExit("TOPO_STOP after debug overlays")
    contour, reg = register(per, Z, ground, pix)
    offs = [r["vertical_offset_ft"] for r in reg if r.get("vertical_offset_ft") is not None and r["within_3ft"] > 2 * r["chance"]]
    offset = float(np.median(offs)) if offs else 0.0
    log(f"vertical offset map→lidar {offset:+.2f} ft")
    near_lake = ndimage.binary_dilation(lake, iterations=60)
    wat = ndimage.binary_closing(water & near_lake, iterations=2)
    skel = skeletonize(wat)
    lab, n = ndimage.label(skel, structure=np.ones((3, 3)))
    sizes = ndimage.sum(skel, lab, range(1, n + 1))
    skel = np.isin(lab, 1 + np.flatnonzero(sizes >= 40))
    # snap the dam point to the network
    if dam_rc is not None and skel.any():
        _, (ir, ic) = ndimage.distance_transform_edt(~skel, return_indices=True)
        dam_rc = (int(ir[dam_rc]), int(ic[dam_rc]))
    log(f"river/creek network: {int(skel.sum())} px; sheets cover {cover.mean():.2f} of the grid ({time.time() - t0:.0f}s)")

    report = {"registration": reg, "wide_search": wide}
    # ---- holdout: pretend the water line is at 536 ft
    dom = ndimage.binary_dilation(lake, iterations=150) & cover
    low = dom & (np.nan_to_num(Z, nan=9999) < HOLDOUT_LINE)
    lab2, _ = ndimage.label(low | unseen)
    ids = np.unique(lab2[unseen & cover]); ids = ids[ids > 0]
    ho_unknown = np.isin(lab2, ids) & cover
    ho_known = ground & ~ho_unknown & cover
    ho_levels = [440, 460, 480, 500, 520]
    E_ho, st_ho = solve_bottom(Z, ho_known, ho_unknown, contour, skel, dam_rc, HOLDOUT_LINE, ho_levels, pix, "holdout", offset)
    old_ho = old_estimate(Z, ho_known, ho_unknown, HOLDOUT_LINE, pix)
    test = ho_unknown & ground & np.isfinite(Z) & (Z > 497) & (Z < HOLDOUT_LINE - 2) & np.isfinite(E_ho)
    err_new = (E_ho - Z)[test]; err_old = (old_ho - Z)[test]
    def by_depth(err, depth):
        out = {}
        for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 60)):
            m = (depth >= lo) & (depth < hi)
            if m.sum() > 1000:
                out[f"{lo}-{hi}ft_below_line"] = {"cells": int(m.sum()), "median_abs_ft": round(float(np.median(np.abs(err[m]))), 1),
                                                   "bias_ft": round(float(np.median(err[m])), 1)}
        return out
    def summ(e):
        a = np.abs(e)
        return {"median_abs_ft": round(float(np.median(a)), 1), "mean_abs_ft": round(float(a.mean()), 1),
                "within_5ft": round(float((a <= 5).mean()), 3), "within_10ft": round(float((a <= 10).mean()), 3),
                "bias_ft": round(float(np.median(e)), 1)}
    report["holdout"] = {"line_ft": HOLDOUT_LINE, "test_cells": int(test.sum()), "acres": round(float(test.sum() * pix * pix / 43560)),
                         "topo": summ(err_new), "old_estimate": summ(err_old), "solve": st_ho,
                         "topo_by_depth": by_depth(err_new, HOLDOUT_LINE - Z[test]), "old_by_depth": by_depth(err_old, HOLDOUT_LINE - Z[test]),
                         "coverage": round(float(np.isfinite(E_ho)[ho_unknown & ground & (Z > 497)].mean()), 3), "vertical_offset_ft": round(offset, 2)}
    log("HOLDOUT", json.dumps(report["holdout"]))

    # ---- the real thing: below the lidar water line
    known = ground & cover
    unknown = unseen & cover
    line = float(np.nanmedian(WL[unseen])) if np.isfinite(WL[unseen]).any() else 496.0
    E, st = solve_bottom(Z, known, unknown, contour, skel, dam_rc, line + 0.5, [420, 440, 460, 480], pix, "below-waterline", offset)
    report["below_waterline"] = {"line_ft": round(line, 1), "solve": st,
                                 "coverage": round(float(np.isfinite(E)[unseen].mean()), 3),
                                 "min_ft": round(float(np.nanmin(E)), 1) if np.isfinite(E).any() else None,
                                 "minutes": round((time.time() - t0) / 60, 1)}
    old_real = np.where(unknown, old_estimate(Z, known, unknown, line + 0.5, pix), np.nan)
    diff = E - old_real
    v = np.isfinite(diff)
    report["below_waterline"]["topo_minus_old_ft"] = {p: round(float(np.percentile(diff[v], p)), 1) for p in (5, 25, 50, 75, 95)} if v.any() else None
    report["below_waterline"]["deeper_than_480_acres"] = {"topo": round(float((E[unknown] < 480).sum() * pix * pix / 43560)),
                                                          "old": round(float((old_real[unknown] < 480).sum() * pix * pix / 43560))}
    log("BELOW", json.dumps(report["below_waterline"]))
    try:   # picture: lake below the water line, blue = topo deeper than the old estimate, red = shallower
        from PIL import Image
        dd = np.clip(np.nan_to_num(diff), -20, 20)
        img = np.full(diff.shape + (3,), 235, np.uint8)
        img[..., 0] = np.where(v, np.clip(235 + dd * 8, 40, 255), 235).astype(np.uint8)
        img[..., 1] = np.where(v, np.clip(235 - np.abs(dd) * 7, 40, 255), 235).astype(np.uint8)
        img[..., 2] = np.where(v, np.clip(235 - dd * 8, 40, 255), 235).astype(np.uint8)
        img[skel] = (0, 0, 0)
        Image.fromarray(img[::3, ::3]).save(os.path.join(outdir, "topo_vs_old.png"))
    except Exception as e:
        log("png failed", e)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "topo_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    return E, skel, report
