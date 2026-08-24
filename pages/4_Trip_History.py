"""
Trip History - browse, filter, and edit logged sessions.

Punch-list #55 full redesign. Every logged trip - whether from the old
(now-removed) Log a Trip page or the current Spot Session page - lands in
the same shared trip_log.csv via core.storage.TripEntry, so this page
reads and groups all of them together.

--- Sessions, not lure-rows -------------------------------------------------
A single "Spot Session" (one ▶ Start Session through one ⏹ End Session run,
including any lure added mid-session) writes ONE trip_log.csv row PER LURE
fished, all sharing a real `session_id` (see core.storage.TripEntry,
punch-list #55). This page's whole point is to show one RECORD per outing,
not one per lure - `build_sessions()` below groups rows by session_id and
that becomes the unit everything else (filtering, display, editing,
deletion) operates on. A row with no session_id becomes its own
single-lure "session" rather than being guessed into a group.

Rows logged before session_id existed were retroactively backfilled once
(same day punch-list #55 shipped, before any real trips existed with a
session_id already stamped) rather than left permanently ungrouped: every
legacy row was grouped by the exact tuple (trip_date, segment, spot_id,
angler) - not raw logged_at/lure_start_time proximity, which was ruled out
first because a real same-session pair of lure rows can have timestamps
anywhere from ~10 minutes to the full width of a Dawn/Morning/etc. window
apart for the first vs. last lure of a long session. date+segment+spot+
angler is exactly the tuple a live Spot Session run holds fixed for every
lure logged during it, so it's a precise reconstruction of the grouping a
real session_id encodes, not a proximity heuristic - verified against the
real data before running it (every resulting multi-row group's member
timestamps formed one continuous, non-overlapping timeline; none looked
like two distinct outings mashed together). Groups of exactly one row were
left with session_id="" (no behavior change - already handled as solo
above). One acknowledged, unfixed limitation: two genuinely separate
outings by the same angler, at the same spot, in the same time-of-day
segment, on the same calendar date, would be indistinguishable from one
continuous session by this key and would get merged - didn't occur in the
real data checked at backfill time, but a future edit/delete on a session
this old should keep that possibility in mind. Every row logged going
forward gets a real session_id straight from Spot Session - see
pages/6_Spot_Session.py's Start Session handler - so this backfill was a
one-time correction, not an ongoing heuristic.

--- Editing scope (deliberate, documented boundaries) ------------------------
This page is now the ONLY place a logged trip is edited - the old
"Edit this trip" -> Spot Session handoff (and its query-param plumbing) is
gone entirely (see pages/6_Spot_Session.py, punch-list #55). Editing a
session covers: date, time-of-day window, angler, structure type, every
observed condition (water temp/clarity/stain/stirred-up, wind, sky,
precipitation, forage seen, fish/forage activity, fish depth), and per
lure: lure/color/technique, trailer, notes, and the full per-fish catch
list (add/edit/remove). A few things are deliberately OUT of scope, same
spirit as the old grid's own documented limitations:
  - Location (spot_id) stays read-only - remapping it would need to also
    reconsider structure_type/water_clarity implications tied to the spot
    itself, not something this round's ask covers.
  - predicted_score, and the informational-only avg_cloud_pct/avg_wind_mph/
    pressure_trend_24h/moon_phase readouts, stay exactly as originally
    recorded - they're what the forecast/scoring engine actually computed
    at logging time, not something to silently recompute from an edited
    condition. Editing "Wind" here corrects what you observed; it doesn't
    retroactively re-score the trip.
  - lure_start_time/lure_end_time/session_end_time stay read-only - shown
    for reference, not editable here.
  - This page edits SESSION-level conditions once and applies them to
    EVERY lure in that session uniformly. A session where the angler used
    Spot Session's "🔄 Conditions changed? Get updated suggestions"
    mid-session (punch-list #49) can have per-lure divergence in
    fish_activity/forage_activity/wind/sky between lures added before vs.
    after that update - saving an edit here flattens that back to one
    shared value across the whole session. Narrow edge case, not handled
    specially.

The "Location" filter/display resolves each trip's `spot_id` against the
angler's *current* saved-spot catalog (core.lake_spots / data/lake_spots.csv)
rather than trusting the `spot_name` string frozen into the trip row at
logging time - so if a spot gets renamed later, older trips logged against
it still group under its current name instead of splintering into a
separate filter entry per historical name. Falls back to the row's stored
`spot_name` for trips whose `spot_id` no longer matches any saved spot
(a deleted pin, or a legacy row logged against core.spots's separate
reference-spot list).
"""
import json
from datetime import datetime, time as dtime

import pandas as pd
import streamlit as st

from core.appstate import get_lake_spots, get_weather_bundle, get_anglers, github_token, repo_slug
from core.storage import (
    read_all_trips, delete_trip, update_trip, TripEntry, TRIP_LOG_PATH, commit_and_push_data,
)
from core.lures import LURE_PROFILES, STRUCTURE_TYPES, FORAGE_OPTIONS
from core.onwater import (
    LIGHT_CONDITIONS, WIND_BAND_LABELS, WIND_DIRECTIONS, STAIN_COLOR_OPTIONS,
    PRECIPITATION_OPTIONS, resolve_water_clarity,
)
from core.activity_log import (
    FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS, RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
    FISH_SPECIES_OPTIONS, HIT_TYPE_OPTIONS, format_weight_lb_oz, parse_weight_lb_oz,
)
from core.scoring import SEGMENTS, segment_time_ranges
from core.weather import lake_today
from core.ui import inject_mobile_css

st.set_page_config(page_title="Trip History - Nolin Lake", page_icon="📊", layout="wide")
inject_mobile_css()
st.title("📊 Trip History")
st.caption("Filter down to the sessions you want, then open one to see (and edit) everything about it.")

rows = read_all_trips()

if not rows:
    st.info(
        "No trips logged yet. Head to **Lake Map**, pick (or drop) a spot, then use "
        "**Spot Session** to fish it and log what happens."
    )
    st.stop()


# ==============================================================================
# Pure helpers (no Streamlit calls) - kept free of st.* so this logic can be
# exercised by a scratch script without spinning up a script run, same
# convention as this page's previous grid-diff helpers.
# ==============================================================================
def _parse_date(s: str):
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _parse_conditions(row: dict) -> dict:
    try:
        return json.loads(row["conditions_json"]) if row.get("conditions_json") else {}
    except json.JSONDecodeError:
        return {}


def _lure_type_label(cond: dict) -> str:
    category = cond.get("lure_category")
    if not category:
        return "Unspecified / manual entry"
    return LURE_PROFILES.get(category, {}).get("name", category)


def _format_fish_caught_at(iso_time_str) -> str:
    try:
        return dtime.fromisoformat(iso_time_str).strftime("%-I:%M %p")
    except (TypeError, ValueError):
        return None


def _fish_summary_bits(fish: dict) -> list:
    count = fish.get("count") or 1
    species_label = fish.get("species") or "Unknown species"
    bits = [f"{count} x {species_label}" if count > 1 else species_label]
    caught_at_label = _format_fish_caught_at(fish.get("caught_at"))
    if caught_at_label:
        bits.append(caught_at_label)
    if fish.get("weight_lb"):
        weight_str = format_weight_lb_oz(fish["weight_lb"])
        bits.append(f"~{weight_str} each" if count > 1 else weight_str)
    if fish.get("length_in"):
        bits.append(f"{fish['length_in']:g} in")
    if fish.get("depth_ft"):
        bits.append(f"{fish['depth_ft']:g} ft deep")
    if fish.get("hit_types"):
        bits.append(", ".join(fish["hit_types"]))
    presentation = " / ".join(x for x in [fish.get("retrieve_speed"), fish.get("retrieve_style")] if x)
    if presentation:
        bits.append(presentation)
    return bits


def _derive_fish_totals(fish_list: list) -> tuple:
    """(fish_caught, biggest_fish_lb) derived from a structured fish list -
    the same math Spot Session's _record_fish()/_remove_fish() use, so a
    session edited here stays internally consistent with how a live session
    computes these two same columns."""
    if not fish_list:
        return 0, None
    fish_caught = sum((f.get("count") or 1) for f in fish_list)
    weights = [f["weight_lb"] for f in fish_list if f.get("weight_lb")]
    biggest = max(weights) if weights else None
    return fish_caught, biggest


def _session_group_key(row: dict) -> str:
    """Real session_id when present (punch-list #55); otherwise a synthetic,
    guaranteed-unique key so a legacy/solo row becomes its own one-lure
    "session" rather than being silently merged with anything else."""
    sid = (row.get("session_id") or "").strip()
    return sid if sid else f"solo:{row.get('trip_id')}"


def _sort_key_for_member(row: dict) -> str:
    cond = row.get("_conditions") or {}
    return cond.get("lure_start_time") or row.get("logged_at") or ""


def build_sessions(enriched_rows: list) -> list:
    """Groups already-enriched trip rows (each must already carry _date/
    _conditions/_location/_angler/_lure_type - see the enrichment loop
    below) into one dict per session:

      {session_key, rows (member rows, sorted by lure start time), date,
       segment, location, angler, structure_type, fish_total,
       lure_labels (list), lure_types (set), specific_lures (set)}

    date/segment/location/angler/structure_type are taken from whichever
    member row has the EARLIEST _sort_key_for_member (the session's first
    lure) - representative of the session as a whole. fish_total sums
    fish_caught across every member row."""
    groups = {}
    for row in enriched_rows:
        key = _session_group_key(row)
        groups.setdefault(key, []).append(row)

    sessions = []
    for key, members in groups.items():
        members_sorted = sorted(members, key=_sort_key_for_member)
        first = members_sorted[0]
        fish_total = 0
        for m in members:
            try:
                fish_total += int(m.get("fish_caught") or 0)
            except (TypeError, ValueError):
                pass
        sessions.append({
            "session_key": key,
            "rows": members_sorted,
            "date": first["_date"],
            "segment": first.get("segment"),
            "location": first["_location"],
            "angler": first["_angler"],
            "structure_type": first.get("structure_type"),
            "fish_total": fish_total,
            "lure_labels": [m.get("lure_used") or "Unspecified" for m in members_sorted],
            "lure_types": {m["_lure_type"] for m in members},
            "specific_lures": {m.get("lure_used") for m in members if m.get("lure_used")},
        })
    return sessions


def segment_display_label(name, seg_ranges):
    if seg_ranges and name in seg_ranges:
        s, e = seg_ranges[name]
        return f"{name} ({s.strftime('%-I:%M %p')}-{e.strftime('%-I:%M %p')})"
    return name


def segment_label_maps(canonical_options, seg_ranges):
    label_by_name = {name: segment_display_label(name, seg_ranges) for name in canonical_options}
    name_by_label = {label: name for name, label in label_by_name.items()}
    return label_by_name, name_by_label


# ==============================================================================
# Enrichment + session grouping
# ==============================================================================
spot_name_by_id = {s["spot_id"]: s["name"] for s in get_lake_spots()}


def _location_label(row: dict) -> str:
    return spot_name_by_id.get(row.get("spot_id")) or row.get("spot_name") or "Unknown location"


for row in rows:
    row["_date"] = _parse_date(row.get("trip_date"))
    row["_conditions"] = _parse_conditions(row)
    row["_lure_type"] = _lure_type_label(row["_conditions"])
    row["_location"] = _location_label(row)
    row["_angler"] = row["_conditions"].get("angler") or ""

sessions = build_sessions(rows)

try:
    _th_bundle = get_weather_bundle(7)
except Exception:
    _th_bundle = None
_th_seg_ranges = segment_time_ranges(_th_bundle, lake_today())


# ==============================================================================
# Filters - deliberately few, per punch-list #55: date range (single date
# allowed), time of day, location, angler, lure type, specific lure. Each
# multiselect defaults to "all" (empty selection = no filtering on that
# field). Results stay hidden until "See Trips" is pressed at least once;
# after that, changing a filter live-updates the same visible results (no
# need to press the button again).
# ==============================================================================
st.subheader("Filters")

valid_dates = [s["date"] for s in sessions if s["date"] is not None]
min_date, max_date = (min(valid_dates), max(valid_dates)) if valid_dates else (None, None)
# Today should always be pickable even if it has no logged sessions yet (an
# in-progress day's trips aren't in trip_log.csv until Spot Session ends) -
# so the upper bound is the later of the latest logged date and today, not
# just whatever's already been logged.
_today = lake_today()
max_pickable_date = max(max_date, _today) if max_date else _today
min_pickable_date = min(min_date, _today) if min_date else _today

f1, f2, f3 = st.columns(3)
date_range = f1.date_input(
    "Date range", value=(min_date, max_date) if min_date else (_today, _today),
    min_value=min_pickable_date, max_value=max_pickable_date,
    help="Pick a single date, or a start and end date for a range.",
)

segment_options = sorted({s["segment"] for s in sessions if s["segment"]})
segments = f2.multiselect(
    "Time of day", segment_options, default=[],
    format_func=lambda name: segment_display_label(name, _th_seg_ranges),
    help="Clock ranges shown are today's actual sunrise/sunset-derived windows, as a reference point.",
)
location_options = sorted({s["location"] for s in sessions if s["location"]})
locations = f3.multiselect("Location", location_options, default=[])

f4, f5, f6 = st.columns(3)
angler_options = sorted({s["angler"] for s in sessions if s["angler"]})
anglers = f4.multiselect("Angler", angler_options, default=[])
lure_type_options = sorted({lt for s in sessions for lt in s["lure_types"] if lt})
lure_types = f5.multiselect("Lure type", lure_type_options, default=[])
specific_lure_options = sorted({lu for s in sessions for lu in s["specific_lures"] if lu})
specific_lures = f6.multiselect("Specific lure", specific_lure_options, default=[])


def _session_matches(s: dict) -> bool:
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        if s["date"] is None or not (start <= s["date"] <= end):
            return False
    elif date_range and isinstance(date_range, tuple) and len(date_range) == 1:
        # A single date picked in the range-style widget (either the user's
        # first click before picking an end date, or a deliberate single-day
        # "range") - Streamlit represents this as a 1-tuple rather than a
        # bare date. Treat it as "exactly this one date," same as the plain
        # (non-tuple) case below.
        if s["date"] != date_range[0]:
            return False
    elif date_range and not isinstance(date_range, tuple):
        if s["date"] != date_range:
            return False
    if segments and s["segment"] not in segments:
        return False
    if locations and s["location"] not in locations:
        return False
    if anglers and s["angler"] not in anglers:
        return False
    if lure_types and not (s["lure_types"] & set(lure_types)):
        return False
    if specific_lures and not (s["specific_lures"] & set(specific_lures)):
        return False
    return True


st.session_state.setdefault("trip_history_see_trips", False)
if st.button("🔍 See Trips", type="primary"):
    st.session_state["trip_history_see_trips"] = True

if not st.session_state["trip_history_see_trips"]:
    st.caption("Set your filters above, then press **See Trips** to pull up matching sessions.")
    st.stop()

filtered_sessions = [s for s in sessions if _session_matches(s)]
filtered_sessions.sort(key=lambda s: (s["date"] or datetime.min.date(), _sort_key_for_member(s["rows"][0])), reverse=True)

st.caption(f"Showing {len(filtered_sessions)} of {len(sessions)} sessions.")

if not filtered_sessions:
    st.warning("No sessions match these filters.")
    st.stop()


# ==============================================================================
# One card per session - date/time/location/angler/fish-count header, expand
# for full detail + editing. Plain widgets (no st.data_editor) - matches
# this app's established mobile-friendly pattern (Development page, Spot
# Session) rather than a wide grid needing sideways swiping.
# ==============================================================================
def _angler_options_for(current: str) -> list:
    roster = get_anglers()
    opts = list(roster)
    if current and current not in opts:
        opts.append(current)
    if "" not in opts:
        opts = [""] + opts
    return opts


def _push(paths, message):
    token = github_token()
    if token:
        return commit_and_push_data(paths, token, repo_slug(), message)
    return True, None


def _render_fish_editor(ns: str, existing_fish: list) -> list:
    """Renders every existing fish as editable widgets (species/weight/
    length/hit types/retrieve style+speed), each with a "Remove this fish"
    checkbox, plus an "Add a fish" mini-form that appends new blank slots
    to session_state immediately (before the session's own Save button is
    ever pressed) - same "append to a session_state list, mutate freely,
    read it all back on Save" pattern Spot Session's own edit flow used.
    Returns the CURRENT list of fish dicts read straight from this run's
    widget values (skipping any checked "Remove"), for the caller to save."""
    list_key = f"{ns}_fish_list"
    st.session_state.setdefault(list_key, list(existing_fish) if existing_fish else [])
    fish_list = st.session_state[list_key]

    kept = []
    for i, fish in enumerate(fish_list):
        with st.container(border=True):
            remove = st.checkbox("Remove this fish", key=f"{ns}_fish_{i}_remove", value=False)
            species_default = fish.get("species") or FISH_SPECIES_OPTIONS[0]
            species_idx_default = (
                FISH_SPECIES_OPTIONS.index(species_default) if species_default in FISH_SPECIES_OPTIONS
                else len(FISH_SPECIES_OPTIONS) - 1
            )
            sc1, sc2 = st.columns(2)
            species_idx = sc1.selectbox(
                "Species", options=list(range(len(FISH_SPECIES_OPTIONS))),
                format_func=lambda j: FISH_SPECIES_OPTIONS[j], index=species_idx_default,
                key=f"{ns}_fish_{i}_species",
            )
            species_label = FISH_SPECIES_OPTIONS[species_idx]
            species_other = ""
            if species_label == "Other (type in species)":
                species_other = sc2.text_input(
                    "Species (type it in)",
                    value=fish.get("species_other") or (fish.get("species") if species_default not in FISH_SPECIES_OPTIONS else ""),
                    key=f"{ns}_fish_{i}_species_other",
                )
            wc1, wc2, wc3 = st.columns(3)
            weight_text = wc1.text_input(
                "Weight", value=format_weight_lb_oz(fish.get("weight_lb")) if fish.get("weight_lb") else "",
                placeholder="e.g. 3 lb 8 oz", key=f"{ns}_fish_{i}_weight",
            )
            length_in = wc2.number_input(
                "Length (in)", min_value=0.0, max_value=40.0, step=0.5,
                value=float(fish.get("length_in") or 0.0), key=f"{ns}_fish_{i}_length",
            )
            count = wc3.number_input(
                "Count", min_value=1, step=1, value=int(fish.get("count") or 1), key=f"{ns}_fish_{i}_count",
                help="More than 1 for a group of same-size fish logged together.",
            )
            hit_types = st.pills(
                "Type of hit", HIT_TYPE_OPTIONS, selection_mode="multi",
                default=fish.get("hit_types") or [], key=f"{ns}_fish_{i}_hit_types",
            )
            rc1, rc2 = st.columns(2)
            retrieve_style_default = fish.get("retrieve_style") if fish.get("retrieve_style") in RETRIEVE_STYLE_OPTIONS else RETRIEVE_STYLE_OPTIONS[0]
            retrieve_style = rc1.selectbox(
                "Retrieve style", RETRIEVE_STYLE_OPTIONS, index=RETRIEVE_STYLE_OPTIONS.index(retrieve_style_default),
                key=f"{ns}_fish_{i}_style",
            )
            retrieve_speed_default = fish.get("retrieve_speed") if fish.get("retrieve_speed") in RETRIEVE_SPEED_OPTIONS else RETRIEVE_SPEED_OPTIONS[1]
            retrieve_speed = rc2.selectbox(
                "Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=RETRIEVE_SPEED_OPTIONS.index(retrieve_speed_default),
                key=f"{ns}_fish_{i}_speed",
            )
            if remove:
                continue
            species_final = species_other.strip() if (species_label == "Other (type in species)" and species_other.strip()) else species_label
            new_fish = dict(fish)
            new_fish.update({
                "species": species_final,
                "species_other": species_other or None,
                "count": int(count),
                "weight_lb": parse_weight_lb_oz(weight_text) if weight_text.strip() else None,
                "length_in": length_in or None,
                "hit_types": hit_types,
                "retrieve_style": retrieve_style,
                "retrieve_speed": retrieve_speed,
            })
            kept.append(new_fish)

    with st.expander("➕ Add a fish"):
        seq_key = f"{ns}_new_fish_seq"
        st.session_state.setdefault(seq_key, 0)
        seq = st.session_state[seq_key]
        species_idx = st.selectbox(
            "Species", options=list(range(len(FISH_SPECIES_OPTIONS))), format_func=lambda j: FISH_SPECIES_OPTIONS[j],
            key=f"{ns}_addfish_{seq}_species",
        )
        species_label = FISH_SPECIES_OPTIONS[species_idx]
        species_other = ""
        if species_label == "Other (type in species)":
            species_other = st.text_input("Species (type it in)", key=f"{ns}_addfish_{seq}_species_other")
        awc1, awc2, awc3 = st.columns(3)
        weight_text = awc1.text_input("Weight", placeholder="e.g. 3 lb 8 oz", key=f"{ns}_addfish_{seq}_weight")
        length_in = awc2.number_input("Length (in)", min_value=0.0, max_value=40.0, step=0.5, key=f"{ns}_addfish_{seq}_length")
        count = awc3.number_input("Count", min_value=1, step=1, value=1, key=f"{ns}_addfish_{seq}_count")
        hit_types = st.pills("Type of hit", HIT_TYPE_OPTIONS, selection_mode="multi", key=f"{ns}_addfish_{seq}_hit_types")
        arc1, arc2 = st.columns(2)
        retrieve_style = arc1.selectbox("Retrieve style", RETRIEVE_STYLE_OPTIONS, key=f"{ns}_addfish_{seq}_style")
        retrieve_speed = arc2.selectbox("Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=1, key=f"{ns}_addfish_{seq}_speed")
        if st.button("Add fish", key=f"{ns}_addfish_{seq}_button", type="primary", width="stretch"):
            species_final = species_other.strip() if (species_label == "Other (type in species)" and species_other.strip()) else species_label
            fish_list.append({
                "species": species_final, "species_other": species_other or None, "count": int(count),
                "weight_lb": parse_weight_lb_oz(weight_text) if weight_text.strip() else None,
                "length_in": length_in or None, "hit_types": hit_types,
                "retrieve_style": retrieve_style, "retrieve_speed": retrieve_speed,
            })
            st.session_state[list_key] = fish_list
            st.session_state[seq_key] = seq + 1
            st.rerun()

    return kept


def _render_session_card(session: dict):
    ns = f"th_{session['session_key']}"
    first_row = session["rows"][0]
    cond = first_row["_conditions"]

    st.markdown("#### Session")
    ec1, ec2 = st.columns(2)
    edit_date = ec1.date_input("Date", value=session["date"] or lake_today(), max_value=lake_today(), key=f"{ns}_date")
    segment_canon = SEGMENTS if not session["segment"] or session["segment"] in SEGMENTS else SEGMENTS + [session["segment"]]
    label_by_name, name_by_label = segment_label_maps(segment_canon, _th_seg_ranges)
    seg_default = session["segment"] if session["segment"] in segment_canon else SEGMENTS[0]
    seg_label = ec2.selectbox(
        "Time of day", [label_by_name[n] for n in segment_canon],
        index=segment_canon.index(seg_default), key=f"{ns}_segment",
    )
    edit_segment = name_by_label[seg_label]

    ac1, ac2 = st.columns(2)
    angler_opts = _angler_options_for(session["angler"])
    edit_angler = ac1.selectbox("Angler", angler_opts, index=angler_opts.index(session["angler"]) if session["angler"] in angler_opts else 0, key=f"{ns}_angler")
    structure_default = session["structure_type"] if session["structure_type"] in STRUCTURE_TYPES else STRUCTURE_TYPES[0]
    edit_structure = ac2.selectbox("Structure type", STRUCTURE_TYPES, index=STRUCTURE_TYPES.index(structure_default), key=f"{ns}_structure")

    st.caption(f"📍 Location: **{session['location']}** (not editable here)")

    st.markdown("##### Conditions")
    cc1, cc2, cc3 = st.columns(3)
    edit_water_temp = cc1.number_input("Water temp (°F)", min_value=32.0, max_value=100.0, step=0.5, value=float(cond.get("water_temp_f") or 75.0), key=f"{ns}_watertemp")
    edit_secchi = cc2.number_input("Water clarity - Secchi depth (ft)", min_value=0.0, max_value=20.0, step=0.5, value=float(cond.get("secchi_ft") or 2.5), key=f"{ns}_secchi")
    stain_default = cond.get("stain_color") if cond.get("stain_color") in STAIN_COLOR_OPTIONS else STAIN_COLOR_OPTIONS[0]
    edit_stain = cc3.selectbox("Base stain color", STAIN_COLOR_OPTIONS, index=STAIN_COLOR_OPTIONS.index(stain_default), key=f"{ns}_stain")
    edit_stirred = st.checkbox("Stirred up / muddy at the time (overrides Secchi reading)", value=bool(cond.get("stirred_up")), key=f"{ns}_stirred")
    resolved_clarity = resolve_water_clarity(edit_secchi, edit_stain, edit_stirred)
    st.caption(f"Resolved water clarity: **{resolved_clarity}**")

    wc1, wc2, wc3 = st.columns(3)
    wind_default = cond.get("wind_band") if cond.get("wind_band") in WIND_BAND_LABELS else WIND_BAND_LABELS[1]
    edit_wind_band = wc1.selectbox("Wind", WIND_BAND_LABELS, index=WIND_BAND_LABELS.index(wind_default), key=f"{ns}_wind_band")
    wind_dir_default = cond.get("wind_direction") if cond.get("wind_direction") in WIND_DIRECTIONS else WIND_DIRECTIONS[0]
    edit_wind_direction = wc2.selectbox("Wind direction", WIND_DIRECTIONS, index=WIND_DIRECTIONS.index(wind_dir_default), key=f"{ns}_wind_dir")
    light_default = cond.get("light_condition") if cond.get("light_condition") in LIGHT_CONDITIONS else LIGHT_CONDITIONS[0]
    edit_light = wc3.selectbox("Sky condition", LIGHT_CONDITIONS, index=LIGHT_CONDITIONS.index(light_default), key=f"{ns}_light")

    pc1, pc2 = st.columns(2)
    precip_default = cond.get("precipitation") if cond.get("precipitation") in PRECIPITATION_OPTIONS else PRECIPITATION_OPTIONS[0]
    edit_precip = pc1.selectbox("Precipitation", PRECIPITATION_OPTIONS, index=PRECIPITATION_OPTIONS.index(precip_default), key=f"{ns}_precip")
    edit_fish_depth = pc2.number_input("Fish holding depth (ft)", min_value=0.0, max_value=100.0, step=0.5, value=float(cond.get("fish_depth_ft") or 0.0), key=f"{ns}_fishdepth")

    forage_default = [f for f in (cond.get("forage_seen") or []) if f in FORAGE_OPTIONS]
    edit_forage = st.multiselect("Forage seen", FORAGE_OPTIONS, default=forage_default, key=f"{ns}_forage")

    ac3, ac4 = st.columns(2)
    fish_act_default = cond.get("fish_activity") if cond.get("fish_activity") in FISH_ACTIVITY_OPTIONS else FISH_ACTIVITY_OPTIONS[2]
    edit_fish_activity = ac3.selectbox("Fish activity", FISH_ACTIVITY_OPTIONS, index=FISH_ACTIVITY_OPTIONS.index(fish_act_default), key=f"{ns}_fishact")
    forage_act_default = cond.get("forage_activity") if cond.get("forage_activity") in FORAGE_ACTIVITY_OPTIONS else FORAGE_ACTIVITY_OPTIONS[1]
    edit_forage_activity = ac4.selectbox("Forage activity", FORAGE_ACTIVITY_OPTIONS, index=FORAGE_ACTIVITY_OPTIONS.index(forage_act_default), key=f"{ns}_forageact")

    st.caption(
        "Predicted score, and the cloud%/wind-mph/pressure-trend/moon-phase readouts, stay exactly as "
        "originally recorded - editing conditions here corrects what you observed, it doesn't re-run the "
        "scoring engine."
    )

    st.divider()
    st.markdown("##### Lures fished this session")
    lure_edits = []
    for row in session["rows"]:
        lure_cond = row["_conditions"]
        lns = f"{ns}_lure_{row['trip_id']}"
        with st.container(border=True):
            lc1, lc2, lc3 = st.columns(3)
            edit_lure_used = lc1.text_input("Lure", value=row.get("lure_used") or "", key=f"{lns}_name")
            edit_color_used = lc2.text_input("Color", value=row.get("color_used") or "", key=f"{lns}_color")
            edit_technique = lc3.text_input("Technique", value=row.get("technique_used") or "", key=f"{lns}_technique")

            tc1, tc2, tc3 = st.columns(3)
            edit_trailer_used = tc1.checkbox("Used a trailer", value=bool(lure_cond.get("trailer_used")), key=f"{lns}_trailer_used")
            edit_trailer_name = tc2.text_input("Trailer", value=lure_cond.get("trailer_name") or "", key=f"{lns}_trailer_name", disabled=not edit_trailer_used)
            edit_trailer_color = tc3.text_input("Trailer color", value=lure_cond.get("trailer_color") or "", key=f"{lns}_trailer_color", disabled=not edit_trailer_used)

            edit_notes = st.text_area("Notes", value=row.get("notes") or "", key=f"{lns}_notes")

            start_bit = lure_cond.get("lure_start_time")
            end_bit = lure_cond.get("lure_end_time")
            st.caption(f"Started {start_bit or '?'} · Ended {end_bit or 'still open'} (times aren't editable here)")

            is_structured = isinstance(lure_cond.get("fish"), list) and lure_cond.get("source") == "spot_session"
            st.markdown("**Fish caught**")
            if is_structured:
                edited_fish = _render_fish_editor(lns, lure_cond.get("fish") or [])
                fish_caught, biggest_fish_lb = _derive_fish_totals(edited_fish)
                st.caption(f"{fish_caught} fish from this lure, biggest {format_weight_lb_oz(biggest_fish_lb)}" if biggest_fish_lb else f"{fish_caught} fish from this lure")
            else:
                edited_fish = lure_cond.get("fish")  # legacy rows: leave whatever (usually absent) untouched
                fcc1, fcc2 = st.columns(2)
                fish_caught = fcc1.number_input("Fish caught", min_value=0, step=1, value=int(row.get("fish_caught") or 0), key=f"{lns}_fish_caught_flat")
                biggest_text = fcc2.text_input(
                    "Biggest fish", value=format_weight_lb_oz(row.get("biggest_fish_lb")) if row.get("biggest_fish_lb") else "",
                    placeholder="e.g. 3 lb 8 oz", key=f"{lns}_biggest_flat",
                )
                biggest_fish_lb = parse_weight_lb_oz(biggest_text) if biggest_text.strip() else None

            lure_edits.append({
                "trip_id": row["trip_id"], "logged_at": row.get("logged_at"), "spot_id": row.get("spot_id"),
                "spot_name": row.get("spot_name"), "predicted_score": row.get("predicted_score"),
                "raw_conditions": lure_cond, "lure_used": edit_lure_used, "color_used": edit_color_used,
                "technique_used": edit_technique, "notes": edit_notes, "trailer_used": edit_trailer_used,
                "trailer_name": edit_trailer_name if edit_trailer_used else None,
                "trailer_color": edit_trailer_color if edit_trailer_used else None,
                "fish": edited_fish, "fish_caught": fish_caught, "biggest_fish_lb": biggest_fish_lb,
            })

    st.divider()
    save_col, delete_col = st.columns(2)
    if save_col.button("💾 Save changes", key=f"{ns}_save", type="primary", width="stretch"):
        shared_updates = {
            "water_temp_f": edit_water_temp, "secchi_ft": edit_secchi, "stain_color": edit_stain,
            "stirred_up": edit_stirred, "wind_band": edit_wind_band, "wind_direction": edit_wind_direction,
            "light_condition": edit_light, "precipitation": edit_precip, "forage_seen": edit_forage,
            "fish_activity": edit_fish_activity, "forage_activity": edit_forage_activity,
            "fish_depth_ft": edit_fish_depth, "angler": edit_angler,
        }
        saved_ids, missing_ids = [], []
        for le in lure_edits:
            new_cond = dict(le["raw_conditions"])
            new_cond.update(shared_updates)
            new_cond["trailer_used"] = le["trailer_used"]
            new_cond["trailer_name"] = le["trailer_name"]
            new_cond["trailer_color"] = le["trailer_color"]
            if le["fish"] is not None:
                new_cond["fish"] = le["fish"]
            raw_score = le["predicted_score"]
            entry = TripEntry(
                trip_date=edit_date.isoformat(), segment=edit_segment, spot_id=le["spot_id"],
                spot_name=le["spot_name"], structure_type=edit_structure, water_clarity=resolved_clarity,
                lure_used=le["lure_used"], color_used=le["color_used"], technique_used=le["technique_used"],
                fish_caught=le["fish_caught"], biggest_fish_lb=le["biggest_fish_lb"],
                predicted_score=float(raw_score) if raw_score not in (None, "") and not pd.isna(raw_score) else None,
                conditions=new_cond, notes=le["notes"], trip_id=le["trip_id"], logged_at=le["logged_at"] or "",
                session_id=session["session_key"] if not session["session_key"].startswith("solo:") else "",
            )
            if update_trip(entry):
                saved_ids.append(le["trip_id"])
            else:
                missing_ids.append(le["trip_id"])
        if saved_ids:
            _push([TRIP_LOG_PATH], f"Update session {session['session_key']} via Trip History ({len(saved_ids)} lure row(s))")
            st.toast(f"Saved {len(saved_ids)} lure row(s).", icon="✅")
        if missing_ids:
            st.toast("Couldn't save some rows - they may have been deleted elsewhere.", icon="⚠️")
        st.rerun()

    delete_pending_key = f"{ns}_delete_confirm"
    if not st.session_state.get(delete_pending_key):
        if delete_col.button("🗑️ Delete this session", key=f"{ns}_delete", width="stretch"):
            st.session_state[delete_pending_key] = True
            st.rerun()
    else:
        st.warning(
            f"Delete this whole session permanently? This removes all {len(session['rows'])} lure row(s) "
            "and every fish logged on them. This can't be undone."
        )
        dc1, dc2 = st.columns(2)
        if dc1.button("Yes, delete it", key=f"{ns}_confirm_delete", type="primary", width="stretch"):
            deleted = [delete_trip(r["trip_id"]) for r in session["rows"]]
            if any(deleted):
                _push([TRIP_LOG_PATH], f"Delete session {session['session_key']} via Trip History ({sum(deleted)} row(s))")
                st.toast("Session deleted.", icon="✅")
            else:
                st.toast("Couldn't find that session - it may have already been removed.", icon="⚠️")
            st.session_state.pop(delete_pending_key, None)
            st.rerun()
        if dc2.button("Cancel", key=f"{ns}_cancel_delete", width="stretch"):
            st.session_state.pop(delete_pending_key, None)
            st.rerun()


for session in filtered_sessions:
    date_bit = session["date"].isoformat() if session["date"] else "Unknown date"
    lure_summary = ", ".join(session["lure_labels"][:3]) + ("…" if len(session["lure_labels"]) > 3 else "")
    title = (
        f"{date_bit} · {session['segment'] or '?'} · {session['location']} · "
        f"{session['angler'] or 'Unspecified angler'} · {session['fish_total']} fish"
    )
    with st.expander(title):
        st.caption(f"Lure(s): {lure_summary}")
        _render_session_card(session)
