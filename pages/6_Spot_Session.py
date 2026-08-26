import json
import re
import uuid
from datetime import datetime, time as dtime

import streamlit as st

from core.appstate import (
    get_lake_spots, get_inventory, get_weather_bundle, get_anglers, get_trip_history, github_token, repo_slug,
)
from core.anglers import add_angler, ANGLERS_PATH, OTHER_LABEL as ANGLER_OTHER_LABEL
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
    nearest_weight_slider_option, nearest_length_slider_option,
)
from core.lures import recommend, FORAGE_OPTIONS, is_trailer_eligible
from core.ui import render_lure_block, render_lure_recommendation, render_square_thumbnail, inject_mobile_css
from core.storage import (
    TripEntry, TRIP_LOG_PATH, append_trip, commit_and_push_data, push_pending_data,
    read_all_trips, update_trip, delete_trip, parse_conditions,
)
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

if st.button("← Back to Lake Map"):
    st.switch_page("pages/2_Lake_Map.py")

# --- Structure type + session-lookup helpers, needed before the angler
# picker below can warn about (and exclude) anglers who already have a
# session going here right now (punch-list #59) - moved up from where they
# used to live, right next to where "NORMAL MODE" further down uses them
# for the real session-in-progress view. Nothing about their behavior
# changed by moving them.
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")


def _angler_session_slug(angler: str) -> str:
    """Stable, session_state-key-safe token for an angler name, so it can
    be embedded in _active_session_key() below. Falls back to a fixed
    sentinel for a blank/unset angler rather than "" - keeps the key
    readable in a stale session_state dump and avoids a blank name and a
    literally-blank-string name colliding by coincidence."""
    name = (angler or "").strip()
    if not name:
        return "unassigned"
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "unassigned"


def _active_session_key(spot_id: str, angler: str) -> str:
    return f"active_session_{spot_id}_{_angler_session_slug(angler)}"


# Punch-list #29: every lure/fish already lands in data/trip_log.csv the
# instant it happens (see _record_fish()/_add_lure_to_active_session()/the
# Start Session handler below - each calls append_trip()/update_trip() and
# pushes immediately, not batched until End Session), but which lures were
# still "active" and tappable to log a fish lived ONLY in st.session_state -
# in-memory on the server, tied to one browser session. Spotty cell coverage
# (a dropped WebSocket), a phone locking mid-session, or the server itself
# restarting all wipe st.session_state, and the angler's own report was that
# reconnecting after one of these made an in-progress session look like it
# had never started - conditions/spot still there (those ride along via
# query_params, entry 34), but the lure buttons were gone and it dropped
# back to the pre-session builder. Nothing was actually lost on disk; the
# fix is to rebuild the "session in progress" view from what's already
# there instead of losing track of it. True offline operation isn't
# achievable here - every interaction in this app is a live round trip to
# the Python server, there's no offline-capable client code - so this is
# the practical fix within that constraint: reconnecting picks up exactly
# where the last successful save left off, rather than losing the session.
_PER_LURE_CONDITION_KEYS = {
    "lure_category", "trailer_used", "trailer_name", "trailer_color",
    "trailer_category", "lure_start_time", "lure_end_time", "fish", "source",
}


def _open_session_rows(spot_id: str, session_date_iso: str, trips_today: list, angler: str) -> list:
    """Groups today's spot_session-sourced rows at this spot by their
    shared session conditions["start_time"] (the same value every lure in
    one session carries - captured once by Start Session, reused unchanged
    by _add_lure_to_active_session() for every lure added after, so it's a
    reliable session-grouping key even though no explicit "session id" is
    stored anywhere), then returns the rows for whichever group still has
    at least one lure without a lure_end_time yet (i.e. genuinely still in
    progress - a properly "⏹ End Session"-ed group has every row's
    lure_end_time stamped, retired or not) AND whose own conditions["angler"]
    matches `angler` (punch-list #47) - so reconnecting always picks back up
    THIS angler's own open session, never someone else's still-in-progress
    one, even if theirs started more recently. Returns [] if nothing's open
    for this angler - either nothing's been logged here today under this
    name, or their own session logged here today has already been ended.
    If, unusually, this angler has more than one group open at once (this
    page has no flow that starts a second session before ending the first
    under the same name, but a hand-edited CSV or an old bug could produce
    one), the most recently started of THEIR groups wins - the others are
    simply left alone rather than merged or discarded."""
    groups = {}
    for t in trips_today:
        if t.get("spot_id") != spot_id or t.get("trip_date") != session_date_iso:
            continue
        cond = parse_conditions(t)
        if cond.get("source") != "spot_session":
            continue
        key = cond.get("start_time")
        if not key:
            continue
        groups.setdefault(key, []).append((t, cond))
    my_slug = _angler_session_slug(angler)
    open_groups = {
        k: rows for k, rows in groups.items()
        if any(not c.get("lure_end_time") for _, c in rows)
        and _angler_session_slug(rows[0][1].get("angler")) == my_slug
    }
    if not open_groups:
        return []
    latest_key = max(open_groups, key=lambda k: min(t.get("logged_at") or "" for t, _ in open_groups[k]))
    return sorted(open_groups[latest_key], key=lambda tc: tc[0].get("logged_at") or "")


def _anglers_with_open_session(spot_id: str, session_date_iso: str, trips_today: list) -> list:
    """Distinct angler names (first-seen order) who have their own still-
    open spot_session at this spot on session_date_iso - every one of them,
    unfiltered. Punch-list #59: the angler picker below uses this directly
    to keep anyone from silently picking (or defaulting to) a name that's
    already mid-session here, and to offer a choice of whose session to
    watch when more than one is live. _other_anglers_with_open_session()
    just below is a thin wrapper that excludes one name from this same
    list, for the in-session "so-and-so also has a session going" caption."""
    groups = {}
    for t in trips_today:
        if t.get("spot_id") != spot_id or t.get("trip_date") != session_date_iso:
            continue
        cond = parse_conditions(t)
        if cond.get("source") != "spot_session":
            continue
        key = cond.get("start_time")
        if not key:
            continue
        groups.setdefault(key, []).append(cond)
    seen_slugs = set()
    anglers = []
    for conds in groups.values():
        if not any(not c.get("lure_end_time") for c in conds):
            continue
        angler_name = (conds[0].get("angler") or "").strip()
        slug = _angler_session_slug(angler_name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        anglers.append(angler_name or "an unnamed angler")
    return anglers


def _other_anglers_with_open_session(spot_id: str, session_date_iso: str, trips_today: list, my_angler: str) -> list:
    """_anglers_with_open_session() above, minus my_angler - punch-list #47,
    used purely to reassure whoever's looking at this page that starting/
    ending/canceling their own session never touches anyone else's (each
    angler's session is independently tracked - see
    _active_session_key()/_open_session_rows() above)."""
    my_slug = _angler_session_slug(my_angler)
    return [
        a for a in _anglers_with_open_session(spot_id, session_date_iso, trips_today)
        if _angler_session_slug(a) != my_slug
    ]


def _reconstruct_active_session(spot: dict, structure_type: str, session_date_iso: str, trips_today: list, angler: str):
    """Rebuilds this angler's own active_session_{spot_id}_{angler} dict
    (see _active_session_key(), punch-list #47 - the same shape Start
    Session/_add_lure_to_active_session build live) from already-saved
    trip_log.csv rows, for the reconnect-after-a-session_state-loss case -
    see the block comment above. Returns None if there's no still-open
    session for THIS angler logged here today (a different angler's own
    still-open session at this same spot is left completely alone - see
    _open_session_rows()). One thing a persisted row can't give back:
    `item_id` (which inventory item this lure is) was never itself written
    to disk, only the lure's display label - so a reconstructed lure's
    item_id is always None, which just means the "already added" dedup
    check in _add_lure_to_active_session() won't catch re-adding the exact
    same inventory item after a reconnect (picking it again would show up
    as a second, separate row for the same lure - harmless, just tidy up
    manually via Trip History if it happens, not silent data loss).
    Also reused read-only by _render_watch_view() below (punch-list #59) to
    build a "just watching" display of someone else's session - that call
    site never stores the result in st.session_state and never calls
    anything that writes to disk."""
    rows = _open_session_rows(spot["spot_id"], session_date_iso, trips_today, angler)
    if not rows:
        return None
    lures = []
    base_conditions = None
    predicted_score = None
    segment_name = None
    water_clarity = None
    start_time_iso = None
    session_id = None
    for t, cond in rows:
        entry_kwargs = dict(
            trip_date=t.get("trip_date"),
            segment=t.get("segment"),
            spot_id=t.get("spot_id"),
            spot_name=t.get("spot_name"),
            structure_type=t.get("structure_type"),
            water_clarity=t.get("water_clarity"),
            lure_used=t.get("lure_used"),
            color_used=t.get("color_used") or "",
            technique_used=t.get("technique_used") or "",
            fish_caught=int(t["fish_caught"]) if t.get("fish_caught") not in (None, "") else 0,
            biggest_fish_lb=float(t["biggest_fish_lb"]) if t.get("biggest_fish_lb") not in (None, "") else None,
            predicted_score=float(t["predicted_score"]) if t.get("predicted_score") not in (None, "") else None,
            conditions=cond,
            notes=t.get("notes") or "",
            # Punch-list #55: preserve whatever session_id this row already
            # has (blank for a row logged before that field existed) so a
            # reconnect's subsequent update_trip() calls (record/remove a
            # fish, retire a lure, end the session) don't silently drop it.
            session_id=t.get("session_id") or "",
        )
        lures.append({
            "trip_id": t.get("trip_id"), "logged_at": t.get("logged_at"), "label": t.get("lure_used"),
            "item_id": None,
            "entry_kwargs": entry_kwargs, "fish": cond.get("fish") or [],
            "retired": bool(cond.get("lure_end_time")),
        })
        if base_conditions is None:
            # Every lure's own conditions dict is this same shared snapshot
            # plus the per-lure keys layered on top (see the Start Session
            # handler / _add_lure_to_active_session() below) - strip those
            # back off to recover the shared snapshot, so a lure added
            # after reconnecting still reuses the real original session
            # conditions instead of nothing.
            base_conditions = {k: v for k, v in cond.items() if k not in _PER_LURE_CONDITION_KEYS}
            predicted_score = entry_kwargs["predicted_score"]
            segment_name = t.get("segment")
            water_clarity = t.get("water_clarity")
            start_time_iso = cond.get("start_time")
            session_id = t.get("session_id") or ""
    return {
        "spot_name": spot["name"],
        "session_date": session_date_iso,
        "start_time": start_time_iso or lake_now_naive().time().isoformat(),
        "segment_name": segment_name,
        "session_id": session_id,
        "structure_type": structure_type,
        "water_clarity": water_clarity,
        "predicted_score": predicted_score,
        "base_conditions": base_conditions or {},
        "lures": lures,
        "reconstructed": True,
    }


@st.fragment(run_every=20)
def _render_watch_view(spot: dict, structure_type: str, session_date_iso: str, watched_angler: str):
    """Punch-list #59: read-only, no-login 'just watching' view. Rebuilds
    the watched angler's session purely for DISPLAY via the same
    _reconstruct_active_session() the real angler's own reconnect flow
    uses. This function never writes to st.session_state's active_session_*
    key, never calls append_trip()/update_trip()/delete_trip(), and renders
    no button that could touch the real session - a watcher can look, but
    there is nothing here to tap that changes anything. Wrapped in a
    20-second auto-refreshing fragment (same mechanism as the autosave
    heartbeat below) so a new catch shows up without the watcher needing to
    manually reload."""
    trips_today = [
        t for t in read_all_trips()
        if t.get("spot_id") == spot["spot_id"] and t.get("trip_date") == session_date_iso
    ]
    active = _reconstruct_active_session(spot, structure_type, session_date_iso, trips_today, watched_angler)
    if active is None:
        st.info(f"👀 {watched_angler}'s session here has ended (or hasn't started). Nothing to watch right now.")
        return
    st.header(f"👀 Watching {watched_angler}'s session")
    score_bit = f" · predicted score {active['predicted_score']}/10" if active.get("predicted_score") is not None else ""
    st.caption(
        f"Started {active['start_time']} · {active['segment_name']} · {active['water_clarity']} water{score_bit}"
    )
    st.caption("Read-only - refreshes automatically every 20 seconds, no login and nothing you can accidentally change.")
    total_fish = 0
    for lure in active["lures"]:
        fish_count = sum((f.get("count") or 1) for f in lure["fish"])
        total_fish += fish_count
        status = " (retired)" if lure.get("retired") else ""
        st.write(f"🎣 {lure['label']}{status} - {fish_count} caught")
    if not active["lures"]:
        st.caption("No lures logged yet.")
    else:
        st.caption(f"{total_fish} fish total so far this session.")


# Anglers with a session open at this spot RIGHT NOW (today - not whatever
# historical date the "Session date" field below might get changed to,
# which is for logging past sessions, not for who's live at the moment).
# Read once here, before the picker, so it can both keep anyone from
# picking a name that's already mid-session and offer a "just watching"
# option for it instead (punch-list #59).
_today_iso = lake_today().isoformat()
_todays_open_check_entries = [
    t for t in read_all_trips()
    if t.get("spot_id") == spot["spot_id"] and t.get("trip_date") == _today_iso
]
anglers_currently_active_today = _anglers_with_open_session(spot["spot_id"], _today_iso, _todays_open_check_entries)


# --- Angler picker (punch-list #26: lightweight multi-user support) --------
# A plain "who's fishing" name picker, not real accounts/passwords - see
# core/anglers.py's module docstring for why. Every trip this page logs
# gets tagged with whichever name is picked here (baked into every lure's
# conditions dict by _build_base_conditions() below), so Trip History can
# filter by angler while every trip still lands in the same one shared log.
# The picker's own widget key ("active_angler") is deliberately NOT scoped
# by spot_id/trip_id - it's a page-wide "who's at the keyboard right now"
# setting for this browser session, not something tied to any one trip or
# spot, so it should keep whatever was last picked as the angler moves
# between spots/sessions.
angler_roster = get_anglers()
angler_key = "active_angler"
angler_other_key = "active_angler_other_name"
angler_query_key = "angler"
watch_key = "spot_session_watch_angler"
watch_query_key = "watch"
WATCH_LABEL = "👀 Just watching (read-only, no login)"
LANDING_PROMPT = "— pick one —"

_identity_established = angler_key in st.session_state
_watching_established = watch_key in st.session_state

if not _identity_established and not _watching_established:
    # Punch-list #51/#59: session_state alone doesn't survive a full app
    # restart (Streamlit Cloud auto-redeploying after ANY user's save, or
    # just a plain reconnect). Restore an already-established identity (or
    # watch target) from the URL first - the same pattern already used for
    # spot_id - so a reconnecting angler (or a still-watching watcher) lands
    # back on themselves automatically, before anything below ever has to
    # guess who this is.
    _qp_watch = (st.query_params.get(watch_query_key) or "").strip()
    _qp_angler = (st.query_params.get(angler_query_key) or "").strip()
    if _qp_watch:
        st.session_state[watch_key] = _qp_angler if _qp_angler in anglers_currently_active_today else ""
        _watching_established = True
    elif _qp_angler:
        if _qp_angler in angler_roster:
            st.session_state[angler_key] = _qp_angler
        else:
            st.session_state[angler_key] = ANGLER_OTHER_LABEL
            st.session_state[angler_other_key] = _qp_angler
        _identity_established = True

if not _identity_established and not _watching_established:
    # Punch-list #59: no established identity AND no restorable watch link -
    # a genuinely fresh visit (a bare/bookmarked link, someone else's
    # phone). This used to silently default to angler_options[0] -
    # deterministically the first roster name - landing whoever this is
    # directly on that person's real session as if they WERE them. Now it
    # asks first: anglers who don't already have a session going here right
    # now can pick their own name and start fishing; anyone else (including
    # someone who'd type an already-active name into "Other") gets steered
    # to "Just watching" instead - read-only, no way to touch the real
    # session, with a picker of whose session to watch if more than one is
    # live right now.
    _eligible_to_fish = [a for a in angler_roster if a not in anglers_currently_active_today]
    _landing_options = [LANDING_PROMPT] + _eligible_to_fish + [ANGLER_OTHER_LABEL, WATCH_LABEL]
    st.info(
        "👋 New here, or a fresh link with no name attached. Pick your own name to start fishing, "
        "or choose \"Just watching\" to follow someone else's live session with no risk of changing it."
    )
    _landing_choice = st.selectbox("🎣 Who's this?", _landing_options, key="spot_session_landing_choice")

    if _landing_choice == WATCH_LABEL:
        if not anglers_currently_active_today:
            st.caption("No one has a session in progress at this spot right now - nothing to watch yet.")
            st.stop()
        if len(anglers_currently_active_today) > 1:
            _watch_target = st.selectbox(
                "Whose session?", anglers_currently_active_today, key="spot_session_landing_watch_pick",
            )
        else:
            _watch_target = anglers_currently_active_today[0]
        st.session_state[watch_key] = _watch_target
        st.query_params[watch_query_key] = "1"
        st.query_params[angler_query_key] = _watch_target
        st.rerun()

    elif _landing_choice == ANGLER_OTHER_LABEL:
        _typed = (st.text_input("Name", key="spot_session_landing_other_name") or "").strip()
        if _typed and _typed in anglers_currently_active_today:
            st.warning(
                f"⚠️ \"{_typed}\" already has a session in progress here right now. If that's you "
                "reconnecting (a dropped connection, a locked phone), confirm below to pick it back up. "
                "If it's someone else fishing under that name, use a different name, or just watch instead."
            )
            if st.button(f"Yes, that's me - resume {_typed}'s session", key="spot_session_reclaim_confirm"):
                st.session_state[angler_key] = ANGLER_OTHER_LABEL
                st.session_state[angler_other_key] = _typed
                st.query_params[angler_query_key] = _typed
                st.rerun()
        elif _typed:
            st.session_state[angler_key] = ANGLER_OTHER_LABEL
            st.session_state[angler_other_key] = _typed
            st.query_params[angler_query_key] = _typed
            st.rerun()
        st.stop()

    elif _landing_choice == LANDING_PROMPT:
        st.stop()

    else:
        st.session_state[angler_key] = _landing_choice
        st.query_params[angler_query_key] = _landing_choice
        st.rerun()

if _watching_established:
    _watched = st.session_state.get(watch_key) or ""
    if not _watched or _watched not in anglers_currently_active_today:
        if anglers_currently_active_today:
            if len(anglers_currently_active_today) > 1:
                _watched = st.selectbox(
                    "Whose session?", anglers_currently_active_today, key="spot_session_watch_pick_active",
                )
            else:
                _watched = anglers_currently_active_today[0]
            st.session_state[watch_key] = _watched
            st.query_params[angler_query_key] = _watched
        else:
            st.info("👀 No one has a session in progress at this spot right now.")
            if st.button("Stop watching", key="spot_session_stop_watching_empty"):
                st.session_state.pop(watch_key, None)
                st.query_params.pop(watch_query_key, None)
                st.query_params.pop(angler_query_key, None)
                st.rerun()
            st.stop()
    _render_watch_view(spot, structure_type, _today_iso, _watched)
    if st.button("Not watching anymore - let me pick a name and fish", key="spot_session_stop_watching"):
        st.session_state.pop(watch_key, None)
        st.query_params.pop(watch_query_key, None)
        st.query_params.pop(angler_query_key, None)
        st.rerun()
    st.stop()

# From here on, an identity is established (either just now, or already
# from before) - unchanged from before, except the option list now leaves
# out anyone else's already-active session (their own name stays selectable
# even while their own session is active, so ending/reconnecting to their
# own session still works normally).
angler_options = [
    a for a in angler_roster
    if a not in anglers_currently_active_today or a == st.session_state.get(angler_key)
] + [ANGLER_OTHER_LABEL]
if st.session_state.get(angler_key) not in angler_options:
    # The previously-picked name now collides with someone else's session
    # that started since (rare - two browsers racing to pick the same
    # fresh name at the same spot within moments of each other) - fall back
    # to "Other" rather than crash the widget on a stored value that's no
    # longer a valid option.
    st.session_state[angler_key] = ANGLER_OTHER_LABEL
    st.session_state.setdefault(angler_other_key, "")
angler_choice = st.selectbox(
    "🎣 Who's fishing", angler_options, key=angler_key,
    help='Tags every trip you log with your name - Trip History can filter by angler, but '
         'everyone\'s trips stay combined in one shared log. Remembered for this browser '
         'session (and carried in the page link) so a reconnect brings you back as '
         'yourself; pick "Other" to add a new name to the list.',
)
angler_other_name = ""
if angler_choice == ANGLER_OTHER_LABEL:
    st.session_state.setdefault(angler_other_key, "")
    angler_other_name = st.text_input(
        "Name", key=angler_other_key,
        help="Saved as a new dropdown choice the next time you log a trip.",
    )
resolved_angler = angler_other_name.strip() if angler_choice == ANGLER_OTHER_LABEL else angler_choice

# Keep the URL in sync so a reconnect (a redeploy-triggered restart, a
# locked phone, a spotty-signal drop) restores this angler instead of
# ever falling back to a default - see the restore block above.
if resolved_angler:
    st.query_params[angler_query_key] = resolved_angler
elif angler_query_key in st.query_params:
    st.query_params.pop(angler_query_key, None)


def _save_new_angler_if_needed() -> bool:
    """Called right before a trip actually gets saved (Start Session / Save
    changes) - not at picker-render time - so idly typing into "Other"
    without ever logging anything doesn't itself trigger a git commit.
    Returns True if a genuinely new name was just added to the roster, so
    the caller knows to include data/anglers.csv in that same push."""
    if angler_choice == ANGLER_OTHER_LABEL and resolved_angler:
        return add_angler(resolved_angler)
    return False


# structure_type, _angler_session_slug() and _active_session_key() now live
# above, next to the angler picker (punch-list #59 needed them earlier than
# this point) - see the comment block up there for the full "why" behind
# per-angler session scoping.

if st.session_state.pop(f"session_closed_banner_{spot['spot_id']}", False):
    st.success("✅ Session closed - pick lures below whenever you're ready to start a new one.")
if st.session_state.pop(f"session_canceled_banner_{spot['spot_id']}", False):
    st.info("❌ Session canceled - nothing from that session was saved. Pick lures below to start a new one.")

st.session_state.setdefault(f"session_date_{spot['spot_id']}", lake_today())

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


def _build_base_conditions(cond_values: dict, avg_cloud_pct, avg_wind_mph, rt, score_result, start_time, segment_name, angler: str = None):
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
        # Punch-list #26: whichever name the "Who's fishing" picker was set
        # to when this session/edit was saved (core/anglers.py) - blank/None
        # for anything logged before that feature existed, same as every
        # other optional key in this dict.
        "angler": angler or None,
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
            "No lures in your tackle box yet - add some on the Tackle Box page, "
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


# --- Pending-session draft persistence (punch-list #53) ---------------------
# Everything below Start Session (conditions form + picked lures, not yet
# saved anywhere) lived only in st.session_state, so it was the one thing
# punch-list #47/#51/#52 didn't already make durable - an ALREADY-STARTED
# session recovers from disk on reconnect (#47), and #52 made a reconnect a
# lot less frequent, but a session still being set up had nothing to
# recover FROM. Mirrors the exact "carry it in the URL" pattern already
# used for spot_id/edit_trip/angler above (see those for precedent) - one
# JSON blob under a single "draft" query param, since there's real
# structure here (a dozen-odd condition fields plus a list of picked
# lures/trailers) rather than one scalar value.
PENDING_DRAFT_QUERY_KEY = "draft"


def _load_pending_draft(spot_id: str) -> dict:
    """Parses ?draft=... back into {"spot_id", "seq", "cond", "lures"}.
    Returns {} on anything that doesn't check out - no param, invalid JSON,
    missing keys, or (most importantly) a draft that belongs to a
    DIFFERENT spot than the one this URL/page is currently on, e.g. after
    switching spots without ever hitting Start Session at the old one -
    never raises, since this is untrusted input coming from a URL."""
    raw = st.query_params.get(PENDING_DRAFT_QUERY_KEY)
    if not raw:
        return {}
    try:
        draft = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(draft, dict) or draft.get("spot_id") != spot_id:
        return {}
    if not {"seq", "cond", "lures"} <= draft.keys():
        return {}
    return draft


def _save_pending_draft(spot_id: str, seq: int, cond_values: dict, pending_lures: list):
    """Keeps ?draft=... in sync with the current pending build on every
    render, so a reconnect at ANY point - mid-conditions-form, with lures
    already picked, or both - restores exactly where things were left off
    instead of starting over blank."""
    blob = {"spot_id": spot_id, "seq": seq, "cond": cond_values, "lures": pending_lures}
    st.query_params[PENDING_DRAFT_QUERY_KEY] = json.dumps(blob, separators=(",", ":"))


def _clear_pending_draft():
    st.query_params.pop(PENDING_DRAFT_QUERY_KEY, None)


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


def _added_lure_item_ids(spot_id: str, seq: int, mode: str, angler: str = "") -> set:
    """Item ids already queued for this session - the pre-session "pending"
    list before Start Session, or the active session's currently-in-use
    (not yet retired) lures once one's running. Used to disable/relabel a
    picker card that's already been added. `angler` only matters for the
    "active" branch - the active session it looks up is scoped per angler
    (see _active_session_key() above)."""
    if mode == "pending":
        return {p.get("item_id") for p in st.session_state.get(_pending_lures_key(spot_id, seq), [])}
    active = st.session_state.get(_active_session_key(spot_id, angler))
    if not active:
        return set()
    return {l.get("item_id") for l in active["lures"] if not l.get("retired")}


def _trailer_dialog_lure_key(lure_stub: dict) -> str:
    """Stable id for a lure_stub's trailer-dialog widget keys - the same
    inventory item (or the same typed manual name) always maps to the same
    keys, so the dialog's checkbox/selection reflects what's actually been
    picked so far no matter how many times this exact "+ Add" click
    re-renders it while it's open (each click re-runs the whole script,
    and Streamlit only keeps a dialog open by re-satisfying the same
    opening condition every run - a monotonically-incrementing id here
    would hand the dialog a brand new, blank set of keys on every single
    one of those re-renders instead of remembering what was just entered)."""
    if lure_stub.get("item_id"):
        return lure_stub["item_id"]
    return f"manual_{abs(hash(lure_stub.get('label', '')))}"


def _handle_lure_add_click(spot_id: str, seq: int, lure_stub: dict, item_for_trailer_check, mode: str, angler: str = ""):
    """Common "+ Add" handler for a lure card, wherever it's clicked from
    (a recommendation's quick-add, the tackle-box grid, or a manual
    entry) - if that lure's category can take a trailer (or it's a manual
    entry, whose category is unknown), a popup asks about a trailer before
    it's actually added; otherwise it's added immediately, same as before.
    `mode` ("pending" before a session starts, "active" to add a lure
    mid-session) decides which list the lure - and its trailer pick, if
    any - eventually lands in. `angler` is only actually used for "active"
    mode (see _add_lure_to_active_session's own angler-scoping)."""
    if lure_can_take_trailer(item_for_trailer_check):
        _trailer_dialog(spot_id, seq, lure_stub, mode, angler)
    else:
        if mode == "pending":
            _add_lure_to_pending(spot_id, seq, lure_stub)
        else:
            _add_lure_to_active_session(spot_id, lure_stub, angler)
        st.rerun()


@st.dialog("Add a trailer?")
def _trailer_dialog(spot_id: str, seq: int, lure_stub: dict, mode: str, angler: str = ""):
    dkey = _trailer_dialog_lure_key(lure_stub)
    if st.session_state.pop(f"trailer_dialog_reset_pending_{spot_id}_{dkey}", False):
        for k in (
            f"trailer_dialog_use_{spot_id}_{dkey}", f"trailer_dialog_pick_{spot_id}_{dkey}",
            f"trailer_dialog_manual_{spot_id}_{dkey}",
        ):
            st.session_state.pop(k, None)
    st.markdown(f"**{lure_stub['label']}**")
    use_trailer = st.checkbox("Used a trailer with this lure", key=f"trailer_dialog_use_{spot_id}_{dkey}")
    trailer = None
    if use_trailer:
        trailer_items = [it for it in get_inventory() if is_trailer_eligible(it)]
        options = ["Type it in manually"] + [inventory_item_label(it) for it in trailer_items]
        idx = st.selectbox(
            "Trailer", options=list(range(len(options))), format_func=lambda i: options[i],
            key=f"trailer_dialog_pick_{spot_id}_{dkey}",
        )
        if idx == 0:
            manual_trailer_name = st.text_input("Trailer name", key=f"trailer_dialog_manual_{spot_id}_{dkey}")
            if manual_trailer_name.strip():
                trailer = {"item_id": None, "label": manual_trailer_name.strip(), "category": None, "color": None}
        else:
            picked = trailer_items[idx - 1]
            trailer = {
                "item_id": picked.get("item_id"), "label": inventory_item_label(picked),
                "category": picked.get("category"), "color": picked.get("description", ""),
            }

    fc1, fc2 = st.columns(2)
    if fc1.button("Add lure", type="primary", width='stretch', key=f"trailer_dialog_confirm_{spot_id}_{dkey}"):
        final_lure = dict(lure_stub)
        final_lure["trailer"] = trailer
        if mode == "pending":
            _add_lure_to_pending(spot_id, seq, final_lure)
        else:
            _add_lure_to_active_session(spot_id, final_lure, angler)
        # Clears the checkbox/selection back to blank for the NEXT time this
        # exact lure's dialog is opened (e.g. re-adding it later in a future
        # session) - can't just pop the keys here, since they're already
        # instantiated widgets this run; deferred the same way every other
        # "reset before re-instantiation" case on this page is (see
        # session_build_seq_key's own comment for the general pattern).
        st.session_state[f"trailer_dialog_reset_pending_{spot_id}_{dkey}"] = True
        st.rerun()
    if fc2.button("Cancel", width='stretch', key=f"trailer_dialog_cancel_{spot_id}_{dkey}"):
        st.rerun()


def _multi_lure_picker(inventory_items: list, key_prefix: str, spot_id: str, seq: int, mode: str = "pending", angler: str = ""):
    """Multi-select sibling of _visual_lure_picker - same searchable card
    grid, but each card adds to the running "lures for this session" list
    (see _pending_lures_key, or the active session once one's started)
    instead of picking exactly one. Shows the whole tackle box, including
    trailer-eligible baits (craw/creature, paddle-tail swimbait-style; see
    core.lures.is_trailer_eligible) - punch-list #46: those baits are often
    fished on their own too (e.g. a Texas-rigged creature bait or a
    weightless soft plastic), not just attached to another lure via the
    trailer popup below, so they belong here as regular pickable lures.
    The trailer popup's own picker (_trailer_dialog) stays filtered to
    is_trailer_eligible() only - that's the "attach this to another lure"
    list, a separate concern from "what can I fish on its own"."""
    if not inventory_items:
        st.caption("No lures in your tackle box yet - add some on the Tackle Box page.")
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
    added_ids = _added_lure_item_ids(spot_id, seq, mode, angler)
    for row_start in range(0, len(filtered), LURE_PICKER_COLS):
        row_items = filtered[row_start:row_start + LURE_PICKER_COLS]
        cols = st.columns(LURE_PICKER_COLS)
        for col, item in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    if not render_square_thumbnail(item, size_px=LURE_PICKER_THUMBNAIL_PX):
                        st.caption("No photo")
                    st.caption(f"**{item.get('brand', '')}**  \n{item.get('description', '')}"[:90])
                    is_added = item.get("item_id") in added_ids
                    if st.button(
                        "✓ Added" if is_added else "+ Add", key=f"{key_prefix}_toggle_{item['item_id']}",
                        disabled=is_added, width='stretch',
                    ):
                        _handle_lure_add_click(spot_id, seq, {
                            "item_id": item["item_id"], "label": inventory_item_label(item),
                            "category": item.get("category"),
                        }, item, mode, angler)


def _render_recommendation_with_quick_add(rec, spot_id: str, seq: int, key_prefix: str, mode: str = "pending", angler: str = ""):
    """Displays the lure recommendation (reusing core.ui.render_lure_block
    unchanged, so this stays in sync with the 7-Day Forecast page's own
    display) with a "+ Add to session" button under each color-matched
    owned item, so a suggested lure can be added to this session with one
    click instead of having to go find it again in the tackle-box picker
    below. Punch-list #46: blocks for a trailer-eligible category (see
    core.lures.TRAILER_ELIGIBLE_CATEGORIES) get a quick-add button too, same
    as any other category - those baits can be fished standalone, matching
    _multi_lure_picker below no longer excluding them either."""
    added_ids = _added_lure_item_ids(spot_id, seq, mode, angler)
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
                is_added = item_id in added_ids
                btn_label = "✓ Added to session" if is_added else f"+ Add {item.get('brand', '')} - {item.get('description', '')}"[:60]
                if st.button(btn_label, key=f"{key_prefix}_{block.key}_{item_id}", disabled=is_added):
                    _handle_lure_add_click(spot_id, seq, {
                        "item_id": item_id, "label": inventory_item_label(item), "category": block.key,
                    }, {"category": block.key}, mode, angler)
    if rec.rationale:
        st.caption(" · ".join(rec.rationale))


# --- Per-fish entry (used by both the active-session dialog and edit mode) --
def _parse_nonneg_int(text) -> int:
    """Parses a manual lb/oz field's typed text into a non-negative int,
    defaulting to 0 for blank/garbage input rather than raising - same
    fail-soft convention as every other optional numeric field in this
    app."""
    try:
        v = int(str(text).strip())
    except (TypeError, ValueError):
        return 0
    return max(v, 0)


def _parse_nonneg_float(text) -> float:
    try:
        v = float(str(text).strip())
    except (TypeError, ValueError):
        return 0.0
    return max(v, 0.0)


def _format_number(v) -> str:
    """Renders a number without a trailing ".0" for whole values (15.0 ->
    "15", 15.5 -> "15.5") - used to seed the manual length field from a
    slider-derived value without an odd-looking decimal point."""
    v = float(v or 0)
    return str(int(v)) if v == int(v) else str(v)


def _weight_input(key_prefix: str) -> float:
    """Punch-list #31: a 1-oz-increment weight slider
    (core.activity_log.WEIGHT_SLIDER_OPTIONS) plus manual lb/oz fields to
    its right, two-way synced - moving the slider updates the manual
    fields to match, and typing into either manual field snaps the slider
    to its nearest matching position
    (core.activity_log.nearest_weight_slider_option()). A slider alone, 1
    oz at a time across several pounds, turned out too easy to overshoot
    by feel/touch on the water - the manual fields are the real source of
    truth for the value this returns (full 1-oz precision, not limited to
    the slider's own <1 lb floor or +N lb ceiling); the slider is a fast,
    rough starting point, not the final say. Typing an oz value of 16+
    carries over into lb automatically (e.g. "20" oz becomes 1 lb 4 oz),
    so there's no need to do that arithmetic by hand. Returns the resolved
    weight in decimal pounds (0.0 if both fields are left at 0)."""
    slider_key = f"{key_prefix}_slider"
    lb_key = f"{key_prefix}_lb"
    oz_key = f"{key_prefix}_oz"

    def _slider_changed():
        lb, oz = divmod(round((weight_lb_for_slider_option(st.session_state.get(slider_key)) or 0) * 16), 16)
        st.session_state[lb_key] = str(lb)
        st.session_state[oz_key] = str(oz)

    def _manual_changed():
        lb = _parse_nonneg_int(st.session_state.get(lb_key))
        oz = _parse_nonneg_int(st.session_state.get(oz_key))
        lb, oz = lb + oz // 16, oz % 16
        st.session_state[lb_key] = str(lb)
        st.session_state[oz_key] = str(oz)
        st.session_state[slider_key] = nearest_weight_slider_option(lb + oz / 16)

    scol, lcol, ocol = st.columns([3, 1, 1])
    scol.select_slider("Weight", options=WEIGHT_SLIDER_OPTIONS, key=slider_key, on_change=_slider_changed)
    if lb_key not in st.session_state:
        # First render of this key prefix - seed the manual fields from the
        # slider's own default ("<1 lb" -> 0 lb 8 oz) so nothing changes if
        # the angler never touches weight at all, same as before this round.
        _seed_lb, _seed_oz = divmod(round((weight_lb_for_slider_option(st.session_state[slider_key]) or 0) * 16), 16)
        st.session_state[lb_key] = str(_seed_lb)
        st.session_state[oz_key] = str(_seed_oz)
    lcol.text_input("lb", key=lb_key, on_change=_manual_changed)
    ocol.text_input("oz", key=oz_key, on_change=_manual_changed)

    lb = _parse_nonneg_int(st.session_state.get(lb_key))
    oz = _parse_nonneg_int(st.session_state.get(oz_key))
    return round(lb + oz / 16, 4)


def _length_input(key_prefix: str) -> float:
    """Same idea as _weight_input() above but for length: the
    LENGTH_SLIDER_OPTIONS slider plus one manual inches field to its
    right, two-way synced. Punch-list #31 only asked for the manual field
    here, not a wider slider range - length wasn't reported as fiddly the
    way weight was, so LENGTH_SLIDER_OPTIONS itself is unchanged. The
    manual field is still the real source of truth for the returned value
    (e.g. it accepts a half-inch reading the whole-inch slider alone
    can't represent)."""
    slider_key = f"{key_prefix}_slider"
    in_key = f"{key_prefix}_manual"

    def _slider_changed():
        st.session_state[in_key] = _format_number(length_in_for_slider_option(st.session_state.get(slider_key)))

    def _manual_changed():
        v = _parse_nonneg_float(st.session_state.get(in_key))
        st.session_state[in_key] = _format_number(v)
        st.session_state[slider_key] = nearest_length_slider_option(v)

    scol, icol = st.columns([3, 1])
    scol.select_slider("Length", options=LENGTH_SLIDER_OPTIONS, key=slider_key, on_change=_slider_changed)
    if in_key not in st.session_state:
        st.session_state[in_key] = _format_number(length_in_for_slider_option(st.session_state[slider_key]))
    icol.text_input("in", key=in_key, on_change=_manual_changed)

    return _parse_nonneg_float(st.session_state.get(in_key))


def _new_fish_from_form(species_label, species_other, weight_lb, length_in, hit_types, retrieve_style, retrieve_speed) -> dict:
    species_final = (
        species_other.strip() if (species_label == "Other (type in species)" and species_other.strip())
        else species_label
    )
    return {
        "species": species_final,
        "species_other": species_other or None,
        "count": 1,
        "weight_lb": weight_lb or None,
        "length_in": length_in or None,
        "hit_types": hit_types,
        "retrieve_speed": retrieve_speed,
        "retrieve_style": retrieve_style,
        # Punch-list #32: the real moment this catch record was saved (same
        # lake_now_naive().time().isoformat() convention as
        # lure_start_time/lure_end_time above), so Trip History's per-fish
        # detail can show when each fish in a session was actually caught,
        # not just the session's own overall start/end time. Older rows
        # logged before this existed simply have no "caught_at" key -
        # display code below treats that the same as every other optional
        # per-fish field.
        "caught_at": lake_now_naive().time().isoformat(),
    }


def _format_fish_time(iso_time_str) -> str:
    """"08:15:32.123456" -> "8:15 AM" - same %-I:%M %p convention this page
    already uses for time-window ranges (_segment_option_label). Returns
    None (not shown) for a blank/unparseable value, e.g. a fish record
    logged before punch-list #32 added "caught_at"."""
    try:
        return dtime.fromisoformat(iso_time_str).strftime("%-I:%M %p")
    except (TypeError, ValueError):
        return None


def _fish_summary_bits(fish: dict) -> list:
    count = fish.get("count") or 1
    bits = [f"{count} x {fish['species']}" if count > 1 else (fish.get("species") or "Unknown species")]
    caught_at_label = _format_fish_time(fish.get("caught_at"))
    if caught_at_label:
        bits.append(caught_at_label)
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


# --- Push-health tracking + autosave retry (punch-list #58) -----------------
# The angler's own report: a save happens (every fish/lure/etc. already
# writes to data/trip_log.csv and pushes immediately - see each handler
# below), but if that push doesn't land on GitHub for any reason, the row
# only exists on THIS process's local disk. That's invisible and harmless
# right up until the process itself restarts (a real code deploy, or - the
# suspected cause of the actual incident this was built for - a resource-
# limit restart on Streamlit Community Cloud with no code push involved at
# all) - at which point the fresh process's data/ is whatever the "data"
# branch last had, silently dropping anything that was only ever
# committed-not-pushed in the now-dead process. core.storage's retry/backoff
# (punch-list #58) makes any ONE push attempt considerably more resilient to
# a flaky connection, but that alone still leaves a gap: a push that fails
# even after those retries (GITHUB_TOKEN briefly bad, a longer outage) just
# sits there unpushed with nothing else ever trying again - until the very
# next real save happens to succeed and carries it along for free (a `git
# push` always sends everything HEAD is ahead by, not just the newest
# commit). If a while passes with no new save (thinking, watching a bobber,
# between spots) and the process dies in that window, it's gone regardless
# of how good the retry-per-attempt logic is.
#
# _PUSH_HEALTH_KEY tracks whether the LAST push attempt actually succeeded,
# independent of which action triggered it. Whenever it's failing, the
# "session in progress" view below shows a persistent (not a toast that can
# be missed) warning with a manual retry button, AND a background
# st.fragment(run_every=...) heartbeat (see _autosave_heartbeat() below)
# keeps quietly retrying on its own every 30s the tab stays open and
# connected - belt (visible + actionable) and suspenders (automatic),
# exactly what was asked for. This closes the gap for as long as the
# process itself survives; it can't do anything about data that was only
# ever local to a process that's already gone - the real fix for that is
# making each individual push attempt (and the retries around it) as
# resilient as reasonably possible, which is what core.storage's own
# punch-list #58 changes are for.
_PUSH_HEALTH_KEY = "_push_health"


def _push_health() -> dict:
    return st.session_state.setdefault(
        _PUSH_HEALTH_KEY, {"ok": True, "message": "", "consecutive_failures": 0},
    )


def _record_push_result(ok: bool, message: str):
    health = _push_health()
    if ok:
        health["ok"] = True
        health["consecutive_failures"] = 0
        health["message"] = ""
    else:
        health["ok"] = False
        health["consecutive_failures"] = health.get("consecutive_failures", 0) + 1
        health["message"] = message
    st.session_state[_PUSH_HEALTH_KEY] = health


def _push_or_toast(paths, commit_message, local_message):
    token = github_token()
    if token:
        ok, msg = commit_and_push_data(paths, token, repo_slug(), commit_message)
        _record_push_result(ok, msg)
        st.toast(msg, icon="✅" if ok else "⚠️")
    else:
        # No token at all isn't a "failing push" in the retry-worthy sense -
        # there's nothing to retry until one's configured - so this
        # deliberately doesn't touch push health/trigger the warning banner.
        st.toast(local_message, icon="ℹ️")


def _retry_pending_push(show_toast: bool = True) -> bool:
    """Manual/heartbeat retry of whatever's already committed locally but
    hasn't reached GitHub yet - see the block comment above. Safe to call
    any time, including when nothing's actually pending (push_pending_data
    is a harmless no-op then) - so both the manual "🔁 Retry save now"
    button and the automatic heartbeat can call this unconditionally
    without first checking whether there's really something to retry."""
    token = github_token()
    if not token:
        return False
    ok, msg = push_pending_data(token, repo_slug())
    _record_push_result(ok, msg)
    if show_toast:
        st.toast(msg, icon="✅" if ok else "⚠️")
    return ok


def _render_push_health_banner():
    """Persistent (not a toast - those can be missed, especially mid-cast)
    warning shown right at the top of an in-progress session whenever the
    last push attempt failed, with a manual retry button. Silent/renders
    nothing when the last push succeeded or none has happened yet."""
    health = _push_health()
    if health.get("ok", True):
        return
    n = health.get("consecutive_failures", 1)
    st.warning(
        f"⚠️ The last {n} save{'s' if n != 1 else ''} couldn't reach GitHub yet "
        f"(saved on this device, just not backed up there) - {health.get('message', '')}. "
        "Everything you log keeps working normally, and this keeps retrying automatically "
        "every 30 seconds while this page stays open - tap below to retry right now instead."
    )
    if st.button("🔁 Retry save now", key="retry_pending_push_btn"):
        if _retry_pending_push():
            st.rerun()


@st.fragment(run_every=30)
def _autosave_heartbeat():
    """Punch-list #58: a periodic, no-interaction-required retry of any
    currently-unpushed save, running independently of whatever the angler
    is doing on the rest of the page - the "even if I don't touch anything
    for a while" half of the autosave ask. st.fragment(run_every=30) means
    this one small block re-executes on its own every 30 seconds the
    browser tab stays open and connected, without rerunning (or blocking)
    the rest of the page. Only actually does anything when the last known
    push attempt failed - otherwise push_pending_data() is a cheap no-op
    ("Everything up-to-date"), so this doesn't hammer GitHub every 30
    seconds during a session where every save has been landing fine."""
    if not _push_health().get("ok", True):
        _retry_pending_push(show_toast=False)


def _record_fish(spot_id: str, lure_index: int, fish_record: dict, angler: str = ""):
    """Appends one fish to the given lure's running catch list, immediately
    saving that lure's TripEntry (via update_trip) and pushing - per the
    angler's own ask, each catch is saved right away rather than batched
    until the session ends."""
    active_key = _active_session_key(spot_id, angler)
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


def _remove_fish(spot_id: str, lure_index: int, fish_index: int, angler: str = ""):
    active_key = _active_session_key(spot_id, angler)
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


def _add_lure_to_active_session(spot_id: str, lure_stub: dict, angler: str = ""):
    """Adds one more lure to an already-running session - the same "switch
    rods any time" ability as picking lures before Start Session, just
    writing a brand-new TripEntry row (its own lure_start_time = right
    now) instead of queuing into the pre-session pending list, using this
    session's own conditions snapshot (active["base_conditions"]) for
    everything about the SESSION as a whole. That snapshot is captured once
    at Start Session and normally reused unchanged for every lure added
    after - EXCEPT fish activity/forage activity/wind/sky, which the
    "🔄 Conditions changed? Get updated suggestions" panel (punch-list #49)
    can update mid-session; if the angler has tapped "Update conditions"
    there, this picks up whatever was most recently saved, not necessarily
    what was true at Start Session. Water clarity/temp/depth are never
    touched mid-session, so those always stay what they were at the start."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return
    if lure_stub.get("item_id") is not None:
        # Dedupe against currently-ACTIVE (not retired) lures only - picking
        # the same lure back up after retiring it earlier in this same
        # session is allowed and expected (an angler genuinely does switch
        # back and forth), so a past retirement shouldn't block re-adding it.
        if any(not l.get("retired") and l.get("item_id") == lure_stub["item_id"] for l in active["lures"]):
            return
    start_time = lake_now_naive().time()
    trailer = lure_stub.get("trailer")
    lure_conditions = dict(active["base_conditions"])
    lure_conditions.update({
        "lure_category": lure_stub.get("category"),
        "trailer_used": trailer is not None,
        "trailer_name": trailer.get("label") if trailer else None,
        "trailer_color": trailer.get("color") if trailer else None,
        "trailer_category": trailer.get("category") if trailer else None,
        "lure_start_time": start_time.isoformat(),
        "lure_end_time": None,
        "fish": [],
        "source": "spot_session",
    })
    entry_kwargs = dict(
        trip_date=active["session_date"],
        segment=active["segment_name"],
        spot_id=spot_id,
        spot_name=active["spot_name"],
        structure_type=active["structure_type"],
        water_clarity=active["water_clarity"],
        lure_used=lure_stub["label"],
        color_used="",
        technique_used="",
        fish_caught=0,
        biggest_fish_lb=None,
        predicted_score=active.get("predicted_score"),
        conditions=lure_conditions,
        notes="",
        session_id=active.get("session_id", ""),
    )
    entry = TripEntry(**entry_kwargs)
    append_trip(entry)
    active["lures"].append({
        "trip_id": entry.trip_id, "logged_at": entry.logged_at, "label": lure_stub["label"],
        "item_id": lure_stub.get("item_id"), "entry_kwargs": entry_kwargs, "fish": [], "retired": False,
    })
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Add {lure_stub['label']} to active session ({active.get('spot_name', spot_id)})",
        "Lure added locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


def _retire_lure(spot_id: str, lure_index: int, angler: str = ""):
    """"🔄 Change" - stops active use of one lure mid-session without
    ending the whole session: stamps its own lure_end_time right now
    (same field Start Session leaves blank and End Session would otherwise
    fill in later) and marks it retired so it drops out of the active
    button list, while the rest of the session (and any other lure still
    in play) keeps going."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None or lure_index >= len(active["lures"]):
        return
    lure = active["lures"][lure_index]
    if lure.get("retired"):
        return
    end_time = lake_now_naive().time()
    entry_kwargs = dict(lure["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["lure_end_time"] = end_time.isoformat()
    entry_kwargs["conditions"] = conditions
    entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
    update_trip(entry)
    lure["entry_kwargs"] = entry_kwargs
    lure["retired"] = True
    active["lures"][lure_index] = lure
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Retire {lure['label']} from active session ({active.get('spot_name', spot_id)})",
        "Retired locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


@st.dialog("Log a fish")
def _fish_entry_dialog(spot_id: str, lure_index: int, angler: str = ""):
    active = st.session_state.get(_active_session_key(spot_id, angler))
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

    weight_lb_value = _weight_input(f"fish_weight_{spot_id}_{lure_index}_{dseq}")
    length_in_value = _length_input(f"fish_length_{spot_id}_{lure_index}_{dseq}")
    # Punch-list #33: st.pills instead of st.multiselect - a multiselect's
    # option list opens in a floating dropdown that, on a phone, was
    # reported to cut off the last option ("Surface hit") with no way to
    # scroll down to it. Pills render all options as always-visible,
    # directly tappable chips (wrapping onto a second line on a narrow
    # screen instead of hiding anything behind a popover), which sidesteps
    # that failure mode entirely rather than trying to patch the dropdown's
    # scroll behavior. selection_mode="multi" keeps the same "pick any
    # number of these" behavior and still returns a plain list, so nothing
    # downstream (_new_fish_from_form, the ", ".join(...) display bit)
    # needed to change.
    hit_types = st.pills(
        "Type of hit", HIT_TYPE_OPTIONS, selection_mode="multi",
        key=f"fish_hit_types_{spot_id}_{lure_index}_{dseq}",
    )

    rc1, rc2 = st.columns(2)
    retrieve_style = rc1.selectbox("Retrieve style", RETRIEVE_STYLE_OPTIONS, key=f"fish_retrieve_style_{spot_id}_{lure_index}_{dseq}")
    retrieve_speed = rc2.selectbox("Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=1, key=f"fish_retrieve_speed_{spot_id}_{lure_index}_{dseq}")

    fc1, fc2 = st.columns(2)
    if fc1.button("✅ Record", type="primary", width='stretch', key=f"fish_record_{spot_id}_{lure_index}_{dseq}"):
        fish_record = _new_fish_from_form(
            species_label, species_other, weight_lb_value, length_in_value, hit_types, retrieve_style, retrieve_speed,
        )
        _record_fish(spot_id, lure_index, fish_record, angler)
        st.session_state[dseq_key] = dseq + 1
        st.rerun()
    if fc2.button("Cancel", width='stretch', key=f"fish_cancel_{spot_id}_{lure_index}_{dseq}"):
        st.rerun()


def _end_session(spot_id: str, angler: str = ""):
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return
    end_time = lake_now_naive().time()
    for lure in active["lures"]:
        entry_kwargs = dict(lure["entry_kwargs"])
        conditions = dict(entry_kwargs["conditions"])
        # Punch-list #34: "session_end_time" is stamped on EVERY lure in the
        # session (retired or not) - the one moment "⏹ End Session" was
        # actually clicked, so Trip History can show a real session-level
        # end time no matter which lure a trip row belongs to. This is
        # deliberately separate from "lure_end_time", which stays whatever
        # it already was for a retired lure (see below) - a lure retired
        # early via "🔄 Change" mid-session has its own, earlier, real
        # lure_end_time, while every lure's session_end_time is this same
        # single "the whole session closed at X" value.
        conditions["session_end_time"] = end_time.isoformat()
        if not lure.get("retired"):
            # Already stamped its own (earlier, real) lure_end_time when it
            # was retired via "🔄 Change" - don't overwrite that with the
            # session's own end time now.
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


def _cancel_session(spot_id: str, angler: str = ""):
    """"❌ Cancel Session" (punch-list #32) - discards an in-progress session
    entirely, rather than finalizing it like "⏹ End Session" does: deletes
    every trip_log.csv row this session created (delete_trip(), the same
    row-removal primitive Trip History's own "🗑️ Delete this trip" uses)
    and drops this angler's own active session key (see
    _active_session_key(), punch-list #47) from session_state, leaving no
    trace of the session behind. For testing sessions, or wanting a clean
    restart at this spot without keeping anything logged so far. Every row
    to delete comes from active["lures"] (in-memory, not a fresh disk
    read), so this only ever touches rows THIS session itself created -
    it can't reach into some other, unrelated angler's session data."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return
    trip_ids = [lure["trip_id"] for lure in active["lures"]]
    for trip_id in trip_ids:
        delete_trip(trip_id)
    _push_or_toast(
        [TRIP_LOG_PATH],
        f"Cancel spot session ({active.get('spot_name', spot_id)}) - discard {len(trip_ids)} row(s)",
        "Session canceled locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )
    st.session_state.pop(active_key, None)
    st.session_state[f"session_canceled_banner_{spot_id}"] = True


# _PER_LURE_CONDITION_KEYS, _open_session_rows(), _other_anglers_with_open_
# session() and _reconstruct_active_session() now live up near the angler
# picker (punch-list #59 needed them earlier than this point, to check for
# already-active sessions before the picker renders) - see the comment
# block up there for the full "why" behind reconstruct-on-reconnect
# (originally punch-list #29).

# ==============================================================================
# NORMAL MODE - either a session is already in progress at this spot, or the
# angler is setting one up (conditions -> lure selection -> Start Session).
# ==============================================================================
active_session_key = _active_session_key(spot["spot_id"], resolved_angler)
active = st.session_state.get(active_session_key)

if active is None:
    # Punch-list #29 - see the block comment above _reconstruct_active_session()
    # for the full story. Reuses todays_entries (already read above for the
    # "Already logged for this spot" caption) rather than a second
    # read_all_trips() call. Punch-list #47: scoped to resolved_angler, so
    # this only ever reconnects THIS angler's own still-open session at this
    # spot, never someone else's - see _open_session_rows()'s own docstring.
    active = _reconstruct_active_session(spot, structure_type, session_date.isoformat(), todays_entries, resolved_angler)
    if active is not None:
        st.session_state[active_session_key] = active

# Punch-list #47: surfaced whether building a new session or already inside
# one, so it's never a surprise that someone else is independently fishing
# this same spot right now - each angler's own session (start/add-lure/log
# fish/end/cancel) is fully independent of everyone else's.
_other_open_anglers = _other_anglers_with_open_session(
    spot["spot_id"], session_date.isoformat(), todays_entries, resolved_angler,
)
if _other_open_anglers:
    st.caption(
        f"🎣 {', '.join(_other_open_anglers)} also "
        f"{'has' if len(_other_open_anglers) == 1 else 'have'} an active session here today - "
        "starting, ending, or canceling your own session never affects theirs."
    )

if active is not None:
    st.divider()
    _session_angler = (active.get("base_conditions") or {}).get("angler") or resolved_angler
    st.header(f"🎣 Session in progress{f' - {_session_angler}' if _session_angler else ''}")
    if active.pop("reconstructed", False):
        st.info(
            "Reconnected - picked this session back up from what was already saved "
            "(nothing was lost, but double-check the fish list below matches what you've logged)."
        )
        st.session_state[active_session_key] = active
    score_bit = f" · predicted score {active['predicted_score']}/10" if active.get("predicted_score") is not None else ""
    st.caption(
        f"Started {active['start_time']} · {active['segment_name']} · {active['water_clarity']} water{score_bit}"
    )
    st.caption("Tap a lure below every time you land a fish on it. \"🔄 Change\" retires a lure without ending the session.")

    # Punch-list #58: persistent save-health warning + silent 30s background
    # retry heartbeat - see the block comment above _push_or_toast() for the
    # full "why". Rendered/started once here, right under the session
    # header, so it's visible no matter how far down the angler has
    # scrolled to tap a lure or open "Add a lure to this session."
    _render_push_health_banner()
    _autosave_heartbeat()

    retired_lures = []
    for i, lure in enumerate(active["lures"]):
        if lure.get("retired"):
            retired_lures.append((i, lure))
            continue
        fish_count = sum((f.get("count") or 1) for f in lure["fish"])
        label = f"🎣 {lure['label']}" + (f" ({fish_count} caught)" if fish_count else "")
        lcol1, lcol2 = st.columns([4, 1])
        if lcol1.button(label, key=f"open_fish_dialog_{spot['spot_id']}_{i}", width='stretch'):
            _fish_entry_dialog(spot["spot_id"], i, resolved_angler)
        if lcol2.button("🔄 Change", key=f"retire_lure_{spot['spot_id']}_{i}", width='stretch'):
            _retire_lure(spot["spot_id"], i, resolved_angler)
            st.rerun()
        if lure["fish"]:
            with st.expander(f"Fish caught on {lure['label']} ({fish_count})", expanded=False):
                for fi, fish in enumerate(lure["fish"]):
                    frow1, frow2 = st.columns([5, 1])
                    frow1.write(f"- {', '.join(str(b) for b in _fish_summary_bits(fish))}")
                    if frow2.button("Remove", key=f"remove_active_fish_{spot['spot_id']}_{i}_{fi}"):
                        _remove_fish(spot["spot_id"], i, fi, resolved_angler)
                        st.rerun()

    if retired_lures:
        with st.expander(f"Retired lures ({len(retired_lures)})", expanded=False):
            for i, lure in retired_lures:
                fish_count = sum((f.get("count") or 1) for f in lure["fish"])
                start = lure["entry_kwargs"]["conditions"].get("lure_start_time") or "?"
                end = lure["entry_kwargs"]["conditions"].get("lure_end_time") or "?"
                st.caption(f"{lure['label']} - {fish_count} fish - {start} to {end}")

    st.divider()
    # Punch-list #49: "conditions change on a dime mid-session (fish/forage
    # activity, wind/clouds) - let me adjust these and see quick new lure
    # suggestions and why, without ending the session." A live preview, not
    # a form you submit: every widget below recomputes the score + lure
    # cards (with per-lure "why") on the spot, prefilled from whatever this
    # session's conditions currently are. Tapping "Update conditions" is a
    # separate, deliberate step that bakes the shown values into
    # active["base_conditions"] - only then does any NEW lure you add (from
    # here down, or from "Add a lure to this session" below) pick them up;
    # lures already added keep whatever was true when *they* were added
    # (see _add_lure_to_active_session()'s own docstring). Only exposes the
    # fields that genuinely "change on a dime" - water clarity/temp/depth
    # stay as captured at Start Session, same as before this feature.
    #
    # Punch-list #56: the score updates live as soon as a condition slider
    # moves, but the lure suggestion cards below it are tucked into their
    # OWN nested, collapsed-by-default expander now - most of the time an
    # angler opens this panel just to nudge a reading and re-check the
    # score, planning to keep fishing the same lure, and doesn't want a
    # full recommendation list (with per-lure "why" text) shoving that out
    # of view every time. "🔄 Update conditions" itself stays OUTSIDE that
    # nested expander, directly under the score, so updating conditions and
    # moving on never requires opening the lure suggestions at all.
    with st.expander("🔄 Conditions changed? Get updated suggestions", expanded=False):
        st.caption(
            "Fish/forage activity, wind, and sky conditions can shift fast mid-session - adjust them here to "
            "preview fresh lure suggestions (and why) right away. Tap \"Update conditions\" below to also apply "
            "them to any new lure you add from this point forward; lures you've already added keep what was "
            "true when you added them."
        )
        mc_ns = f"midsession_{spot['spot_id']}_{_angler_session_slug(resolved_angler)}"
        mc_base = active.get("base_conditions") or {}

        fa_key = f"{mc_ns}_fish_activity"
        st.session_state.setdefault(fa_key, mc_base.get("fish_activity") or "Moderate")
        mid_fish_activity = st.select_slider("Fish activity", options=FISH_ACTIVITY_OPTIONS, key=fa_key)
        fo_key = f"{mc_ns}_forage_activity"
        st.session_state.setdefault(fo_key, mc_base.get("forage_activity") or "Moderate")
        mid_forage_activity = st.select_slider("Forage activity", options=FORAGE_ACTIVITY_OPTIONS, key=fo_key)

        mw1, mw2 = st.columns(2)
        wb_key = f"{mc_ns}_wind_band"
        st.session_state.setdefault(wb_key, mc_base.get("wind_band") or WIND_BAND_LABELS[1])
        mid_wind_band = mw1.selectbox("Wind", WIND_BAND_LABELS, help=_wind_help, key=wb_key)
        wd_key = f"{mc_ns}_wind_dir"
        st.session_state.setdefault(wd_key, mc_base.get("wind_direction") or "SW")
        mid_wind_direction = mw2.selectbox("Wind direction", WIND_DIRECTIONS, key=wd_key)

        lc_key = f"{mc_ns}_light_condition"
        st.session_state.setdefault(lc_key, mc_base.get("light_condition") or LIGHT_CONDITIONS[2])
        mid_light_condition = st.selectbox(
            "Sky conditions", LIGHT_CONDITIONS,
            help="\n".join(f"{k} ({v['range']}): {v['detail']}" for k, v in LIGHT_CONDITION_INFO.items()),
            key=lc_key,
        )

        mid_cond = dict(mc_base)
        mid_cond.update({
            "fish_activity": mid_fish_activity, "forage_activity": mid_forage_activity,
            "wind_band": mid_wind_band, "wind_direction": mid_wind_direction,
            "light_condition": mid_light_condition,
        })
        _mid_now = lake_now_naive()
        _mid_segment = _guess_segment(_mid_now.hour, _mid_now)
        mid_water_clarity, mid_season, mid_avg_cloud_pct, mid_avg_wind_mph, mid_rt, mid_score_result = _compute_scoring(
            mid_cond, session_date, bundle, _mid_now, _mid_segment,
        )

        st.divider()
        mm1, mm2 = st.columns([1, 2])
        mm1.metric(
            f"{_mid_segment} activity score", f"{mid_score_result.score}/10",
            help=_score_breakdown_help(mid_score_result.breakdown, mid_score_result.score),
        )
        mm2.write(
            f"**Season:** {mid_season.replace('_', ' ').title()}  \n"
            f"**Structure:** {active['structure_type']}  \n"
            f"**Water clarity:** {mid_water_clarity} (unchanged from session start)"
        )
        if mid_score_result.notes:
            st.caption(" · ".join(mid_score_result.notes))
        for warn in mid_score_result.warnings:
            st.warning(warn)

        mid_rec = recommend(
            mid_season, mid_cond.get("water_temp_f"), _mid_segment, mid_rt["pressure_trend_24h"],
            structure_type=active["structure_type"], water_clarity=mid_water_clarity,
            fish_depth_ft=mid_cond.get("fish_depth_ft"), forage=mid_cond.get("forage_seen"),
            inventory=get_inventory(), trip_history=get_trip_history(), spot_id=spot["spot_id"],
            fish_activity=mid_fish_activity, forage_activity=mid_forage_activity,
            wind_mph=wind_mph_for_band(mid_wind_band),
        )
        with st.expander("🎣 See updated lure suggestions", expanded=False):
            render_lure_recommendation(mid_rec)

        if st.button(
            "🔄 Update conditions", key=f"{mc_ns}_apply", type="primary",
            help="Any lure you add from now on will use these readings; lures already added are untouched.",
        ):
            mid_cond.update({
                "avg_cloud_pct": mid_avg_cloud_pct, "avg_wind_mph": mid_avg_wind_mph,
                "pressure_trend_24h": mid_rt["pressure_trend_24h"] if mid_rt else None,
                "wind_band_logged": mid_wind_band,
            })
            active["base_conditions"] = mid_cond
            st.session_state[active_session_key] = active
            st.success("Saved - any lure you add from here on will use these updated conditions.")

    st.divider()
    with st.expander("➕ Add a lure to this session"):
        inventory_items = get_inventory()
        _multi_lure_picker(
            inventory_items, key_prefix=f"active_lure_picker_{spot['spot_id']}",
            spot_id=spot["spot_id"], seq=0, mode="active", angler=resolved_angler,
        )
        st.markdown("**Not in your inventory?**")
        active_manual_seq_key = f"active_manual_lure_seq_{spot['spot_id']}"
        st.session_state.setdefault(active_manual_seq_key, 0)
        active_manual_seq = st.session_state[active_manual_seq_key]
        amc1, amc2 = st.columns([4, 1])
        active_manual_name = amc1.text_input(
            "Lure name", key=f"active_manual_lure_name_{spot['spot_id']}_{active_manual_seq}",
            label_visibility="collapsed", placeholder="Type a lure name to add it manually",
        )
        if amc2.button("+ Add", key=f"active_manual_lure_add_{spot['spot_id']}_{active_manual_seq}"):
            if active_manual_name.strip():
                st.session_state[active_manual_seq_key] = active_manual_seq + 1
                _handle_lure_add_click(
                    spot["spot_id"], 0, {"item_id": None, "label": active_manual_name.strip(), "category": None},
                    None, "active", resolved_angler,
                )

    st.divider()
    escol1, escol2 = st.columns(2)
    if escol1.button("⏹ End Session", key=f"end_session_{spot['spot_id']}", type="primary", width='stretch'):
        _end_session(spot["spot_id"], resolved_angler)
        st.rerun()

    # "❌ Cancel Session" (punch-list #32) - discards the whole in-progress
    # session instead of finalizing it, for testing sessions or wanting a
    # clean restart without keeping anything logged. This permanently
    # deletes every trip_log.csv row the session created with no undo, so
    # it gets the same two-step "are you sure" confirm Trip History's own
    # "🗑️ Delete this trip" uses, rather than acting on the first click.
    cancel_pending_key = f"cancel_session_confirm_{spot['spot_id']}"
    if not st.session_state.get(cancel_pending_key):
        if escol2.button("❌ Cancel Session", key=f"cancel_session_{spot['spot_id']}", width='stretch'):
            st.session_state[cancel_pending_key] = True
            st.rerun()
    else:
        _cancel_fish_count = sum(
            (f.get("count") or 1) for lure in active["lures"] for f in lure["fish"]
        )
        st.warning(
            f"Cancel this session? This permanently discards everything logged so far - "
            f"{len(active['lures'])} lure(s) and {_cancel_fish_count} fish - and can't be undone."
        )
        ccol1, ccol2 = st.columns(2)
        if ccol1.button("Yes, cancel it", key=f"confirm_cancel_session_{spot['spot_id']}", type="primary", width='stretch'):
            st.session_state.pop(cancel_pending_key, None)
            _cancel_session(spot["spot_id"], resolved_angler)
            st.rerun()
        if ccol2.button("Keep session", key=f"keep_session_{spot['spot_id']}", width='stretch'):
            st.session_state.pop(cancel_pending_key, None)
            st.rerun()

else:
    session_build_seq_key = f"session_build_seq_{spot['spot_id']}"
    # Punch-list #53: only look for a draft to restore when session_state
    # is genuinely fresh for this spot (the key not existing yet means this
    # browser has never rendered a pending build here since it last reset -
    # a real reconnect, not just a normal rerun) - otherwise this would
    # re-apply a stale URL value over whatever's actually live every single
    # render, fighting a manual edit made moments ago.
    _pending_draft = {} if session_build_seq_key in st.session_state else _load_pending_draft(spot["spot_id"])
    st.session_state.setdefault(session_build_seq_key, _pending_draft.get("seq", 0))
    session_build_seq = st.session_state[session_build_seq_key]
    # Only actually usable if its seq still matches - if session_state
    # already had a DIFFERENT (newer) seq for this spot by the time this
    # ran, the draft is for a build that's already moved on.
    if _pending_draft.get("seq") != session_build_seq:
        _pending_draft = {}
    st.session_state.setdefault(_pending_lures_key(spot["spot_id"], session_build_seq), _pending_draft.get("lures", []))

    st.divider()
    st.header("Conditions")
    st.caption(
        "Enter what you're actually seeing at the water - weather-related fields below default from the "
        "live forecast, override any of them if what you see is different. Once you've picked your "
        "lure(s) below, Start Session locks in the exact time and this whole snapshot."
    )
    weather_defaults = _weather_defaults(bundle, session_date, lake_now_naive())
    cond_key_ns = f"cond_{spot['spot_id']}_{session_build_seq}"
    cond_values = render_conditions_block(cond_key_ns, weather_defaults, prefill=_pending_draft.get("cond"))

    _preview_now = lake_now_naive()
    _preview_segment = _guess_segment(_preview_now.hour, _preview_now)
    water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
        cond_values, session_date, bundle, _preview_now, _preview_segment,
    )

    st.divider()
    # Punch-list #33: starts collapsed now (was expanded=True) - the angler's
    # own ask, so the score/lure-suggestion block doesn't take up the whole
    # screen above the actual "Lures for this session" picker every time this
    # page loads; still one tap away whenever it's actually wanted.
    with st.expander("Suggestions for right now", expanded=False):
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
        # Punch-list #37: spot_id lets recommend()'s personal-history boost use
        # the strongest possible match - "have I actually caught fish on this
        # lure AT THIS SPOT before" - not just a general structure-type match.
        # Punch-list #49: fish_activity/forage_activity/wind_mph are Spot
        # Session's own live, on-the-water read (render_conditions_block()'s
        # sliders/wind picker above) - the one thing this page can offer that
        # the 7-Day Forecast page never can, since it's an actual observation,
        # not a forecast.
        rec = recommend(
            season, cond_values["water_temp_f"], _preview_segment, rt["pressure_trend_24h"],
            structure_type=structure_type, water_clarity=water_clarity,
            fish_depth_ft=cond_values.get("fish_depth_ft"), forage=cond_values.get("forage_seen"),
            inventory=inventory_items, trip_history=get_trip_history(), spot_id=spot["spot_id"],
            fish_activity=cond_values.get("fish_activity"), forage_activity=cond_values.get("forage_activity"),
            wind_mph=wind_mph_for_band(cond_values.get("wind_band")),
        )
        _render_recommendation_with_quick_add(rec, spot["spot_id"], session_build_seq, key_prefix=f"quickadd_{spot['spot_id']}_{session_build_seq}")

    st.divider()
    st.markdown("#### Lures for this session")
    pending_lures = st.session_state.get(_pending_lures_key(spot["spot_id"], session_build_seq), [])
    # Punch-list #53: keep the URL's draft in sync with wherever this build
    # actually is right now - conditions form values plus whatever lures
    # are queued so far - every render, so a reconnect at any point (even
    # before a single lure's been picked) restores it instead of starting
    # over blank.
    _save_pending_draft(spot["spot_id"], session_build_seq, cond_values, pending_lures)
    if pending_lures:
        for i, lure in enumerate(pending_lures):
            lcol1, lcol2 = st.columns([5, 1])
            trailer = lure.get("trailer")
            trailer_bit = f" + {trailer['label']} trailer" if trailer else ""
            lcol1.write(f"🎣 {lure['label']}{trailer_bit}")
            if lcol2.button("Remove", key=f"remove_pending_lure_{spot['spot_id']}_{session_build_seq}_{i}"):
                # Removing a lure removes its trailer too, since the trailer
                # is stored nested inside this same pending-list entry, not
                # tracked separately.
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
                st.session_state[manual_seq_key] = manual_seq + 1
                _handle_lure_add_click(
                    spot["spot_id"], session_build_seq,
                    {"item_id": None, "label": manual_name.strip(), "category": None}, None, "pending",
                )

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
        base_conditions = _build_base_conditions(cond_values, avg_cloud_pct, avg_wind_mph, rt, score_result, start_time, segment_name, angler=resolved_angler)
        # Punch-list #55: a real session_id, stamped once here and reused by
        # every lure this session ever writes (including ones added later
        # via _add_lure_to_active_session()) - lets Trip History group every
        # lure/fish from one outing into a single record. Rows written
        # before this existed have no session_id; Trip History treats those
        # as their own single-lure "session" rather than guessing at
        # grouping from date/spot/timestamp proximity (see that page's own
        # docstring for why).
        session_id = str(uuid.uuid4())[:8]

        active_lures = []
        for lure in pending_lures:
            trailer = lure.get("trailer")
            lure_conditions = dict(base_conditions)
            lure_conditions.update({
                "lure_category": lure.get("category"),
                "trailer_used": trailer is not None,
                "trailer_name": trailer.get("label") if trailer else None,
                "trailer_color": trailer.get("color") if trailer else None,
                "trailer_category": trailer.get("category") if trailer else None,
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
                session_id=session_id,
            )
            entry = TripEntry(**entry_kwargs)
            append_trip(entry)
            active_lures.append({
                "trip_id": entry.trip_id, "logged_at": entry.logged_at, "label": lure["label"],
                "item_id": lure.get("item_id"), "entry_kwargs": entry_kwargs, "fish": [], "retired": False,
            })

        st.session_state[active_session_key] = {
            "spot_name": spot["name"],
            "session_date": session_date.isoformat(),
            "start_time": start_time.isoformat(),
            "segment_name": segment_name,
            "structure_type": structure_type,
            "water_clarity": water_clarity,
            "predicted_score": score_result.score,
            # Reused unchanged by _add_lure_to_active_session() for every
            # lure added after Start Session - this session's conditions
            # snapshot/time window are locked in once, not re-captured per
            # lure.
            "base_conditions": base_conditions,
            "lures": active_lures,
            "session_id": session_id,
        }
        st.session_state[session_build_seq_key] = session_build_seq + 1
        # Punch-list #53: this build is no longer "pending" - it's active
        # and durably saved to disk/data branch below, so the draft that
        # was only ever a stand-in for that isn't needed anymore. Leaving
        # it would also risk a stale seq lingering in the URL indefinitely.
        _clear_pending_draft()
        _push_paths = [TRIP_LOG_PATH]
        if _save_new_angler_if_needed():
            _push_paths.append(ANGLERS_PATH)
        _push_or_toast(
            _push_paths, f"Start spot session ({spot['name']}, {len(active_lures)} lure(s))",
            "Session started locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
        )
        st.rerun()
    if not pending_lures:
        st.caption("Select at least one lure above before starting the session.")
