import streamlit as st
import json
import pandas as pd

from core.storage import read_all_trips
from core.calibration import calibration_summary, MIN_SAMPLES_PER_SIDE

st.set_page_config(page_title="Trip History - Nolin Lake", page_icon="📊", layout="wide")
st.title("📊 Trip History & Model Calibration")

rows = read_all_trips()

if not rows:
    st.info("No trips logged yet. Head to **Log a Trip** after your next outing on Nolin Lake.")
else:
    df = pd.DataFrame(rows)
    display_cols = ["trip_date", "segment", "spot_name", "structure_type", "water_clarity",
                     "lure_used", "color_used", "technique_used", "fish_caught",
                     "biggest_fish_lb", "predicted_score", "notes"]
    st.dataframe(df[display_cols].sort_values("trip_date", ascending=False), width='stretch', hide_index=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Trips logged", len(df))
    total_caught = pd.to_numeric(df["fish_caught"], errors="coerce").fillna(0).sum()
    c2.metric("Total bass caught", int(total_caught))
    success_rate = (pd.to_numeric(df["fish_caught"], errors="coerce").fillna(0) > 0).mean() * 100
    c3.metric("Trips with a catch", f"{success_rate:.0f}%")

    st.divider()
    st.subheader("Model calibration status")
    summary = calibration_summary(rows)
    st.caption(
        f"Each factor needs at least {MIN_SAMPLES_PER_SIDE} logged trips where it was present AND "
        f"{MIN_SAMPLES_PER_SIDE} where it wasn't, before your own results start nudging that factor's weight."
    )
    for factor, counts in summary["detail"].items():
        calibrated = factor in summary["factors_calibrated"]
        label = factor.replace("_", " ").title()
        status = "✅ calibrating from your data" if calibrated else "⏳ needs more trips"
        st.write(f"**{label}** - {status}  \n"
                 f"_{counts['on_total']} trips with factor present, {counts['off_total']} without_")

    st.divider()
    with st.expander("Raw conditions snapshots (debug)"):
        for _, row in df.iterrows():
            try:
                cond = json.loads(row["conditions_json"]) if row["conditions_json"] else {}
            except json.JSONDecodeError:
                cond = {}
            st.write(f"**{row['trip_date']} - {row['spot_name']}**: {cond}")
