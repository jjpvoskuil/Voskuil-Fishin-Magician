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
from core.historic_bathymetry import historic_point_count
from core.cover import get_cover_at, cover_cell_count
from core.fish_attractors import fish_attractor_count

st.set_page_config(page_title="Lake Map - Nolin Lake", page_icon="🗺️", layout="wide")
st.title("🗺️ Nolin Lake Map")
st.caption(
    "Zoom and pan the map, then click **anywhere on the lake** to get a location-specific "
    "recommendation for the day/time you pick below."
)
n_points = survey_point_count()
n_files = survey_file_count()
n_historic = historic_point_count()
n_cover = cover_cell_count()
n_attractors = fish_attractor_count()

sources = []
if n_points:
    sources.append(
        f"**{n_points:,} of your own recorded depth readings** (from {n_files} Quickdraw "
        f"export{'s' if n_files != 1 else ''})"
    )
if n_historic:
    sources.append(
        f"**{n_historic:,} points read from pre-dam USGS historical topo maps** "
        f"(1953-54 sheets, against the 515' post-dam shoreline)"
    )

st.info(
    f"There's no free bathymetric survey for Nolin Lake, and two attempts at modeling smooth "
    f"depth contours from public data didn't hold up well enough to trust - so this map doesn't "
    f"draw depth contour lines right now. What it does show is real: the **bottom cover layer** "
    f"({n_cover:,} cells) classifies what each part of the lake bottom looked like on the 1953-54 "
    f"pre-dam USGS topo sheets - wooded (likely standing timber) vs. cleared (likely open bottom) "
    f"vs. the original stream channel - clipped to the real digitized shoreline. Also shown: "
    f"**{n_attractors:,} real fish attractors** (brush piles, Christmas trees, pallet stacks, and "
    f"more) GPS-placed by Kentucky Fish & Wildlife - the most authoritative point data on this map. "
    + (f"Also blended in: {' and '.join(sources)}. " if sources else "")
    + "A 'Modeled depth' estimate still appears below when you click a point, but treat it as a "
    "rough guess, not a chart - always confirm with your own electronics on the water.",
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
    cover_hit = get_cover_at(click["lat"], click["lon"])

    col_depth, col_cover = st.columns(2)
    with col_depth:
        if depth is None:
            st.caption("Modeled depth: no data at this point")
        else:
            st.metric("Modeled depth (rough guess)", f"{depth} ft")
    with col_cover:
        if cover_hit is None:
            st.caption("Bottom cover: no pre-dam data at this point")
        else:
            cover_label = {
                "wooded": "Wooded (likely timber)",
                "cleared": "Cleared (likely open)",
                "water": "Old stream channel",
            }.get(cover_hit["dominant_class"], cover_hit["dominant_class"].title())
            st.metric("Bottom cover (pre-dam)", cover_label)

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
