import json
from datetime import date

from core.stringer import (
    build_frames, season_label, hero_states, biggest_fish, longest_fish,
    top_anglers, hot_lures, top_spots, top_sessions, daily_activity_series,
    species_mix, format_date_short, format_weight, TOP_N,
)

SPOT_NAMES = {"s1": "Stripe Island Point", "s2": "Midnight Point"}


def _row(trip_id, trip_date, angler="John", spot_id="s1", lure_used="Fluke",
         color_used="Green Pumpkin", fish_caught=0, fish=None, session_id=""):
    cond = {"angler": angler, "source": "spot_session"}
    if fish is not None:
        cond["fish"] = fish
    return {
        "trip_id": trip_id, "session_id": session_id, "trip_date": trip_date, "spot_id": spot_id,
        "spot_name": None, "lure_used": lure_used, "color_used": color_used,
        "fish_caught": fish_caught, "conditions_json": json.dumps(cond),
    }


def _fish(species, weight_lb=None, count=1, length_in=None):
    d = {"species": species, "weight_lb": weight_lb, "count": count}
    if length_in is not None:
        d["length_in"] = length_in
    return d


# --- build_frames -----------------------------------------------------------

def test_build_frames_expands_fish_list_and_carries_lure_color_spot():
    rows = [_row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", 2.5, length_in=18.0)])]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    assert len(fish_df) == 1
    r = fish_df.iloc[0]
    assert r["species"] == "Largemouth Bass"
    assert r["weight_lb"] == 2.5
    assert r["length_in"] == 18.0
    assert r["lure"] == "Fluke"
    assert r["color"] == "Green Pumpkin"
    assert r["spot"] == "Stripe Island Point"
    assert r["angler"] == "John"
    assert len(trips_df) == 1
    assert trips_df.iloc[0]["fish_count"] == 1


def test_build_frames_group_logged_fish_count_sums_into_trip_fish_count():
    rows = [_row("t1", "2026-08-01", fish=[_fish("White Bass", 0.8, count=3)])]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    assert fish_df.iloc[0]["count"] == 3
    assert trips_df.iloc[0]["fish_count"] == 3


def test_build_frames_legacy_row_falls_back_to_fish_caught_column():
    rows = [_row("t1", "2026-08-01", fish_caught=4, fish=None)]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    assert fish_df.empty
    assert trips_df.iloc[0]["fish_count"] == 4


def test_build_frames_blank_angler_lure_color_default_to_unspecified():
    rows = [_row("t1", "2026-08-01", angler="", lure_used="", color_used="", fish=[_fish("Catfish", 1.0)])]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    assert fish_df.iloc[0]["angler"] == "Unspecified"
    assert fish_df.iloc[0]["lure"] == "Unspecified"
    assert fish_df.iloc[0]["color"] == "Unspecified"


def test_build_frames_session_key_groups_by_real_session_id_or_falls_back_to_trip_id():
    rows = [
        _row("t1", "2026-08-01", session_id="sess-A", fish=[_fish("Largemouth Bass", 2.0)]),
        _row("t2", "2026-08-01", session_id="sess-A", fish=[_fish("Largemouth Bass", 1.0)]),
        _row("t3", "2026-08-01", session_id="", fish=[_fish("Largemouth Bass", 3.0)]),
    ]
    _, trips_df = build_frames(rows, SPOT_NAMES)
    keys = dict(zip(trips_df["trip_id"], trips_df["session_key"]))
    assert keys["t1"] == keys["t2"] == "s:sess-A"
    assert keys["t3"] == "t:t3"


# --- season_label -------------------------------------------------------------

def test_season_label_spans_min_to_max_date():
    rows = [_row("t1", "2026-08-01"), _row("t2", "2026-09-10")]
    _, trips_df = build_frames(rows, SPOT_NAMES)
    assert season_label(trips_df) == "Aug 1 – Sep 10"


def test_season_label_single_day():
    rows = [_row("t1", "2026-08-01")]
    _, trips_df = build_frames(rows, SPOT_NAMES)
    assert season_label(trips_df) == "Aug 1"


def test_season_label_none_when_empty():
    fish_df, trips_df = build_frames([], SPOT_NAMES)
    assert season_label(trips_df) is None


# --- hero_states --------------------------------------------------------------

def test_hero_states_days_on_water_and_shares():
    rows = [
        _row("t1", "2026-08-01", spot_id="s1", fish=[_fish("Largemouth Bass", 2.0)]),
        _row("t2", "2026-08-03", spot_id="s1", fish=[_fish("Largemouth Bass", 1.0)]),
        _row("t3", "2026-08-03", spot_id="s2", fish=[_fish("White Bass", 0.8)]),
    ]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    states = hero_states(fish_df, trips_df)
    assert len(states) == 3

    days = states[0]
    assert days.title == "Days on the Water"
    assert days.value == 2  # Aug 1 and Aug 3
    assert days.total == 3  # Aug 1,2,3 inclusive
    assert days.sec_value == "3"  # 3 trip_log rows

    spot = states[1]
    assert spot.title == "Stripe Island Point Share"
    assert spot.value == 2  # 2 of 3 fish caught there
    assert spot.total == 3

    species = states[2]
    assert species.title == "Largemouth Bass Share"
    assert species.value == 2
    assert species.total == 3
    assert "White Bass" in species.desc


def test_hero_states_skips_share_states_when_no_fish_logged():
    rows = [_row("t1", "2026-08-01", fish=None, fish_caught=0)]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    states = hero_states(fish_df, trips_df)
    assert len(states) == 1
    assert states[0].title == "Days on the Water"


def test_hero_states_empty_history():
    fish_df, trips_df = build_frames([], SPOT_NAMES)
    assert hero_states(fish_df, trips_df) == []


# --- biggest_fish / longest_fish ------------------------------------------------

def test_biggest_fish_sorted_desc_and_formatted():
    rows = [
        _row("t1", "2026-08-01", angler="John", fish=[_fish("Largemouth Bass", 2.5)]),
        _row("t2", "2026-08-02", angler="Matthew", fish=[_fish("Largemouth Bass", 4.4375)]),
    ]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    rows_out = biggest_fish(fish_df)
    assert len(rows_out) == 2
    assert rows_out[0]["primary"] == format_weight(4.4375) == "4 lb 7 oz"
    assert "Matthew" in rows_out[0]["secondary"]
    assert rows_out[0]["num"] == rows_out[0]["primary"]


def test_biggest_fish_ignores_fish_with_no_weight():
    rows = [_row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", None)])]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    assert biggest_fish(fish_df) == []


def test_biggest_fish_caps_at_top_n():
    rows = [_row(f"t{i}", "2026-08-01", fish=[_fish("Largemouth Bass", float(i))]) for i in range(TOP_N + 5)]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    assert len(biggest_fish(fish_df)) == TOP_N


def test_longest_fish_primary_includes_species_and_weight():
    rows = [_row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", 2.5, length_in=19.0)])]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    out = longest_fish(fish_df)
    assert out[0]["primary"] == "Largemouth Bass · 2 lb 8 oz"
    assert out[0]["num"] == "19.0 in"


def test_longest_fish_falls_back_when_weight_missing():
    rows = [_row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", None, length_in=19.0)])]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    assert longest_fish(fish_df)[0]["primary"] == "Largemouth Bass"


# --- top_anglers ----------------------------------------------------------------

def test_top_anglers_totals_weight_times_count_and_averages():
    rows = [
        _row("t1", "2026-08-01", angler="John", fish=[_fish("White Bass", 1.0, count=3)]),
        _row("t2", "2026-08-02", angler="John", fish=[_fish("Largemouth Bass", 2.0, count=1)]),
        _row("t3", "2026-08-03", angler="Matthew", fish=[_fish("Largemouth Bass", 0.5, count=1)]),
    ]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    out = top_anglers(fish_df)
    john = next(r for r in out if r["primary"] == "John")
    assert john["num"] == "4 fish"
    assert "5 lb" in john["secondary"]  # 3*1.0 + 1*2.0 = 5 lb total
    assert out[0]["primary"] == "John"  # sorted by fish count desc


def test_top_anglers_no_weight_data_yet_fallback_text():
    rows = [_row("t1", "2026-08-01", angler="John", fish=[_fish("Catfish", None, count=2)])]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    out = top_anglers(fish_df)
    assert "no weight data" in out[0]["secondary"]


# --- hot_lures --------------------------------------------------------------------

def test_hot_lures_groups_by_lure_and_color_with_rate_and_low_sample_tag():
    rows = [
        _row("t1", "2026-08-01", lure_used="Spook", color_used="Blue Chrome", fish=[_fish("Largemouth Bass", 2.0, count=2)]),
        _row("t2", "2026-08-02", lure_used="Spook", color_used="Blue Chrome", fish=[_fish("Largemouth Bass", 1.0, count=1)]),
    ]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    out = hot_lures(fish_df, trips_df)
    assert out[0]["primary"] == "Spook"
    assert out[0]["num"] == "3 fish"
    assert "Blue Chrome" in out[0]["secondary"]
    assert "2 uses" in out[0]["secondary"]
    assert out[0]["tag"] == "2 use sample"  # uses < 3


def test_hot_lures_no_tag_when_uses_at_or_above_three():
    rows = [_row(f"t{i}", "2026-08-01", lure_used="Spook", color_used="Blue Chrome",
                 fish=[_fish("Largemouth Bass", 1.0)]) for i in range(3)]
    fish_df, trips_df = build_frames(rows, SPOT_NAMES)
    assert hot_lures(fish_df, trips_df)[0]["tag"] is None


def test_hot_lures_empty_when_no_fish_or_no_trips():
    fish_df, trips_df = build_frames([], SPOT_NAMES)
    assert hot_lures(fish_df, trips_df) == []


# --- top_spots --------------------------------------------------------------------

def test_top_spots_ranks_by_biggest_fish_and_shows_total_landed():
    rows = [
        _row("t1", "2026-08-01", spot_id="s1", angler="John", fish=[_fish("Largemouth Bass", 4.0)]),
        _row("t2", "2026-08-02", spot_id="s1", angler="Matthew", fish=[_fish("Largemouth Bass", 1.0)]),
        _row("t3", "2026-08-03", spot_id="s2", angler="John", fish=[_fish("Largemouth Bass", 2.0)]),
    ]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    out = top_spots(fish_df)
    assert out[0]["primary"] == "Stripe Island Point"
    assert out[0]["num"] == format_weight(4.0)
    assert "2 fish landed here" in out[0]["secondary"]
    assert "best by John" in out[0]["secondary"]


def test_top_spots_empty_when_no_weighed_fish():
    rows = [_row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", None)])]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    assert top_spots(fish_df) == []


# --- top_sessions -----------------------------------------------------------------

def test_top_sessions_groups_by_session_id_summing_fish_across_lures():
    rows = [
        _row("t1", "2026-08-13", session_id="sessA", spot_id="s1", angler="Matthew", fish_caught=10, fish=[_fish("Largemouth Bass", 2.0, count=10)]),
        _row("t2", "2026-08-13", session_id="sessA", spot_id="s1", angler="Matthew", fish=[_fish("Largemouth Bass", 1.0, count=5)]),
        _row("t3", "2026-08-14", session_id="", spot_id="s2", angler="John", fish=[_fish("Largemouth Bass", 1.0, count=1)]),
    ]
    _, trips_df = build_frames(rows, SPOT_NAMES)
    out = top_sessions(trips_df)
    assert out[0]["primary"] == "Aug 13 outing"
    assert out[0]["num"] == "15 fish"
    assert "Stripe Island Point" in out[0]["secondary"]
    assert "Matthew" in out[0]["secondary"]


def test_top_sessions_excludes_zero_fish_sessions():
    rows = [_row("t1", "2026-08-01", fish_caught=0, fish=None)]
    _, trips_df = build_frames(rows, SPOT_NAMES)
    assert top_sessions(trips_df) == []


# --- glance panel helpers ----------------------------------------------------------

def test_daily_activity_series_zero_fills_days_with_no_catches():
    rows = [_row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", 1.0, count=2)])]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    series = daily_activity_series(fish_df, date(2026, 8, 1), date(2026, 8, 3))
    assert series == [(date(2026, 8, 1), 2), (date(2026, 8, 2), 0), (date(2026, 8, 3), 0)]


def test_daily_activity_series_empty_bounds():
    fish_df, _ = build_frames([], SPOT_NAMES)
    assert daily_activity_series(fish_df, None, None) == []


def test_species_mix_sorted_desc_and_capped():
    rows = [
        _row("t1", "2026-08-01", fish=[_fish("Largemouth Bass", 1.0, count=8)]),
        _row("t2", "2026-08-02", fish=[_fish("White Bass", 1.0, count=3)]),
    ]
    fish_df, _ = build_frames(rows, SPOT_NAMES)
    mix = species_mix(fish_df)
    assert mix[0] == ("Largemouth Bass", 8)
    assert mix[1] == ("White Bass", 3)


def test_species_mix_empty():
    fish_df, _ = build_frames([], SPOT_NAMES)
    assert species_mix(fish_df) == []


def test_format_date_short():
    assert format_date_short(date(2026, 8, 13)) == "Aug 13"
    assert format_date_short(None) == ""


def test_format_weight_fallback_dash():
    assert format_weight(None) == "–"
    assert format_weight(0) == "–"
    assert format_weight(2.5) == "2 lb 8 oz"
