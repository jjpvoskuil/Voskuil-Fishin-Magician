"""Writes web/src/lib/data/cabelas_picks.json from the old app's curated data/cabelas_picks_cache.csv (2 real Cabela's
products per lure type, public catalog info - no private data). The new app can't search Cabela's live: their site
blocks servers (403) and other websites (CORS) - tested 11-10. Re-run if the CSV is refreshed:
    python3 web/tools/export_cabelas_picks.py   (reads the data branch if data/ isn't checked out)"""
import csv, io, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.lures import LURE_PROFILES
p = ROOT / "data" / "cabelas_picks_cache.csv"
text = p.read_text() if p.exists() else subprocess.check_output(["git", "-C", str(ROOT), "show", "origin/data:data/cabelas_picks_cache.csv"]).decode()
by_name = {v["name"]: k for k, v in LURE_PROFILES.items()}
out = {}
for r in csv.DictReader(io.StringIO(text)):
    k = by_name.get(r["category"])
    if not k:
        continue
    out.setdefault(k, []).append({"sku": r["sku"], "brand": r["brand"], "description": r["description"],
                                  "price": float(r["price"]) if r["price"] else None, "image_url": r["image_url"]})
for k in out:
    out[k] = out[k][:2]
dest = ROOT / "web" / "src" / "lib" / "data" / "cabelas_picks.json"
dest.write_text(json.dumps(out, indent=1))
print(f"wrote {dest.relative_to(ROOT)}: {sum(len(v) for v in out.values())} products for {len(out)} lure types")
