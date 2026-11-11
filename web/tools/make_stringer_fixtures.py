"""Parity fixtures for web/src/lib/stringer.js from core/stringer.py (synthetic trips only).
Run: TZ=UTC python3 web/tools/make_stringer_fixtures.py
pandas' default sort (quicksort) doesn't keep ties in a fixed order on bigger frames, so the sorts are forced to
"stable" here — the same tie order the JS uses (and what pandas gives anyway on small groups)."""
import gzip, json, random, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402

for cls in (pd.Series, pd.DataFrame):
    orig = cls.sort_values
    def stable(self, *a, _orig=orig, **k):
        k.setdefault("kind", "stable")
        return _orig(self, *a, **k)
    cls.sort_values = stable

from core import stringer as S  # noqa: E402

rng = random.Random(97)
spots = {"s1": "Dam Point", "s2": "Moutardier Cove", "s3": "Wax Bridge", "s4": "Bacon Creek"}
lures = ["Z-Man ChatterBait", "Roboworm FAT Straight", "Strike King 1.5", "Rapala Shadow Rap", ""]
cats = ["chatterbait", "drop_shot", "squarebill_crankbait", None, "made_up_cat"]
colors = ["Green pumpkin", "Morning dawn", " ", ""]
species = ["Largemouth Bass", "Spotted Bass", "White Bass", "Crappie", "", None, " Catfish "]


def make_rows(n, start, days):
    rows = []
    sessions = [f"sess{i}" for i in range(n // 4)]
    for i in range(n):
        d = (start + timedelta(days=rng.randrange(days))).isoformat()
        li = rng.randrange(len(lures))
        cond = {"angler": rng.choice(["John", "Matthew", "Alex", " ", None]), "lure_category": rng.choice(cats)}
        r = rng.random()
        if r < 0.75:
            fl = []
            for _ in range(rng.randrange(0, 4)):
                if rng.random() < 0.08:
                    fl.append("bad")
                    continue
                fl.append({"species": rng.choice(species), "count": rng.choice([None, 1, 1, 1, 2, "3", "x", 0, -1, 2.7]),
                           "weight_lb": rng.choice([None, round(rng.uniform(0.3, 6.5), 2), round(rng.uniform(0.3, 6.5), 2), 2.5]),
                           "length_in": rng.choice([None, round(rng.uniform(8, 22), 2), 15.25, 14.75])})
            cond["fish"] = fl
        elif r < 0.85:
            cond["fish"] = "not a list"
        sid = rng.choice(sessions + ["", "", " "])
        sp = rng.choice(list(spots) + ["gone", None])
        rows.append({"trip_id": f"t{i}", "trip_date": d, "session_id": sid, "lure_used": lures[li],
                     "color_used": rng.choice(colors), "spot_id": sp, "spot_name": rng.choice(["Old name", ""]),
                     "fish_caught": rng.choice(["0", "1", "2.0", "", "x", 3]),
                     "conditions_json": json.dumps(cond)})
    return rows


def run(rows):
    f, t = S.build_frames(rows, spots)
    dates = t["date"].dropna() if not t.empty else []
    lo, hi = (dates.min(), dates.max()) if len(dates) else (None, None)
    iso = lambda x: x.isoformat() if x else None
    return {
        "season": S.season_label(t),
        "hero": [h.__dict__ for h in S.hero_states(f, t)],
        "cats": {k: b(f, t) for k, _, _, b in S.CATEGORIES},
        "daily": [[iso(d), c] for d, c in S.daily_activity_series(f, lo, hi)],
        "mix": S.species_mix(f),
    }


cases = []
for n, start, days in [(320, date(2026, 3, 1), 250), (40, date(2026, 8, 1), 20), (6, date(2026, 11, 2), 1), (0, date(2026, 1, 1), 1)]:
    rows = make_rows(n, start, days)
    cases.append({"rows": rows, "out": run(rows)})
fx = {"spots": spots, "cases": cases}


def clean(o):
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, "item"):
        return o.item()
    return o


out = ROOT / "web" / "src" / "lib" / "fixtures" / "stringer.fixtures.json.gz"
out.write_bytes(gzip.compress(json.dumps(clean(fx), separators=(",", ":"), ensure_ascii=False).encode(), mtime=0))
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(cases)} cases)")
