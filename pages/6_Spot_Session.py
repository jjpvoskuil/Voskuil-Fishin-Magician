import streamlit as st

from core.appstate import get_lake_spots, get_inventory, get_weather_bundle, github_token, repo_slug
from core.lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE, split_bottom_structure
from core.onwater import (
    LIGHT_CONDITIONS, LIGHT_CONDITION_INFO, cloud_proxy_for_light_condition,
    wind_band, visibility_band, resolve_water_clarity, STAIN_COLOR_OPTIONS,
    water_temp_band, PRECIPITATION_OPTIONS, precipitation_proxy,
)
from core.scoring import SEGMENTS, season_stage, manual_segment_score, realtime_context_from_bundle, lake_now_naive
from core.lures import recommend, FORAGE_OPTIONS, DEFAULT_FORAGE
from core.ui import render_lure_recommendation
from core.thermocline import default_thermocline_input_ft
from core.storage import TripEntry, TRIP_LOG_PATH, append_trip, commit_and_push
from core.weather import lake_today

st.set_page_config(page_title="Spot Session - Nolin Lake", page_icon="🎯", layout="wide")
st.title("🎯 Spot Session")

# session_state is the reliable channel from the "Fish this spot now" button on the
# Lake Map page (st.switch_page doesn't consistently carry query params set in that
# same run over to this page's initial load); query_params is kept as a fallback so a
# manual page refresh or a bookmarked/shared link with ?spot_id=... still works.
spot_id = st.session_state.get("spot_session_target_id") or st.query_params.get("spot_id")
spots = get_lake_spots()
spot = next((s for s in spots if s["spot_id"] == spot_id), None) if spot_id else None

if spot is not None:
    # Keep both channels in sync once resolved, so a refresh of this exact page
    # keeps working from the URL alone, and the URL is shareable/bookmarkable.
    st.session_state["spot_session_target_id"] = spot_id
    st.query_params["spot_id"] = spot_id

if spot is None:
    st.info(
        "No spot selected. Go to the Lake Map page, click (or jump to) a saved spot, and use "
        "\"🎯 Fish this spot now\" to get here with that spot's info pre-loaded."
    )
    if st.button("Go to Lake Map"):
        st.switch_page("pages/2_Lake_Map.py")
    st.stop()


def _guess_segment(hour: int) -> str:
    if hour < 7:
        return "Dawn"
    if hour < 11:
        return "Morning"
    if hour < 14:
        return "Midday"
    if hour < 18:
        return "Afternoon"
    if hour < 20:
        return "Dusk"
    return "Night"


st.subheader(f"📍 {spot['name']}")
bottom = split_bottom_structure(spot.get("bottom_structure", ""))
meta_bits = []
if spot.get("location_type"):
    meta_bits.append(spot["location_type"])
if bottom:
    meta_bits.append(", ".join(bottom))
if spot.get("main_depth_ft"):
    meta_bits.append(f"main area {spot['main_depth_ft']} ft")
if spot.get("transition_depth_ft"):
    meta_bits.append(f"transition {spot['transition_depth_ft']} ft ({spot.get('transition_grade', '')})")
st.caption(" · ".join(meta_bits) if meta_bits else "No saved details for this spot yet - add some from the Lake Map page.")

if st.button("← Back to Lake Map"):
    st.switch_page("pages/2_Lake_Map.py")

st.divider()
st.header("Conditions right now")
st.caption(
    "Enter what you're actually seeing at the water - unlike the 7-Day Forecast page (which relies on "
    "a weather API), everything here is your own on-the-spot reading, so it drives suggestions "
    "specific to this exact moment at this exact spot."
)

with st.form(f"conditions_form_{spot['spot_id']}"):
    c1, c2 = st.columns(2)
    water_temp_f = c1.number_input("Water temperature (°F)", min_value=32.0, max_value=100.0, value=75.0, step=0.5)
    secchi_ft = c2.number_input(
        "Water visibility / Secchi depth (ft)", min_value=0.0, max_value=20.0, value=3.0, step=0.5,
        help="How far down you can see a light-colored object/lure. Estimate visually if you don't carry a Secchi disk.",
    )
    temp_band = water_temp_band(water_temp_f)
    st.caption(f"Metabolic state: **{temp_band['label']}** - {temp_band['detail']}")
    vis_band = visibility_band(secchi_ft)
    st.caption(f"Visibility band: **{vis_band['label']}** ({vis_band['detail']})")

    stain_color = None
    if vis_band["label"] == "Stained":
        stain_color = st.selectbox(
            "Stain color (Nolin normally runs greenish-brown, leaning brown)", STAIN_COLOR_OPTIONS, index=1,
        )

    c3, c4 = st.columns(2)
    wind_mph = c3.number_input("Wind speed (mph)", min_value=0.0, max_value=60.0, value=6.0, step=1.0)
    w_band = wind_band(wind_mph)
    c3.caption(f"**{w_band['label']}** - {w_band['detail']}")
    light_condition = c4.selectbox(
        "Light conditions", LIGHT_CONDITIONS, index=2,
        help="\n".join(f"{k} ({v['range']}): {v['detail']}" for k, v in LIGHT_CONDITION_INFO.items()),
    )

    c5, c6 = st.columns(2)
    precipitation = c5.selectbox("Precipitation", PRECIPITATION_OPTIONS)
    start_time = c6.time_input("Session start time", value=lake_now_naive().time())

    segment_name = st.selectbox("Time window", SEGMENTS, index=SEGMENTS.index(_guess_segment(lake_now_naive().hour)))

    with st.expander("Additional details (optional) - sharpens the suggestions further"):
        forage_seen = st.multiselect("Forage seen", FORAGE_OPTIONS, default=DEFAULT_FORAGE)
        fc1, fc2 = st.columns(2)
        fish_depth_ft = fc1.number_input(
            "Depth fish are showing up on electronics (ft)", min_value=0.0, max_value=100.0, value=0.0, step=1.0,
        )
        thermocline_ft = fc2.number_input(
            "Thermocline depth (ft)", min_value=0.0, max_value=100.0,
            value=default_thermocline_input_ft(lake_today()), step=1.0,
        )

    submitted = st.form_submit_button("Get lure suggestions", width='stretch')

if submitted:
    st.session_state.setdefault("spot_session_conditions", {})[spot["spot_id"]] = {
        "water_temp_f": water_temp_f, "secchi_ft": secchi_ft, "stain_color": stain_color,
        "wind_mph": wind_mph, "light_condition": light_condition, "precipitation": precipitation,
        "start_time": start_time.isoformat(), "segment_name": segment_name,
        "forage_seen": forage_seen, "fish_depth_ft": fish_depth_ft or None,
        "thermocline_ft": thermocline_ft or None,
    }

cond = st.session_state.get("spot_session_conditions", {}).get(spot["spot_id"])

if not cond:
    st.info("Fill in the conditions above and click **Get lure suggestions** to continue.")
    st.stop()

water_clarity = resolve_water_clarity(cond["secchi_ft"], cond.get("stain_color"))
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")
today = lake_today()
season = season_stage(today.timetuple().tm_yday, cond["water_temp_f"])
avg_cloud_pct = cloud_proxy_for_light_condition(cond["light_condition"])
total_precip_in, max_precip_prob_pct = precipitation_proxy(cond["precipitation"])

try:
    bundle = get_weather_bundle(7)
except Exception:
    bundle = None
rt = realtime_context_from_bundle(bundle, cond["segment_name"], today)

score_result = manual_segment_score(
    cond["segment_name"], season, avg_cloud_pct, cond["wind_mph"], total_precip_in, max_precip_prob_pct,
    pressure_trend_24h=rt["pressure_trend_24h"], solunar_overlap=rt["solunar_overlap"],
)

st.divider()
st.header("Suggestions for right now")

m1, m2 = st.columns([1, 2])
m1.metric(f"{cond['segment_name']} activity score", f"{score_result.score}/10")
m2.write(
    f"**Season:** {season.replace('_', ' ').title()}  \n"
    f"**Structure:** {structure_type} (from this spot's saved type)  \n"
    f"**Water clarity:** {water_clarity}"
)
if score_result.notes:
    st.caption(" · ".join(score_result.notes))
for warn in score_result.warnings:
    st.warning(warn)
if bundle is None:
    st.caption(
        "Pressure trend and solunar timing aren't factored into the score above - no weather forecast "
        "data was available just now."
    )

rec = recommend(
    season, cond["water_temp_f"], cond["segment_name"], rt["pressure_trend_24h"],
    structure_type=structure_type, water_clarity=water_clarity,
    fish_depth_ft=cond.get("fish_depth_ft"), forage=cond.get("forage_seen"),
    thermocline_ft=cond.get("thermocline_ft"), inventory=get_inventory(),
)
render_lure_recommendation(rec)

st.divider()
st.header("Log actual activity")
st.caption(
    "Logged here just like the Log a Trip page - it goes into the same shared trip log, tagged to this "
    "exact spot and these exact conditions, so it can help calibrate future suggestions."
)

with st.form(f"log_activity_form_{spot['spot_id']}"):
    lc1, lc2 = st.columns(2)
    lure_used = lc1.text_input("Lure used", placeholder="e.g. Chartreuse/white spinnerbait")
    color_used = lc2.text_input("Color used", placeholder="e.g. Chartreuse/white")
    technique_used = st.text_input("Technique/presentation", placeholder="e.g. Slow-rolled along a windblown point")

    lc3, lc4 = st.columns(2)
    fish_caught = lc3.number_input("Bass caught", min_value=0, step=1, value=0)
    biggest_fish_lb = lc4.number_input("Biggest fish (lb)", min_value=0.0, step=0.1, value=0.0)

    log_notes = st.text_area("Notes", placeholder="Anything else worth remembering about this session")

    log_submitted = st.form_submit_button("Log this session", width='stretch')

if log_submitted:
    conditions = {
        "pressure_trend_24h": rt["pressure_trend_24h"],
        "moon_near_new_full": score_result.moon.is_new_or_full_window,
        "moon_phase": score_result.moon.name,
        "avg_cloud_pct": avg_cloud_pct,
        "avg_wind_mph": cond["wind_mph"],
        "water_temp_f": cond["water_temp_f"],
        "secchi_ft": cond["secchi_ft"],
        "light_condition": cond["light_condition"],
        "precipitation": cond["precipitation"],
        "start_time": cond["start_time"],
        "forage_seen": cond.get("forage_seen"),
        "fish_depth_ft": cond.get("fish_depth_ft"),
        "modeled_thermocline_ft": cond.get("thermocline_ft"),
        "source": "spot_session",
    }
    entry = TripEntry(
        trip_date=today.isoformat(),
        segment=cond["segment_name"],
        spot_id=spot["spot_id"],
        spot_name=spot["name"],
        structure_type=structure_type,
        water_clarity=water_clarity,
        lure_used=lure_used,
        color_used=color_used,
        technique_used=technique_used,
        fish_caught=int(fish_caught),
        biggest_fish_lb=float(biggest_fish_lb) if biggest_fish_lb else None,
        predicted_score=score_result.score,
        conditions=conditions,
        notes=log_notes,
    )
    append_trip(entry)

    token = github_token()
    if token:
        ok, msg = commit_and_push(
            [TRIP_LOG_PATH], token, repo_slug(), f"Log trip {entry.trip_id} from spot session ({spot['name']})",
        )
        (st.success if ok else st.warning)(msg)
    else:
        st.success("Session logged locally.")
        st.info(
            "No GITHUB_TOKEN configured in Streamlit secrets, so this entry wasn't pushed to GitHub "
            "and won't survive an app restart. See README for how to add it."
        )
