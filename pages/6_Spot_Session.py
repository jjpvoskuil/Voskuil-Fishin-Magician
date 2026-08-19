import json
from datetime import date as ddate, datetime, time as dtime

import streamlit as st

from core.appstate import get_lake_spots, get_inventory, get_weather_bundle, github_token, repo_slug
from core.lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE, split_bottom_structure
from core.onwater import (
    LIGHT_CONDITIONS, LIGHT_CONDITION_INFO, cloud_proxy_for_light_condition, light_condition_for_cloud_pct,
    WIND_BANDS, WIND_BAND_LABELS, WIND_DIRECTIONS, wind_band, wind_mph_for_band, wind_direction_for_degrees,
    resolve_water_clarity, STAIN_COLOR_OPTIONS, water_temp_band, visibility_band,
    PRECIPITATION_OPTIONS, precipitation_proxy, precipitation_option_for_forecast,
)
from core.scoring import (
    SEGMENTS, season_stage, manual_segment_score, realtime_context_from_bundle,
    segment_time_ranges, lake_now_naive,
)
from core.activity_log import (
    inventory_item_label, lure_can_take_trailer,
    FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS, RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
    FISH_SPECIES_OPTIONS, HIT_TYPE_OPTIONS, WEIGHT_SLIDER_OPTIONS, LENGTH_SLIDER_OPTIONS,
    weight_lb_for_slider_option, length_in_for_slider_option, format_weight_lb_oz,
)
from core.lures import recommend, FORAGE_OPTIONS, is_trailer_eligible
from core.ui import render_lure_block, render_square_thumbnail, inject_mobile_css
from core.storage import TripEntry, TRIP_LOG_PATH, append_trip, commit_and_push, read_all_trips, update_trip
from core.weather import lake_today, hourly_rows_for_date, estimate_water_temp_f

st.set_page_config(page_title="Spot Session - Nolin Lake", page_icon="🎯", layout="wide")
inject_mobile_css()
st.title("🎯 Spot Session")

# --- Spot picker (unchanged from before the redesign) ------------------------
# session_state is the reliable channel from the "Fish this spot now" button on the
# Lake Map page (st.switch_page doesn't consistently carry query params set in that
# same run over to this page's initial load); query_params is kept as a fallback so a
# manual page refresh or a bookmarked/shared link with ?spot_id=... still works.
spot_id = st.session_state.get("spot_session_target_id") or st.query_params.get("spot_id")
spots = get_lake_spots()
spot = next((s for s in spots if s["spot_id"] == spot_id), None) if spot_id else None

if spot is not None:
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

if spot is not None:
    current_spot_idx = next(i for i, s in enumerate(sorted_spots) if s["spot_id"] == spot["spot_id"])
    picked_idx = st.selectbox(
        "📍 Location", options=range(len(sorted_spots)), format_func=lambda i: sorted_spots[i]["name"],
        index=current_spot_idx, key=f"spot_picker_{spot['spot_id']}",
    )
    picked_spot = sorted_spots[picked_idx]
    if picked_spot["spot_id"] != spot["spot_id"]:
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

# --- Edit mode detection (arrived via Trip History's "Edit this trip") ------
edit_trip_id = st.session_state.get("spot_session_edit_trip_id") or st.query_params.get("edit_trip")
editing_trip = None
editing_cond = {}
if edit_trip_id:
    editing_trip = next((t for t in read_all_trips() if t.get("trip_id") == edit_trip_id), None)
    if editing_trip is None:
        st.session_state.pop("spot_session_edit_trip_id", None)
        st.query_params.pop("edit_trip", None)
        edit_trip_id = None
    else:
        st.session_state["spot_session_edit_trip_id"] = edit_trip_id
        st.query_params["edit_trip"] = edit_trip_id
        try:
            editing_cond = json.loads(editing_trip.get("conditions_json") or "{}")
        except json.JSONDecodeError:
            editing_cond = {}


def _exit_edit_mode():
    st.session_state.pop("spot_session_edit_trip_id", None)
    st.query_params.pop("edit_trip", None)


def _guess_segment(hour: int, now: datetime = None) -> str:
    """Best-effort guess at the time-of-day segment for a given moment
    (`now`). Prefers the real thing - `seg_ranges` (module-level, computed a
    little below from segment_time_ranges() for this session's date, the
    same real sunrise/sunset-derived windows the 7-Day Forecast page's own
    labels use) checked against `now`. One extra case those windows alone
    don't cover: `now` in the early hours after midnight but before *today's*
    Dawn actually belongs to the tail end of *last night's* Night window.
    Falls back to fixed clock-hour cutoffs when no weather bundle is
    available or `now` isn't given."""
    if seg_ranges and now is not None:
        for name in SEGMENTS:
            window = seg_ranges.get(name)
            if window and window[0] <= now < window[1]:
                return name
        dawn = seg_ranges.get("Dawn")
        if dawn and now < dawn[0]:
            return "Night"
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

# Computed from the spot alone, so it's always available regardless of mode.
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")

if st.session_state.pop(f"session_closed_banner_{spot['spot_id']}", False):
    st.success("✅ Session closed - pick lures below whenever you're ready to start a new one.")

st.session_state.setdefault(f"session_date_{spot['spot_id']}", lake_today())
if editing_trip is not None:
    try:
        _edit_date = ddate.fromisoformat(editing_trip.get("trip_date")) if editing_trip.get("trip_date") else None
    except ValueError:
        _edit_date = None
    if _edit_date:
        st.session_state[f"session_date_{spot['spot_id']}"] = _edit_date

session_date = st.date_input(
    "Session date",
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

todays_entries = [
    t for t in read_all_trips()
    if t.get("spot_id") == spot["spot_id"] and t.get("trip_date") == session_date.isoformat()
    and t.get("trip_id") != edit_trip_id
]
if todays_entries:
    summary_bits = [f"{t.get('lure_used') or 'unknown lure'} ({t.get('fish_caught') or 0} fish)" for t in todays_entries]
    st.caption(f"📋 Already logged for this spot on {session_date.isoformat()}: {', '.join(summary_bits)}")


# --- Weather-driven defaults for the consolidated conditions block ----------
def _weather_defaults(bundle, d, now) -> dict:
    """Best-effort live-forecast-driven defaults for the conditions block
    below, computed fresh every run (cheap - a plain list scan over one
    day's ~24 hourly rows). Any field it can't compute (no bundle, no
    hourly coverage for this date) is simply left out, so the conditions
    block falls back to its own hardcoded default for that one field via
    st.session_state.setdefault()."""
    defaults = {}
    if bundle is None:
        return defaults
    try:
        water_temp = estimate_water_temp_f(bundle, d, d.timetuple().tm_yday)
        if water_temp:
            defaults["water_temp_f"] = round(water_temp, 1)
    except Exception:
        pass
    rows = hourly_rows_for_date(bundle, d)
    if rows:
        nearest = min(rows, key=lambda r: abs((r["time"] - now).total_seconds()))
        if nearest.get("windspeed_10m") is not None:
            defaults["wind_band"] = wind_band(nearest["windspeed_10m"])["label"]
        if nearest.get("winddirection_10m") is not None:
            defaults["wind_direction"] = wind_direction_for_degrees(nearest["winddirection_10m"])
        if nearest.get("cloudcover") is not None:
            defaults["light_condition"] = light_condition_for_cloud_pct(nearest["cloudcover"])
        defaults["precipitation"] = precipitation_option_for_forecast(
            nearest.get("precipitation"), nearest.get("precipitation_probability"),
        )
    return defaults


def render_conditions_block(key_ns: str, weather_defaults: dict, prefill: dict = None):
    """The single consolidated "conditions" block - merges what used to be
    two separate sections ("Conditions right now" and "Conditions during
    this lure use") into one, per the angler's own redesign ask, with
    redundant fields (there used to be two separate Wind fields, and two
    separate forage-seen fields) shown just once each. Every
    weather-related field defaults from the live forecast
    (`weather_defaults`, see _weather_defaults() above) rather than a fixed
    literal, with the angler always free to override.

    `key_ns` namespaces every widget key so this same function can render a
    brand-new blank block (new session) or an edit-mode block seeded from
    an already-logged trip's data (`prefill`) without the two colliding.
    Each field is seeded via st.session_state.setdefault() - which only
    ever applies the FIRST time this exact key exists - so `prefill`/
    `weather_defaults` only ever set the initial value, never fight a
    manual override on a later rerun, the same pattern every other keyed
    widget on this page follows."""
    prefill = prefill or {}

    def _default(field, fallback):
        if field in prefill and prefill[field] not in (None, ""):
            return prefill[field]
        return weather_defaults.get(field, fallback)

    c1, c2 = st.columns(2)
    wt_key = f"{key_ns}_water_temp"
    st.session_state.setdefault(wt_key, _default("water_temp_f", 85.0))
    water_temp_f = c1.number_input(
        "Water temperature (°F)", min_value=32.0, max_value=100.0, step=0.5, key=wt_key,
    )
    sec_key = f"{key_ns}_secchi"
    st.session_state.setdefault(sec_key, _default("secchi_ft", 2.5))
    secchi_ft = c2.number_input(
        "Water visibility / Secchi depth (ft)", min_value=0.0, max_value=20.0, step=0.5,
        help="How far down you can see a light-colored object/lure. Estimate visually if you don't carry a Secchi disk.",
        key=sec_key,
    )
    temp_band = water_temp_band(water_temp_f)
    st.caption(f"Metabolic state: **{temp_band['label']}** - {temp_band['detail']}")
    vis_band = visibility_band(secchi_ft)
    st.caption(f"Visibility band: **{vis_band['label']}** ({vis_band['detail']})")

    stain_color = None
    if vis_band["label"] == "Stained":
        stain_key = f"{key_ns}_stain_color"
        st.session_state.setdefault(stain_key, _default("stain_color", STAIN_COLOR_OPTIONS[0]))
        stain_color = st.selectbox(
            "Stain color (Nolin normally runs greenish-brown, leaning brown)", STAIN_COLOR_OPTIONS,
            key=stain_key,
        )
    stirred_key = f"{key_ns}_stirred_up"
    st.session_state.setdefault(stirred_key, _default("stirred_up", False))
    stirred_up = st.checkbox(
        "Stirred up / muddy right now (recent wind or rain)",
        help="Overrides the reading above straight to Muddy, regardless of Secchi depth or stain color.",
        key=stirred_key,
    )

    c3, c4 = st.columns(2)
    wind_key = f"{key_ns}_wind_band"
    st.session_state.setdefault(wind_key, _default("wind_band", WIND_BAND_LABELS[1]))
    wind_band_choice = c3.selectbox("Wind", WIND_BAND_LABELS, help=_wind_help, key=wind_key)
    wind_dir_key = f"{key_ns}_wind_dir"
    st.session_state.setdefault(wind_dir_key, _default("wind_direction", "SW"))
    wind_direction = c4.selectbox("Wind direction", WIND_DIRECTIONS, key=wind_dir_key)

    c5, c6 = st.columns(2)
    light_key = f"{key_ns}_light_condition"
    st.session_state.setdefault(light_key, _default("light_condition", LIGHT_CONDITIONS[2]))
    light_condition = c5.selectbox(
        "Sky conditions", LIGHT_CONDITIONS,
        help="\n".join(f"{k} ({v['range']}): {v['detail']}" for k, v in LIGHT_CONDITION_INFO.items()),
        key=light_key,
    )
    precip_key = f"{key_ns}_precipitation"
    st.session_state.setdefault(precip_key, _default("precipitation", PRECIPITATION_OPTIONS[0]))
    precipitation = c6.selectbox("Precipitation", PRECIPITATION_OPTIONS, key=precip_key)

    forage_key = f"{key_ns}_forage_seen"
    st.session_state.setdefault(forage_key, _default("forage_seen", []) or [])
    forage_seen = st.multiselect("Forage seen (optional)", FORAGE_OPTIONS, key=forage_key)

    c7, c8 = st.columns(2)
    fish_act_key = f"{key_ns}_fish_activity"
    st.session_state.setdefault(fish_act_key, _default("fish_activity", "Moderate"))
    fish_activity = c7.select_slider("Fish activity", options=FISH_ACTIVITY_OPTIONS, key=fish_act_key)
    forage_act_key = f"{key_ns}_forage_activity"
    st.session_state.setdefault(forage_act_key, _default("forage_activity", "Moderate"))
    forage_activity = c8.select_slider("Forage activity", options=FORAGE_ACTIVITY_OPTIONS, key=forage_act_key)

    depth_key = f"{key_ns}_fish_depth"
    st.session_state.setdefault(depth_key, _default("fish_depth_ft", 8.0))
    fish_depth_ft = st.number_input(
        "Depth fish are showing up on electronics (ft, optional)", min_value=0.0, max_value=100.0, step=1.0,
        key=depth_key,
    )

    return {
        "water_temp_f": water_temp_f, "secchi_ft": secchi_ft, "stain_color": stain_color,
        "stirred_up": stirred_up, "wind_band": wind_band_choice, "wind_direction": wind_direction,
        "light_condition": light_condition, "precipitation": precipitation,
        "forage_seen": forage_seen, "fish_activity": fish_activity, "forage_activity": forage_activity,
        "fish_depth_ft": fish_depth_ft or None,
    }


def _compute_scoring(cond_values: dict, session_date, bundle, at_time: datetime, segment_name: str):
    """Shared scoring path for both a live setup preview (using "right now"
    as at_time/segment) and edit mode (using that trip's own logged time/
    segment) - one formula, one place, instead of the old page's separate
    "cond may or may not exist yet" branches."""
    water_clarity = resolve_water_clarity(
        cond_values["secchi_ft"], cond_values.get("stain_color"), cond_values.get("stirred_up", False),
    )
    season = season_stage(session_date.timetuple().tm_yday, cond_values["water_temp_f"])
    avg_cloud_pct = cloud_proxy_for_light_condition(cond_values["light_condition"])
    avg_wind_mph = wind_mph_for_band(cond_values["wind_band"])
    total_precip_in, max_precip_prob_pct = precipitation_proxy(cond_values["precipitation"])
    rt = realtime_context_from_bundle(bundle, segment_name, session_date, at_time=at_time)
    score_result = manual_segment_score(
        segment_name, season, avg_cloud_pct, avg_wind_mph, total_precip_in, max_precip_prob_pct,
        pressure_trend_24h=rt["pressure_trend_24h"], solunar_overlap=rt["solunar_overlap"], at_time=at_time,
        water_temp_f=cond_values["water_temp_f"], water_clarity=water_clarity,
        forage_present=bool(cond_values.get("forage_seen")),
    )
    return water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result


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


def _build_base_conditions(cond_values: dict, avg_cloud_pct, avg_wind_mph, rt, score_result, start_time, segment_name):
    """Everything about the SESSION as a whole (not any one lure) that gets
    saved into every lure's TripEntry.conditions this session produces."""
    d = dict(cond_values)
    d.update({
        "avg_cloud_pct": avg_cloud_pct,
        "avg_wind_mph": avg_wind_mph,
        "pressure_trend_24h": rt["pressure_trend_24h"] if rt else None,
        "moon_near_new_full": score_result.moon.is_new_or_full_window if score_result else None,
        "moon_phase": score_result.moon.name if score_result else None,
        "start_time": start_time.isoformat() if start_time else None,
        "segment_name": segment_name,
        # Trip History's FIELD_SPECS still reads a separate "Wind (logged)"
        # column under its old name - both that and "Wind" above now just
        # show this same single reading, since the redesign merged what
        # used to be two separate Wind fields into one.
        "wind_band_logged": cond_values.get("wind_band"),
    })
    return d


LURE_PICKER_COLS = 4
LURE_PICKER_THUMBNAIL_PX = 90


def _visual_lure_picker(inventory_items: list, key_prefix: str, empty_message: str = None):
    """Searchable, single-select image-card picker over the tackle
    inventory (edit mode's "Lure used"/"Trailer" pickers). Returns the
    selected inventory row, or None if nothing's picked."""
    selected_key = f"{key_prefix}_selected_id"
    if not inventory_items:
        st.caption(
            empty_message or
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
                        is_selected = item.get("item_id") == st.session_state.get(selected_key)
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


# --- Multi-lure selection for a NEW session ----------------------------------
def _pending_lures_key(spot_id: str, seq: int) -> str:
    return f"pending_session_lures_{spot_id}_{seq}"


def _add_lure_to_pending(spot_id: str, seq: int, lure: dict):
    key = _pending_lures_key(spot_id, seq)
    pending = st.session_state.setdefault(key, [])
    if lure.get("item_id") is not None:
        if any(p.get("item_id") == lure["item_id"] for p in pending):
            return
    else:
        # Manual (not-in-inventory) entries have no item_id - dedupe by
        # label instead, so typing the exact same name twice doesn't add it
        # twice.
        if any(p.get("item_id") is None and p.get("label") == lure.get("label") for p in pending):
            return
    pending.append(lure)
    st.session_state[key] = pending


def _remove_lure_from_pending(spot_id: str, seq: int, index: int):
    key = _pending_lures_key(spot_id, seq)
    pending = st.session_state.get(key, [])
    if 0 <= index < len(pending):
        pending.pop(index)
        st.session_state[key] = pending


def _multi_lure_picker(inventory_items: list, key_prefix: str, spot_id: str, seq: int):
    """Multi-select sibling of _visual_lure_picker - same searchable card
    grid, but each card toggles membership in the running "lures for this
    session" list (see _pending_lures_key) instead of picking exactly one."""
    if not inventory_items:
        st.caption("No lures in your tackle box yet - add some on the Lure Inventory page.")
        return
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
    if not filtered:
        st.caption("No matches for that search.")
        return
    pending_ids = {p.get("item_id") for p in st.session_state.get(_pending_lures_key(spot_id, seq), [])}
    for row_start in range(0, len(filtered), LURE_PICKER_COLS):
        row_items = filtered[row_start:row_start + LURE_PICKER_COLS]
        cols = st.columns(LURE_PICKER_COLS)
        for col, item in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    if not render_square_thumbnail(item, size_px=LURE_PICKER_THUMBNAIL_PX):
                        st.caption("No photo")
                    st.caption(f"**{item.get('brand', '')}**  \n{item.get('description', '')}"[:90])
                    is_added = item.get("item_id") in pending_ids
                    if st.button(
                        "✓ Added" if is_added else "+ Add", key=f"{key_prefix}_toggle_{item['item_id']}",
                        disabled=is_added, width='stretch',
                    ):
                        _add_lure_to_pending(spot_id, seq, {
                            "item_id": item["item_id"], "label": inventory_item_label(item),
                            "category": item.get("category"),
                        })
                        st.rerun()


def _render_recommendation_with_quick_add(rec, spot_id: str, seq: int, key_prefix: str):
    """Displays the lure recommendation (reusing core.ui.render_lure_block
    unchanged, so this stays in sync with the 7-Day Forecast page's own
    display) with a "+ Add to session" button under each color-matched
    owned item, so a suggested lure can be added to this session with one
    click instead of having to go find it again in the tackle-box picker
    below."""
    pending_ids = {p.get("item_id") for p in st.session_state.get(_pending_lures_key(spot_id, seq), [])}
    for label, blocks in (("First choice", rec.first_choice), ("Second choice", rec.second_choice)):
        if not blocks:
            continue
        st.markdown(f"**{label}**")
        for block in blocks:
            render_lure_block(block)
            for item in block.owned_items:
                item_id = item.get("item_id")
                if not item_id:
                    continue
                is_added = item_id in pending_ids
                btn_label = "✓ Added to session" if is_added else f"+ Add {item.get('brand', '')} - {item.get('description', '')}"[:60]
                if st.button(btn_label, key=f"{key_prefix}_{block.key}_{item_id}", disabled=is_added):
                    _add_lure_to_pending(spot_id, seq, {
                        "item_id": item_id, "label": inventory_item_label(item), "category": block.key,
                    })
                    st.rerun()
    if rec.rationale:
        st.caption(" · ".join(rec.rationale))


# --- Per-fish entry (used by both the active-session dialog and edit mode) --
def _new_fish_from_form(species_label, species_other, weight_option, length_option, hit_types, retrieve_style, retrieve_speed) -> dict:
    species_final = (
        species_other.strip() if (species_label == "Other (type in species)" and species_other.strip())
        else species_label
    )
    return {
        "species": species_final,
        "species_other": species_other or None,
        "count": 1,
        "weight_lb": weight_lb_for_slider_option(weight_option),
        "length_in": length_in_for_slider_option(length_option),
        "hit_types": hit_types,
        "retrieve_speed": retrieve_speed,
        "retrieve_style": retrieve_style,
    }


def _fish_summary_bits(fish: dict) -> list:
    count = fish.get("count") or 1
    bits = [f"{count} x {fish['species']}" if count > 1 else (fish.get("species") or "Unknown species")]
    if fish.get("weight_lb"):
        bits.append(format_weight_lb_oz(fish["weight_lb"]))
    if fish.get("length_in"):
        bits.append(f"{fish['length_in']:g} in")
    if fish.get("hit_types"):
        bits.append(", ".join(fish["hit_types"]))
    presentation = " / ".join(x for x in [fish.get("retrieve_speed"), fish.get("retrieve_style")] if x)
    if presentation:
        bits.append(presentation)
    return bits


def _push_or_toast(paths, commit_message, local_message):
    token = github_token()
    if token:
        ok, msg = commit_and_push(paths, token, repo_slug(), commit_message)
        st.toast(msg, icon="✅" if ok else "⚠️")
    else:
        st.toast(local_message, icon="ℹ️")


def _record_fish(spot_id: str, lure_index: int, fish_record: dict):
    """Appends one fish to the given lure's running catch list, immediately
    saving that lure's TripEntry (via update_trip) and pushing - per the
    angler's own ask, each catch is saved right away rather than batched
    until the session ends."""
    active_key = f"active_session_{spot_id}"
    active = st.session_state.get(active_key)
    if active is None or lure_index >= len(active["lures"]):
        return
    lure = active["lures"][lure_index]
    lure["fish"].append(fish_record)
    entry_kwargs = dict(lure["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["fish"] = lure["fish"]
    entry_kwargs["conditions"] = conditions
    fish_weights = [f["weight_lb"] for f in lure["fish"] if f.get("weight_lb")]
    entry_kwargs["fish_caught"] = sum((f.get("count") or 1) for f in lure["fish"])
    entry_kwargs["biggest_fish_lb"] = max(fish_weights) if fish_weights else None
    entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
    update_trip(entry)
    lure["entry_kwargs"] = entry_kwargs
    active["lures"][lure_index] = lure
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Log a fish on {lure['label']} ({active.get('spot_name', spot_id)})",
        "Fish logged locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


def _remove_fish(spot_id: str, lure_index: int, fish_index: int):
    active_key = f"active_session_{spot_id}"
    active = st.session_state.get(active_key)
    if active is None or lure_index >= len(active["lures"]):
        return
    lure = active["lures"][lure_index]
    if not (0 <= fish_index < len(lure["fish"])):
        return
    lure["fish"].pop(fish_index)
    entry_kwargs = dict(lure["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["fish"] = lure["fish"]
    entry_kwargs["conditions"] = conditions
    fish_weights = [f["weight_lb"] for f in lure["fish"] if f.get("weight_lb")]
    entry_kwargs["fish_caught"] = sum((f.get("count") or 1) for f in lure["fish"])
    entry_kwargs["biggest_fish_lb"] = max(fish_weights) if fish_weights else None
    entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
    update_trip(entry)
    lure["entry_kwargs"] = entry_kwargs
    active["lures"][lure_index] = lure
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Remove a fish from {lure['label']} ({active.get('spot_name', spot_id)})",
        "Removed locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


@st.dialog("Log a fish")
def _fish_entry_dialog(spot_id: str, lure_index: int):
    active = st.session_state.get(f"active_session_{spot_id}")
    if active is None or lure_index >= len(active["lures"]):
        st.error("This session has ended.")
        return
    lure = active["lures"][lure_index]
    st.markdown(f"**{lure['label']}**")

    dseq_key = f"fish_dialog_seq_{spot_id}_{lure_index}"
    st.session_state.setdefault(dseq_key, 0)
    dseq = st.session_state[dseq_key]

    species_idx = st.selectbox(
        "Species", options=list(range(len(FISH_SPECIES_OPTIONS))), format_func=lambda j: FISH_SPECIES_OPTIONS[j],
        key=f"fish_species_{spot_id}_{lure_index}_{dseq}",
    )
    species_label = FISH_SPECIES_OPTIONS[species_idx]
    species_other = ""
    if species_label == "Other (type in species)":
        species_other = st.text_input("Species (type it in)", key=f"fish_species_other_{spot_id}_{lure_index}_{dseq}")

    weight_option = st.select_slider("Weight", options=WEIGHT_SLIDER_OPTIONS, key=f"fish_weight_{spot_id}_{lure_index}_{dseq}")
    length_option = st.select_slider("Length", options=LENGTH_SLIDER_OPTIONS, key=f"fish_length_{spot_id}_{lure_index}_{dseq}")
    hit_types = st.multiselect("Type of hit", HIT_TYPE_OPTIONS, key=f"fish_hit_types_{spot_id}_{lure_index}_{dseq}")

    rc1, rc2 = st.columns(2)
    retrieve_style = rc1.selectbox("Retrieve style", RETRIEVE_STYLE_OPTIONS, key=f"fish_retrieve_style_{spot_id}_{lure_index}_{dseq}")
    retrieve_speed = rc2.selectbox("Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=1, key=f"fish_retrieve_speed_{spot_id}_{lure_index}_{dseq}")

    fc1, fc2 = st.columns(2)
    if fc1.button("✅ Record", type="primary", width='stretch', key=f"fish_record_{spot_id}_{lure_index}_{dseq}"):
        fish_record = _new_fish_from_form(
            species_label, species_other, weight_option, length_option, hit_types, retrieve_style, retrieve_speed,
        )
        _record_fish(spot_id, lure_index, fish_record)
        st.session_state[dseq_key] = dseq + 1
        st.rerun()
    if fc2.button("Cancel", width='stretch', key=f"fish_cancel_{spot_id}_{lure_index}_{dseq}"):
        st.rerun()


def _end_session(spot_id: str):
    active_key = f"active_session_{spot_id}"
    active = st.session_state.get(active_key)
    if active is None:
        return
    end_time = lake_now_naive().time()
    for lure in active["lures"]:
        entry_kwargs = dict(lure["entry_kwargs"])
        conditions = dict(entry_kwargs["conditions"])
        conditions["lure_end_time"] = end_time.isoformat()
        entry_kwargs["conditions"] = conditions
        entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
        update_trip(entry)
    _push_or_toast(
        [TRIP_LOG_PATH], f"End spot session ({active.get('spot_name', spot_id)})",
        "Session ended locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )
    st.session_state.pop(active_key, None)
    st.session_state[f"session_closed_banner_{spot_id}"] = True


# ==============================================================================
# EDIT MODE - correcting one already-logged trip
# ==============================================================================
if editing_trip is not None:
    st.divider()
    st.header("Conditions")

    def _find_inventory_item_by_label(label, items):
        if not label:
            return None
        return next((it for it in items if inventory_item_label(it) == label), None)

    def _parse_iso_time(s):
        try:
            return dtime.fromisoformat(s) if s else None
        except ValueError:
            return None

    if editing_cond.get("wind_band_logged") in WIND_BAND_LABELS:
        _prefill_wind_band = editing_cond["wind_band_logged"]
    elif editing_cond.get("wind_band") in WIND_BAND_LABELS:
        _prefill_wind_band = editing_cond["wind_band"]
    elif isinstance(editing_cond.get("wind_speed_mph"), (int, float)):
        _prefill_wind_band = wind_band(editing_cond["wind_speed_mph"])["label"]
    else:
        _prefill_wind_band = None

    edit_prefill = {
        "water_temp_f": editing_cond.get("water_temp_f"),
        "secchi_ft": editing_cond.get("secchi_ft"),
        "stain_color": editing_cond.get("stain_color") if editing_cond.get("stain_color") in STAIN_COLOR_OPTIONS else None,
        "stirred_up": bool(editing_cond.get("stirred_up", False)),
        "wind_band": _prefill_wind_band,
        "wind_direction": editing_cond.get("wind_direction") if editing_cond.get("wind_direction") in WIND_DIRECTIONS else None,
        "light_condition": editing_cond.get("light_condition") if editing_cond.get("light_condition") in LIGHT_CONDITIONS else None,
        "precipitation": editing_cond.get("precipitation") if editing_cond.get("precipitation") in PRECIPITATION_OPTIONS else None,
        "forage_seen": editing_cond.get("forage_seen") or editing_cond.get("forage_type_seen") or [],
        "fish_activity": editing_cond.get("fish_activity"),
        "forage_activity": editing_cond.get("forage_activity"),
        "fish_depth_ft": editing_cond.get("fish_depth_ft"),
    }
    edit_key_ns = f"editcond_{edit_trip_id}_{spot['spot_id']}"
    cond_values = render_conditions_block(edit_key_ns, weather_defaults={}, prefill=edit_prefill)

    tc1, tc2 = st.columns(2)
    _edit_start_key = f"{edit_key_ns}_start_time"
    st.session_state.setdefault(_edit_start_key, _parse_iso_time(editing_cond.get("start_time")) or lake_now_naive().time())
    edit_start_time = tc1.time_input("Session start time", key=_edit_start_key)
    _edit_segment_default = editing_trip.get("segment") if editing_trip.get("segment") in SEGMENTS else _guess_segment(edit_start_time.hour)
    _edit_segment_key = f"{edit_key_ns}_segment"
    st.session_state.setdefault(_edit_segment_key, _edit_segment_default)
    edit_segment_name = tc2.selectbox("Time window", SEGMENTS, format_func=_segment_option_label, key=_edit_segment_key)

    edit_at_time = datetime.combine(session_date, edit_start_time)
    water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
        cond_values, session_date, bundle, edit_at_time, edit_segment_name,
    )
    st.caption(f"Recomputed score for this entry: **{score_result.score}/10** ({season.replace('_', ' ').title()}, {water_clarity} water)")

    st.divider()
    st.markdown("#### Lure used")
    inventory_items = get_inventory()
    _edit_lure_prefix = f"editlure_{edit_trip_id}_{spot['spot_id']}"
    _matched_lure = _find_inventory_item_by_label(editing_trip.get("lure_used"), inventory_items)
    if _matched_lure:
        st.session_state.setdefault(f"{_edit_lure_prefix}_selected_id", _matched_lure["item_id"])
    selected_lure_item = _visual_lure_picker(inventory_items, key_prefix=_edit_lure_prefix)
    lure_used = inventory_item_label(selected_lure_item) if selected_lure_item else (editing_trip.get("lure_used") or "")
    color_used = selected_lure_item.get("description", "") if selected_lure_item else (editing_trip.get("color_used") or "")

    use_trailer = False
    if lure_can_take_trailer(selected_lure_item):
        _use_trailer_key = f"edit_use_trailer_{edit_trip_id}_{spot['spot_id']}"
        st.session_state.setdefault(_use_trailer_key, bool(editing_cond.get("trailer_used")))
        use_trailer = st.checkbox("Used a trailer", key=_use_trailer_key)

    trailer_name, trailer_color, trailer_category = "", "", None
    selected_trailer_item = None
    if use_trailer:
        st.markdown("**Trailer**")
        trailer_items = [it for it in inventory_items if is_trailer_eligible(it)]
        _edit_trailer_prefix = f"edittrailer_{edit_trip_id}_{spot['spot_id']}"
        _matched_trailer = _find_inventory_item_by_label(editing_cond.get("trailer_name"), inventory_items)
        if _matched_trailer:
            st.session_state.setdefault(f"{_edit_trailer_prefix}_selected_id", _matched_trailer["item_id"])
        selected_trailer_item = _visual_lure_picker(
            trailer_items, key_prefix=_edit_trailer_prefix,
            empty_message="No trailer-style baits found in your tackle box - add one on the Lure Inventory page, or type this one in below.",
        )
        if selected_trailer_item is None:
            _trailer_name_key = f"edit_trailer_name_{edit_trip_id}_{spot['spot_id']}"
            st.session_state.setdefault(_trailer_name_key, editing_cond.get("trailer_name") or "")
            trailer_name = st.text_input("Trailer name", key=_trailer_name_key)
        else:
            trailer_name = inventory_item_label(selected_trailer_item)
            trailer_category = selected_trailer_item.get("category")
        _trailer_color_key = f"edit_trailer_color_{edit_trip_id}_{spot['spot_id']}"
        st.session_state.setdefault(
            _trailer_color_key,
            selected_trailer_item.get("description", "") if selected_trailer_item else (editing_cond.get("trailer_color") or ""),
        )
        trailer_color = st.text_input("Trailer color", key=_trailer_color_key)

    _notes_key = f"edit_notes_{edit_trip_id}_{spot['spot_id']}"
    st.session_state.setdefault(_notes_key, editing_trip.get("notes") or "")
    log_notes = st.text_area("Notes", key=_notes_key)

    st.divider()
    st.markdown("#### Fish caught")
    _edit_fish_key = f"edit_fish_list_{edit_trip_id}_{spot['spot_id']}"
    _edit_fish_list = editing_cond.get("fish")
    st.session_state.setdefault(_edit_fish_key, list(_edit_fish_list) if isinstance(_edit_fish_list, list) else [])
    edit_fish_records = st.session_state[_edit_fish_key]

    if edit_fish_records:
        for i, fish in enumerate(edit_fish_records):
            frow1, frow2 = st.columns([5, 1])
            frow1.write(f"🐟 Fish #{i + 1}: {', '.join(str(b) for b in _fish_summary_bits(fish))}")
            if frow2.button("Remove", key=f"edit_remove_fish_{edit_trip_id}_{spot['spot_id']}_{i}"):
                edit_fish_records.pop(i)
                st.session_state[_edit_fish_key] = edit_fish_records
                st.rerun()
    else:
        st.caption("No fish logged yet for this trip.")

    _edit_fish_seq_key = f"edit_fish_seq_{edit_trip_id}_{spot['spot_id']}"
    st.session_state.setdefault(_edit_fish_seq_key, 0)
    _efseq = st.session_state[_edit_fish_seq_key]
    with st.container(border=True):
        st.markdown("**Add a fish**")
        species_idx = st.selectbox(
            "Species", options=list(range(len(FISH_SPECIES_OPTIONS))), format_func=lambda j: FISH_SPECIES_OPTIONS[j],
            key=f"edit_new_fish_species_{edit_trip_id}_{spot['spot_id']}_{_efseq}",
        )
        species_label = FISH_SPECIES_OPTIONS[species_idx]
        species_other = ""
        if species_label == "Other (type in species)":
            species_other = st.text_input("Species (type it in)", key=f"edit_new_fish_species_other_{edit_trip_id}_{spot['spot_id']}_{_efseq}")
        weight_option = st.select_slider("Weight", options=WEIGHT_SLIDER_OPTIONS, key=f"edit_new_fish_weight_{edit_trip_id}_{spot['spot_id']}_{_efseq}")
        length_option = st.select_slider("Length", options=LENGTH_SLIDER_OPTIONS, key=f"edit_new_fish_length_{edit_trip_id}_{spot['spot_id']}_{_efseq}")
        hit_types = st.multiselect("Type of hit", HIT_TYPE_OPTIONS, key=f"edit_new_fish_hit_types_{edit_trip_id}_{spot['spot_id']}_{_efseq}")
        rc1, rc2 = st.columns(2)
        retrieve_style = rc1.selectbox("Retrieve style", RETRIEVE_STYLE_OPTIONS, key=f"edit_new_fish_style_{edit_trip_id}_{spot['spot_id']}_{_efseq}")
        retrieve_speed = rc2.selectbox("Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=1, key=f"edit_new_fish_speed_{edit_trip_id}_{spot['spot_id']}_{_efseq}")
        if st.button("Add fish", key=f"edit_new_fish_add_{edit_trip_id}_{spot['spot_id']}_{_efseq}", type="primary", width='stretch'):
            edit_fish_records.append(_new_fish_from_form(
                species_label, species_other, weight_option, length_option, hit_types, retrieve_style, retrieve_speed,
            ))
            st.session_state[_edit_fish_key] = edit_fish_records
            st.session_state[_edit_fish_seq_key] = _efseq + 1
            st.rerun()

    st.divider()
    save_col, cancel_col = st.columns(2)
    if save_col.button("💾 Save changes", key=f"save_edit_{spot['spot_id']}", type="primary", width='stretch'):
        fish_weights = [f["weight_lb"] for f in edit_fish_records if f.get("weight_lb")]
        conditions = _build_base_conditions(cond_values, avg_cloud_pct, avg_wind_mph, rt, score_result, edit_start_time, edit_segment_name)
        conditions.update({
            "lure_category": selected_lure_item.get("category") if selected_lure_item else None,
            "trailer_used": use_trailer,
            "trailer_name": trailer_name or None,
            "trailer_color": trailer_color or None,
            "trailer_category": trailer_category,
            "lure_start_time": edit_start_time.isoformat() if edit_start_time else None,
            "lure_end_time": editing_cond.get("lure_end_time"),
            "fish": edit_fish_records,
            "source": "spot_session",
        })
        entry = TripEntry(
            trip_id=edit_trip_id,
            logged_at=editing_trip.get("logged_at") or datetime.utcnow().isoformat(),
            trip_date=session_date.isoformat(),
            segment=edit_segment_name,
            spot_id=spot["spot_id"],
            spot_name=spot["name"],
            structure_type=structure_type,
            water_clarity=water_clarity,
            lure_used=lure_used,
            color_used=color_used,
            technique_used="",
            fish_caught=sum((f.get("count") or 1) for f in edit_fish_records),
            biggest_fish_lb=max(fish_weights) if fish_weights else None,
            predicted_score=score_result.score,
            conditions=conditions,
            notes=log_notes,
        )
        update_trip(entry)
        _push_or_toast(
            [TRIP_LOG_PATH], f"Update trip {entry.trip_id} from spot session edit ({spot['name']})",
            "Trip updated locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
        )
        _exit_edit_mode()
        st.rerun()
    if cancel_col.button("Cancel edit", key=f"cancel_edit_bottom_{spot['spot_id']}", width='stretch'):
        _exit_edit_mode()
        st.rerun()

    st.stop()


# ==============================================================================
# NORMAL MODE - either a session is already in progress at this spot, or the
# angler is setting one up (conditions -> lure selection -> Start Session).
# ==============================================================================
active_session_key = f"active_session_{spot['spot_id']}"
active = st.session_state.get(active_session_key)

if active is not None:
    st.divider()
    st.header("🎣 Session in progress")
    score_bit = f" · predicted score {active['predicted_score']}/10" if active.get("predicted_score") is not None else ""
    st.caption(
        f"Started {active['start_time']} · {active['segment_name']} · {active['water_clarity']} water{score_bit}"
    )
    st.caption("Tap a lure below every time you land a fish on it.")

    for i, lure in enumerate(active["lures"]):
        fish_count = sum((f.get("count") or 1) for f in lure["fish"])
        label = f"🎣 {lure['label']}" + (f" ({fish_count} caught)" if fish_count else "")
        if st.button(label, key=f"open_fish_dialog_{spot['spot_id']}_{i}", width='stretch'):
            _fish_entry_dialog(spot["spot_id"], i)
        if lure["fish"]:
            with st.expander(f"Fish caught on {lure['label']} ({fish_count})", expanded=False):
                for fi, fish in enumerate(lure["fish"]):
                    frow1, frow2 = st.columns([5, 1])
                    frow1.write(f"- {', '.join(str(b) for b in _fish_summary_bits(fish))}")
                    if frow2.button("Remove", key=f"remove_active_fish_{spot['spot_id']}_{i}_{fi}"):
                        _remove_fish(spot["spot_id"], i, fi)
                        st.rerun()

    st.divider()
    if st.button("⏹ End Session", key=f"end_session_{spot['spot_id']}", type="primary", width='stretch'):
        _end_session(spot["spot_id"])
        st.rerun()

else:
    session_build_seq_key = f"session_build_seq_{spot['spot_id']}"
    st.session_state.setdefault(session_build_seq_key, 0)
    session_build_seq = st.session_state[session_build_seq_key]

    st.divider()
    st.header("Conditions")
    st.caption(
        "Enter what you're actually seeing at the water - weather-related fields below default from the "
        "live forecast, override any of them if what you see is different. Once you've picked your "
        "lure(s) below, Start Session locks in the exact time and this whole snapshot."
    )
    weather_defaults = _weather_defaults(bundle, session_date, lake_now_naive())
    cond_key_ns = f"cond_{spot['spot_id']}_{session_build_seq}"
    cond_values = render_conditions_block(cond_key_ns, weather_defaults)

    _preview_now = lake_now_naive()
    _preview_segment = _guess_segment(_preview_now.hour, _preview_now)
    water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
        cond_values, session_date, bundle, _preview_now, _preview_segment,
    )

    st.divider()
    with st.expander("Suggestions for right now", expanded=True):
        m1, m2 = st.columns([1, 2])
        m1.metric(
            f"{_preview_segment} activity score", f"{score_result.score}/10",
            help=_score_breakdown_help(score_result.breakdown, score_result.score),
        )
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
            st.caption("Pressure trend and solunar timing aren't factored into the score above - no weather forecast data was available just now.")

        inventory_items = get_inventory()
        rec = recommend(
            season, cond_values["water_temp_f"], _preview_segment, rt["pressure_trend_24h"],
            structure_type=structure_type, water_clarity=water_clarity,
            fish_depth_ft=cond_values.get("fish_depth_ft"), forage=cond_values.get("forage_seen"),
            inventory=inventory_items,
        )
        _render_recommendation_with_quick_add(rec, spot["spot_id"], session_build_seq, key_prefix=f"quickadd_{spot['spot_id']}_{session_build_seq}")

    st.divider()
    st.markdown("#### Lures for this session")
    pending_lures = st.session_state.get(_pending_lures_key(spot["spot_id"], session_build_seq), [])
    if pending_lures:
        for i, lure in enumerate(pending_lures):
            lcol1, lcol2 = st.columns([5, 1])
            lcol1.write(f"🎣 {lure['label']}")
            if lcol2.button("Remove", key=f"remove_pending_lure_{spot['spot_id']}_{session_build_seq}_{i}"):
                _remove_lure_from_pending(spot["spot_id"], session_build_seq, i)
                st.rerun()
    else:
        st.caption("No lures selected yet - use the suggestions above or the tackle box below.")

    with st.expander("➕ Add from tackle box"):
        _multi_lure_picker(
            inventory_items, key_prefix=f"session_lure_picker_{spot['spot_id']}_{session_build_seq}",
            spot_id=spot["spot_id"], seq=session_build_seq,
        )
        st.markdown("**Not in your inventory?**")
        manual_seq_key = f"manual_lure_seq_{spot['spot_id']}_{session_build_seq}"
        st.session_state.setdefault(manual_seq_key, 0)
        manual_seq = st.session_state[manual_seq_key]
        manual_col1, manual_col2 = st.columns([4, 1])
        manual_name = manual_col1.text_input(
            "Lure name", key=f"manual_lure_name_{spot['spot_id']}_{session_build_seq}_{manual_seq}",
            label_visibility="collapsed", placeholder="Type a lure name to add it manually",
        )
        if manual_col2.button("+ Add", key=f"manual_lure_add_{spot['spot_id']}_{session_build_seq}_{manual_seq}"):
            if manual_name.strip():
                _add_lure_to_pending(spot["spot_id"], session_build_seq, {
                    "item_id": None, "label": manual_name.strip(), "category": None,
                })
                st.session_state[manual_seq_key] = manual_seq + 1
                st.rerun()

    st.divider()
    if st.button(
        "▶ Start Session", type="primary", width='stretch', disabled=not pending_lures,
        key=f"start_session_{spot['spot_id']}_{session_build_seq}",
    ):
        start_time = lake_now_naive().time()
        at_time = datetime.combine(session_date, start_time)
        segment_name = _guess_segment(at_time.hour, at_time)
        water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
            cond_values, session_date, bundle, at_time, segment_name,
        )
        base_conditions = _build_base_conditions(cond_values, avg_cloud_pct, avg_wind_mph, rt, score_result, start_time, segment_name)

        active_lures = []
        for lure in pending_lures:
            lure_conditions = dict(base_conditions)
            lure_conditions.update({
                "lure_category": lure.get("category"),
                "trailer_used": False,
                "trailer_name": None,
                "trailer_color": None,
                "trailer_category": None,
                "lure_start_time": start_time.isoformat(),
                "lure_end_time": None,
                "fish": [],
                "source": "spot_session",
            })
            entry_kwargs = dict(
                trip_date=session_date.isoformat(),
                segment=segment_name,
                spot_id=spot["spot_id"],
                spot_name=spot["name"],
                structure_type=structure_type,
                water_clarity=water_clarity,
                lure_used=lure["label"],
                color_used="",
                technique_used="",
                fish_caught=0,
                biggest_fish_lb=None,
                predicted_score=score_result.score,
                conditions=lure_conditions,
                notes="",
            )
            entry = TripEntry(**entry_kwargs)
            append_trip(entry)
            active_lures.append({
                "trip_id": entry.trip_id, "logged_at": entry.logged_at, "label": lure["label"],
                "entry_kwargs": entry_kwargs, "fish": [],
            })

        st.session_state[active_session_key] = {
            "spot_name": spot["name"],
            "session_date": session_date.isoformat(),
            "start_time": start_time.isoformat(),
            "segment_name": segment_name,
            "water_clarity": water_clarity,
            "predicted_score": score_result.score,
            "lures": active_lures,
        }
        st.session_state[session_build_seq_key] = session_build_seq + 1
        _push_or_toast(
            [TRIP_LOG_PATH], f"Start spot session ({spot['name']}, {len(active_lures)} lure(s))",
            "Session started locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
        )
        st.rerun()
    if not pending_lures:
        st.caption("Select at least one lure above before starting the session.")
