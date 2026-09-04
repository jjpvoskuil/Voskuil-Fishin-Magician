"""
Leaderboard - punch-list #54.

Ranks the logged trip history (data/trip_log.csv, same source as Trip
History) a bunch of different ways: biggest/longest fish, most fish by
lure/spot/angler/day, best fish-per-use rate by lure/spot, and a few more -
see CATEGORIES below for the full list. Every category shares one flat
"top N, sorted either direction, optionally filtered to one angler/species"
control panel rather than being fifteen bespoke pages, so adding a new
ranking later is one new entry in CATEGORIES, not a new page.

Two granularities get built once up front and every category reads from
one or the other:
- `fish_df`: one row per INDIVIDUAL fish catch record, flattened out of
  every trip's conditions_json["fish"] list (see core/activity_log.py's
  _new_fish_from_form() for that shape). This is the only place species/
  weight/length actually live, so anything ranking individual catches or
  aggregating "total fish caught" reads from here.
- `trips_df`: one row per trip_log.csv row (one lure USE, in this app's own
  vocabulary - a single Spot Session can produce several "trips," one per
  lure fished). Used for lure/spot/angler/day aggregates and for "most fish
  in a single trip."

A trip's fish COUNT is read from its own fish list when it has one (summing
each fish record's "count," matching Trip History's own convention - a
record can represent a small group logged together, not always exactly
one fish); trips logged before the Spot Session redesign have no fish
list at all, so those fall back to the trip_log.csv "fish_caught" column
instead. That fallback is also why the Species filter only applies to
fish-level categories (Biggest fish, Longest fish, Biggest by species) -
a fallback-only trip has no species to filter by, so filtering aggregate
categories by species would silently make older trips vanish from a "most
fish by lure" ranking without any indication why. Worth revisiting if that
ever turns out to matter in practice.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from core.appstate import (
    get_lake_spots, get_trip_history, get_calibrated_weights, get_location_adjustments, get_anglers, github_token, repo_slug,
)
from core.lures import LURE_PROFILES
from core.activity_log import format_weight_lb_oz
from core.ui import inject_mobile_css
from core.storage import parse_conditions, sync_data_from_data_branch

st.set_page_config(page_title="Leaderboard - Nolin Lake", page_icon="🏆", layout="wide")
inject_mobile_css()
st.title("🏆 Leaderboard")

# Punch-list #61: get_trip_history() is a 5-minute st.cache_data cache (see
# core/appstate.py) that, unlike every OTHER cached getter in this app
# (get_lake_spots, get_inventory, get_dev_tasks - each cleared right after
# its own page's own writes), was never cleared after a trip is logged/
# edited/deleted anywhere. That means this page could show data up to 5
# minutes stale after ANY save, on top of the separate "this running
# server only syncs from the data branch once, at boot" gap Trip History's
# own refresh button (below) exists for - see that button's comment in
# pages/4_Trip_History.py and core.storage.sync_data_from_data_branch's
# docstring for the full "why" behind that second gap. This mirrors that
# same button here, and - unlike Trip History's own copy - explicitly
# clears both trip caches too, since this page (and 7-Day Forecast) reads
# through them rather than a live, uncached read_all_trips() call.
_refresh_col, _ = st.columns([1, 3])
if _refresh_col.button(
    "🔄 Refresh from GitHub", help=(
        "Pulls the latest trip_log.csv (and the rest of data/) from GitHub right now, and "
        "clears this page's own cache of it - use this if you know a trip was saved (by you "
        "or someone else, or by a change pushed straight to GitHub) but this page still "
        "looks out of date."
    ),
):
    _token = github_token()
    if _token:
        _ok, _msg = sync_data_from_data_branch(_token, repo_slug())
        get_trip_history.clear()
        get_calibrated_weights.clear()
        get_location_adjustments.clear()
        (st.success if _ok else st.warning)(_msg)
    else:
        st.info("No GitHub token configured here - nothing to refresh.")

rows = get_trip_history()

if not rows:
    st.info(
        "No trips logged yet - the leaderboard fills in as you log sessions on the "
        "**Spot Session** page."
    )
    st.stop()


# --- Shared parsing (mirrors pages/4_Trip_History.py's own conventions) -----
def _parse_conditions(row: dict) -> dict:
    return parse_conditions(row)


def _parse_date(s: str):
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _lure_type_label(cond: dict) -> str:
    category = cond.get("lure_category")
    if not category:
        return None
    return LURE_PROFILES.get(category, {}).get("name", category)


_spot_name_by_id = {s["spot_id"]: s["name"] for s in get_lake_spots()}


def _location_label(row: dict) -> str:
    return _spot_name_by_id.get(row.get("spot_id")) or row.get("spot_name") or "Unknown location"


def _build_frames(rows: list):
    """One pass over trip_log builds both fish_df (per catch) and trips_df
    (per lure-use), so every category below can just filter/group instead
    of re-parsing conditions_json itself."""
    fish_records = []
    trip_records = []
    for row in rows:
        cond = _parse_conditions(row)
        trip_id = row.get("trip_id")
        date = _parse_date(row.get("trip_date"))
        angler = (cond.get("angler") or "").strip() or "Unspecified"
        lure = row.get("lure_used") or _lure_type_label(cond) or "Unspecified"
        spot = _location_label(row)

        fish_list = cond.get("fish")
        trip_fish_count = 0
        if isinstance(fish_list, list) and fish_list:
            for fish in fish_list:
                if not isinstance(fish, dict):
                    continue
                count = fish.get("count") or 1
                trip_fish_count += count
                fish_records.append({
                    "trip_id": trip_id, "date": date, "angler": angler, "lure": lure, "spot": spot,
                    "species": (fish.get("species") or "Unspecified").strip() or "Unspecified",
                    "count": count, "weight_lb": fish.get("weight_lb"), "length_in": fish.get("length_in"),
                    "caught_at": fish.get("caught_at"),
                })
        else:
            # Legacy row (pre-redesign, or "Log a Trip") - no per-fish detail,
            # just the trip's own summary column.
            try:
                trip_fish_count = int(float(row.get("fish_caught") or 0))
            except (TypeError, ValueError):
                trip_fish_count = 0

        try:
            biggest = float(row.get("biggest_fish_lb")) if row.get("biggest_fish_lb") not in (None, "") else None
        except (TypeError, ValueError):
            biggest = None

        trip_records.append({
            "trip_id": trip_id, "date": date, "angler": angler, "lure": lure, "spot": spot,
            "fish_count": trip_fish_count, "biggest_fish_lb": biggest,
        })

    fish_df = pd.DataFrame(fish_records)
    trips_df = pd.DataFrame(trip_records)
    return fish_df, trips_df


fish_df, trips_df = _build_frames(rows)


# --- Filters ------------------------------------------------------------------
angler_roster = get_anglers()
anglers_present = sorted(set(trips_df["angler"]) - set(angler_roster)) if not trips_df.empty else []
ANGLER_OPTIONS = ["All anglers"] + angler_roster + [a for a in anglers_present if a != "Unspecified"] + (
    ["Unspecified"] if (not trips_df.empty and "Unspecified" in set(trips_df["angler"])) else []
)
SPECIES_OPTIONS = ["All species"] + (sorted(fish_df["species"].dropna().unique().tolist()) if not fish_df.empty else [])


def _filtered_frames(angler_choice: str, species_choice: str):
    f_df, t_df = fish_df, trips_df
    if angler_choice != "All anglers":
        f_df = f_df[f_df["angler"] == angler_choice] if not f_df.empty else f_df
        t_df = t_df[t_df["angler"] == angler_choice] if not t_df.empty else t_df
    if species_choice != "All species" and not f_df.empty:
        f_df = f_df[f_df["species"] == species_choice]
    return f_df, t_df


# --- Category builders ---------------------------------------------------------
# Each builder returns (result_df, value_col, value_label, value_kind,
# display_cols) where value_kind is "int" | "weight" | "rate" (drives
# formatting), or None if there's nothing to rank (no data after filters).
# display_cols is [(col, header), ...] shown alongside the rank/value.

def _fish_ranked(f_df, numeric_col):
    d = f_df[f_df[numeric_col].notna()].copy()
    return d


def _biggest_fish(f_df, t_df):
    d = _fish_ranked(f_df, "weight_lb")
    if d.empty:
        return None
    d = d.rename(columns={"weight_lb": "value"})
    return d, "value", "Weight", "weight", [
        ("species", "Species"), ("angler", "Angler"), ("lure", "Lure"), ("spot", "Spot"), ("date", "Date"),
    ]


def _longest_fish(f_df, t_df):
    d = _fish_ranked(f_df, "length_in")
    if d.empty:
        return None
    d = d.rename(columns={"length_in": "value"})
    return d, "value", "Length (in)", "length", [
        ("species", "Species"), ("angler", "Angler"), ("lure", "Lure"), ("spot", "Spot"), ("date", "Date"),
    ]


def _biggest_by_species(f_df, t_df):
    d = _fish_ranked(f_df, "weight_lb")
    if d.empty:
        return None
    idx = d.groupby("species")["weight_lb"].idxmax()
    d = d.loc[idx].rename(columns={"weight_lb": "value"})
    return d, "value", "Weight", "weight", [
        ("species", "Species"), ("angler", "Angler"), ("lure", "Lure"), ("spot", "Spot"), ("date", "Date"),
    ]


def _agg_fish_count(f_df, group_col, label):
    if f_df.empty:
        return None
    g = f_df.groupby(group_col)["count"].sum().reset_index().rename(columns={"count": "value"})
    if g.empty:
        return None
    return g, "value", "Total fish", "int", [(group_col, label)]


def _by_lure_count(f_df, t_df):
    return _agg_fish_count(f_df, "lure", "Lure")


def _by_spot_count(f_df, t_df):
    return _agg_fish_count(f_df, "spot", "Spot")


def _by_angler_count(f_df, t_df):
    return _agg_fish_count(f_df, "angler", "Angler")


def _by_day_count(f_df, t_df):
    d = _agg_fish_count(f_df, "date", "Date")
    if d is None:
        return None
    g, value_col, value_label, kind, display_cols = d
    # Extra context: who actually caught them that day, so an "All anglers"
    # view doesn't just show a bare number.
    who = f_df.groupby("date")["angler"].agg(lambda s: ", ".join(sorted(set(s)))).reset_index()
    who.columns = ["date", "anglers"]
    g = g.merge(who, on="date", how="left")
    return g, value_col, value_label, kind, [("date", "Date"), ("anglers", "Angler(s)")]


def _rate_by(t_df, group_col, label, min_uses=1):
    if t_df.empty:
        return None
    g = t_df.groupby(group_col).agg(total_fish=("fish_count", "sum"), uses=("trip_id", "count")).reset_index()
    g = g[g["uses"] >= min_uses]
    if g.empty:
        return None
    g["value"] = (g["total_fish"] / g["uses"]).round(2)
    return g, "value", "Fish per use", "rate", [(group_col, label), ("total_fish", "Total fish"), ("uses", "Uses")]


def _rate_by_lure(f_df, t_df):
    return _rate_by(t_df, "lure", "Lure")


def _rate_by_spot(f_df, t_df):
    return _rate_by(t_df, "spot", "Spot")


def _rate_by_angler(f_df, t_df):
    return _rate_by(t_df, "angler", "Angler")


def _biggest_by_group(f_df, group_col, label):
    d = _fish_ranked(f_df, "weight_lb")
    if d.empty:
        return None
    idx = d.groupby(group_col)["weight_lb"].idxmax()
    d = d.loc[idx].rename(columns={"weight_lb": "value"})
    extra = [(group_col, label)] if group_col != "species" else []
    return d, "value", "Biggest fish", "weight", extra + [("species", "Species"), ("angler", "Angler"), ("date", "Date")]


def _biggest_by_lure(f_df, t_df):
    return _biggest_by_group(f_df, "lure", "Lure")


def _biggest_by_spot(f_df, t_df):
    return _biggest_by_group(f_df, "spot", "Spot")


def _biggest_by_angler(f_df, t_df):
    return _biggest_by_group(f_df, "angler", "Angler")


def _single_trip(f_df, t_df):
    if t_df.empty:
        return None
    d = t_df[t_df["fish_count"] > 0].copy()
    if d.empty:
        return None
    d = d.rename(columns={"fish_count": "value"})
    return d, "value", "Fish caught", "int", [
        ("date", "Date"), ("angler", "Angler"), ("lure", "Lure"), ("spot", "Spot"),
    ]


CATEGORIES = [
    ("biggest_fish", "🐟 Biggest fish (by weight)", _biggest_fish, True, True),
    ("longest_fish", "📏 Longest fish (by length)", _longest_fish, True, True),
    ("biggest_by_species", "🐟 Biggest fish by species (best of each)", _biggest_by_species, True, False),
    ("by_lure_count", "🎣 Most fish caught — by lure", _by_lure_count, True, True),
    ("rate_by_lure", "🎣 Best fish-per-use rate — by lure", _rate_by_lure, True, False),
    ("biggest_by_lure", "🎣 Biggest fish caught — by lure", _biggest_by_lure, True, True),
    ("by_spot_count", "📍 Most fish caught — by spot", _by_spot_count, True, True),
    ("rate_by_spot", "📍 Best fish-per-trip rate — by spot", _rate_by_spot, True, False),
    ("biggest_by_spot", "📍 Biggest fish caught — by spot", _biggest_by_spot, True, True),
    ("by_angler_count", "🧑 Most fish caught — by angler", _by_angler_count, False, True),
    ("rate_by_angler", "🧑 Best fish-per-trip rate — by angler", _rate_by_angler, False, False),
    ("biggest_by_angler", "🧑 Biggest fish caught — by angler", _biggest_by_angler, False, True),
    ("by_day_count", "📅 Most fish caught — in a single day", _by_day_count, True, True),
    ("single_trip", "🎯 Most fish caught — in a single trip", _single_trip, True, True),
]
CATEGORY_LABELS = [c[1] for c in CATEGORIES]
CATEGORY_BY_LABEL = {c[1]: c for c in CATEGORIES}

st.caption(
    "Ranks your logged trip history (same data as Trip History) different ways - biggest/"
    "longest fish, most productive lures/spots/anglers, best fish-per-use rates, and more. "
    "Pick a category, filter it down if you want, and see the top of the list either direction."
)

f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
category_label = f1.selectbox("Category", CATEGORY_LABELS, key="lb_category")
_key, _label, _builder, _supports_angler, _supports_species = CATEGORY_BY_LABEL[category_label]

angler_choice = "All anglers"
if _supports_angler:
    angler_choice = f2.selectbox("Angler", ANGLER_OPTIONS, key="lb_angler")
else:
    f2.selectbox("Angler", ["All anglers"], disabled=True, key="lb_angler_disabled",
                 help="This category already ranks by angler.")

species_choice = "All species"
if _supports_species:
    species_choice = f3.selectbox("Species", SPECIES_OPTIONS, key="lb_species")
else:
    f3.selectbox("Species", ["All species"], disabled=True, key="lb_species_disabled",
                 help="This category isn't broken out by individual catch, so a species filter "
                      "wouldn't change anything - and would silently drop trips logged before "
                      "per-fish detail existed.")

is_species_view = _key == "biggest_by_species"
if is_species_view:
    f4.selectbox("Show", ["All species"], disabled=True, key="lb_topn_disabled")
    top_n = None
    sort_dir = "High to low"
else:
    top_n_choice = f4.selectbox("Show", ["Top 5", "Top 10", "Top 25", "All"], index=1, key="lb_topn")
    top_n = None if top_n_choice == "All" else int(top_n_choice.split()[1])
    sort_dir = st.radio("Sort", ["High to low", "Low to high"], horizontal=True, key="lb_sort")

f_filtered, t_filtered = _filtered_frames(angler_choice, species_choice)
result = _builder(f_filtered, t_filtered)

st.divider()

if result is None:
    st.caption("No data matches these filters yet - try a different angler/species, or log a few more trips.")
else:
    df, value_col, value_label, value_kind, display_cols = result
    ascending = sort_dir == "Low to high"
    df = df.sort_values(value_col, ascending=ascending)
    if top_n is not None:
        df = df.head(top_n)
    df = df.reset_index(drop=True)

    def _fmt_value(v):
        if value_kind == "weight":
            return format_weight_lb_oz(v) or "-"
        if value_kind == "length":
            return f"{v:g} in"
        if value_kind == "rate":
            return f"{v:g}"
        try:
            return f"{int(v):,}"
        except (TypeError, ValueError):
            return str(v)

    def _medal(i):
        return {0: "🥇", 1: "🥈", 2: "🥉"}.get(i, f"{i + 1}")

    show = pd.DataFrame({"Rank": [_medal(i) for i in range(len(df))]})
    for col, header in display_cols:
        vals = df[col]
        if col == "date":
            vals = vals.apply(lambda d: d.strftime("%m/%d/%Y") if d else "-")
        show[header] = vals.values
    show[value_label] = df[value_col].apply(_fmt_value).values

    st.dataframe(show, width='stretch', hide_index=True)

    if not is_species_view and value_kind in ("int", "rate") and len(df) > 1:
        chart_labels = display_cols[0][0]
        chart_series = pd.Series(df[value_col].values, index=df[chart_labels].astype(str).values, name=value_label)
        st.bar_chart(chart_series, horizontal=True)

    st.caption(f"{len(df)} row(s) shown.")
    if _key in ("rate_by_lure", "rate_by_spot", "rate_by_angler"):
        st.caption(
            "A high rate from very few uses isn't necessarily reliable - check the \"Uses\" "
            "column before reading too much into it."
        )
