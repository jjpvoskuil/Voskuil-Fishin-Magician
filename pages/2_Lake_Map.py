import streamlit as st
from streamlit_folium import st_folium

from core.appstate import get_lake_spots, github_token, repo_slug
from core.lake_map import build_folium_map
from core.lake_spots import (
    LakeSpot, LOCATION_TYPES, BOTTOM_STRUCTURE_OPTIONS, TRANSITION_GRADE_OPTIONS, SPOTS_PATH,
    append_spot, update_spot, delete_spot, nearest_spot_within, split_bottom_structure,
)
from core.fish_attractors import fish_attractor_count
from core.storage import commit_and_push
from core.ui import inject_mobile_css

st.set_page_config(page_title="Lake Map - Nolin Lake", page_icon="🗺️", layout="wide")
inject_mobile_css()
st.title("🗺️ Nolin Lake Map")
st.caption(
    f"Real, GPS-placed fish attractors from Kentucky Fish & Wildlife ({fish_attractor_count():,} shown) "
    "plus your own saved spots - use the layer selector in the map's top-right corner to toggle either "
    "on or off. Click anywhere on the map to drop a pin and record what you know about "
    "it, or click an existing pin (or jump to it below) to view or edit it."
)

if "clicked_latlon" not in st.session_state:
    st.session_state.clicked_latlon = None

spots = get_lake_spots()

col_map, col_detail = st.columns([3, 2])

with col_map:
    if spots:
        jump_to = st.selectbox(
            "Jump to a saved spot (optional)", ["(none - click the map instead)"] + [s["name"] for s in spots]
        )
        if jump_to != "(none - click the map instead)":
            s = next(s for s in spots if s["name"] == jump_to)
            st.session_state.clicked_latlon = {"lat": float(s["lat"]), "lon": float(s["lon"])}

    click = st.session_state.clicked_latlon
    selected_existing = nearest_spot_within(click["lat"], click["lon"], spots) if click else None

    fmap = build_folium_map(
        spots, clicked=click, selected_spot_id=selected_existing["spot_id"] if selected_existing else None,
    )
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

    if click is None:
        st.info("Click anywhere on the map, or jump to a saved spot above, to see or add details.")
    else:
        existing = nearest_spot_within(click["lat"], click["lon"], spots)

        if existing:
            st.subheader(f"📍 {existing['name']}")
            st.caption(f"{float(existing['lat']):.5f}, {float(existing['lon']):.5f}")

            bottom = split_bottom_structure(existing.get("bottom_structure", ""))
            st.write(f"**Type of location:** {existing.get('location_type') or '—'}")
            st.write(f"**Bottom structure:** {', '.join(bottom) if bottom else '—'}")

            c1, c2 = st.columns(2)
            c1.metric("Main area depth", f"{existing['main_depth_ft']} ft" if existing.get("main_depth_ft") else "—")
            c2.metric("Transition depth", f"{existing['transition_depth_ft']} ft" if existing.get("transition_depth_ft") else "—")
            st.write(f"**Transition steepness:** {existing.get('transition_grade') or '—'}")
            if existing.get("notes"):
                st.write(f"**Notes:** {existing['notes']}")

            if st.button(
                "🎯 Fish this spot now - conditions & lure suggestions", key=f"session_btn_{existing['spot_id']}",
                width='stretch',
            ):
                # st.session_state is the reliable channel for handing data to the
                # next page - st.switch_page doesn't consistently carry query params
                # set in this same run over to the new page's initial load.
                st.session_state["spot_session_target_id"] = existing["spot_id"]
                st.query_params["spot_id"] = existing["spot_id"]
                st.switch_page("pages/6_Spot_Session.py")

            with st.expander("Edit this spot"):
                with st.form(f"edit_spot_{existing['spot_id']}"):
                    e_name = st.text_input("Name", value=existing["name"])
                    e_type = st.selectbox(
                        "Type of location", LOCATION_TYPES,
                        index=LOCATION_TYPES.index(existing["location_type"]) if existing.get("location_type") in LOCATION_TYPES else 0,
                    )
                    e_bottom = st.multiselect(
                        "Bottom structure", BOTTOM_STRUCTURE_OPTIONS,
                        default=[b for b in bottom if b in BOTTOM_STRUCTURE_OPTIONS],
                    )
                    ec1, ec2 = st.columns(2)
                    e_main_depth = ec1.number_input(
                        "Depth of main area (ft)", min_value=0.0, step=0.5,
                        value=float(existing.get("main_depth_ft") or 0.0),
                    )
                    e_trans_depth = ec2.number_input(
                        "Transition / drop-off depth (ft)", min_value=0.0, step=0.5,
                        value=float(existing.get("transition_depth_ft") or 0.0),
                    )
                    e_grade = st.selectbox(
                        "How fast the transition is", TRANSITION_GRADE_OPTIONS,
                        index=TRANSITION_GRADE_OPTIONS.index(existing["transition_grade"]) if existing.get("transition_grade") in TRANSITION_GRADE_OPTIONS else 1,
                    )
                    e_notes = st.text_area("Notes", value=existing.get("notes", ""))

                    ebtn1, ebtn2 = st.columns(2)
                    save_clicked = ebtn1.form_submit_button("Save changes", width='stretch')
                    delete_clicked = ebtn2.form_submit_button("Delete spot", width='stretch')

                if save_clicked:
                    if not e_name.strip():
                        st.warning("Name is required.")
                    else:
                        update_spot(
                            existing["spot_id"], name=e_name.strip(), location_type=e_type,
                            bottom_structure=e_bottom, main_depth_ft=e_main_depth or None,
                            transition_depth_ft=e_trans_depth or None, transition_grade=e_grade,
                            notes=e_notes.strip(),
                        )
                        get_lake_spots.clear()
                        token = github_token()
                        if token:
                            ok, msg = commit_and_push([SPOTS_PATH], token, repo_slug(), f"Update lake spot: {e_name.strip()}")
                            (st.success if ok else st.warning)(msg)
                        else:
                            st.success("Saved locally.")
                        st.rerun()

                if delete_clicked:
                    delete_spot(existing["spot_id"])
                    st.session_state.clicked_latlon = None
                    get_lake_spots.clear()
                    token = github_token()
                    if token:
                        commit_and_push([SPOTS_PATH], token, repo_slug(), f"Delete lake spot: {existing['name']}")
                    st.rerun()

        else:
            st.subheader("➕ Add a new spot here")
            st.caption(f"{click['lat']:.5f}, {click['lon']:.5f}")

            with st.form("add_spot_form", clear_on_submit=True):
                name = st.text_input("Name")
                location_type = st.selectbox("Type of location", LOCATION_TYPES)
                bottom_structure = st.multiselect("Bottom structure", BOTTOM_STRUCTURE_OPTIONS)
                c1, c2 = st.columns(2)
                main_depth = c1.number_input("Depth of main area (ft)", min_value=0.0, step=0.5, value=0.0)
                transition_depth = c2.number_input("Transition / drop-off depth (ft)", min_value=0.0, step=0.5, value=0.0)
                transition_grade = st.selectbox(
                    "How fast the transition is", TRANSITION_GRADE_OPTIONS, index=1,
                    help="High = steep break that concentrates fish along a short stretch. "
                         "Low = gradual taper that spreads them over a wider area.",
                )
                notes = st.text_area("Notes (optional)", placeholder="Anything else worth remembering about this spot")
                submitted = st.form_submit_button("Save spot", width='stretch')

            if submitted:
                if not name.strip():
                    st.warning("Name is required.")
                else:
                    spot = LakeSpot(
                        name=name.strip(), lat=click["lat"], lon=click["lon"],
                        location_type=location_type, bottom_structure=bottom_structure,
                        main_depth_ft=main_depth or None, transition_depth_ft=transition_depth or None,
                        transition_grade=transition_grade, notes=notes.strip(),
                    )
                    append_spot(spot)
                    get_lake_spots.clear()

                    token = github_token()
                    if token:
                        ok, msg = commit_and_push([SPOTS_PATH], token, repo_slug(), f"Add lake spot: {spot.name}")
                        (st.success if ok else st.warning)(msg)
                    else:
                        st.success("Saved locally.")
                        st.info(
                            "No GITHUB_TOKEN configured in Streamlit secrets, so this spot wasn't pushed "
                            "to GitHub and won't survive an app restart. See README for how to add it."
                        )
                    st.rerun()
