"""
"The Stringer" - punch-list #97 Phase 2: pages/8_Leaderboard.py's real
content, rebuilt around the validated "The Stringer" mockup (a cyclable
ring-chart hero + underline tab bar + ranked list, plus a "season activity"
/ "species mix" glance panel) instead of the old flat category-dropdown +
dataframe table. Mockup artifact + full design-critique history:
SESSION_NOTES.md entries 171/172 and punch-list #97's own text.

Streamlit-free and unit tested on its own (tests/test_stringer.py) - same
reasoning as core/daily_leaderboard.py (punch-list #91) and core/reports.py
(punch-list #92): built independently rather than reusing pages/
8_Leaderboard.py's OLD frame-builder/category logic, so a bug here can't
regress whatever the old page was doing and vice versa. This module
REPLACES that old builder outright - the old page's 14-category dropdown +
angler/species-filtered table is fully superseded by this curated 6-tab
"highlight reel" view, per the validated redesign (deep, flexible ad hoc
filtering/correlation now lives on the Reports page instead - punch-list
#92 - so this page can be a highlight reel rather than trying to be both).

Vocabulary carried over from the old page's own docstring, extended with
one more grain:
- `fish_df`: one row per INDIVIDUAL fish catch record, flattened out of
  every trip's conditions_json["fish"] list. This is the only place
  species/weight/length actually live. Extended here (vs. the old page's
  frame) to also carry the trip's own `color` and `session_key`, so a
  fish-level category can be grouped/joined by either without a second pass
  over trip_log.
- `trips_df`: one row per trip_log.csv row (one lure USE, in this app's own
  vocabulary - a single Spot Session can produce several "trips," one per
  lure fished).
- **No separate `sessions_df`** - "Top Sessions" groups `trips_df` by
  `session_key` (see `_session_key()` below) on demand rather than
  materializing a third frame, since it's the only category that needs
  session-grain aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls, timedelta
from typing import Optional

import pandas as pd

from .activity_log import format_weight_lb_oz
from .lures import LURE_PROFILES
from .storage import parse_conditions

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# How many rows each ranked-list tab shows. The mockup's own hardcoded
# example arrays ran 6-8 rows purely for illustration - this is a real cap
# for real (potentially much longer) data, chosen to keep a tab scannable
# on a phone without an inner scroll area of its own.
TOP_N = 10

UNSPECIFIED = "Unspecified"


def format_date_short(d) -> str:
    """"Aug 13" style, no year - matches the mockup's own fmtDate()."""
    if not d:
        return ""
    return f"{MONTHS[d.month - 1]} {d.day}"


def format_weight(w) -> str:
    """format_weight_lb_oz() already matches the mockup's fmtWeight() shape
    exactly (whole lb only / oz only / both), so this is just a friendlier
    "no reading" fallback than that function's own bare ''."""
    text = format_weight_lb_oz(w)
    return text or "–"  # en dash


def _lure_type_label(cond: dict) -> Optional[str]:
    category = cond.get("lure_category")
    if not category:
        return None
    return LURE_PROFILES.get(category, {}).get("name", category)


def _location_label(row: dict, spot_name_by_id: dict) -> str:
    return spot_name_by_id.get(row.get("spot_id")) or row.get("spot_name") or "Unknown location"


def _parse_date(s):
    try:
        from datetime import datetime
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _session_key(row: dict) -> str:
    """Groups trip_log rows into a "session" for the Top Sessions tab. A
    real `session_id` (every Spot Session run since punch-list #55) groups
    its rows directly; a blank one (any row logged before that redesign)
    falls back to its own `trip_id` as a singleton one-lure session, rather
    than attempting Trip History's own, more elaborate legacy backfill
    clustering (date + segment + angler + a same-day time-gap check - see
    SESSION_NOTES.md entry 118). That's a deliberate scope choice, not an
    oversight: reproducing that heuristic here risks a second, possibly-
    diverging opinion about which old rows belong together, for a "top
    sessions" highlight reel where the real, session_id-backed rows (every
    outing logged since) are what actually matters day to day. A pre-#55
    multi-lure outing will show here as several separate single-lure
    "sessions" rather than one - a known, narrower view than Trip History's,
    not a bug."""
    session_id = (row.get("session_id") or "").strip()
    if session_id:
        return f"s:{session_id}"
    return f"t:{row.get('trip_id')}"


def build_frames(rows: list, spot_name_by_id: dict) -> tuple:
    """One pass over trip_log rows builds both fish_df (per catch) and
    trips_df (per lure-use) - every hero-stat/category builder below just
    filters/groups one of these instead of re-parsing conditions_json
    itself. `spot_name_by_id` should be `{s["spot_id"]: s["name"] for s in
    get_lake_spots()}` - passed in rather than fetched here so this module
    stays Streamlit-free (no core.appstate import), matching core.reports/
    core.daily_leaderboard's own convention."""
    fish_records = []
    trip_records = []
    for row in rows:
        cond = parse_conditions(row)
        trip_id = row.get("trip_id")
        date = _parse_date(row.get("trip_date"))
        angler = (cond.get("angler") or "").strip() or UNSPECIFIED
        lure = row.get("lure_used") or _lure_type_label(cond) or UNSPECIFIED
        color = (row.get("color_used") or "").strip() or UNSPECIFIED
        spot = _location_label(row, spot_name_by_id)
        session_key = _session_key(row)

        fish_list = cond.get("fish")
        trip_fish_count = 0
        if isinstance(fish_list, list) and fish_list:
            for fish in fish_list:
                if not isinstance(fish, dict):
                    continue
                count = fish.get("count") or 1
                try:
                    count = max(int(count), 1)
                except (TypeError, ValueError):
                    count = 1
                trip_fish_count += count
                fish_records.append({
                    "trip_id": trip_id, "date": date, "angler": angler, "lure": lure,
                    "color": color, "spot": spot, "session_key": session_key,
                    "species": (fish.get("species") or UNSPECIFIED).strip() or UNSPECIFIED,
                    "count": count, "weight_lb": fish.get("weight_lb"), "length_in": fish.get("length_in"),
                })
        else:
            # Legacy row (pre-redesign, or "Log a Trip") - no per-fish detail,
            # just the trip's own summary column.
            try:
                trip_fish_count = int(float(row.get("fish_caught") or 0))
            except (TypeError, ValueError):
                trip_fish_count = 0

        trip_records.append({
            "trip_id": trip_id, "date": date, "angler": angler, "lure": lure,
            "color": color, "spot": spot, "session_key": session_key,
            "fish_count": trip_fish_count,
        })

    fish_df = pd.DataFrame(fish_records)
    trips_df = pd.DataFrame(trip_records)
    return fish_df, trips_df


def season_label(trips_df) -> Optional[str]:
    """"Aug 1 - Sep 10" style chip text spanning every logged trip date -
    unlike the mockup's own hardcoded example window, this always reflects
    whatever's actually in trip_log right now. None when there's no dated
    trip to anchor a range on at all (empty history, or every row's date
    failed to parse)."""
    if trips_df.empty:
        return None
    dates = trips_df["date"].dropna()
    if dates.empty:
        return None
    lo, hi = dates.min(), dates.max()
    if lo == hi:
        return format_date_short(lo)
    return f"{format_date_short(lo)} – {format_date_short(hi)}"


def _join_names(names: list) -> str:
    """"White Bass, Striped Bass & Catfish" - Oxford-less list with a final
    "&", matching the mockup's own hand-written species-mix description."""
    names = list(names)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " & " + names[-1]


@dataclass
class HeroState:
    title: str
    legend: str
    value: float           # numerator
    total: float            # denominator
    desc: str
    sec_label: str
    sec_value: str


def hero_states(fish_df, trips_df) -> list:
    """Builds the ring hero's cyclable season stats - up to 3, matching the
    mockup exactly (days on the water, top-spot share, top-species share) -
    each SKIPPED (not a placeholder) when the data it needs isn't there yet,
    so a brand-new install with only a few undated or unspeciated trips
    still shows whatever it honestly can rather than a fake 0%/broken
    state. Order matches the mockup's own cycle order."""
    states = []

    dates = trips_df["date"].dropna() if not trips_df.empty else pd.Series(dtype="object")
    if not dates.empty:
        lo, hi = dates.min(), dates.max()
        total_days = (hi - lo).days + 1
        distinct_days = dates.nunique()
        label = season_label(trips_df) or ""
        states.append(HeroState(
            title="Days on the Water", legend="Days fished",
            value=distinct_days, total=total_days,
            desc=f"{distinct_days} of {total_days} days, {label}",
            sec_label="Trips logged", sec_value=str(len(trips_df)),
        ))

    if not fish_df.empty:
        by_spot = fish_df.groupby("spot")["count"].sum()
        total_fish = int(by_spot.sum())
        if total_fish > 0:
            top_spot = by_spot.idxmax()
            top_spot_count = int(by_spot.max())
            spot_fish = fish_df[(fish_df["spot"] == top_spot) & fish_df["weight_lb"].notna()]
            best_there = format_weight(spot_fish["weight_lb"].max()) if not spot_fish.empty else "–"
            states.append(HeroState(
                title=f"{top_spot} Share", legend="Catches there",
                value=top_spot_count, total=total_fish,
                desc=f"{top_spot_count} of {total_fish} catches this season",
                sec_label="Best fish landed there", sec_value=best_there,
            ))

        by_species = fish_df.groupby("species")["count"].sum().sort_values(ascending=False)
        total_fish2 = int(by_species.sum())
        if total_fish2 > 0:
            top_species = by_species.index[0]
            top_species_count = int(by_species.iloc[0])
            rest = [s for s in by_species.index[1:4]]
            rest_txt = f" — rest are {_join_names(rest)}" if rest else ""
            states.append(HeroState(
                title=f"{top_species} Share", legend="Of all catches",
                value=top_species_count, total=total_fish2,
                desc=f"{top_species_count} of {total_fish2}{rest_txt}",
                sec_label="Species logged", sec_value=str(by_species.shape[0]),
            ))

    return states


# --- Ranked-list tabs -----------------------------------------------------
# Each builder returns a list of plain dicts: {"primary", "secondary",
# "num", "tag"} (tag is None when there's nothing to flag), already sorted
# and capped to TOP_N - the page just renders them, no further logic.

def _row(primary, secondary, num, tag=None) -> dict:
    return {"primary": primary, "secondary": secondary, "num": num, "tag": tag}


def biggest_fish(fish_df) -> list:
    if fish_df.empty:
        return []
    d = fish_df[fish_df["weight_lb"].notna()].sort_values("weight_lb", ascending=False).head(TOP_N)
    return [
        _row(
            format_weight(r.weight_lb),
            f"{r.species} · {r.lure} · {r.spot} · {r.angler} · {format_date_short(r.date)}",
            format_weight(r.weight_lb),
        )
        for r in d.itertuples()
    ]


def longest_fish(fish_df) -> list:
    if fish_df.empty:
        return []
    d = fish_df[fish_df["length_in"].notna()].sort_values("length_in", ascending=False).head(TOP_N)
    rows = []
    for r in d.itertuples():
        primary = f"{r.species} · {format_weight(r.weight_lb)}" if pd.notna(r.weight_lb) else r.species
        rows.append(_row(
            primary,
            f"{r.lure} · {r.spot} · {r.angler} · {format_date_short(r.date)}",
            f"{r.length_in:.1f} in",
        ))
    return rows


def top_anglers(fish_df) -> list:
    if fish_df.empty:
        return []
    d = fish_df.copy()
    d["weighted"] = d["weight_lb"].fillna(0) * d["count"]
    g = d.groupby("angler").agg(total_count=("count", "sum"), total_weight=("weighted", "sum"))
    g = g.sort_values("total_count", ascending=False).head(TOP_N)
    rows = []
    for angler, r in g.iterrows():
        if r.total_weight > 0:
            avg = r.total_weight / r.total_count
            secondary = f"{format_weight(r.total_weight)} total · {avg:.2f} lb avg"
        else:
            secondary = f"{int(r.total_count)} fish logged, no weight data yet"
        rows.append(_row(angler, secondary, f"{int(r.total_count)} fish"))
    return rows


def hot_lures(fish_df, trips_df) -> list:
    if fish_df.empty or trips_df.empty:
        return []
    counts = fish_df.groupby(["lure", "color"])["count"].sum()
    uses = trips_df.groupby(["lure", "color"])["trip_id"].count()
    g = pd.DataFrame({"count": counts, "uses": uses}).dropna()
    g = g[g["count"] > 0].sort_values("count", ascending=False).head(TOP_N)
    rows = []
    for (lure, color), r in g.iterrows():
        uses_n = int(r.uses)
        rate = r["count"] / uses_n if uses_n else 0.0
        secondary = f"{color} · {uses_n} use{'' if uses_n == 1 else 's'} · {rate:.2f} / use"
        tag = f"{uses_n} use sample" if uses_n < 3 else None
        rows.append(_row(lure, secondary, f"{int(r['count'])} fish", tag))
    return rows


def top_spots(fish_df) -> list:
    if fish_df.empty:
        return []
    totals = fish_df.groupby("spot")["count"].sum()
    weighted = fish_df[fish_df["weight_lb"].notna()]
    if weighted.empty:
        return []
    idx = weighted.groupby("spot")["weight_lb"].idxmax()
    best = weighted.loc[idx].set_index("spot")
    best = best.sort_values("weight_lb", ascending=False).head(TOP_N)
    rows = []
    for spot, r in best.iterrows():
        total = int(totals.get(spot, 0))
        rows.append(_row(
            spot,
            f"{total} fish landed here · best by {r.angler}",
            format_weight(r.weight_lb),
        ))
    return rows


def top_sessions(trips_df) -> list:
    if trips_df.empty:
        return []
    g = trips_df.groupby("session_key").agg(
        total=("fish_count", "sum"), date=("date", "first"),
        spot=("spot", "first"), angler=("angler", "first"),
    )
    g = g[g["total"] > 0].sort_values("total", ascending=False).head(TOP_N)
    rows = []
    for _, r in g.iterrows():
        outing = f"{format_date_short(r.date)} outing" if r.date else "Undated outing"
        rows.append(_row(outing, f"{r.spot} · {r.angler}", f"{int(r.total)} fish"))
    return rows


CATEGORIES = [
    ("biggest", "Biggest Fish", "sorted by weight", lambda f, t: biggest_fish(f)),
    ("anglers", "Top Anglers", "sorted by fish caught", lambda f, t: top_anglers(f)),
    ("lures", "Hot Lures", "sorted by fish caught", lambda f, t: hot_lures(f, t)),
    ("spots", "Top Spots", "sorted by biggest fish", lambda f, t: top_spots(f)),
    ("longest", "Longest Fish", "sorted by length", lambda f, t: longest_fish(f)),
    ("sessions", "Top Sessions", "sorted by fish per outing", lambda f, t: top_sessions(t)),
]


# --- Glance panel: season activity + species mix --------------------------

def daily_activity_series(fish_df, lo: date_cls, hi: date_cls) -> list:
    """One entry per calendar day from lo to hi inclusive: (date, total fish
    that day) - zero-filled for a day with no catches, so the bar chart's X
    axis is a real, unbroken calendar rather than only the days that
    happened to produce a fish."""
    if lo is None or hi is None:
        return []
    totals = fish_df.groupby("date")["count"].sum() if not fish_df.empty else pd.Series(dtype="int64")
    days = []
    d = lo
    while d <= hi:
        days.append((d, int(totals.get(d, 0))))
        d += timedelta(days=1)
    return days


def species_mix(fish_df, top_n: int = 5) -> list:
    """(species, count) pairs, most-caught first, capped to top_n - matches
    the mockup's compact "Species mix" bar-row list."""
    if fish_df.empty:
        return []
    g = fish_df.groupby("species")["count"].sum().sort_values(ascending=False)
    return [(name, int(count)) for name, count in g.head(top_n).items()]
