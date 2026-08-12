from datetime import datetime, time as dtime

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
from core.ui import render_lure_recommendation, render_square_thumbnail
from core.storage import TripEntry, TRIP_LOG_PATH, append_trip, commit_and_push, read_all_trips
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
        "No spot selected yet. Pick one of your saved spots below to start a session here directly, "
        "or go to the Lake Map page to click (or jump to) one instead."
    )

    if spots:
        CHOOSE_PROMPT = "— choose a saved spot —"
        sorted_spots = sorted(spots, key=lambda s: s["name"])
        picked_idx = st.selectbox(
            "Start a session at",
            options=range(len(sorted_spots) + 1),
            format_func=lambda i: CHOOSE_PROMPT if i == 0 else sorted_spots[i - 1]["name"],
        )
        if picked_idx != 0:
            picked_spot = sorted_spots[picked_idx - 1]
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
        st.caption("You don't have any saved spots yet - drop a pin on the Lake Map page first.")

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

# Computed from the spot alone (not from the Conditions form below), so it's always
# available - "Add results" needs it even if the angler never fills in conditions.
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")

session_date = st.date_input(
    "Session date", value=lake_today(), max_value=lake_today(),
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

# Everything below (score, recommendation, and the values folded into a logged
# entry's conditions) only exists once the angler has filled in Conditions above
# and clicked "Get lure suggestions" - but "Add results" further down must NOT be
# gated on that, so nothing here calls st.stop(). water_clarity/season/at_time/rt/
# score_result all stay None when cond is empty, and every place downstream that
# reads them (the Suggestions expander, the "Log this session" submit handler)
# checks for that instead of assuming they exist.
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
        "Fill in **Conditions right now** above and click **Get lure suggestions** to see a live activity "
        "score and lure recommendation here. You don't need to do that to log results below, though."
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

results_expander = st.expander("Log a lure/time-window result and any fish caught", expanded=False)

# Bumped after each successful "Log this session" save (see the submit handler
# below) so the lure/trailer/time/notes widgets below all get fresh, blank
# keys for the next lure - a full reset, ready to log another lure in the same
# visit right away. The "Conditions during this lure use" fields further down
# (wind/fish activity/forage activity/forage seen) deliberately do NOT fold
# this in, so they keep showing whatever was last entered instead of resetting -
# per the angler's own call: those conditions apply to the whole time at this
# spot, not just to one lure, so carrying them forward into the next lure entry
# is the right default (still editable if something actually changed).
lure_entry_seq_key = f"lure_entry_seq_{spot['spot_id']}"
st.session_state.setdefault(lure_entry_seq_key, 0)
lure_seq = st.session_state[lure_entry_seq_key]

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
    # lures instead of resetting.
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
            bits = [fish["species"]]
            if fish.get("weight_lb"):
                bits.append(f"{fish['weight_lb']:g} lb")
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

    st.divider()
    log_submitted = st.button(
        "Log this session", key=f"log_submit_{spot['spot_id']}", type="primary", width='stretch',
    )

    if log_submitted:
        fish_weights = [f["weight_lb"] for f in fish_records if f["weight_lb"]]

        # Everything in this first block only exists if Conditions right now was
        # filled in and scored (cond/rt/score_result/avg_cloud_pct/avg_wind_mph are
        # all None otherwise, per the "cond may be empty" note above) - logging
        # results doesn't require that, so these keys are simply left out of
        # conditions_json when there's no live reading behind them, same treatment
        # Trip History's FIELD_SPECS loop already gives any other missing key.
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
        entry = TripEntry(
            trip_date=session_date.isoformat(),
            # cond["segment_name"] reflects the time window picked in Conditions
            # right now; without that, fall back to the same hour-of-day guess that
            # field defaults to, so a result logged without conditions still lands
            # in a sensible time-of-day bucket for Trip History's filters.
            segment=cond["segment_name"] if cond else _guess_segment(lake_now_naive().hour),
            spot_id=spot["spot_id"],
            spot_name=spot["name"],
            structure_type=structure_type,
            water_clarity=water_clarity or "Unknown",
            lure_used=lure_used,
            color_used=color_used,
            technique_used=technique_used,
            fish_caught=len(fish_records),
            biggest_fish_lb=max(fish_weights) if fish_weights else None,
            predicted_score=score_result.score if score_result else None,
            conditions=conditions,
            notes=log_notes,
        )
        append_trip(entry)

        token = github_token()
        if token:
            ok, msg = commit_and_push(
                [TRIP_LOG_PATH], token, repo_slug(), f"Log trip {entry.trip_id} from spot session ({spot['name']})",
            )
            # st.toast rather than st.success/st.info - this confirmation needs to
            # survive the st.rerun() below (an inline st.success would get wiped
            # out by the rerun before the angler has a chance to read it; a toast
            # keeps showing across it).
            st.toast(msg, icon="✅" if ok else "⚠️")
        else:
            st.toast(
                "Session logged locally. No GITHUB_TOKEN configured in Streamlit secrets, so this "
                "entry won't survive an app restart - see README for how to add it.",
                icon="ℹ️",
            )

        # Full reset for the next lure entry, now that this one's saved: clear the
        # per-fish list, and bump lure_entry_seq_key so every lure/trailer/time/
        # notes widget above gets a fresh blank key next render (the "Conditions
        # during this lure use" fields deliberately keep their values - see the
        # comment above lure_entry_seq_key). The rerun is what actually makes this
        # visible immediately, ready to log another lure in the same visit.
        st.session_state[pending_key] = []
        st.session_state[seq_key] = 0
        st.session_state[adding_key] = False
        st.session_state[lure_entry_seq_key] = lure_seq + 1
        st.rerun()
