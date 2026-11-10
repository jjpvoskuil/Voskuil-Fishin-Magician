"""Export the lure data tables from the Python reference into web/src/lib/data/lures.data.json, so the JS port uses
exactly the same profiles, colors, presentations, forage notes and video links. Re-run after editing core/lures.py
or core/videos.py:   python3 web/tools/export_lure_data.py
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core import lures, videos  # noqa: E402

profiles = {}
for k, p in lures.LURE_PROFILES.items():
    q = dict(p)
    lo, hi = p["depth_range_ft"]
    q["depth_range_ft"] = [lo, hi]
    q["depth_range_str"] = [str(lo), str(hi)]  # Python prints 12 vs 2.0 differently - keep its exact text
    profiles[k] = q
data = {
    "BASE_STAIN_OPTIONS": lures.BASE_STAIN_OPTIONS, "DEFAULT_BASE_STAIN": lures.DEFAULT_BASE_STAIN,
    "WATER_CLARITY_OPTIONS": lures.WATER_CLARITY_OPTIONS, "STRUCTURE_TYPES": lures.STRUCTURE_TYPES,
    "FORAGE_OPTIONS": lures.FORAGE_OPTIONS, "DEFAULT_FORAGE": lures.DEFAULT_FORAGE,
    "FORAGE_NOTES": lures.FORAGE_NOTES, "FORAGE_LURE_BOOST": lures.FORAGE_LURE_BOOST,
    "LURE_PROFILES": profiles, "CATEGORY_KEYWORD_RULES": lures._CATEGORY_KEYWORD_RULES,
    "VIDEO_LIBRARY": videos.VIDEO_LIBRARY, "VIDEO_KEYWORD_MAP": videos._KEYWORD_MAP,
}
out = ROOT / "web" / "src" / "lib" / "data" / "lures.data.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, ensure_ascii=False, indent=0))
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(profiles)} lure profiles, {len(videos.VIDEO_LIBRARY)} video entries)")
