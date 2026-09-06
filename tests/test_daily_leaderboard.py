import json
from datetime import date

from core.daily_leaderboard import (
    active_anglers, build_daily_activity, build_period_activity, build_weekly_activity,
    daily_awards, grand_total, leaderboard_table_rows, week_bounds,
)

TODAY = "2026-09-06"  # a Sunday
YESTERDAY = "2026-09-05"


def _row(angler, trip_date=TODAY, fish=None, source="spot_session",
         session_end_time=None, fish_caught=None, biggest_fish_lb=None):
    cond = {"angler": angler, "source": source}
    if session_end_time is not None:
        cond["session_end_time"] = session_end_time
    if fish is not None:
        cond["fish"] = fish
    row = {"trip_date": trip_date, "conditions_json": json.dumps(cond)}
    if fish_caught is not None:
        row["fish_caught"] = fish_caught
    if biggest_fish_lb is not None:
        row["biggest_fish_lb"] = biggest_fish_lb
    return row


def _fish(species, weight_lb, count=1):
    return {"species": species, "weight_lb": weight_lb, "count": count}


# --- active_anglers -----------------------------------------------------------

def test_active_angler_has_open_session_with_no_end_time():
    rows = [_row("John", session_end_time=None)]
    assert active_anglers(rows) == {"John"}


def test_ended_session_is_not_active():
    rows = [_row("John", session_end_time="2026-09-06T18:00:00")]
    assert active_anglers(rows) == set()


def test_non_spot_session_rows_never_count_as_active():
    rows = [_row("John", source="log_a_trip", session_end_time=None)]
    assert active_anglers(rows) == set()


def test_open_session_from_a_different_day_still_counts_active():
    # a session spanning a midnight rollover shouldn't vanish from "who's
    # out there right now"
    rows = [_row("John", trip_date=YESTERDAY, session_end_time=None)]
    assert active_anglers(rows) == {"John"}


def test_blank_angler_never_counted():
    rows = [_row("", session_end_time=None)]
    assert active_anglers(rows) == set()


# --- build_daily_activity ------------------------------------------------------

def test_active_angler_with_no_fish_today_still_appears():
    rows = [_row("John", session_end_time=None)]
    stats = build_daily_activity(rows, TODAY)
    assert len(stats) == 1
    assert stats[0].angler == "John"
    assert stats[0].active is True
    assert stats[0].fish_count == 0


def test_angler_posted_today_but_not_active_still_appears():
    rows = [_row("Dave", session_end_time="2026-09-06T12:00:00",
                  fish=[_fish("Largemouth Bass", 3.5)])]
    stats = build_daily_activity(rows, TODAY)
    assert len(stats) == 1
    assert stats[0].angler == "Dave"
    assert stats[0].active is False
    assert stats[0].fish_count == 1


def test_row_from_a_different_day_is_excluded_from_todays_stats():
    rows = [_row("Dave", trip_date=YESTERDAY, session_end_time="2026-09-05T12:00:00",
                  fish=[_fish("Largemouth Bass", 3.5)])]
    stats = build_daily_activity(rows, TODAY)
    assert stats == []


def test_group_logged_fish_multiplies_weight_by_count():
    # a group entry's weight_lb is an approximate weight EACH, not the
    # whole group's combined weight
    rows = [_row("John", session_end_time="x",
                  fish=[_fish("Bluegill", 0.5, count=4)])]
    stats = build_daily_activity(rows, TODAY)
    s = stats[0]
    assert s.fish_count == 4
    assert s.total_weight_lb == 2.0
    sp = s.species["Bluegill"]
    assert sp.count == 4
    assert sp.biggest_weight_lb == 0.5
    assert sp.total_weight_lb == 2.0


def test_biggest_fish_tracked_per_angler_across_species():
    rows = [_row("John", session_end_time="x", fish=[
        _fish("Largemouth Bass", 2.0), _fish("Smallmouth Bass", 4.5), _fish("Bluegill", 0.4),
    ])]
    stats = build_daily_activity(rows, TODAY)
    assert stats[0].biggest_fish == {"species": "Smallmouth Bass", "weight_lb": 4.5}


def test_multiple_rows_for_same_angler_accumulate():
    rows = [
        _row("John", session_end_time="x", fish=[_fish("Largemouth Bass", 2.0)]),
        _row("John", session_end_time="x", fish=[_fish("Largemouth Bass", 3.0)]),
    ]
    stats = build_daily_activity(rows, TODAY)
    assert len(stats) == 1
    assert stats[0].fish_count == 2
    assert stats[0].total_weight_lb == 5.0
    assert stats[0].species["Largemouth Bass"].count == 2


def test_legacy_row_with_no_fish_list_falls_back_to_summary_columns():
    rows = [_row("Grandpa", session_end_time="x", fish=None, fish_caught=3, biggest_fish_lb=2.25)]
    stats = build_daily_activity(rows, TODAY)
    s = stats[0]
    assert s.fish_count == 3
    assert s.biggest_fish == {"species": "Unspecified", "weight_lb": 2.25}


def test_sort_order_active_first_then_fish_count_desc_then_name():
    rows = [
        _row("Carl", session_end_time="x", fish=[_fish("Bass", 1.0)]),  # not active, 1 fish
        _row("Amy", session_end_time="x", fish=[_fish("Bass", 1.0), _fish("Bass", 1.0)]),  # not active, 2 fish
        _row("Bob", session_end_time=None, fish=[_fish("Bass", 1.0)]),  # active, 1 fish
    ]
    stats = build_daily_activity(rows, TODAY)
    assert [s.angler for s in stats] == ["Bob", "Amy", "Carl"]


def test_blank_angler_rows_are_skipped_entirely():
    rows = [_row("", session_end_time="x", fish=[_fish("Bass", 1.0)])]
    assert build_daily_activity(rows, TODAY) == []


def test_no_rows_at_all_gives_empty_roster():
    assert build_daily_activity([], TODAY) == []


# --- daily_awards ---------------------------------------------------------------

def test_awards_are_none_when_nobody_has_fish_today():
    rows = [_row("John", session_end_time=None)]  # active, but no fish yet
    stats = build_daily_activity(rows, TODAY)
    awards = daily_awards(stats)
    assert awards["biggest_fish"] is None
    assert awards["top_angler_weight"] is None
    assert awards["top_bag_count"] is None


def test_biggest_fish_award_picks_the_single_biggest_across_anglers():
    rows = [
        _row("Amy", session_end_time="x", fish=[_fish("Largemouth Bass", 2.0)]),
        _row("Bob", session_end_time="x", fish=[_fish("Largemouth Bass", 6.5)]),
    ]
    stats = build_daily_activity(rows, TODAY)
    awards = daily_awards(stats)
    assert awards["biggest_fish"] == {"species": "Largemouth Bass", "weight_lb": 6.5, "angler": "Bob"}


def test_top_angler_by_weight_vs_top_bag_by_count_can_differ():
    rows = [
        # Amy: 1 big fish, 5.0 total lb
        _row("Amy", session_end_time="x", fish=[_fish("Largemouth Bass", 5.0)]),
        # Bob: 4 small fish, 2.0 total lb
        _row("Bob", session_end_time="x", fish=[_fish("Bluegill", 0.5, count=4)]),
    ]
    stats = build_daily_activity(rows, TODAY)
    awards = daily_awards(stats)
    assert awards["top_angler_weight"].angler == "Amy"
    assert awards["top_bag_count"].angler == "Bob"


# --- grand_total -----------------------------------------------------------------

def test_grand_total_sums_every_angler():
    rows = [
        _row("Amy", session_end_time="x", fish=[_fish("Largemouth Bass", 5.0)]),
        _row("Bob", session_end_time="x", fish=[_fish("Bluegill", 0.5, count=4)]),
    ]
    stats = build_daily_activity(rows, TODAY)
    total = grand_total(stats)
    assert total["fish_count"] == 5
    assert total["total_weight_lb"] == 7.0


def test_grand_total_of_empty_roster_is_zero():
    assert grand_total([]) == {"fish_count": 0, "total_weight_lb": 0}


# --- leaderboard_table_rows -------------------------------------------------------

def test_table_rows_empty_when_nobody_has_fish():
    rows = [_row("John", session_end_time=None)]  # active, no fish yet
    stats = build_daily_activity(rows, TODAY)
    assert leaderboard_table_rows(stats) == []


def test_table_has_species_rows_then_subtotal_then_grand_total():
    rows = [
        _row("Amy", session_end_time="x", fish=[
            _fish("Largemouth Bass", 3.0), _fish("Bluegill", 0.5, count=2),
        ]),
        _row("Bob", session_end_time="x", fish=[_fish("Largemouth Bass", 1.0)]),
    ]
    stats = build_daily_activity(rows, TODAY)
    rows_out = leaderboard_table_rows(stats)

    # Amy sorts first (3 fish vs Bob's 1): 2 species rows (Bluegill's count
    # of 2 outranks the single Largemouth Bass) + her subtotal, then Bob's
    # 1 species row + his subtotal, then the grand total.
    assert len(rows_out) == 6
    assert rows_out[0]["Angler"] == "Amy"
    assert rows_out[0]["Species"] == "Bluegill"
    assert rows_out[1]["Angler"] == ""  # second species row for Amy - angler not repeated
    assert rows_out[1]["Species"] == "Largemouth Bass"
    assert rows_out[2] == {
        "Angler": "Subtotal", "Species": "", "# Fish": 3, "Largest": "", "Total": "4 lb",
    }
    assert rows_out[3]["Angler"] == "Bob"
    assert rows_out[4]["Angler"] == "Subtotal"
    assert rows_out[5] == {
        "Angler": "All anglers - total", "Species": "", "# Fish": 4, "Largest": "", "Total": "5 lb",
    }


def test_active_angler_with_zero_fish_contributes_no_table_rows():
    rows = [
        _row("Active Guy", session_end_time=None),  # active, 0 fish - no rows
        _row("Amy", session_end_time="x", fish=[_fish("Largemouth Bass", 3.0)]),
    ]
    stats = build_daily_activity(rows, TODAY)
    rows_out = leaderboard_table_rows(stats)
    anglers_in_table = {r["Angler"] for r in rows_out if r["Angler"] not in ("", "Subtotal", "All anglers - total")}
    assert anglers_in_table == {"Amy"}


# --- week_bounds -------------------------------------------------------------------

def test_week_bounds_sunday_is_the_start_of_its_own_week():
    start, end = week_bounds(date(2026, 9, 6))  # a Sunday
    assert start == date(2026, 9, 6)
    assert end == date(2026, 9, 12)  # the following Saturday


def test_week_bounds_saturday_is_the_end_of_its_own_week():
    start, end = week_bounds(date(2026, 9, 12))  # a Saturday
    assert start == date(2026, 9, 6)
    assert end == date(2026, 9, 12)


def test_week_bounds_mid_week_day():
    start, end = week_bounds(date(2026, 9, 9))  # a Wednesday
    assert start == date(2026, 9, 6)
    assert end == date(2026, 9, 12)


def test_week_bounds_spans_a_month_boundary():
    start, end = week_bounds(date(2026, 10, 1))  # a Thursday
    assert start == date(2026, 9, 27)  # the prior Sunday, in September
    assert end == date(2026, 10, 3)


# --- build_period_activity / build_weekly_activity ----------------------------------

def test_period_activity_includes_rows_anywhere_in_an_inclusive_range():
    rows = [
        _row("Amy", trip_date="2026-09-06", session_end_time="x", fish=[_fish("Bass", 2.0)]),
        _row("Amy", trip_date="2026-09-09", session_end_time="x", fish=[_fish("Bass", 1.0)]),
        _row("Amy", trip_date="2026-09-12", session_end_time="x", fish=[_fish("Bass", 3.0)]),
    ]
    stats = build_period_activity(rows, "2026-09-06", "2026-09-12")
    assert len(stats) == 1
    assert stats[0].fish_count == 3
    assert stats[0].total_weight_lb == 6.0


def test_period_activity_excludes_rows_outside_the_range():
    rows = [
        _row("Amy", trip_date="2026-09-05", session_end_time="x", fish=[_fish("Bass", 2.0)]),  # Saturday before
        _row("Amy", trip_date="2026-09-13", session_end_time="x", fish=[_fish("Bass", 3.0)]),  # Sunday after
    ]
    stats = build_period_activity(rows, "2026-09-06", "2026-09-12")
    assert stats == []


def test_weekly_activity_uses_sunday_start_week_containing_today():
    rows = [
        _row("Amy", trip_date="2026-09-06", session_end_time="x", fish=[_fish("Bass", 2.0)]),  # Sun (in week)
        _row("Amy", trip_date="2026-09-12", session_end_time="x", fish=[_fish("Bass", 1.0)]),  # Sat (in week)
        _row("Amy", trip_date="2026-09-05", session_end_time="x", fish=[_fish("Bass", 5.0)]),  # prior Sat (out)
    ]
    stats = build_weekly_activity(rows, date(2026, 9, 9))  # a Wednesday in that week
    assert len(stats) == 1
    assert stats[0].fish_count == 2
    assert stats[0].total_weight_lb == 3.0


def test_weekly_activity_still_includes_an_active_angler_with_no_catch_this_week():
    rows = [_row("John", trip_date="2026-08-01", session_end_time=None)]  # open session, old date
    stats = build_weekly_activity(rows, date(2026, 9, 9))
    assert len(stats) == 1
    assert stats[0].angler == "John"
    assert stats[0].active is True
    assert stats[0].fish_count == 0


def test_weekly_awards_and_table_reuse_the_same_functions_as_daily():
    rows = [
        _row("Amy", trip_date="2026-09-06", session_end_time="x", fish=[_fish("Largemouth Bass", 5.0)]),
        _row("Bob", trip_date="2026-09-10", session_end_time="x", fish=[_fish("Bluegill", 0.5, count=4)]),
    ]
    stats = build_weekly_activity(rows, date(2026, 9, 9))
    awards = daily_awards(stats)
    assert awards["top_angler_weight"].angler == "Amy"
    assert awards["top_bag_count"].angler == "Bob"
    total = grand_total(stats)
    assert total == {"fish_count": 5, "total_weight_lb": 7.0}
    table = leaderboard_table_rows(stats)
    assert table[-1] == {
        "Angler": "All anglers - total", "Species": "", "# Fish": 5, "Largest": "", "Total": "7 lb",
    }
