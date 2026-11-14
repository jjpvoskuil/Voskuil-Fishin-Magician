"""Probe the pre-dam USGS 1:24,000 topo sheets (1953/54, before Nolin was impounded in 1963) for John's option B
(11-14): can the contour lines under today's lake be read well enough to replace the estimated bottom below ~496 ft?

Runs in GitHub Actions (probe-topo.yml); the sandbox can't reach USGS S3. Writes to OUTDIR:
  <name>_full.jpg       whole sheet, shrunk (to see the collar: contour interval, datum)
  crop_<place>_<sheet>.png  full-resolution crops around a few lake places, both scans where there are two
  info.json             CRS, size, resolution of every sheet
Public-domain USGS maps; no private data (crop centers are public map places, not saved spots).
"""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform as wtransform
from rasterio.windows import Window

S3 = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Maps/HistoricalTopo/GeoTIFF/KY/"
SHEETS = {
    "dickeys_708534": "KY_Dickeys%20Mills_708534_1954_24000_geo.tif",
    "dickeys_803463": "KY_Dickeys%20Mills_803463_1954_24000_geo.tif",
    "beespring_803316": "KY_Bee%20Spring_803316_1953_24000_geo.tif",
    "cubrun_803441": "KY_Cub%20Run_803441_1954_24000_geo.tif",
    "cubrun_708478": "KY_Cub%20Run_708478_1954_24000_geo.tif",
    "clarkson_708385": "KY_Clarkson_708385_1954_24000_geo.tif",
}
# public places: mid-lake by Dog Creek arm, the dam gorge, main lake near the state park (generic map coordinates)
PLACES = {"midlake_east": (37.332, -86.179), "dam": (37.280, -86.247), "statepark": (37.300, -86.210), "upper": (37.36, -86.13)}
HALF_M = 900  # crop half-size in metres


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    info = {}
    for name, fn in SHEETS.items():
        with rasterio.open(f"/vsicurl/{S3}{fn}") as ds:
            info[name] = {"crs": str(ds.crs), "w": ds.width, "h": ds.height, "res": ds.res, "bands": ds.count, "bounds": list(ds.bounds)}
            # whole sheet shrunk
            f = max(1, ds.width // 1800)
            arr = ds.read(out_shape=(ds.count, ds.height // f, ds.width // f))
            img = arr[:3].transpose(1, 2, 0) if ds.count >= 3 else arr[0]
            if ds.count == 1 and ds.colormap(1):
                cm = ds.colormap(1); lut = np.array([cm.get(i, (0, 0, 0, 0))[:3] for i in range(256)], np.uint8); img = lut[arr[0]]
            Image.fromarray(img.astype(np.uint8)).save(out / f"{name}_full.jpg", quality=80)
            for pname, (lat, lon) in PLACES.items():
                xs, ys = wtransform("EPSG:4326", ds.crs, [lon], [lat])
                r, c = ds.index(xs[0], ys[0])
                # pixel size in metres (geographic CRS: degrees)
                px = ds.res[0] * (111320 * np.cos(np.radians(lat)) if ds.crs.is_geographic else 1)
                h = int(HALF_M / px)
                if not (0 <= r < ds.height and 0 <= c < ds.width):
                    continue
                win = Window(max(0, c - h), max(0, r - h), 2 * h, 2 * h)
                a = ds.read(window=win, boundless=True)
                if ds.count == 1 and ds.colormap(1):
                    cm = ds.colormap(1); lut = np.array([cm.get(i, (0, 0, 0, 0))[:3] for i in range(256)], np.uint8); im = lut[a[0]]
                else:
                    im = a[:3].transpose(1, 2, 0)
                Image.fromarray(im.astype(np.uint8)).save(out / f"crop_{pname}_{name}.png")
                info[name].setdefault("crops", {})[pname] = {"px_m": px, "size": 2 * h}
            print(name, info[name]["crs"], ds.width, ds.height)
    (out / "info.json").write_text(json.dumps(info, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
