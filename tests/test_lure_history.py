import json

from core.lure_history import (
    lure_track_records, track_record_note, MIN_SIMILAR_TRIPS,
    item_fish_per_hour, ITEM_FISH_PER_HOUR_MIN_TRIPS,
)


def _trip(lure_category, structure_type="Main-lake point", water_clarity="Green stained",
          segment="Dawn", spot_id="spot1", fish_caught=1, biggest_fish_lb=1.5, water_temp_f=75.0):
    return {
        "spot_id": spot_id,
        "structure_type": structure_type,
        "water_clarity": water_clarity,
        "segment": segment,
        "fish_caught": fish_caught,
        "biggest_fish_lb": biggest_fish_lb,
        "conditions_json": json.dumps({"lure_category": lure_category, "water_temp_f": water_temp_f}),
    }


def _item_trip(lure_used, structure_type="Main-lake point", spot_id="spot1", fish_caught=1,
               lure_start_time="08:00:00", lure_end_time="09:00:00", lure_category="football_jig"):
    """Same shape as _trip() above, plus the fields item_fish_per_hour() (and,
    underneath it, core.calibration.trip_fish_per_hour()) actually need: a
    top-level lure_used label and a start/end time pair inside
    conditions_json. Defaults to a clean, trustworthy 1-hour window so tests
    only need to override what they're actually exercising."""
    return {
        "spot_id": spot_id,
        "structure_type": structure_type,
        "lure_used": lure_used,
        "fish_caught": fish_caught,
        "conditions_json": json.dumps({
            "lure_category": lure_category,
            "lure_start_time": lure_start_time,
            "lure_end_time": lure_end_time,
        }),
    }


def test_lure_track_records_requires_minimum_similar_trips():
    # A single situation-matching trip on a lure never counts on its own -
    # the angler explicitly asked for this to be cautious.
    rows = [_trip("football_jig")]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert lure_track_records(rows, situation) == {}


def test_lure_track_records_counts_once_minimum_met():
    rows = [_trip("football_jig", fish_caught=1), _trip("football_jig", fish_caught=0)]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    records = lure_track_records(rows, situation)
    assert "football_jig" in records
    rec = records["football_jig"]
    assert rec.similar_trips == 2
    assert rec.trips_with_fish == 1
    assert rec.catch_rate == 0.5


def test_lure_track_records_ignores_trips_that_dont_match_the_situation():
    # Same lure, but at a totally different spot/structure - shouldn't count
    # toward "similar" trips for the CURRENT situation at all.
    rows = [
        _trip("football_jig", spot_id="spot1", structure_type="Main-lake point"),
        _trip("football_jig", spot_id="spot2", structure_type="Flat"),
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    records = lure_track_records(rows, situation, min_similar_trips=1)
    assert set(records.keys()) == {"football_jig"}
    assert records["football_jig"].similar_trips == 1


def test_lure_track_records_same_structure_alone_is_enough_to_match():
    # No spot_id in the current situation (e.g. the 7-Day Forecast page,
    # which only has a general structure type, not a specific spot) - same
    # structure type alone should still be a valid match.
    rows = [_trip("spinnerbait", structure_type="Flat", spot_id="some-other-spot")] * 2
    situation = {"structure_type": "Flat"}
    records = lure_track_records(rows, situation)
    assert "spinnerbait" in records


def test_lure_track_records_skips_rows_with_no_lure_category_or_bad_json():
    rows = [
        {"spot_id": "spot1", "structure_type": "Main-lake point", "conditions_json": "not json", "fish_caught": 1},
        {"spot_id": "spot1", "structure_type": "Main-lake point", "conditions_json": "{}", "fish_caught": 1},
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert lure_track_records(rows, situation) == {}


def test_lure_track_records_skips_rows_where_conditions_json_is_valid_json_but_not_an_object():
    # A real (if latent) bug: conditions_json is JSON-encoded free text, not
    # schema-validated, so a bare number/string/list/null is valid JSON that
    # parses without error but isn't a dict. The old code only caught a
    # genuine parse *error* and then called conditions.get(...) unconditionally
    # on whatever came back - an uncaught AttributeError on any of these,
    # rather than the row just being skipped like any other unusable row.
    rows = [
        {"spot_id": "spot1", "structure_type": "Main-lake point", "conditions_json": "24", "fish_caught": 1},
        {"spot_id": "spot1", "structure_type": "Main-lake point", "conditions_json": '"a string"', "fish_caught": 1},
        {"spot_id": "spot1", "structure_type": "Main-lake point", "conditions_json": "[1, 2]", "fish_caught": 1},
        {"spot_id": "spot1", "structure_type": "Main-lake point", "conditions_json": "null", "fish_caught": 1},
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert lure_track_records(rows, situation) == {}


def test_lure_track_records_tracks_biggest_fish():
    rows = [
        _trip("carolina_rig", biggest_fish_lb=1.2),
        _trip("carolina_rig", biggest_fish_lb=3.4),
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    rec = lure_track_records(rows, situation)["carolina_rig"]
    assert rec.biggest_fish_lb == 3.4


def test_track_record_note_mentions_real_numbers():
    rows = [_trip("carolina_rig", fish_caught=1, biggest_fish_lb=2.5)] * 2
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    rec = lure_track_records(rows, situation)["carolina_rig"]
    note = track_record_note(rec, in_plan_already=False)
    assert "2 of 2" in note
    assert "2.5" in note
    assert "tackle box" in note.lower()

    note_in_plan = track_record_note(rec, in_plan_already=True)
    assert "2 of 2" in note_in_plan
    assert "tackle box" not in note_in_plan.lower()


# --- item_fish_per_hour (punch-list #88) -------------------------------------

KVD = "Strike King - KVD Perfect Plastics Blade Minnow - Pearl, 4-1/2\", 8-pack"
FLUKE = "Zoom - Super Fluke - Pearl"


def test_item_fish_per_hour_requires_minimum_trips():
    # A single logged trip on this exact item shouldn't produce a rate at
    # all yet - same "don't trust one lucky trip" floor as lure_track_records.
    rows = [_item_trip(KVD, fish_caught=2)]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour(rows, situation, KVD) is None


def test_item_fish_per_hour_medians_once_minimum_met():
    rows = [
        _item_trip(KVD, fish_caught=2),  # 2.0 fish/hr
        _item_trip(KVD, fish_caught=4),  # 4.0 fish/hr
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour(rows, situation, KVD) == 3.0


def test_item_fish_per_hour_ignores_an_outlier_via_median_not_mean():
    # Mirrors core.calibration's own median-not-mean rationale - a single
    # freak session (here, 17 fish in one trustworthy hour) shouldn't single-
    # handedly decide a specific lure's rate.
    rows = [
        _item_trip(KVD, fish_caught=1),
        _item_trip(KVD, fish_caught=1),
        _item_trip(KVD, fish_caught=17),
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour(rows, situation, KVD) == 1.0


def test_item_fish_per_hour_matches_only_the_exact_label():
    # Same category, different product - a Zoom Super Fluke's trips must
    # never bleed into the KVD's rate (this is the whole point of #88: tell
    # two same-category products apart, unlike the blended lure_track_records
    # category stat above).
    rows = [
        _item_trip(KVD, fish_caught=1),
        _item_trip(KVD, fish_caught=1),
        _item_trip(FLUKE, fish_caught=10),
        _item_trip(FLUKE, fish_caught=10),
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour(rows, situation, KVD) == 1.0
    assert item_fish_per_hour(rows, situation, FLUKE) == 10.0


def test_item_fish_per_hour_requires_location_match():
    rows = [
        _item_trip(KVD, spot_id="spot1", structure_type="Main-lake point", fish_caught=1),
        _item_trip(KVD, spot_id="spot2", structure_type="Flat", fish_caught=1),
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    # Only one of the two rows matches the current situation's location -
    # below the min-trips floor, so no rate yet.
    assert item_fish_per_hour(rows, situation, KVD) is None


def test_item_fish_per_hour_excludes_rows_with_no_trustworthy_duration():
    rows = [
        _item_trip(KVD, fish_caught=1, lure_start_time="", lure_end_time=""),
        _item_trip(KVD, fish_caught=1, lure_start_time="", lure_end_time=""),
        _item_trip(KVD, fish_caught=3),
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    # Only 1 of 3 rows has a usable duration - still below min_trips (2).
    assert item_fish_per_hour(rows, situation, KVD) is None


def test_item_fish_per_hour_handles_blank_or_missing_input():
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour([], situation, KVD) is None
    assert item_fish_per_hour(None, situation, KVD) is None
    assert item_fish_per_hour([_item_trip(KVD)] * 3, situation, "") is None
    assert item_fish_per_hour([_item_trip(KVD)] * 3, situation, None) is None
    assert item_fish_per_hour([_item_trip(KVD)] * 3, {}, KVD) is None


def test_item_fish_per_hour_ignores_manual_lure_used_entries_that_dont_match_any_label():
    # A manually-typed lure_used string (not built from inventory_item_label)
    # simply won't match - same fallback-to-no-rate behavior as an item with
    # no track record at all, not an error.
    rows = [_item_trip("just some hand-typed note", fish_caught=5)] * 3
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour(rows, situation, KVD) is None


def test_item_fish_per_hour_respects_custom_min_trips():
    rows = [_item_trip(KVD, fish_caught=2)] * 3
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    assert item_fish_per_hour(rows, situation, KVD, min_trips=5) is None
    assert item_fish_per_hour(rows, situation, KVD, min_trips=3) == 2.0
    assert ITEM_FISH_PER_HOUR_MIN_TRIPS == 2
