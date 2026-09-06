"""
Today's/this week's activity + leaderboard - punch-list #91 (day view),
extended (same day) to add an identical week view.

Home page feature: "show fishing activity for any or all anglers that are
currently logged in and/or posted a session," three "award" tiles for the
period's biggest fish / top angler by total weight / top angler by fish
count, and a detailed per-angler, per-species leaderboard table with
subtotals and a grand total - originally scoped to just "today" (the
lake's own local day, see core.weather.lake_today()), then extended to
offer the identical set of categories for "this week" too, per the
angler's own follow-up ask: "lets also add the same categories, but for
the week as well as the day (week starting on the Sunday of every week)."
The "currently active" roster check is the one thing that's never scoped
to a period - it looks at open Spot Sessions across ALL dates (a session
spanning a midnight rollover shouldn't vanish from the roster), for both
the day and the week view.

build_period_activity() is the one real builder - it takes an inclusive
[start_iso, end_iso] trip_date range. build_daily_activity() and
build_weekly_activity() are both thin, differently-scoped wrappers around
it; daily_awards()/grand_total()/leaderboard_table_rows() below don't care
which period built their input, so the exact same three functions render
both the day and the week section on the Home page.

Deliberately a separate, self-contained module rather than reusing/
importing from pages/8_Leaderboard.py's private helpers - that page's
_build_frames()/category builders are page-local, all-time, filterable
rankings; this is a narrower "today/this week only" activity summary with
a very different shape (per-angler grouped table with subtotals, not a
flat top-N). Some logic (fish-list parsing, count-aware weight math) is
necessarily similar, but keeping them independent avoids any regression
risk on the already-shipped Leaderboard page.

No Streamlit import here on purpose - every function takes plain rows (as
returned by core.appstate.get_trip_history()) and plain date/string
bounds, and returns plain dataclasses/dicts, so this can be unit tested
without AppTest and reused anywhere "today's" or "this week's" activity is
needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from core.activity_log import format_weight_lb_oz
from core.storage import parse_conditions


def _fish_count(fish: dict) -> int:
    try:
        return max(int(fish.get("count") or 1), 1)
    except (TypeError, ValueError):
        return 1


def _fish_weight(fish: dict) -> float:
    try:
        return float(fish.get("weight_lb") or 0)
    except (TypeError, ValueError):
        return 0.0


def active_anglers(rows: list) -> set:
    """Anglers with a Spot Session still open ANYWHERE on the lake (any
    spot, any date) - i.e. they've logged at least one lure via the Spot
    Session flow (conditions["source"] == "spot_session") that hasn't been
    through "End Session" yet. Mirrors pages/6_Spot_Session.py's own
    open-session bookkeeping - "session_end_time" is stamped onto every
    lure in a session group at End Session, regardless of whether that
    particular lure had already been individually retired (see that page's
    handler around "Punch-list #34") - but scoped across the WHOLE lake
    rather than one spot, since this roster answers "is this angler out on
    the water right now," not "at this specific spot.\""""
    active = set()
    for row in rows:
        cond = parse_conditions(row)
        if cond.get("source") != "spot_session":
            continue
        angler = (cond.get("angler") or "").strip()
        if not angler or cond.get("session_end_time"):
            continue
        active.add(angler)
    return active


@dataclass
class SpeciesStats:
    species: str
    count: int = 0
    biggest_weight_lb: float = 0.0
    total_weight_lb: float = 0.0


@dataclass
class AnglerActivityStats:
    """Per-angler stats for whatever period built it (a single day, or a
    Sunday-start week) - the period itself isn't tracked here, only the
    aggregated numbers, since every renderer/award function below is
    period-agnostic."""
    angler: str
    active: bool = False
    fish_count: int = 0
    total_weight_lb: float = 0.0
    biggest_fish: Optional[dict] = None  # {"species": ..., "weight_lb": ...}
    species: dict = field(default_factory=dict)  # species -> SpeciesStats

    def species_sorted(self) -> list:
        """Most-caught species first, matching the roster's own
        most-active-first spirit."""
        return sorted(self.species.values(), key=lambda s: (-s.count, s.species.lower()))


def build_period_activity(rows: list, start_iso: str, end_iso: str) -> list:
    """One AnglerActivityStats per angler who is either active right now
    (open session anywhere) or has logged at least one row with trip_date
    in [start_iso, end_iso] inclusive - a combined "activity" roster per
    the angler's own answer when asked what "currently logged in" should
    mean. Sorted active-first, then by the period's fish count descending,
    then name - also per the angler's own answer on ordering.

    A currently-active angler with zero fish logged yet in this period
    still appears (with fish_count 0) - "I'm out there right now" is
    itself activity worth showing, even before the first catch.

    build_daily_activity() and build_weekly_activity() below are both
    thin wrappers around this with start_iso == end_iso (one day) or a
    Sunday-through-Saturday week, respectively."""
    active = active_anglers(rows)
    stats: dict = {}

    def _get(angler: str) -> AnglerActivityStats:
        if angler not in stats:
            stats[angler] = AnglerActivityStats(angler=angler, active=angler in active)
        return stats[angler]

    for a in active:
        _get(a)

    for row in rows:
        trip_date = row.get("trip_date") or ""
        if not (start_iso <= trip_date <= end_iso):
            continue
        cond = parse_conditions(row)
        angler = (cond.get("angler") or "").strip()
        if not angler:
            continue
        s = _get(angler)

        fish_list = cond.get("fish")
        if isinstance(fish_list, list) and fish_list:
            for fish in fish_list:
                if not isinstance(fish, dict):
                    continue
                species = (fish.get("species") or "Unspecified").strip() or "Unspecified"
                count = _fish_count(fish)
                weight = _fish_weight(fish)
                # Punch-list #91: a group-logged small-fish entry's weight_lb
                # is an approximate weight PER FISH (see
                # core.activity_log._new_fish_from_form()'s "count" field),
                # so a fair "total weight caught" multiplies by count rather
                # than summing weight_lb across records as-is.
                total_w = weight * count

                sp = s.species.setdefault(species, SpeciesStats(species=species))
                sp.count += count
                sp.total_weight_lb += total_w
                if weight > sp.biggest_weight_lb:
                    sp.biggest_weight_lb = weight

                s.fish_count += count
                s.total_weight_lb += total_w
                if weight > 0 and (s.biggest_fish is None or weight > s.biggest_fish["weight_lb"]):
                    s.biggest_fish = {"species": species, "weight_lb": weight}
        else:
            # Legacy fallback (a pre-Spot-Session-redesign row, or one
            # logged via the old "Log a Trip" flow) - no per-fish detail,
            # just the trip's own summary columns. Shouldn't happen for
            # anything logged "today" going forward, but stays consistent
            # with pages/8_Leaderboard.py's own fail-soft handling of rows
            # with no fish list at all.
            try:
                trip_fish_count = int(float(row.get("fish_caught") or 0))
            except (TypeError, ValueError):
                trip_fish_count = 0
            if trip_fish_count:
                sp = s.species.setdefault("Unspecified", SpeciesStats(species="Unspecified"))
                sp.count += trip_fish_count
                s.fish_count += trip_fish_count
            try:
                biggest = float(row.get("biggest_fish_lb")) if row.get("biggest_fish_lb") not in (None, "") else None
            except (TypeError, ValueError):
                biggest = None
            if biggest and (s.biggest_fish is None or biggest > s.biggest_fish["weight_lb"]):
                s.biggest_fish = {"species": "Unspecified", "weight_lb": biggest}

    return sorted(stats.values(), key=lambda s: (not s.active, -s.fish_count, s.angler.lower()))


def build_daily_activity(rows: list, today_iso: str) -> list:
    """build_period_activity() scoped to a single day (today_iso as both
    bounds) - see that function's docstring for the full behavior."""
    return build_period_activity(rows, today_iso, today_iso)


def week_bounds(today: date) -> tuple:
    """The Sunday-start, Saturday-end calendar week (inclusive) containing
    `today`, per the angler's own request: "week starting on the Sunday of
    every week." date.weekday() is Monday=0..Sunday=6, so
    (weekday() + 1) % 7 gives days-since-the-most-recent-Sunday for any
    day (Sunday itself -> 0, Monday -> 1, ..., Saturday -> 6)."""
    days_since_sunday = (today.weekday() + 1) % 7
    start = today - timedelta(days=days_since_sunday)
    end = start + timedelta(days=6)
    return start, end


def build_weekly_activity(rows: list, today: date) -> list:
    """build_period_activity() scoped to the Sunday-start calendar week
    containing `today` (see week_bounds()) - same combined roster/sort
    order as build_daily_activity(), just widened to a week of trip_dates
    instead of one. `today` is a plain date object (pass core.weather.
    lake_today()), not an isoformat string, since week_bounds() needs to
    do real date arithmetic on it."""
    start, end = week_bounds(today)
    return build_period_activity(rows, start.isoformat(), end.isoformat())


def daily_awards(day_stats: list) -> dict:
    """The three "of the day/week" tiles - Berkley Biggest Fish, String
    King Top Angler (total weight), Z-Man Top Bag Limit Buster (total fish
    count) - computed across every angler in day_stats who's actually
    logged a fish in this period (works identically whether day_stats came
    from build_daily_activity() or build_weekly_activity()). Each value is
    None when nobody has (a fresh morning, or a no-fish day/week) rather
    than crashing or showing a misleading zero "winner." Ties break toward
    whichever angler sorts first in day_stats (i.e. active anglers, then
    higher fish count, then name - the same
    roster order shown everywhere else on this section)."""
    with_fish = [s for s in day_stats if s.fish_count > 0]
    biggest_fish = None
    for s in with_fish:
        if s.biggest_fish is None:
            continue
        if biggest_fish is None or s.biggest_fish["weight_lb"] > biggest_fish["weight_lb"]:
            biggest_fish = {**s.biggest_fish, "angler": s.angler}
    top_angler_weight = max(with_fish, key=lambda s: s.total_weight_lb) if with_fish else None
    top_bag_count = max(with_fish, key=lambda s: s.fish_count) if with_fish else None
    return {
        "biggest_fish": biggest_fish,
        "top_angler_weight": top_angler_weight,
        "top_bag_count": top_bag_count,
    }


def grand_total(day_stats: list) -> dict:
    """Total fish and total weight across every angler and every species,
    for the leaderboard table's closing "totals for all anglers so far on
    the day/week" row."""
    return {
        "fish_count": sum(s.fish_count for s in day_stats),
        "total_weight_lb": sum(s.total_weight_lb for s in day_stats),
    }


def leaderboard_table_rows(day_stats: list) -> list:
    """Builds the flat display table the angler asked for: one row per
    angler-per-species (Angler, Species, # Fish, Largest, Total), a
    subtotal row closing out each angler's own species rows ("total for
    type of fish and total of all fish" - read as "the angler's own grand
    total across every species they caught"), and one final grand-total row
    across every angler ("the totals for all anglers so far on the day").
    Every value is already display-formatted (lb-oz strings, "-" for a
    weightless/absent reading) so callers can hand this straight to
    st.dataframe with no further formatting.

    Anglers with zero fish today (active but nothing caught yet) contribute
    no rows here at all - they're already covered by the roster line above
    this table; a species-less subtotal row for them would just be a
    "0 fish, 0 lb" row nobody asked to see."""
    rows = []
    for s in day_stats:
        if s.fish_count == 0:
            continue
        first = True
        for sp in s.species_sorted():
            rows.append({
                "Angler": s.angler if first else "",
                "Species": sp.species,
                "# Fish": sp.count,
                "Largest": format_weight_lb_oz(sp.biggest_weight_lb) or "-",
                "Total": format_weight_lb_oz(sp.total_weight_lb) or "-",
            })
            first = False
        rows.append({
            "Angler": "Subtotal",
            "Species": "",
            "# Fish": s.fish_count,
            "Largest": "",
            "Total": format_weight_lb_oz(s.total_weight_lb) or "-",
        })
    total = grand_total(day_stats)
    if total["fish_count"] > 0:
        rows.append({
            "Angler": "All anglers - total",
            "Species": "",
            "# Fish": total["fish_count"],
            "Largest": "",
            "Total": format_weight_lb_oz(total["total_weight_lb"]) or "-",
        })
    return rows
