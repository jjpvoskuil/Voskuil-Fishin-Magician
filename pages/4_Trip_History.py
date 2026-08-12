"""
Trip History & Model Calibration.

Every logged trip - whether from the old (now-removed) Log a Trip page or
the current Spot Session page - lands in the same shared trip_log.csv via
core.storage.TripEntry, so this page reads and filters all of them
together. Spot Session rows carry a much richer `conditions` dict (water
temp, wind band, retrieve style, etc. - see core/activity_log.py and
core/onwater.py); legacy rows carry a smaller, different set of keys (e.g.
modeled_thermocline_band_ft). The "Trip details" expander below renders
whatever keys are actually present for a given row and skips the rest, so
both kinds of entries display sensibly without special-casing.

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
from datetime import datetime

import pandas as pd
import streamlit as st

from core.appstate import get_lake_spots
from core.storage import read_all_trips
from core.calibration import calibration_summary, MIN_SAMPLES_PER_SIDE
from core.lures import LURE_PROFILES

st.set_page_config(page_title="Trip History - Nolin Lake", page_icon="📊", layout="wide")
st.title("📊 Trip History & Model Calibration")

rows = read_all_trips()

if not rows:
    st.info(
        "No trips logged yet. Head to **Lake Map**, pick (or drop) a spot, then use "
        "**Spot Session** to fish it and log what happens."
    )
    st.stop()


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


spot_name_by_id = {s["spot_id"]: s["name"] for s in get_lake_spots()}


def _location_label(row: dict) -> str:
    """Current saved-spot name for this trip's spot_id, falling back to
    whatever spot_name was stored at logging time if that spot_id isn't (or
    is no longer) in the saved-spot catalog."""
    return spot_name_by_id.get(row.get("spot_id")) or row.get("spot_name") or "Unknown location"


# Parse once up front so every row has a usable date, a conditions dict, a
# derived lure-type label, and a resolved location name available for both
# filtering and display.
for row in rows:
    row["_date"] = _parse_date(row.get("trip_date"))
    row["_conditions"] = _parse_conditions(row)
    row["_lure_type"] = _lure_type_label(row["_conditions"])
    row["_location"] = _location_label(row)

df = pd.DataFrame(rows)

# --- Filters -----------------------------------------------------------------
st.subheader("Filters")

valid_dates = [d for d in df["_date"] if d is not None]
min_date, max_date = (min(valid_dates), max(valid_dates)) if valid_dates else (None, None)

f1, f2, f3 = st.columns(3)
date_range = f1.date_input(
    "Date range", value=(min_date, max_date) if min_date else None,
    min_value=min_date, max_value=max_date,
) if min_date else None
segment_options = sorted(df["segment"].dropna().unique().tolist())
segments = f2.multiselect("Time of day", segment_options, default=[])
spot_options = sorted(df["_location"].dropna().unique().tolist())
spots = f3.multiselect("Location", spot_options, default=[])

f4, f5, f6 = st.columns(3)
lure_type_options = sorted(df["_lure_type"].dropna().unique().tolist())
lure_types = f4.multiselect("Lure type", lure_type_options, default=[])
clarity_options = sorted(df["water_clarity"].dropna().unique().tolist())
clarities = f5.multiselect("Water clarity", clarity_options, default=[])
structure_options = sorted(df["structure_type"].dropna().unique().tolist())
structures = f6.multiselect("Structure type", structure_options, default=[])

f7, f8 = st.columns([1, 3])
catches_only = f7.checkbox("Only trips with a catch", value=False)
search_text = f8.text_input("Search lure, color, or notes", value="")

filtered = df.copy()

if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[filtered["_date"].apply(lambda d: d is not None and start <= d <= end)]
if segments:
    filtered = filtered[filtered["segment"].isin(segments)]
if spots:
    filtered = filtered[filtered["_location"].isin(spots)]
if lure_types:
    filtered = filtered[filtered["_lure_type"].isin(lure_types)]
if clarities:
    filtered = filtered[filtered["water_clarity"].isin(clarities)]
if structures:
    filtered = filtered[filtered["structure_type"].isin(structures)]
if catches_only:
    filtered = filtered[pd.to_numeric(filtered["fish_caught"], errors="coerce").fillna(0) > 0]
if search_text.strip():
    needle = search_text.strip().lower()
    haystack = (
        filtered["lure_used"].fillna("") + " " +
        filtered["color_used"].fillna("") + " " +
        filtered["notes"].fillna("")
    ).str.lower()
    filtered = filtered[haystack.str.contains(needle, regex=False)]

st.caption(f"Showing {len(filtered)} of {len(df)} logged trips.")

if filtered.empty:
    st.warning("No trips match these filters.")
else:
    display_cols = ["trip_date", "segment", "_location", "structure_type", "water_clarity",
                     "_lure_type", "lure_used", "color_used", "technique_used", "fish_caught",
                     "biggest_fish_lb", "predicted_score", "notes"]
    display_df = filtered[display_cols].rename(columns={"_lure_type": "lure_type", "_location": "location"})
    st.dataframe(display_df.sort_values("trip_date", ascending=False), width='stretch', hide_index=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Trips shown", len(filtered))
    total_caught = pd.to_numeric(filtered["fish_caught"], errors="coerce").fillna(0).sum()
    c2.metric("Total bass caught", int(total_caught))
    success_rate = (pd.to_numeric(filtered["fish_caught"], errors="coerce").fillna(0) > 0).mean() * 100
    c3.metric("Trips with a catch", f"{success_rate:.0f}%")

# --- Calibration status (always over ALL logged trips, not just the filtered
# view - it's a property of the model, not of whatever the user is looking at
# right now) ------------------------------------------------------------------
st.divider()
st.subheader("Model calibration status")
summary = calibration_summary(rows)
st.caption(
    f"Each factor needs at least {MIN_SAMPLES_PER_SIDE} logged trips where it was present AND "
    f"{MIN_SAMPLES_PER_SIDE} where it wasn't, before your own results start nudging that factor's weight."
)
for factor, counts in summary["detail"].items():
    calibrated = factor in summary["factors_calibrated"]
    label = factor.replace("_", " ").title()
    status = "✅ calibrating from your data" if calibrated else "⏳ needs more trips"
    st.write(f"**{label}** - {status}  \n"
             f"_{counts['on_total']} trips with factor present, {counts['off_total']} without_")

# --- Trip details --------------------------------------------------------
# (json_key, label, formatter). Every key is optional - legacy Log a Trip
# rows and Spot Session rows each only populate a subset, so a row simply
# shows whichever of these it has data for.
FIELD_SPECS = [
    ("source", "Logged from", lambda v: "🎯 Spot Session" if v == "spot_session" else "📝 Legacy (Log a Trip)"),
    ("start_time", "Session start time", str),
    ("water_temp_f", "Water temp", lambda v: f"{v}°F"),
    ("secchi_ft", "Water clarity (secchi)", lambda v: f"{v} ft"),
    ("stirred_up", "Muddy / stirred up", lambda v: "Yes" if v else None),
    ("wind_band", "Wind", str),
    ("avg_wind_mph", "Avg wind", lambda v: f"{v:.0f} mph" if isinstance(v, (int, float)) else str(v)),
    ("light_condition", "Light condition", str),
    ("precipitation", "Precipitation", str),
    ("avg_cloud_pct", "Cloud cover", lambda v: f"{v:.0f}%" if isinstance(v, (int, float)) else str(v)),
    ("pressure_trend_24h", "Pressure trend (24h)", lambda v: f"{v:+.1f} hPa" if isinstance(v, (int, float)) else str(v)),
    ("moon_phase", "Moon phase", str),
    ("fish_depth_ft", "Fish holding depth", lambda v: f"{v} ft"),
    ("forage_seen", "Forage seen (pre-trip)", lambda v: ", ".join(v) if isinstance(v, list) else str(v)),
    ("lure_start_time", "Lure start time", str),
    ("lure_end_time", "Lure end time", str),
    ("wind_speed_mph", "Wind speed (logged)", lambda v: f"{v:g} mph" if isinstance(v, (int, float)) else str(v)),
    ("wind_direction", "Wind direction (logged)", str),
    # depth_fished_ft/depth_fished_varied_note (an overall "primary depth" for the
    # whole lure use) were dropped from the "Add results" form - per-fish "depth
    # caught at" already captures this in more detail. Only trips logged before
    # that change still set these two.
    ("depth_fished_ft", "Depth fished", lambda v: f"{v} ft"),
    ("depth_fished_varied_note", "Depth variation notes", str),
    ("fish_activity", "Fish activity", str),
    ("forage_activity", "Forage activity", str),
    ("forage_type_seen", "Forage type seen (while fishing)", lambda v: ", ".join(v) if isinstance(v, list) else str(v)),
    # retrieve_speed/retrieve_style used to be logged once per lure-use entry; Spot
    # Session's "Add results" redesign moved presentation to a per-fish record
    # instead (see the "fish" renderer below), so these two only ever populate for
    # trips logged before that change - kept here so that older history still
    # renders, not because new entries write them.
    ("retrieve_speed", "Retrieve speed", str),
    ("retrieve_style", "Retrieve style", str),
    ("trailer_used", "Trailer used", lambda v: "Yes" if v else None),
    ("trailer_name", "Trailer", str),
    ("trailer_color", "Trailer color", str),
    ("modeled_thermocline_band_ft", "Modeled thermocline band", str),
]

st.divider()
st.subheader("Trip details")
if filtered.empty:
    st.caption("No trips to show for the current filters.")
else:
    for _, row in filtered.sort_values("trip_date", ascending=False).iterrows():
        cond = row["_conditions"]
        title = f"{row['trip_date']} · {row['_location']} · {row['segment']}"
        with st.expander(title):
            # predicted_score is blank for a trip logged via "Add results" without ever
            # filling in "Conditions right now" first - no live reading, no score.
            raw_score = row.get("predicted_score")
            has_score = raw_score not in (None, "") and not pd.isna(raw_score)
            top_bits = [
                f"**Lure:** {row['lure_used'] or '-'} ({row['color_used'] or 'color n/a'})",
                f"**Technique:** {row['technique_used'] or '-'}",
                f"**Fish caught:** {row['fish_caught']}"
                + (f", biggest {row['biggest_fish_lb']} lb" if row.get("biggest_fish_lb") else ""),
                f"**Predicted score:** {raw_score}/10" if has_score else "**Predicted score:** n/a (no live conditions entered)",
            ]
            st.markdown("  \n".join(top_bits))
            if row.get("notes"):
                st.caption(f"Notes: {row['notes']}")

            detail_lines = []
            for key, label, fmt in FIELD_SPECS:
                value = cond.get(key)
                if value in (None, "", [], False) and key not in ("stirred_up", "trailer_used"):
                    continue
                if key in ("stirred_up", "trailer_used") and not value:
                    continue
                try:
                    formatted = fmt(value)
                except (TypeError, ValueError):
                    formatted = str(value)
                if formatted is None:
                    continue
                detail_lines.append(f"- **{label}:** {formatted}")
            if detail_lines:
                st.markdown("\n".join(detail_lines))
            else:
                st.caption("No additional condition details recorded for this trip.")

            # Per-fish catch records (Spot Session's "Add results" section) - a list of
            # dicts, one per fish, so it gets its own renderer rather than the generic
            # single-line FIELD_SPECS formatter above (which would otherwise show an
            # unreadable raw Python list-of-dicts string).
            fish_list = cond.get("fish")
            if isinstance(fish_list, list) and fish_list:
                st.markdown(f"**Fish caught ({len(fish_list)}):**")
                for i, fish in enumerate(fish_list, start=1):
                    if not isinstance(fish, dict):
                        continue
                    bits = [fish.get("species") or "Unknown species"]
                    if fish.get("weight_lb"):
                        bits.append(f"{fish['weight_lb']:g} lb")
                    if fish.get("length_in"):
                        bits.append(f"{fish['length_in']:g} in")
                    if fish.get("depth_ft"):
                        bits.append(f"{fish['depth_ft']:g} ft deep")
                    presentation = " / ".join(x for x in [fish.get("retrieve_speed"), fish.get("retrieve_style")] if x)
                    if presentation:
                        bits.append(presentation)
                    st.markdown(f"- Fish #{i}: {', '.join(str(b) for b in bits)}")
                    if fish.get("notes"):
                        st.caption(f"　{fish['notes']}")
