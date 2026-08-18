import json
from datetime import date as ddate, datetime, time as dtime

import streamlit as st

from core.appstate import get_lake_spots, get_inventory, get_weather_bundle, github_token, repo_slug
from core.lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE, split_bottom_structure
from core.onwater import (
    LIGHT_CONDITIONS, LIGHT_CONDITION_INFO, cloud_proxy_for_light_condition,
    WIND_BANDS, WIND_BAND_LABELS, WIND_DIRECTIONS, wind_mph_for_band, resolve_water_clarity, STAIN_COLOR_OPTIONS,
    water_temp_band, visibility_band, PRECIPITATION_OPTIONS, precipitation_proxy,
)
from core.scoring import (
    SEGMENTS, season_stage, manual_segment_score, realtime_context_from_bundle,
    segment_time_ranges, lake_now_naive,
)
from core.activity_log import (
    inventory_item_label, lure_can_take_trailer,
    FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS, RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
    FISH_SPECIES_OPTIONS,
)
from core.lures import recommend, FORAGE_OPTIONS
from core.ui import render_lure_recommendation, render_square_thumbnail, inject_mobile_css
from core.storage import TripEntry, TRIP_LOG_PATH, append_trip, commit_and_push, read_all_trips, update_trip
from core.weather import lake_today

st.set_page_config(page_title="Spot Session - Nolin Lake", page_icon="🎯", layout="wide")
inject_mobile_css()
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

if not spots:
    st.info(
        "No spot selected yet. Pick one of your saved spots below to start a session here directly, "
        "or go to the Lake Map page to click (or jump to) one instead."
    )
    st.caption("You don't have any saved spots yet - drop a pin on the Lake Map page first.")
    if st.button("Go to Lake Map"):
        st.switch_page("pages/2_Lake_Map.py")
    st.stop()

sorted_spots = sorted(spots, key=lambda s: s["name"])

# Location picker - always visible at the top, so a spot can be switched
# directly from this page instead of always having to go back to the Lake
# Map first. Keyed on the CURRENTLY loaded spot_id (rather than one fixed
# key) so that however a spot got selected - clicking "Fish this spot now"
# on the Lake Map, a bookmarked/shared ?spot_id= link, or picking a
# different spot from this exact dropdown a moment ago - it always shows
# the right thing already selected: a fresh key means Streamlit applies the
# `index=` default fresh every time spot_id changes, instead of clinging to
# a stale selection tied to the previous spot's widget instance.
if spot is not None:
    current_spot_idx = next(i for i, s in enumerate(sorted_spots) if s["spot_id"] == spot["spot_id"])
    picked_idx = st.selectbox(
        "📍 Location", options=range(len(sorted_spots)), format_func=lambda i: sorted_spots[i]["name"],
        index=current_spot_idx, key=f"spot_picker_{spot['spot_id']}",
    )
    picked_spot = sorted_spots[picked_idx]
    if picked_spot["spot_id"] != spot["spot_id"]:
        # Same session_state-primary/query_params-fallback handoff the Lake Map
        # page's "Fish this spot now" button uses (see comment above) - setting
        # it here means the rest of this page (which reads spot_id from those
        # same two places) picks it up identically on the rerun below, no
        # separate code path needed for "arrived via this dropdown" vs. "arrived
        # via the map".
        st.session_state["spot_session_target_id"] = picked_spot["spot_id"]
        st.query_params["spot_id"] = picked_spot["spot_id"]
        st.rerun()
else:
    st.info(
        "No spot selected yet. Pick one of your saved spots below to start a session here directly, "
        "or go to the Lake Map page to click (or jump to) one instead."
    )
    NO_SPOT_PROMPT = "— choose a saved spot —"
    picked_idx = st.selectbox(
        "📍 Location", options=range(len(sorted_spots) + 1),
        format_func=lambda i: NO_SPOT_PROMPT if i == 0 else sorted_spots[i - 1]["name"],
        key="spot_picker_none",
    )
    if picked_idx != 0:
        picked_spot = sorted_spots[picked_idx - 1]
        st.session_state["spot_session_target_id"] = picked_spot["spot_id"]
        st.query_params["spot_id"] = picked_spot["spot_id"]
        st.rerun()

    if st.button("Go to Lake Map"):
        st.switch_page("pages/2_Lake_Map.py")
    st.stop()

# Edit mode: arrived here via Trip History's "Edit this trip" button (or a
# bookmarked/shared ?edit_trip=... link) instead of a normal new-session
# visit - session_state is primary / query_params is the page-refresh
# fallback, same handoff pattern spot_id itself uses above. When set, the
# "Add results" section below gets pre-populated from that trip's stored
# data and "Log this lure"/"Log this session" are replaced with a single
# "Save changes" that updates that same row in place (see update_trip in
# core/storage.py) instead of appending a new one.
edit_trip_id = st.session_state.get("spot_session_edit_trip_id") or st.query_params.get("edit_trip")
editing_trip = None
editing_cond = {}
edit_prefill_done_key = None
if edit_trip_id:
    editing_trip = next((t for t in read_all_trips() if t.get("trip_id") == edit_trip_id), None)
    if editing_trip is None:
        # Stale/broken link, or the trip was deleted out from under an open
        # edit - drop out of edit mode instead of getting stuck pointing at
        # nothing.
        st.session_state.pop("spot_session_edit_trip_id", None)
        st.query_params.pop("edit_trip", None)
        edit_trip_id = None
    else:
        st.session_state["spot_session_edit_trip_id"] = edit_trip_id
        st.query_params["edit_trip"] = edit_trip_id
        # Keyed by BOTH edit_trip_id and the currently-loaded spot_id, not
        # just edit_trip_id alone - every widget the prefill block below
        # seeds is scoped to spot_id (e.g. f"log_wind_speed_{spot_id}"), so
        # switching the "📍 Location" picker to a different spot WHILE
        # editing (the angler correcting which spot a trip actually
        # happened at) lands on a brand-new set of spot-scoped widget keys
        # that have never been seeded. A key that only tracked edit_trip_id
        # would already read as "done" from the original spot and skip
        # re-seeding these - which is exactly what happened when reported:
        # switching location mid-edit made the lure/conditions/notes/fish
        # fields all revert to blank, as if starting a brand new session.
        edit_prefill_done_key = f"edit_prefill_done_{edit_trip_id}_{spot['spot_id']}"
        try:
            editing_cond = json.loads(editing_trip.get("conditions_json") or "{}")
        except json.JSONDecodeError:
            editing_cond = {}


def _exit_edit_mode():
    """Drop every bit of edit-mode state for whichever trip was being
    edited, so the next run lands back in normal "log a new session" mode
    for this same spot. Sweeps every edit_prefill_done_<trip_id>_<spot_id>
    flag for this trip, not just the current spot's - switching location
    mid-edit (see above) can leave one behind per spot visited, and a stale
    leftover from a spot no longer being edited would silently skip
    prefill if this same trip is ever edited again in this browser
    session."""
    if edit_trip_id:
        prefix = f"edit_prefill_done_{edit_trip_id}_"
        for stale_key in [k for k in st.session_state.keys() if k.startswith(prefix)]:
            st.session_state.pop(stale_key, None)
    st.session_state.pop("spot_session_edit_trip_id", None)
    st.query_params.pop("edit_trip", None)


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

if editing_trip is not None:
    ec1, ec2 = st.columns([5, 1])
    ec1.info(
        f"✏️ Editing the trip logged **{editing_trip['trip_date']}** - conditions and results below are "
        f"pre-filled from that entry. **Save changes** updates that same trip instead of adding a new one."
    )
    if ec2.button("Cancel edit", key="cancel_edit_top"):
        _exit_edit_mode()
        st.rerun()

if st.button("← Back to Lake Map"):
    st.switch_page("pages/2_Lake_Map.py")

# Computed from the spot alone (not from the Conditions form below), so it's always
# available - "Add results" needs it even if the angler never fills in conditions.
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")

# lure_entry_seq_key/lure_seq are computed here (rather than down by "Add
# results", where the reset logic that bumps them lives) because the
# edit-mode prefill block right below needs a fresh, not-currently-in-use
# seq number to seed lure/trailer/time/notes widget keys into before they're
# ever instantiated - see the "must happen before instantiation in this
# run" rule explained down at results_expander_reopen_key.
lure_entry_seq_key = f"lure_entry_seq_{spot['spot_id']}"
st.session_state.setdefault(lure_entry_seq_key, 0)
lure_seq = st.session_state[lure_entry_seq_key]

if editing_trip is not None and not st.session_state.get(edit_prefill_done_key):
    # One-time seed of every widget-backed session_state key the "Add
    # results" section (and the Session date field) reads, so the form
    # opens already showing this trip's data instead of blank defaults.
    # Guarded by edit_prefill_done_key so it only runs once per edit visit -
    # otherwise every rerun (e.g. typing in a text field) would stomp
    # whatever the angler had just changed back to the original values.
    #
    # Bump lure_entry_seq_key first so the lure/trailer/time/notes keys we
    # seed below (which fold lure_seq into their key) are guaranteed unused,
    # even if this exact spot already had some unsaved lure entry in
    # progress earlier in this same browser session.
    st.session_state[lure_entry_seq_key] = lure_seq + 1
    lure_seq = st.session_state[lure_entry_seq_key]

    def _find_inventory_item_by_label(label, items):
        """Best-effort match back to an inventory item by its display label -
        conditions_json only stores the resolved lure_used/trailer_name
        label and category, not the item_id itself (see
        _save_current_lure_entry below), so a renamed or since-deleted item
        just won't preselect and this falls back to blank, same as if
        nothing had been picked at all."""
        if not label:
            return None
        return next((it for it in items if inventory_item_label(it) == label), None)

    def _parse_iso_date(s):
        try:
            return ddate.fromisoformat(s) if s else None
        except ValueError:
            return None

    def _parse_iso_time(s):
        try:
            return dtime.fromisoformat(s) if s else None
        except ValueError:
            return None

    st.session_state[f"session_date_{spot['spot_id']}"] = _parse_iso_date(editing_trip.get("trip_date")) or lake_today()

    st.session_state[f"log_wind_speed_{spot['spot_id']}"] = editing_cond.get("wind_speed_mph") or 0.0
    st.session_state[f"log_wind_dir_{spot['spot_id']}"] = editing_cond.get("wind_direction") or WIND_DIRECTIONS[8]
    st.session_state[f"log_fish_activity_{spot['spot_id']}"] = editing_cond.get("fish_activity") or "Moderate"
    st.session_state[f"log_forage_activity_{spot['spot_id']}"] = editing_cond.get("forage_activity") or "Moderate"
    st.session_state[f"log_forage_type_{spot['spot_id']}"] = editing_cond.get("forage_type_seen") or []

    prefill_inventory = get_inventory()
    matched_lure = _find_inventory_item_by_label(editing_trip.get("lure_used"), prefill_inventory)
    if matched_lure:
        st.session_state[f"log_lure_{spot['spot_id']}_{lure_seq}_selected_id"] = matched_lure["item_id"]

    st.session_state[f"log_use_trailer_{spot['spot_id']}_{lure_seq}"] = bool(editing_cond.get("trailer_used"))
    if editing_cond.get("trailer_used"):
        matched_trailer = _find_inventory_item_by_label(editing_cond.get("trailer_name"), prefill_inventory)
        if matched_trailer:
            st.session_state[f"log_trailer_{spot['spot_id']}_{lure_seq}_selected_id"] = matched_trailer["item_id"]
        else:
            st.session_state[f"log_trailer_name_{spot['spot_id']}_{lure_seq}"] = editing_cond.get("trailer_name") or ""

    st.session_state[f"log_start_time_{spot['spot_id']}_{lure_seq}"] = _parse_iso_time(editing_cond.get("lure_start_time"))
    st.session_state[f"log_end_time_{spot['spot_id']}_{lure_seq}"] = _parse_iso_time(editing_cond.get("lure_end_time"))
    st.session_state[f"log_notes_{spot['spot_id']}_{lure_seq}"] = editing_trip.get("notes") or ""

    edit_fish_list = editing_cond.get("fish")
    st.session_state[f"pending_fish_{spot['spot_id']}"] = list(edit_fish_list) if isinstance(edit_fish_list, list) else []
    st.session_state[f"adding_fish_{spot['spot_id']}"] = False

    st.session_state[f"results_expander_{spot['spot_id']}"] = True
    st.session_state[edit_prefill_done_key] = True

session_date = st.date_input(
    "Session date",
    # Reads back whatever the edit-mode prefill block above just seeded into
    # session_state (falling back to today, same as always, outside edit
    # mode) rather than passing today as a separate literal default -
    # passing a differing hardcoded default alongside a pre-set
    # session_state value for the same key trips Streamlit's "widget was
    # created with a default value but also had its value set via the
    # Session State API" warning.
    value=st.session_state.get(f"session_date_{spot['spot_id']}", lake_today()),
    max_value=lake_today(),
    help="Defaults to today - pick an earlier date to log a past session at this spot. Pressure trend and "
         "solunar timing may fall back to their no-data defaults for dates outside the current forecast window.",
    key=f"session_date_{spot['spot_id']}",
)

try:
    bundle = get_weather_bundle(7)
except Exception:
    bundle = None
seg_ranges = segment_time_ranges(bundle, session_date)


def _segment_option_label(name: str) -> str:
    if seg_ranges and name in seg_ranges:
        s, e = seg_ranges[name]
        return f"{name} ({s.strftime('%-I:%M %p')}-{e.strftime('%-I:%M %p')})"
    return name


_wind_help = "\n".join(
    f"{label} ({lo:g}-{hi:g} mph): {detail}" if hi != float("inf") else f"{label} ({lo:g}+ mph): {detail}"
    for lo, hi, label, detail in WIND_BANDS
)

# Defaults for the (unkeyed) "Conditions right now" form below - editing_cond
# is {} outside edit mode, so every .get() here just falls through to the
# same hardcoded default the form always used, with no extra branching
# needed for the non-edit case.
_cond_water_temp_f = editing_cond.get("water_temp_f", 75.0)
_cond_secchi_ft = editing_cond.get("secchi_ft", 3.0)
_cond_stain_idx = (
    STAIN_COLOR_OPTIONS.index(editing_cond["stain_color"])
    if editing_cond.get("stain_color") in STAIN_COLOR_OPTIONS else 1
)
_cond_stirred_up = bool(editing_cond.get("stirred_up", False))
_cond_wind_band_idx = (
    WIND_BAND_LABELS.index(editing_cond["wind_band"]) if editing_cond.get("wind_band") in WIND_BAND_LABELS else 1
)
_cond_light_idx = (
    LIGHT_CONDITIONS.index(editing_cond["light_condition"])
    if editing_cond.get("light_condition") in LIGHT_CONDITIONS else 2
)
_cond_precip_idx = (
    PRECIPITATION_OPTIONS.index(editing_cond["precipitation"])
    if editing_cond.get("precipitation") in PRECIPITATION_OPTIONS else 0
)
_cond_start_time = None
if editing_cond.get("start_time"):
    try:
        _cond_start_time = dtime.fromisoformat(editing_cond["start_time"])
    except ValueError:
        _cond_start_time = None
_cond_forage_seen = editing_cond.get("forage_seen") or []
_cond_fish_depth_ft = editing_cond.get("fish_depth_ft") or 0.0
_editing_segment = (editing_trip or {}).get("segment")
_cond_segment_name = _editing_segment if _editing_segment in SEGMENTS else _guess_segment(lake_now_naive().hour)

st.divider()
st.header("Conditions right now")
st.caption(
    "Enter what you're actually seeing at the water - unlike the 7-Day Forecast page (which relies on "
    "a weather API), everything here is your own on-the-spot reading, so it drives suggestions "
    "specific to this exact moment at this exact spot. As soon as a session start time is set below, "
    "these values are saved and scored automatically - no extra button to click, and no need to open "
    "the suggestions panel below for that to happen."
)

# No st.form here (there used to be one, gated behind a "Get lure suggestions"
# submit button) - these fields update cond/score_result live on every
# rerun, same as any other widget outside a form. That's the point: an
# activity score gets computed and attached to a logged trip as soon as
# these fields are filled in, whether or not the angler ever opens "Add
# results" below to see it. The only genuinely required field is session
# start time (deliberately blank by default, per its help text below) -
# every other field already has a sane default, so cond starts existing the
# moment a start time is entered.
c1, c2 = st.columns(2)
water_temp_f = c1.number_input(
    "Water temperature (°F)", min_value=32.0, max_value=100.0, value=_cond_water_temp_f, step=0.5,
)
secchi_ft = c2.number_input(
    "Water visibility / Secchi depth (ft)", min_value=0.0, max_value=20.0, value=_cond_secchi_ft, step=0.5,
    help="How far down you can see a light-colored object/lure. Estimate visually if you don't carry a Secchi disk.",
)
temp_band = water_temp_band(water_temp_f)
st.caption(f"Metabolic state: **{temp_band['label']}** - {temp_band['detail']}")
vis_band = visibility_band(secchi_ft)
st.caption(f"Visibility band: **{vis_band['label']}** ({vis_band['detail']})")

stain_color = None
if vis_band["label"] == "Stained":
    stain_color = st.selectbox(
        "Stain color (Nolin normally runs greenish-brown, leaning brown)", STAIN_COLOR_OPTIONS,
        index=_cond_stain_idx,
    )
stirred_up = st.checkbox(
    "Stirred up / muddy right now (recent wind or rain)", value=_cond_stirred_up,
    help="Overrides the reading above straight to Muddy, regardless of Secchi depth or stain color - a "
         "fresh disturbance can outrun what you can see or measure yet.",
)

c3, c4 = st.columns(2)
wind_band_choice = c3.selectbox("Wind", WIND_BAND_LABELS, index=_cond_wind_band_idx, help=_wind_help)
light_condition = c4.selectbox(
    "Light conditions", LIGHT_CONDITIONS, index=_cond_light_idx,
    help="\n".join(f"{k} ({v['range']}): {v['detail']}" for k, v in LIGHT_CONDITION_INFO.items()),
)

c5, c6 = st.columns(2)
precipitation = c5.selectbox("Precipitation", PRECIPITATION_OPTIONS, index=_cond_precip_idx)
start_time = c6.time_input(
    "Session start time (enter manually)", value=_cond_start_time, step=300,
    help="When you actually started fishing this spot - enter it yourself rather than relying on "
         "whatever time it happens to be while you're filling this out, since you might do that "
         "before heading out or after you're done. Used to line up the score/suggestions below with "
         "that exact moment, and is what triggers a live score to be saved with this trip once you "
         "log results below.",
)

segment_display_options = [_segment_option_label(s) for s in SEGMENTS]
segment_display_choice = st.selectbox(
    "Time window", segment_display_options,
    index=SEGMENTS.index(_cond_segment_name),
)
segment_name = SEGMENTS[segment_display_options.index(segment_display_choice)]

c7, c8 = st.columns(2)
forage_seen = c7.multiselect("Forage seen (optional)", FORAGE_OPTIONS, default=_cond_forage_seen)
fish_depth_ft = c8.number_input(
    "Depth fish are showing up on electronics (ft, optional)", min_value=0.0, max_value=100.0,
    value=_cond_fish_depth_ft, step=1.0,
)

if start_time is not None:
    st.session_state.setdefault("spot_session_conditions", {})[spot["spot_id"]] = {
        "water_temp_f": water_temp_f, "secchi_ft": secchi_ft, "stain_color": stain_color,
        "stirred_up": stirred_up, "wind_band": wind_band_choice, "light_condition": light_condition,
        "precipitation": precipitation, "start_time": start_time.isoformat(), "segment_name": segment_name,
        "forage_seen": forage_seen, "fish_depth_ft": fish_depth_ft or None,
    }
else:
    # Nothing typed into "Session start time" yet - clear out any stale
    # snapshot for this spot rather than leaving a previous visit's cond
    # (and score) hanging around after the one required field got blanked.
    st.session_state.setdefault("spot_session_conditions", {}).pop(spot["spot_id"], None)

cond = st.session_state.get("spot_session_conditions", {}).get(spot["spot_id"])

# Everything below (score, recommendation, and the values folded into a logged
# entry's conditions) only exists once a session start time has been entered
# above - but "Add results" further down must NOT be gated on that, so nothing
# here calls st.stop(). water_clarity/season/at_time/rt/score_result all stay
# None when cond is empty, and every place downstream that reads them (the
# Suggestions expander, "Log this session"/"Save changes") checks for that
# instead of assuming they exist.
water_clarity = season = avg_cloud_pct = avg_wind_mph = at_time = rt = score_result = None

if cond:
    water_clarity = resolve_water_clarity(cond["secchi_ft"], cond.get("stain_color"), cond.get("stirred_up", False))
    season = season_stage(session_date.timetuple().tm_yday, cond["water_temp_f"])
    avg_cloud_pct = cloud_proxy_for_light_condition(cond["light_condition"])
    avg_wind_mph = wind_mph_for_band(cond["wind_band"])
    total_precip_in, max_precip_prob_pct = precipitation_proxy(cond["precipitation"])

    # The angler's own entered session-start time - not "right now" - is what "for
    # that exact time of day" should mean here, so it overrides the generic
    # wall-clock-now default that pressure-trend/moon-phase lookups would
    # otherwise fall back to.
    at_time = datetime.combine(session_date, dtime.fromisoformat(cond["start_time"]))

    rt = realtime_context_from_bundle(bundle, cond["segment_name"], session_date, at_time=at_time)

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
if cond:
    with st.expander("Suggestions for right now", expanded=True):
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
else:
    st.caption(
        "Enter a **session start time** in Conditions right now above to compute a live activity score "
        "and lure recommendation here - it'll save automatically with this trip too. You don't need to "
        "fill any of this in to log results below, though."
    )

LURE_PICKER_COLS = 4
LURE_PICKER_THUMBNAIL_PX = 90


def _visual_lure_picker(inventory_items: list, key_prefix: str):
    """Searchable, image-card picker over the tackle inventory. A plain
    st.selectbox can't show a photo inside its own option list - no browser
    <select> element supports that - so this renders a compact card grid
    instead (reusing core.ui.render_square_thumbnail, the same thumbnail
    helper the Lure Inventory page's browse grid already uses), with a
    search box to narrow a bigger tackle box down first. It lives entirely
    outside any st.form: clicking a card needs an immediate rerun so
    downstream fields (default color, trailer eligibility) update in the
    same pass, and a form only reruns on submit.

    Returns the selected inventory row, or None if nothing's picked (the
    caller then falls back to a plain text entry, same as the old "Other /
    not in inventory" selectbox option did).
    """
    selected_key = f"{key_prefix}_selected_id"
    if not inventory_items:
        st.caption(
            "No lures in your tackle box yet - add some on the Lure Inventory page, "
            "or just type this one in below."
        )
        return None

    search = st.text_input(
        "Search", key=f"{key_prefix}_search",
        placeholder="Search your tackle box by brand or description...",
        label_visibility="collapsed",
    )
    filtered = inventory_items
    if search:
        s = search.lower()
        filtered = [
            it for it in filtered
            if s in (it.get("description") or "").lower() or s in (it.get("brand") or "").lower()
        ]

    current_id = st.session_state.get(selected_key)

    if not filtered:
        st.caption("No matches for that search.")
    else:
        for row_start in range(0, len(filtered), LURE_PICKER_COLS):
            row_items = filtered[row_start:row_start + LURE_PICKER_COLS]
            cols = st.columns(LURE_PICKER_COLS)
            for col, item in zip(cols, row_items):
                with col:
                    with st.container(border=True):
                        if not render_square_thumbnail(item, size_px=LURE_PICKER_THUMBNAIL_PX):
                            st.caption("No photo")
                        st.caption(f"**{item.get('brand', '')}**  \n{item.get('description', '')}"[:90])
                        is_selected = item.get("item_id") == current_id
                        if st.button(
                            "✅ Selected" if is_selected else "Select",
                            key=f"{key_prefix}_pick_{item['item_id']}",
                            disabled=is_selected, width='stretch',
                        ):
                            st.session_state[selected_key] = item["item_id"]
                            st.rerun()

    current_id = st.session_state.get(selected_key)
    selected_item = next((it for it in inventory_items if it.get("item_id") == current_id), None)
    if selected_item is not None:
        cc1, cc2 = st.columns([5, 1])
        cc1.caption(f"Selected: **{inventory_item_label(selected_item)}**")
        if cc2.button("Clear", key=f"{key_prefix}_clear"):
            st.session_state[selected_key] = None
            st.rerun()
    return selected_item


st.divider()
st.subheader("Add results")
st.caption(
    "Log what actually happened, tagged to this exact spot and these exact conditions - see the "
    "Trip History page to review, filter, and let it calibrate future suggestions."
)

# One-shot, non-toast confirmation that "Log this session" actually did
# something - reported directly: after logging several lures with "Log
# this lure" (which worked), clicking "Log this session" left the angler
# unsure whether it saved and whether the form had actually reset for a
# new session. Root cause, confirmed with a scratch AppTest repro against
# real data (reverted afterward, no data lost): "Log this session" DOES
# correctly skip writing a duplicate row when nothing new was picked (by
# design - see has_pending_lure_data below) and DOES correctly reset
# "Conditions during this lure use" back to defaults - but the only
# confirmation was st.toast(), which is easy to miss on a phone, and if
# those condition fields already happened to be sitting at their defaults
# (very plausible - wind speed/fish activity aren't touched every visit),
# there was no VISIBLE difference on screen before vs. after clicking, so
# it read as "nothing happened" even though everything worked correctly.
# Popped (shown once) rather than a standing banner, so it doesn't linger
# on an unrelated later visit to this page.
if st.session_state.pop(f"session_closed_banner_{spot['spot_id']}", False):
    st.success(
        "✅ Session closed - conditions cleared for a new session. Pick a lure below whenever "
        "you're ready to start logging again."
    )

# Fresh from the CSV every render (cheap - this file is small) rather than a
# separate in-memory list, so it's correct even across a page refresh: every
# result already logged for this exact spot+date, so switching lures mid-visit
# reads as one cohesive "session" even though each lure is still its own row.
todays_entries = [
    t for t in read_all_trips()
    if t.get("spot_id") == spot["spot_id"] and t.get("trip_date") == session_date.isoformat()
]
if todays_entries:
    summary_bits = [f"{t.get('lure_used') or 'unknown lure'} ({t.get('fish_caught') or 0} fish)" for t in todays_entries]
    st.caption(f"📋 Already logged for this spot today: {', '.join(summary_bits)}")

# Keyed + on_change="rerun" (same fix as the Lure Inventory "Scan a lure" section -
# see SESSION_NOTES entry 46) so its expanded/collapsed state actually round-trips
# through st.session_state instead of being purely a client-side toggle. That
# matters here specifically because the submit handler below explicitly re-opens
# it after a save (see results_expander_reopen_key there) - without a key, a plain
# st.expander(expanded=False) always reverts to closed on the st.rerun() that
# follows a save, since "expanded" is only read as the INITIAL default. Losing
# all that expanded content collapses the page by hundreds of pixels, which
# looks exactly like "the page jumped back to the top and nothing happened" -
# reported after this feature first shipped, even though the save itself was
# working correctly the whole time.
#
# The submit handler can't write st.session_state[results_expander_key] directly
# to force it back open - Streamlit forbids writing to a keyed widget's state
# once that widget has already been instantiated in the current run, and the
# submit button lives inside `with results_expander:`, i.e. after it. So the
# handler instead sets a separate plain (non-widget) "pending reopen" flag, and
# it's applied here, right before the widget is created, on the following run.
results_expander_key = f"results_expander_{spot['spot_id']}"
results_expander_reopen_key = f"{results_expander_key}_reopen"
if st.session_state.pop(results_expander_reopen_key, False):
    st.session_state[results_expander_key] = True
st.session_state.setdefault(results_expander_key, False)
results_expander = st.expander(
    "Log a lure/time-window result and any fish caught",
    expanded=st.session_state[results_expander_key], key=results_expander_key, on_change="rerun",
)

# lure_entry_seq_key/lure_seq were already computed up near the top of the
# script (see the comment there) - repeated here as a reminder of why they
# exist: bumped after each successful "Log this session" save (see the
# submit handler below) so the lure/trailer/time/notes widgets below all get
# fresh, blank keys for the next lure - a full reset, ready to log another
# lure in the same visit right away. The "Conditions during this lure use"
# fields further down (wind/fish activity/forage activity/forage seen)
# deliberately do NOT fold this in, so they keep showing whatever was last
# entered instead of resetting - per the angler's own call: those conditions
# apply to the whole time at this spot, not just to one lure, so carrying
# them forward into the next lure entry is the right default (still
# editable if something actually changed).

with results_expander:
    inventory_items = get_inventory()

    # "Conditions during this lure use" is rendered FIRST, before the lure/trailer
    # pickers below - not just for reading order. The pickers' "Select" buttons
    # call st.rerun() mid-script the instant they're clicked, and Streamlit drops
    # session_state for any widget whose key hasn't been (re-)declared yet in the
    # script run that triggers a rerun - it only keeps state for widgets already
    # "seen" earlier in that same run. Declaring these here means they're always
    # registered before any picker click can interrupt the run, so their values
    # (wind/fish activity/forage activity/forage seen) actually survive picking a
    # lure instead of silently snapping back to their defaults. Confirmed with a
    # minimal repro during development - this ordering matters, don't move these
    # below the pickers again without re-testing.
    st.markdown("#### Conditions during this lure use")
    st.caption(
        "These carry over automatically to the next lure you log in this same session - "
        "update them here if something actually changed."
    )

    # These four fields intentionally keep a stable key (no lure_seq folded in) -
    # see the comment above lure_entry_seq_key for why they carry over between
    # lures instead of resetting. "Log this session" (below) is the one action
    # that clears them back to their own coded defaults, for a genuinely new
    # session - it can't write st.session_state[key] for these directly, since
    # by the time that button handler runs they're already instantiated this
    # run (same restriction, and same deferred-flag fix, as
    # results_expander_reopen_key above); session_reset_pending_key is applied
    # here, right before these widgets are created, on the run that follows.
    session_reset_pending_key = f"session_reset_pending_{spot['spot_id']}"
    condition_field_keys = (
        f"log_wind_speed_{spot['spot_id']}", f"log_wind_dir_{spot['spot_id']}",
        f"log_fish_activity_{spot['spot_id']}", f"log_forage_activity_{spot['spot_id']}",
        f"log_forage_type_{spot['spot_id']}",
    )
    if st.session_state.pop(session_reset_pending_key, False):
        for condition_key in condition_field_keys:
            st.session_state.pop(condition_key, None)

    wc1, wc2 = st.columns(2)
    wind_speed_mph = wc1.number_input(
        "Wind speed (mph)", min_value=0.0, max_value=60.0, value=0.0, step=1.0,
        key=f"log_wind_speed_{spot['spot_id']}",
    )
    wind_direction = wc2.selectbox(
        "Wind direction", WIND_DIRECTIONS, index=8, key=f"log_wind_dir_{spot['spot_id']}",
    )

    ac1, ac2 = st.columns(2)
    fish_activity = ac1.select_slider(
        "Fish activity", options=FISH_ACTIVITY_OPTIONS, value="Moderate", key=f"log_fish_activity_{spot['spot_id']}",
    )
    forage_activity = ac2.select_slider(
        "Forage activity", options=FORAGE_ACTIVITY_OPTIONS, value="Moderate", key=f"log_forage_activity_{spot['spot_id']}",
    )

    forage_type_seen = st.multiselect(
        "Forage type/species seen", FORAGE_OPTIONS, default=(cond.get("forage_seen", []) if cond else []),
        key=f"log_forage_type_{spot['spot_id']}",
    )

    st.divider()
    st.markdown("#### Lure used")
    selected_lure_item = _visual_lure_picker(inventory_items, key_prefix=f"log_lure_{spot['spot_id']}_{lure_seq}")
    # No manual name/color/technique/depth entry here anymore - those were dropped
    # in favor of just the picker plus the trailer selector below. lure_used/
    # color_used still get derived from whichever inventory item was picked (blank
    # if none was), since Trip History and the saved conditions still read them.
    lure_used = inventory_item_label(selected_lure_item) if selected_lure_item else ""
    color_used = selected_lure_item.get("description", "") if selected_lure_item else ""
    technique_used = ""

    use_trailer = False
    if lure_can_take_trailer(selected_lure_item):
        use_trailer = st.checkbox("Used a trailer", key=f"log_use_trailer_{spot['spot_id']}_{lure_seq}")

    trailer_name, trailer_color = "", ""
    selected_trailer_item = None
    if use_trailer:
        st.markdown("**Trailer**")
        selected_trailer_item = _visual_lure_picker(inventory_items, key_prefix=f"log_trailer_{spot['spot_id']}_{lure_seq}")
        if selected_trailer_item is None:
            trailer_name = st.text_input(
                "Trailer name", placeholder="e.g. Green pumpkin craw trailer",
                key=f"log_trailer_name_{spot['spot_id']}_{lure_seq}",
            )
        else:
            trailer_name = inventory_item_label(selected_trailer_item)
        trailer_color = st.text_input(
            "Trailer color",
            value=(selected_trailer_item.get("description", "") if selected_trailer_item else ""),
            key=f"log_trailer_color_{spot['spot_id']}_{lure_seq}_"
                f"{selected_trailer_item.get('item_id') if selected_trailer_item else 'manual'}",
        )

    tc3, tc4 = st.columns(2)
    lure_start_time = tc3.time_input(
        "Started using this lure at (optional)", value=None, key=f"log_start_time_{spot['spot_id']}_{lure_seq}",
    )
    lure_end_time = tc4.time_input(
        "Stopped using this lure at (optional)", value=None, key=f"log_end_time_{spot['spot_id']}_{lure_seq}",
    )

    log_notes = st.text_area(
        "Notes for this time range", placeholder="Anything else worth remembering about this lure/time window",
        key=f"log_notes_{spot['spot_id']}_{lure_seq}",
    )

    st.divider()
    st.markdown("#### Fish caught")

    pending_key = f"pending_fish_{spot['spot_id']}"
    seq_key = f"fish_entry_seq_{spot['spot_id']}"
    adding_key = f"adding_fish_{spot['spot_id']}"
    st.session_state.setdefault(pending_key, [])
    st.session_state.setdefault(seq_key, 0)
    st.session_state.setdefault(adding_key, False)
    fish_records = st.session_state[pending_key]

    if fish_records:
        for i, fish in enumerate(fish_records):
            frow1, frow2 = st.columns([5, 1])
            count = fish.get("count") or 1
            bits = [f"{count} x {fish['species']}" if count > 1 else fish["species"]]
            if fish.get("weight_lb"):
                bits.append(f"~{fish['weight_lb']:g} lb each" if count > 1 else f"{fish['weight_lb']:g} lb")
            if fish.get("length_in"):
                bits.append(f"{fish['length_in']:g} in")
            if fish.get("depth_ft"):
                bits.append(f"{fish['depth_ft']:g} ft deep")
            presentation = " / ".join(x for x in [fish.get("retrieve_speed"), fish.get("retrieve_style")] if x)
            if presentation:
                bits.append(presentation)
            frow1.write(f"🐟 Fish #{i + 1}: {', '.join(bits)}")
            if frow2.button("Remove", key=f"remove_fish_{spot['spot_id']}_{i}"):
                fish_records.pop(i)
                st.session_state[pending_key] = fish_records
                st.rerun()
    else:
        st.caption("No fish logged yet for this lure/time window.")

    if not st.session_state[adding_key]:
        if st.button("➕ Add fish", key=f"open_add_fish_{spot['spot_id']}"):
            st.session_state[adding_key] = True
            st.rerun()
    else:
        seq = st.session_state[seq_key]
        with st.container(border=True):
            st.markdown("**New fish**")
            species_idx = st.selectbox(
                "Fish type", options=list(range(len(FISH_SPECIES_OPTIONS))),
                format_func=lambda j: FISH_SPECIES_OPTIONS[j],
                key=f"log_new_fish_species_{spot['spot_id']}_{seq}",
            )
            species_label = FISH_SPECIES_OPTIONS[species_idx]
            species_other = ""
            if species_label == "Other (type in species)":
                species_other = st.text_input(
                    "Species (type it in)", key=f"log_new_fish_species_other_{spot['spot_id']}_{seq}",
                )

            is_group = st.checkbox(
                "Log as a group of small fish (all under 1 lb)",
                key=f"log_new_fish_is_group_{spot['spot_id']}_{seq}",
                help="For a bunch of small dinks caught on the same lure/window that aren't worth a "
                     "separate entry each - enter how many instead of adding them one at a time.",
            )

            if is_group:
                gc1, gc2, gc3 = st.columns(3)
                new_count = gc1.number_input(
                    "How many fish", min_value=2, step=1, value=2,
                    key=f"log_new_fish_count_{spot['spot_id']}_{seq}",
                )
                new_weight_lb = gc2.number_input(
                    "Approx weight each (lb, optional)", min_value=0.0, max_value=1.0, step=0.1, value=0.0,
                    key=f"log_new_fish_group_weight_{spot['spot_id']}_{seq}",
                    help="Leave at 0 if you didn't weigh them - a group entry is for fish under 1 lb each.",
                )
                new_depth_ft = gc3.number_input(
                    "Depth caught at (ft)", min_value=0.0, max_value=100.0, step=1.0, value=0.0,
                    key=f"log_new_fish_depth_{spot['spot_id']}_{seq}",
                )
                new_length_in = 0.0
            else:
                fc1, fc2, fc3 = st.columns(3)
                new_weight_lb = fc1.number_input(
                    "Weight (lb)", min_value=0.0, step=0.1, value=0.0,
                    key=f"log_new_fish_weight_{spot['spot_id']}_{seq}",
                )
                new_length_in = fc2.number_input(
                    "Length (in)", min_value=0.0, step=0.25, value=0.0,
                    key=f"log_new_fish_length_{spot['spot_id']}_{seq}",
                )
                new_depth_ft = fc3.number_input(
                    "Depth caught at (ft)", min_value=0.0, max_value=100.0, step=1.0, value=0.0,
                    key=f"log_new_fish_depth_{spot['spot_id']}_{seq}",
                )
                new_count = 1

            fc4, fc5 = st.columns(2)
            new_retrieve_style = fc4.selectbox(
                "Presentation/technique", RETRIEVE_STYLE_OPTIONS, key=f"log_new_fish_style_{spot['spot_id']}_{seq}",
            )
            new_retrieve_speed = fc5.selectbox(
                "Retrieval speed", RETRIEVE_SPEED_OPTIONS, index=1, key=f"log_new_fish_speed_{spot['spot_id']}_{seq}",
            )

            sc1, sc2 = st.columns(2)
            if sc1.button(
                "Save fish", key=f"log_new_fish_save_{spot['spot_id']}_{seq}", type="primary", width='stretch',
            ):
                species_final = (
                    species_other.strip()
                    if (species_label == "Other (type in species)" and species_other.strip())
                    else species_label
                )
                fish_records.append({
                    "species": species_final,
                    "species_other": species_other or None,
                    "count": int(new_count) if is_group else 1,
                    "weight_lb": new_weight_lb or None,
                    "length_in": new_length_in or None,
                    "depth_ft": new_depth_ft or None,
                    "retrieve_speed": new_retrieve_speed,
                    "retrieve_style": new_retrieve_style,
                })
                st.session_state[pending_key] = fish_records
                st.session_state[seq_key] = seq + 1
                st.session_state[adding_key] = False
                st.rerun()
            if sc2.button("Cancel", key=f"log_new_fish_cancel_{spot['spot_id']}_{seq}", width='stretch'):
                st.session_state[adding_key] = False
                st.rerun()

    # Every key _save_current_lure_entry's cond-derived block below writes,
    # used to carry the original snapshot forward when editing a trip and
    # the angler didn't re-fill in "Conditions right now" this visit (see
    # that function for why - otherwise a plain notes/fish-count correction
    # would silently blow away the whole condition reading it was scored
    # against).
    _COND_DERIVED_KEYS = (
        "pressure_trend_24h", "moon_near_new_full", "moon_phase", "avg_cloud_pct", "avg_wind_mph",
        "wind_band", "water_temp_f", "secchi_ft", "stirred_up", "light_condition", "precipitation",
        "start_time", "forage_seen", "fish_depth_ft",
    )

    def _save_current_lure_entry():
        """Build a TripEntry from the current form state and save it - append
        as a new row normally, or update the existing row in place when
        editing (see editing_trip above). Pushes to GitHub if configured and
        toasts a confirmation. Shared by "Log this lure"/"Log this session"
        (always append) and "Save changes" (always update) so there's
        exactly one place that assembles a TripEntry from these fields."""
        fish_weights = [f["weight_lb"] for f in fish_records if f["weight_lb"]]

        # Everything in this first block only exists if Conditions right now was
        # filled in and scored (cond/rt/score_result/avg_cloud_pct/avg_wind_mph are
        # all None otherwise, per the "cond may be empty" note above) - logging
        # results doesn't require that, so these keys are simply left out of
        # conditions_json when there's no live reading behind them, same treatment
        # Trip History's FIELD_SPECS loop already gives any other missing key.
        #
        # When editing a trip and the angler didn't re-fill in "Conditions right
        # now" this visit (e.g. left session start time blank), fall back to
        # whatever condition snapshot the original entry already had instead
        # of dropping it - a save should only ever change what was actually
        # touched.
        conditions = {}
        if cond:
            conditions.update({
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
            })
        elif editing_trip is not None:
            conditions.update({k: editing_cond[k] for k in _COND_DERIVED_KEYS if k in editing_cond})
        conditions.update({
            # lure_category is the raw core.lures.LURE_PROFILES key (e.g. "football_jig"),
            # not the display name - only set when the lure was picked from inventory, so
            # Trip History can offer a real "lure type" filter without guessing a
            # category from free text for manually-entered lures.
            "lure_category": selected_lure_item.get("category") if selected_lure_item else None,
            "trailer_used": use_trailer,
            "trailer_name": trailer_name or None,
            "trailer_color": trailer_color or None,
            "trailer_category": selected_trailer_item.get("category") if selected_trailer_item else None,
            "lure_start_time": lure_start_time.isoformat() if lure_start_time else None,
            "lure_end_time": lure_end_time.isoformat() if lure_end_time else None,
            "wind_speed_mph": wind_speed_mph or None,
            "wind_direction": wind_direction,
            "fish_activity": fish_activity,
            "forage_activity": forage_activity,
            "forage_type_seen": forage_type_seen,
            # Per-fish catch records - a separate entry for each fish caught on this
            # lure during this time window, each with its own species/size/depth/
            # presentation, added one at a time via the "Add fish" button above.
            # fish_caught/biggest_fish_lb below are derived from this list so
            # existing Trip History metrics and core.calibration's factor-flag
            # logic (both keyed on those two top-level TripEntry fields) keep
            # working unchanged.
            "fish": fish_records,
            "source": "spot_session",
        })
        # Same fallback logic as the conditions block above: a fresh score
        # only exists if "Conditions right now" has a session start time
        # filled in this visit; otherwise, when editing, keep the original
        # trip's score rather than blanking it out just because that section
        # wasn't touched.
        if score_result:
            predicted_score = score_result.score
        elif editing_trip is not None and editing_trip.get("predicted_score") not in (None, ""):
            try:
                predicted_score = float(editing_trip["predicted_score"])
            except ValueError:
                predicted_score = None
        else:
            predicted_score = None

        # cond["segment_name"] reflects the time window picked in Conditions
        # right now this visit. Without that: when editing and conditions
        # weren't re-filled in, keep the original trip's segment rather than
        # guessing from the CURRENT wall-clock hour (which is almost
        # certainly not when the original session happened); otherwise (a
        # brand new result with no conditions filled in) fall back to that
        # same hour-of-day guess, so it still lands in a sensible time-of-day
        # bucket for Trip History's filters.
        if cond:
            entry_segment = cond["segment_name"]
        elif editing_trip is not None and editing_trip.get("segment") in SEGMENTS:
            entry_segment = editing_trip["segment"]
        else:
            entry_segment = _guess_segment(lake_now_naive().hour)

        # Same story as segment above: water_clarity is derived from cond
        # too, so without "Conditions right now" refilled in this visit,
        # an edit should keep the original trip's stored water_clarity
        # rather than resetting it to "Unknown" just because that section
        # wasn't touched this time.
        if water_clarity:
            entry_water_clarity = water_clarity
        elif editing_trip is not None and editing_trip.get("water_clarity"):
            entry_water_clarity = editing_trip["water_clarity"]
        else:
            entry_water_clarity = "Unknown"

        entry_kwargs = dict(
            trip_date=session_date.isoformat(),
            segment=entry_segment,
            spot_id=spot["spot_id"],
            spot_name=spot["name"],
            structure_type=structure_type,
            water_clarity=entry_water_clarity,
            lure_used=lure_used,
            color_used=color_used,
            technique_used=technique_used,
            fish_caught=sum((f.get("count") or 1) for f in fish_records),
            biggest_fish_lb=max(fish_weights) if fish_weights else None,
            predicted_score=predicted_score,
            conditions=conditions,
            notes=log_notes,
        )

        if editing_trip is not None:
            # Same trip_id, and the original logged_at (first-logged time) is
            # preserved rather than reset to now - an edit corrects a trip,
            # it doesn't create a new one.
            entry = TripEntry(
                trip_id=edit_trip_id,
                logged_at=editing_trip.get("logged_at") or datetime.utcnow().isoformat(),
                **entry_kwargs,
            )
            update_trip(entry)
            commit_message = f"Update trip {entry.trip_id} from spot session edit ({spot['name']})"
        else:
            entry = TripEntry(**entry_kwargs)
            append_trip(entry)
            commit_message = f"Log trip {entry.trip_id} from spot session ({spot['name']})"

        token = github_token()
        if token:
            ok, msg = commit_and_push([TRIP_LOG_PATH], token, repo_slug(), commit_message)
            # st.toast rather than st.success/st.info - this confirmation needs to
            # survive the st.rerun() below (an inline st.success would get wiped
            # out by the rerun before the angler has a chance to read it; a toast
            # keeps showing across it).
            st.toast(msg, icon="✅" if ok else "⚠️")
        else:
            st.toast(
                "Lure logged locally. No GITHUB_TOKEN configured in Streamlit secrets, so this "
                "entry won't survive an app restart - see README for how to add it.",
                icon="ℹ️",
            )

    def _reset_for_next_lure():
        """Clear the per-fish list and bump lure_entry_seq_key so every lure/
        trailer/time/notes widget above gets a fresh blank key next render -
        called after EVERY save, whether from "Log this lure" or "Log this
        session" (see the comment above lure_entry_seq_key for why the
        "Conditions during this lure use" fields are deliberately NOT touched
        here - that's "Log this session"'s job, via session_reset_pending_key,
        since a plain "Log this lure" save should keep carrying them
        forward). Setting results_expander_reopen_key means the "Add results"
        section stays open through the rerun below instead of snapping shut -
        without this the angler has to scroll back down and re-expand it by
        hand before logging the next lure, which reads as "nothing happened."
        """
        st.session_state[pending_key] = []
        st.session_state[seq_key] = 0
        st.session_state[adding_key] = False
        st.session_state[lure_entry_seq_key] = lure_seq + 1
        st.session_state[results_expander_reopen_key] = True

    st.divider()

    if editing_trip is not None:
        # Editing one specific already-logged trip - there's no "next lure in
        # this session" concept here, just this one row to correct, so a
        # single Save/Cancel pair replaces the normal two-button flow.
        save_col, cancel_col = st.columns(2)
        save_changes_submitted = save_col.button(
            "💾 Save changes", key=f"save_edit_{spot['spot_id']}", type="primary", width='stretch',
            help="Updates this same trip in place - it stays one row in Trip History, not a duplicate.",
        )
        cancel_edit_submitted = cancel_col.button(
            "Cancel edit", key=f"cancel_edit_bottom_{spot['spot_id']}", width='stretch',
        )
        if save_changes_submitted:
            _save_current_lure_entry()
            _exit_edit_mode()
            st.toast("Trip updated.", icon="✅")
            st.rerun()
        if cancel_edit_submitted:
            _exit_edit_mode()
            st.rerun()
    else:
        lure_col, session_col = st.columns(2)
        log_lure_submitted = lure_col.button(
            "Log this lure", key=f"log_submit_{spot['spot_id']}", type="primary", width='stretch',
            help="Save this lure's results and stay in this session - wind/fish activity/forage "
                 "conditions carry over, ready to pick your next lure.",
        )
        log_session_submitted = session_col.button(
            "Log this session", key=f"log_session_submit_{spot['spot_id']}", width='stretch',
            help="Done fishing this spot for now: saves this lure too if you haven't yet, then clears "
                 "conditions so the next thing you log starts as a brand-new session.",
        )

        if log_lure_submitted:
            _save_current_lure_entry()
            _reset_for_next_lure()
            st.rerun()

        if log_session_submitted:
            # A lure counts as "pending" (worth saving before closing out) if
            # anything about it was actually filled in - a lure was picked, a
            # fish was logged, or a note was typed. Guards against writing a
            # blank/junk trip_log row on the common case where the angler already
            # clicked "Log this lure" for their last one and the form is sitting
            # empty when they click "Log this session" right after.
            has_pending_lure_data = selected_lure_item is not None or bool(fish_records) or bool(log_notes.strip())
            if has_pending_lure_data:
                _save_current_lure_entry()
            else:
                st.toast("Session closed - conditions cleared for a new session.", icon="✅")
            _reset_for_next_lure()
            # Consumed right before the "Conditions during this lure use" widgets
            # are (re-)created next run (see where this key is read, above) -
            # that's what actually clears wind/fish activity/forage activity/
            # forage seen back to their own coded defaults, so the NEXT session
            # starts from a genuinely blank slate instead of carrying over
            # whatever this session's conditions happened to be.
            st.session_state[session_reset_pending_key] = True
            # Shown once, right at the top of "Add results" (see above) -
            # backstops the st.toast() calls above/inside
            # _save_current_lure_entry() with a confirmation that survives
            # long enough to actually be seen and doesn't depend on the
            # conditions fields having visibly changed.
            st.session_state[f"session_closed_banner_{spot['spot_id']}"] = True
            st.rerun()
