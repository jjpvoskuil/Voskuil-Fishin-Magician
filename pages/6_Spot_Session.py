from datetime import datetime, time as dtime

import streamlit as st

from core.appstate import get_lake_spots, get_inventory, get_weather_bundle, github_token, repo_slug
from core.lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE, split_bottom_structure
from core.onwater import (
    LIGHT_CONDITIONS, LIGHT_CONDITION_INFO, cloud_proxy_for_light_condition,
    WIND_BANDS, WIND_BAND_LABELS, wind_mph_for_band, resolve_water_clarity, STAIN_COLOR_OPTIONS,
    water_temp_band, visibility_band, PRECIPITATION_OPTIONS, precipitation_proxy,
)
from core.scoring import (
    SEGMENTS, season_stage, manual_segment_score, realtime_context_from_bundle,
    segment_time_ranges, lake_now_naive,
)
from core.activity_log import (
    lure_picker_options, inventory_item_label, lure_can_take_trailer,
    FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS, RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
)
from core.lures import recommend, FORAGE_OPTIONS
from core.ui import render_lure_recommendation
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

today = lake_today()
try:
    bundle = get_weather_bundle(7)
except Exception:
    bundle = None
seg_ranges = segment_time_ranges(bundle, today)


def _segment_option_label(name: str) -> str:
    if seg_ranges and name in seg_ranges:
        s, e = seg_ranges[name]
        return f"{name} ({s.strftime('%-I:%M %p')}-{e.strftime('%-I:%M %p')})"
    return name


_wind_help = "\n".join(
    f"{label} ({lo:g}-{hi:g} mph): {detail}" if hi != float("inf") else f"{label} ({lo:g}+ mph): {detail}"
    for lo, hi, label, detail in WIND_BANDS
)

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
    stirred_up = st.checkbox(
        "Stirred up / muddy right now (recent wind or rain)",
        help="Overrides the reading above straight to Muddy, regardless of Secchi depth or stain color - a "
             "fresh disturbance can outrun what you can see or measure yet.",
    )

    c3, c4 = st.columns(2)
    wind_band_choice = c3.selectbox("Wind", WIND_BAND_LABELS, index=1, help=_wind_help)
    c3.caption(f"≈ {wind_mph_for_band(wind_band_choice):.0f} mph")
    light_condition = c4.selectbox(
        "Light conditions", LIGHT_CONDITIONS, index=2,
        help="\n".join(f"{k} ({v['range']}): {v['detail']}" for k, v in LIGHT_CONDITION_INFO.items()),
    )

    c5, c6 = st.columns(2)
    precipitation = c5.selectbox("Precipitation", PRECIPITATION_OPTIONS)
    start_time = c6.time_input(
        "Session start time (enter manually)", value=None, step=300,
        help="When you actually started fishing this spot - enter it yourself rather than relying on "
             "whatever time it happens to be while you're filling this out, since you might do that "
             "before heading out or after you're done. Used to line up the score/suggestions below with "
             "that exact moment.",
    )

    segment_display_options = [_segment_option_label(s) for s in SEGMENTS]
    segment_display_choice = st.selectbox(
        "Time window", segment_display_options,
        index=SEGMENTS.index(_guess_segment(lake_now_naive().hour)),
    )
    segment_name = SEGMENTS[segment_display_options.index(segment_display_choice)]

    c7, c8 = st.columns(2)
    forage_seen = c7.multiselect("Forage seen (optional)", FORAGE_OPTIONS, default=[])
    fish_depth_ft = c8.number_input(
        "Depth fish are showing up on electronics (ft, optional)", min_value=0.0, max_value=100.0, value=0.0, step=1.0,
    )

    submitted = st.form_submit_button("Get lure suggestions", width='stretch')

if submitted:
    if start_time is None:
        st.warning("Session start time is required - enter the time you actually started fishing this spot.")
    else:
        st.session_state.setdefault("spot_session_conditions", {})[spot["spot_id"]] = {
            "water_temp_f": water_temp_f, "secchi_ft": secchi_ft, "stain_color": stain_color,
            "stirred_up": stirred_up, "wind_band": wind_band_choice, "light_condition": light_condition,
            "precipitation": precipitation, "start_time": start_time.isoformat(), "segment_name": segment_name,
            "forage_seen": forage_seen, "fish_depth_ft": fish_depth_ft or None,
        }

cond = st.session_state.get("spot_session_conditions", {}).get(spot["spot_id"])

if not cond:
    st.info("Fill in the conditions above and click **Get lure suggestions** to continue.")
    st.stop()

water_clarity = resolve_water_clarity(cond["secchi_ft"], cond.get("stain_color"), cond.get("stirred_up", False))
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")
season = season_stage(today.timetuple().tm_yday, cond["water_temp_f"])
avg_cloud_pct = cloud_proxy_for_light_condition(cond["light_condition"])
avg_wind_mph = wind_mph_for_band(cond["wind_band"])
total_precip_in, max_precip_prob_pct = precipitation_proxy(cond["precipitation"])

# The angler's own entered session-start time - not "right now" - is what "for that
# exact time of day" should mean here, so it overrides the generic wall-clock-now
# default that pressure-trend/moon-phase lookups would otherwise fall back to.
at_time = datetime.combine(today, dtime.fromisoformat(cond["start_time"]))

rt = realtime_context_from_bundle(bundle, cond["segment_name"], today, at_time=at_time)

score_result = manual_segment_score(
    cond["segment_name"], season, avg_cloud_pct, avg_wind_mph, total_precip_in, max_precip_prob_pct,
    pressure_trend_24h=rt["pressure_trend_24h"], solunar_overlap=rt["solunar_overlap"], at_time=at_time,
    water_temp_f=cond["water_temp_f"], water_clarity=water_clarity,
    forage_present=bool(cond.get("forage_seen")),
)


def _score_breakdown_help(breakdown: list, final_score: float) -> str:
    lines = ["**How this score was derived:**", ""]
    raw_total = 0.0
    for label, delta, detail in breakdown:
        raw_total += delta
        sign = "+" if delta >= 0 else ""
        lines.append(f"- {label}: {sign}{delta:g} — {detail}")
    if round(raw_total, 1) != final_score:
        lines.append("")
        lines.append(f"Raw total {raw_total:g} is clamped to the 1-10 range → **{final_score}/10**.")
    return "\n".join(lines)


st.divider()
st.header("Suggestions for right now")

m1, m2 = st.columns([1, 2])
m1.metric(
    f"{cond['segment_name']} activity score", f"{score_result.score}/10",
    help=_score_breakdown_help(score_result.breakdown, score_result.score),
)
m2.write(
    f"**Season:** {season.replace('_', ' ').title()}  \n"
    f"**Structure:** {structure_type} (from this spot's saved type)  \n"
    f"**Water clarity:** {water_clarity}"
)
st.caption(f"Scored for about {at_time.strftime('%-I:%M %p')} - your entered session start time.")
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
    inventory=get_inventory(),
)
render_lure_recommendation(rec)

st.divider()
st.header("Log actual activity")
st.caption(
    "Logged here just like the Log a Trip page - it goes into the same shared trip log, tagged to this "
    "exact spot and these exact conditions, so it can help calibrate future suggestions."
)

inventory_items = get_inventory()
lure_labels, lure_items = lure_picker_options(inventory_items)

pc1, pc2 = st.columns(2)
lure_idx = pc1.selectbox(
    "Lure used", options=list(range(len(lure_labels))), format_func=lambda i: lure_labels[i],
    key=f"log_lure_idx_{spot['spot_id']}",
)
selected_lure_item = lure_items[lure_idx]

use_trailer = False
if lure_can_take_trailer(selected_lure_item):
    use_trailer = pc2.checkbox("Used a trailer", key=f"log_use_trailer_{spot['spot_id']}")

trailer_idx = 0
selected_trailer_item = None
if use_trailer:
    trailer_idx = st.selectbox(
        "Trailer", options=list(range(len(lure_labels))), format_func=lambda i: lure_labels[i],
        key=f"log_trailer_idx_{spot['spot_id']}",
    )
    selected_trailer_item = lure_items[trailer_idx]

with st.form(f"log_activity_form_{spot['spot_id']}"):
    if selected_lure_item is None:
        lure_used = st.text_input("Lure name", placeholder="e.g. Chartreuse/white spinnerbait")
    else:
        lure_used = inventory_item_label(selected_lure_item)
        st.caption(f"Lure: **{lure_used}**")
    color_used = st.text_input(
        "Color used", value=(selected_lure_item.get("description", "") if selected_lure_item else ""),
        key=f"log_color_used_{spot['spot_id']}_{lure_idx}", placeholder="e.g. Chartreuse/white",
    )

    trailer_name, trailer_color = "", ""
    if use_trailer:
        tc1, tc2 = st.columns(2)
        if selected_trailer_item is None:
            trailer_name = tc1.text_input("Trailer name", placeholder="e.g. Green pumpkin craw trailer")
        else:
            trailer_name = inventory_item_label(selected_trailer_item)
            tc1.caption(f"Trailer: **{trailer_name}**")
        trailer_color = tc2.text_input(
            "Trailer color",
            value=(selected_trailer_item.get("description", "") if selected_trailer_item else ""),
            key=f"log_trailer_color_{spot['spot_id']}_{trailer_idx}",
        )

    technique_used = st.text_input("Technique/presentation", placeholder="e.g. Slow-rolled along a windblown point")

    tc3, tc4 = st.columns(2)
    lure_start_time = tc3.time_input("Started using this lure at (optional)", value=None)
    lure_end_time = tc4.time_input("Stopped using this lure at (optional)", value=None)

    dc1, dc2 = st.columns(2)
    depth_fished_ft = dc1.number_input(
        "Primary depth fished (ft)", min_value=0.0, max_value=100.0, value=0.0, step=1.0,
    )
    depth_fished_varied_note = dc2.text_input(
        "Or, several depths tried", placeholder="e.g. worked 2-15 ft, fish suspended over the channel",
    )

    ac1, ac2 = st.columns(2)
    fish_activity = ac1.select_slider("Fish activity", options=FISH_ACTIVITY_OPTIONS, value="Moderate")
    retrieve_speed = ac2.selectbox("Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=1)

    rc1, rc2 = st.columns(2)
    retrieve_style = rc1.selectbox("Retrieve style", RETRIEVE_STYLE_OPTIONS)
    forage_activity = rc2.select_slider("Forage activity", options=FORAGE_ACTIVITY_OPTIONS, value="Moderate")

    forage_type_seen = st.multiselect("Forage type/species seen", FORAGE_OPTIONS, default=cond.get("forage_seen", []))

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
        "avg_wind_mph": avg_wind_mph,
        "wind_band": cond["wind_band"],
        "water_temp_f": cond["water_temp_f"],
        "secchi_ft": cond["secchi_ft"],
        "stirred_up": cond.get("stirred_up", False),
        "light_condition": cond["light_condition"],
        "precipitation": cond["precipitation"],
        "start_time": cond["start_time"],
        "forage_seen": cond.get("forage_seen"),
        "fish_depth_ft": cond.get("fish_depth_ft"),
        "trailer_used": use_trailer,
        "trailer_name": trailer_name or None,
        "trailer_color": trailer_color or None,
        "lure_start_time": lure_start_time.isoformat() if lure_start_time else None,
        "lure_end_time": lure_end_time.isoformat() if lure_end_time else None,
        "depth_fished_ft": depth_fished_ft or None,
        "depth_fished_varied_note": depth_fished_varied_note or None,
        "fish_activity": fish_activity,
        "forage_activity": forage_activity,
        "forage_type_seen": forage_type_seen,
        "retrieve_speed": retrieve_speed,
        "retrieve_style": retrieve_style,
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
