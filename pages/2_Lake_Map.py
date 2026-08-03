import streamlit as st
from datetime import date, timedelta

from core.appstate import get_weather_bundle, get_calibrated_weights, get_spots
from core.scoring import score_day
from core.lures import recommend, WATER_CLARITY_OPTIONS
from core.spots import build_map_figure

st.set_page_config(page_title="Lake Map - Nolin Lake", page_icon="🗺️", layout="wide")
st.title("🗺️ Nolin Lake Spot Map")
st.caption(
    "Click a marker to get a location-specific lure/color/technique recommendation "
    "for the day and time you pick below. Locations are planning approximations - "
    "verify with your own GPS/chartplotter on the water."
)

spot_data = get_spots()
spots = spot_data["spots"]

if "selected_spot_id" not in st.session_state:
    st.session_state.selected_spot_id = spots[0]["id"]

col_map, col_detail = st.columns([3, 2])

with col_map:
    fig = build_map_figure(spots, selected_id=st.session_state.selected_spot_id)
    event = st.plotly_chart(fig, width='stretch', on_select="rerun", key="lake_map")
    if event and event.get("selection", {}).get("points"):
        idx = event["selection"]["points"][0].get("point_index")
        if idx is not None:
            st.session_state.selected_spot_id = spots[idx]["id"]

    legend = ", ".join(sorted({s["structure_type"] for s in spots}))
    st.caption(f"Structure types shown: {legend}")

spot = next(s for s in spots if s["id"] == st.session_state.selected_spot_id)

with col_detail:
    st.subheader(spot["name"])
    st.write(f"**Structure type:** {spot['structure_type']}")
    st.write(f"**Typical depth:** {spot['depth_range_ft'][0]}-{spot['depth_range_ft'][1]} ft")
    st.caption(f"Source: {spot['source']}")
    st.write(spot["notes"])

    picked_date = st.selectbox("Date", [date.today() + timedelta(days=i) for i in range(7)],
                                format_func=lambda d: d.strftime("%A, %B %d"))
    clarity = st.selectbox("Water clarity", WATER_CLARITY_OPTIONS, index=1)

    weights, n_trips = get_calibrated_weights()
    bundle = get_weather_bundle(7)
    try:
        day = score_day(bundle, picked_date, weights=weights)
        segment_name = st.selectbox("Time of day", [s.name for s in day.segments])
        seg = next(s for s in day.segments if s.name == segment_name)

        st.metric(f"{segment_name} activity score", f"{seg.score}/10")
        rec = recommend(day.season, day.water_temp_f, segment_name, day.pressure_trend_24h,
                         spot["structure_type"], clarity)

        st.markdown(f"**Lures:** {', '.join(rec.primary_lures)}")
        st.markdown(f"**Colors:** {', '.join(rec.colors)}")
        st.markdown(f"**Technique:** {rec.technique}")
        st.markdown(f"**Retrieve:** {rec.retrieve}")
        st.markdown(f"**Target depth:** {rec.target_depth}")
        if rec.rationale:
            st.caption(" · ".join(rec.rationale))
    except ValueError as e:
        st.error(str(e))
