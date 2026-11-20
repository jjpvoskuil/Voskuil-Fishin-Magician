"""Army Corps dam-site temp/DO profiles → web/src/lib/data/corps_profiles.json (public USACE data, for the
"Oxygen & catch" report). Input = the Corps workbook John gets from the Louisville District Water Quality Team
(Nolin_Temp_DO_Data.xlsx, sheet "Regular Chem Data"). Keeps station NRR20001 (dam) from FROM_YEAR on.
    python3 web/tools/corps_profiles.py Nolin_Temp_DO_Data.xlsx [FROM_YEAR=2026]
New profiles after that arrive by themselves (fm_water_quality.profile, logged twice a day by deercast-data)."""
import json, sys
from pathlib import Path
import pandas as pd
src, y0 = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2026
d = pd.read_excel(src, "Regular Chem Data", dtype=str)
d = d[(d.Location == "NRR20001") & d.Parameter.isin(["Oxygen, Dissolved", "Temperature, Water"])]
for c in ("Year", "Month", "Day"): d[c] = d[c].astype(int)
d = d[d.Year >= y0]
d["v"] = pd.to_numeric(d.Value, errors="coerce"); d["z"] = pd.to_numeric(d.Depth_ft, errors="coerce")
d["date"] = d.apply(lambda r: f"{r.Year:04d}-{r.Month:02d}-{r.Day:02d}", axis=1)
out = []
for day, g in d.dropna(subset=["v", "z"]).groupby("date"):
    w = g.pivot_table(index="z", columns="Parameter", values="v", aggfunc="mean").sort_index()
    rows = [{"depth_ft": float(z), "temp_f": None if pd.isna(r.get("Temperature, Water")) else round(r["Temperature, Water"] * 9 / 5 + 32, 1),
             "do_mg_l": round(float(r["Oxygen, Dissolved"]), 2)} for z, r in w.iterrows() if not pd.isna(r.get("Oxygen, Dissolved"))]
    if len(rows) >= 3: out.append({"date": day, "rows": rows})
p = Path(__file__).resolve().parents[1] / "src/lib/data/corps_profiles.json"
p.write_text(json.dumps({"source": "USACE Louisville District, Nolin River Lake dam site NRR20001 (Nolin_Temp_DO_Data.xlsx)", "profiles": out}, separators=(",", ":")))
print(p, len(out), "profiles", out[0]["date"] if out else "", "→", out[-1]["date"] if out else "")
