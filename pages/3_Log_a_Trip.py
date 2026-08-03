import streamlit as st
from datetime import date, timedelta

from core.appstate import get_weather_bundle, get_calibrated_weights, get_spots, github_token, repo_slug
from core.scoring import score_day
from core.lures import WATER_CLARITY_OPTIONS, STRUCTURE_TYPES
from core.storage import TripEntry, append_trip, commit_and_push

st.set_page_config(page_title="Log a Trip - Nolin Lake", page_icon="📝", layout="centered")
st.title("📝 Log a Trip")
st.caption(
    "Log what actually happened out on the water. Logged trips are used by the Trip History "
    "page to calibrate the forecast model over time - the more you log, the smarter it gets."
)

spot_data = get_spots()
spots = spot_data["spots"]
weights, _ = get_calibrated_weights()
bundle = get_weather_bundle(7)

with st.form("log_trip_form"):
    trip_date = st.date_input("Trip date", value=date.today(),
                               min_value=date.today() - timedelta(days=6),
                               max_value=date.today() + timedelta(days=6))
    segment = st.selectbox("Time of day fished", ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"])
    spot_choice = st.selectbox("Spot fished", spots, format_func=lambda s: s["name"])
    structure_type = st.selectbox("Structure type", STRUCTURE_TYPES,
                                   index=STRUCTURE_TYPES.index(spot_choice["structure_type"]))
    water_clarity = st.selectbox("Water clarity that day", WATER_CLARITY_OPTIONS, index=WATER_CLARITY_OPTIONS.index("Brown stained"))

    c1, c2 = st.columns(2)
    lure_used = c1.text_input("Lure used", placeholder="e.g. Chartreuse/white spinnerbait")
    color_used = c2.text_input("Color used", placeholder="e.g. Chartreuse/white")
    technique_used = st.text_input("Technique/presentation", placeholder="e.g. Slow-rolled along a windblown point")

    c3, c4 = st.columns(2)
    fish_caught = c3.number_input("Bass caught", min_value=0, step=1, value=0)
    biggest_fish_lb = c4.number_input("Biggest fish (lb)", min_value=0.0, step=0.1, value=0.0)

    notes = st.text_area("Notes", placeholder="Anything else worth remembering about this trip")

    submitted = st.form_submit_button("Log trip", width='stretch')

if submitted:
    try:
        day = score_day(bundle, trip_date, weights=weights)
        seg = next(s for s in day.segments if s.name == segment)
        conditions = {
            "pressure_trend_24h": day.pressure_trend_24h,
            "moon_near_new_full": day.moon.is_new_or_full_window,
            "moon_phase": day.moon.name,
            "avg_cloud_pct": day.weather_summary["avg_cloud_pct"],
            "avg_wind_mph": day.weather_summary["avg_wind_mph"],
        }
        predicted_score = seg.score
    except ValueError:
        conditions = {}
        predicted_score = 0.0
        st.warning("Couldn't fetch conditions for that date (outside the current forecast window) - "
                   "logging without a conditions snapshot.")

    entry = TripEntry(
        trip_date=trip_date.isoformat(),
        segment=segment,
        spot_id=spot_choice["id"],
        spot_name=spot_choice["name"],
        structure_type=structure_type,
        water_clarity=water_clarity,
        lure_used=lure_used,
        color_used=color_used,
        technique_used=technique_used,
        fish_caught=int(fish_caught),
        biggest_fish_lb=float(biggest_fish_lb) if biggest_fish_lb else None,
        predicted_score=predicted_score,
        conditions=conditions,
        notes=notes,
    )
    append_trip(entry)
    get_calibrated_weights.clear()

    token = github_token()
    if token:
        ok, msg = commit_and_push(token, repo_slug(), f"Log trip {entry.trip_id} ({entry.trip_date})")
        (st.success if ok else st.warning)(msg)
    else:
        st.success("Trip logged locally.")
        st.info("No GITHUB_TOKEN configured in Streamlit secrets, so this entry wasn't pushed to GitHub "
                "and won't survive an app restart. See README for how to add it.")
