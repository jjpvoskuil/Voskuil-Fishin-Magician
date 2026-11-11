"""Parity fixtures for web/src/lib/reports.js from core/reports.py (synthetic trips only).
Run: TZ=UTC python3 web/tools/make_report_fixtures.py   (sorts forced to kind="stable", as in make_stringer_fixtures.py)"""
import gzip, json, random, sys
from datetime import date, datetime, timedelta
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

from core import reports as R  # noqa: E402
from core.weather import WeatherBundle  # noqa: E402

rng = random.Random(92)
C = rng.choice
def rows(n, start, days):
    out = []
    for i in range(n):
        d = (start + timedelta(days=rng.randrange(days))).isoformat() if rng.random() > 0.03 else C(["", "2026-13-01", None])
        h0 = rng.randrange(5, 19); m0 = rng.randrange(60); dur = C([0.02, 0.5, 1.25, 2.0, 3.7, 7.0])
        t1 = datetime(2026, 1, 1, h0, m0) + timedelta(hours=dur)
        cond = {"angler": C(["John", "Matthew", "Alex", " ", None]), "water_temp_f": C([None, round(rng.uniform(44, 84), 1), "61.5", "x"]),
                "pressure_trend_24h": C([None, round(rng.uniform(-5, 5), 2)]), "stain_color": C(["green", "brown", " ", None]),
                "secchi_ft": C([None, round(rng.uniform(1, 9), 1)]), "lure_category": C(["chatterbait", "drop_shot", "suspending_jerkbait", None, "made_up"]),
                "wind_band": C(["Glassy", "Light Ripple", "Moderate Chop", None, "Odd"]), "wind_direction": C(["N", "SW", None]),
                "light_condition": C(["Clear / Sunny", "Overcast", "Partly Cloudy", None]), "precipitation": C(["None", "Light rain", None]),
                "fish_activity": C(["Active", None]), "forage_activity": C(["Some", None]),
                "lure_start_time": f"{h0:02d}:{m0:02d}:00", "lure_end_time": C([t1.strftime("%H:%M:%S"), None, "bad"])}
        if rng.random() < 0.05: cond["times_estimated"] = True
        if rng.random() < 0.8:
            cond["fish"] = [C([{"species": C(["Largemouth", "Spotted", "Crappie", "", None]), "count": C([None, 1, 1, 2, "3", "x", 2.7]),
                                "weight_lb": C([None, round(rng.uniform(0.4, 6), 2), 2.5]), "length_in": C([None, 15.5])}, "bad"]) for _ in range(rng.randrange(0, 4))]
        out.append({"trip_id": f"t{i}", "trip_date": d, "spot_name": C(["Dam Point", "Wax Bridge", "Bacon Creek", ""]),
                    "structure_type": C(["Main-lake point", "Flat", ""]), "water_clarity": C(["Clear", "Green stained", ""]),
                    "lure_used": C(["Z-Man ChatterBait", "Roboworm", ""]), "color_used": C(["Green pumpkin", ""]), "technique_used": C(["Slow roll", ""]),
                    "segment": C(["Dawn", "Morning", "Midday", "Dusk", "", "Weird"]), "fish_caught": C(["0", "2", "2.0", "", "x"]),
                    "biggest_fish_lb": C(["", "2.5", None, "x"]), "conditions_json": json.dumps(cond)})
    return out

def enc(v):
    if isinstance(v, float) and v != v: return None
    if isinstance(v, (date, datetime)): return v.isoformat()
    if hasattr(v, "item"): return v.item()
    return v

trips = rows(300, date(2026, 3, 1), 240)
t_df, f_df = R.build_reports_dataframe(trips)
cases = []
for fname, fcol in R.FACTOR_OPTIONS.items():
    for mname, mkey in R.METRIC_OPTIONS.items():
        for _ in range(2):
            opts = {}
            if rng.random() < 0.5 or fcol in R.DATE_FACTOR_COLUMNS:
                s = date(2026, 3, 1) + timedelta(days=rng.randrange(150)); opts["from"] = s.isoformat(); opts["to"] = (s + timedelta(days=rng.randrange(10, 80))).isoformat()
            if rng.random() < 0.3: opts["anglers"] = rng.sample(["John", "Matthew", "Alex", "Unspecified"], 2)
            if rng.random() < 0.3: opts["segments"] = rng.sample(["Dawn", "Morning", "Midday", "Dusk"], 2)
            if rng.random() < 0.4: opts["species"] = C(["Largemouth", "All species", "Spotted"])
            if rng.random() < 0.5: opts["tempWidth"] = C([1.0, 2.5, 5.0]); opts["secchiWidth"] = C([0.25, 1.0])
            df = R.compute_report(t_df, f_df, fcol, mkey, species=opts.get("species"),
                                  date_start=date.fromisoformat(opts["from"]) if "from" in opts else None,
                                  date_end=date.fromisoformat(opts["to"]) if "to" in opts else None,
                                  anglers=opts.get("anglers"), segments=opts.get("segments"),
                                  water_temp_bucket_width_f=opts.get("tempWidth"), secchi_bucket_width_ft=opts.get("secchiWidth"))
            out = [{"key": enc(r[fcol]), "value": enc(r["value"]), "n": enc(r["n"])} for _, r in df.iterrows()]
            cases.append({"factor": fcol, "metric": mkey, "opts": opts, "out": out})

# pressure bundle: hourly 2026-05-01 .. 05-08
t0 = datetime(2026, 5, 1)
hours = [t0 + timedelta(hours=h) for h in range(24 * 8)]
bundle = {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours], "surface_pressure": [1013 + 6 * __import__("math").sin(i / 17) for i in range(len(hours))]}
wb = WeatherBundle(hourly=bundle, daily={})
preds = []
for d in ["2026-04-20", "2026-05-01", "2026-05-02", "2026-05-05", "2026-05-08", "2026-05-12", "2026-07-04", "2026-10-31"]:
    for m in ["fish_per_hour", "total_fish", "biggest_fish"]:
        dd = date.fromisoformat(d)
        pm = R.predict_by_moon_illumination(t_df, f_df, dd, metric_key=m)
        pp = R.predict_by_pressure_trend(t_df, f_df, dd, wb, metric_key=m)
        preds.append({"date": d, "metric": m, "moon": {k: enc(v) for k, v in pm.items()}, "pressure": {k: enc(v) for k, v in pp.items()}})
fx = {"rows": trips, "cases": cases, "bundle": bundle, "preds": preds, "species": R.species_options(f_df),
      "moon_bins": [[p, R._moon_illumination_bin(p)] for p in [0, 9.99, 10, 55.5, 99.9, 100, 104]],
      "labels": [[v, w, R._water_temp_bucket_label(v, w), R._secchi_bucket_label(v, w)] for v, w in [(54.3, 2.0), (54.3, 2.5), (3.3, 0.25), (61, 5.0), (0.2, 0.5)]]}
out = ROOT / "web" / "src" / "lib" / "fixtures" / "reports.fixtures.json.gz"
out.write_bytes(gzip.compress(json.dumps(fx, separators=(",", ":"), ensure_ascii=False).encode(), mtime=0))
print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(cases)} report cases, {len(preds)} predictions)")
