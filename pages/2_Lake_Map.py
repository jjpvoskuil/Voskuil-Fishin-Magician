import streamlit as st
from datetime import date, timedelta
from streamlit_folium import st_folium

from core.appstate import get_weather_bundle, get_calibrated_weights, get_spots
from core.scoring import score_day, effective_season_and_temp
from core.lures import recommend, STRUCTURE_TYPES
from core.ui import render_lure_recommendation, render_lake_setup_sidebar
from core.lake_map import build_folium_map
from core.bathymetry import get_depth_at_ft, infer_structure_type, lake_center
from core.survey_points import survey_point_count, survey_file_count

st.set_page_config(page_title="Lake Map - Nolin Lake", page_icon="🗺️", layout="wide")
st.title("🗺️ Nolin Lake Contour Map")
st.caption(
    "Zoom and pan the map, then click **anywhere on the lake** to get a location-specific "
    "recommendation for the day/time you pick below."
)
n_points = survey_point_count()
n_files = survey_file_count()
if n_points:
    st.info(
        f"Depth contours blend **{n_points:,} of your own recorded depth readings** "
        f"(from {n_files} Quickdraw export{'s' if n_files != 1 else ''}) with a **modeled "
        f"approximation** everywhere else (river-channel + Gaussian cross-section) - there's "
        f"no free bathymetric survey for Nolin Lake. Real readings take over near where you've "
        f"actually recorded them and fade back to the model beyond that. Always confirm with "
        f"your own electronics on the water.",
        icon="🧭",
    )
else:
    st.info(
        "Depth contours are a **modeled approximation** (river-channel + Gaussian cross-section), "
        "not a survey - there's no free bathymetric dataset for Nolin Lake. It's anchored to a few "
        "verified points (USACE gauge, KY State Parks coordinate, Census-geocoded Dog Creek/Wax "
        "access points). Drop your own Garmin Quickdraw exports into data/quickdraw/ to start "
        "replacing this with real recorded depths. Always confirm with your own electronics "
        "on the water.",
        icon="🧭",
    )

lake_setup = render_lake_setup_sidebar(include_structure=False)

spot_data = get_spots()
spots = spot_data["spots"]

if "clicked_latlon" not in st.session_state:
    center_lat, center_lon = lake_center()
    st.session_state.clicked_latlon = {"lat": center_lat, "lon": center_lon}

col_map, col_detail = st.columns([3, 2])

with col_map:
    jump_to = st.selectbox(
        "Jump to a named spot (optional)", ["(none - click the map instead)"] + [s["name"] for s in spots]
    )
    if jump_to != "(none - click the map instead)":
        s = next(s for s in spots if s["name"] == jump_to)
        st.session_state.clicked_latlon = {"lat": s["lat"], "lon": s["lon"]}

    fmap = build_folium_map(spots, clicked=st.session_state.clicked_latlon)
    map_state = st_folium(
        fmap, height=560, use_container_width=True, key="lake_map",
        returned_objects=["last_clicked", "last_object_clicked"],
    )

    new_click = map_state.get("last_object_clicked") or map_state.get("last_clicked")
    if new_click and "lat" in new_click and "lng" in new_click:
        candidate = {"lat": new_click["lat"], "lon": new_click["lng"]}
        if candidate != st.session_state.clicked_latlon:
            st.session_state.clicked_latlon = candidate
            st.rerun()

with col_detail:
    click = st.session_state.clicked_latlon
    st.subheader("Selected location")
    st.write(f"**Coordinates:** {click['lat']:.5f}, {click['lon']:.5f}")

    depth = get_depth_at_ft(click["lat"], click["lon"])
    inferred_structure = infer_structure_type(click["lat"], click["lon"])

    if depth is None:
        st.warning("This point is outside the modeled lake area (likely shoreline/land or an "
                    "un-modeled upper arm) - pick a point within the blue contour lines, or a "
                    "named spot, for a depth-based recommendation.")
    else:
        st.metric("Modeled depth", f"{depth} ft")

    structure_type = st.selectbox(
        "Structure type (auto-suggested, override if you know better)",
        STRUCTURE_TYPES,
        index=STRUCTURE_TYPES.index(inferred_structure) if inferred_structure in STRUCTURE_TYPES else 0,
    )
    clarity = lake_setup.water_clarity

    picked_date = st.selectbox(
        "Date", [date.today() + timedelta(days=i) for i in range(7)],
        format_func=lambda d: d.strftime("%A, %B %d"),
    )

    weights, n_trips = get_calibrated_weights()
    bundle = get_weather_bundle(7)
    try:
        day = score_day(bundle, picked_date, weights=weights)
        eff_season, eff_water_temp = effective_season_and_temp(day, lake_setup.water_temp_override_f)
        segment_name = st.selectbox("Time of day", [s.name for s in day.segments])
        seg = next(s for s in day.segments if s.name == segment_name)

        st.caption(f"Water temp (Lake Setup Options): {eff_water_temp}°F  |  "
                   f"Thermocline (Lake Setup Options): {lake_setup.thermocline_ft:.0f} ft"
                   + (f" - shifts pattern to {eff_season.replace('_', ' ').title()} "
                      f"(weather-only estimate: {day.season.replace('_', ' ').title()})" if eff_season != day.season else ""))
        st.metric(f"{segment_name} activity score", f"{seg.score}/10")
        rec = recommend(eff_season, eff_water_temp, segment_name, day.pressure_trend_24h,
                         structure_type, clarity, fish_depth_ft=lake_setup.fish_depth_ft,
                         forage=lake_setup.forage, thermocline_ft=lake_setup.thermocline_ft)

        render_lure_recommendation(rec)
    except ValueError as e:
        st.error(str(e))
