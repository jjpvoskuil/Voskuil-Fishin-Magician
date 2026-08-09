from core.lake_spots import (
    LakeSpot, LOCATION_TYPES, BOTTOM_STRUCTURE_OPTIONS, TRANSITION_GRADE_OPTIONS,
    append_spot, delete_spot, nearest_spot_within, read_all_spots, split_bottom_structure,
    update_spot,
)


def test_empty_spots_file_returns_empty_list(tmp_path):
    path = tmp_path / "spots.csv"
    assert read_all_spots(path) == []


def test_append_and_read_spot(tmp_path):
    path = tmp_path / "spots.csv"
    spot = LakeSpot(
        name="Rock Point East", lat=37.3, lon=-86.2, location_type="Main-lake point",
        bottom_structure=["Rocky", "Gravel"], main_depth_ft=12.0, transition_depth_ft=22.0,
        transition_grade="High (steep break)", notes="Good in summer.",
    )
    append_spot(spot, path)
    rows = read_all_spots(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Rock Point East"
    assert row["lat"] == "37.3"
    assert row["lon"] == "-86.2"
    assert row["location_type"] == "Main-lake point"
    assert split_bottom_structure(row["bottom_structure"]) == ["Rocky", "Gravel"]
    assert row["main_depth_ft"] == "12.0"
    assert row["transition_depth_ft"] == "22.0"
    assert row["transition_grade"] == "High (steep break)"
    assert row["notes"] == "Good in summer."
    assert row["spot_id"] == spot.spot_id


def test_spot_with_no_bottom_structure_round_trips_as_empty_list(tmp_path):
    path = tmp_path / "spots.csv"
    spot = LakeSpot(name="Mystery Flat", lat=37.31, lon=-86.21)
    append_spot(spot, path)
    row = read_all_spots(path)[0]
    assert split_bottom_structure(row["bottom_structure"]) == []


def test_update_spot_changes_fields(tmp_path):
    path = tmp_path / "spots.csv"
    spot = LakeSpot(name="Dock Row", lat=37.3, lon=-86.2, location_type="Boat dock")
    append_spot(spot, path)

    found = update_spot(spot.spot_id, path, main_depth_ft=8.5, transition_depth_ft=15.0,
                         transition_grade="Medium", notes="Shady in the afternoon.")
    assert found is True
    row = read_all_spots(path)[0]
    assert row["main_depth_ft"] == "8.5"
    assert row["transition_depth_ft"] == "15.0"
    assert row["transition_grade"] == "Medium"
    assert row["notes"] == "Shady in the afternoon."


def test_update_spot_accepts_bottom_structure_as_list(tmp_path):
    path = tmp_path / "spots.csv"
    spot = LakeSpot(name="Timber Flat", lat=37.3, lon=-86.2)
    append_spot(spot, path)

    update_spot(spot.spot_id, path, bottom_structure=["Standing timber", "Stumps"])
    row = read_all_spots(path)[0]
    assert split_bottom_structure(row["bottom_structure"]) == ["Standing timber", "Stumps"]


def test_update_spot_none_value_clears_field(tmp_path):
    path = tmp_path / "spots.csv"
    spot = LakeSpot(name="Bluff Wall", lat=37.3, lon=-86.2, main_depth_ft=20.0)
    append_spot(spot, path)

    update_spot(spot.spot_id, path, main_depth_ft=None)
    row = read_all_spots(path)[0]
    assert row["main_depth_ft"] == ""


def test_update_spot_missing_id_returns_false(tmp_path):
    path = tmp_path / "spots.csv"
    assert update_spot("nonexistent", path, main_depth_ft=5) is False


def test_delete_spot_removes_row(tmp_path):
    path = tmp_path / "spots.csv"
    spot1 = LakeSpot(name="Point A", lat=37.30, lon=-86.20)
    spot2 = LakeSpot(name="Point B", lat=37.31, lon=-86.21)
    append_spot(spot1, path)
    append_spot(spot2, path)

    assert delete_spot(spot1.spot_id, path) is True
    rows = read_all_spots(path)
    assert len(rows) == 1
    assert rows[0]["spot_id"] == spot2.spot_id


def test_delete_spot_missing_id_returns_false(tmp_path):
    path = tmp_path / "spots.csv"
    assert delete_spot("nonexistent", path) is False


def test_nearest_spot_within_finds_close_match():
    spots = [
        {"spot_id": "a", "name": "Point A", "lat": "37.30000", "lon": "-86.20000"},
        {"spot_id": "b", "name": "Point B", "lat": "37.35000", "lon": "-86.25000"},
    ]
    hit = nearest_spot_within(37.30001, -86.20001, spots)
    assert hit is not None
    assert hit["spot_id"] == "a"


def test_nearest_spot_within_returns_none_when_too_far():
    spots = [{"spot_id": "a", "name": "Point A", "lat": "37.30000", "lon": "-86.20000"}]
    assert nearest_spot_within(37.5, -86.5, spots) is None


def test_nearest_spot_within_returns_none_for_empty_list():
    assert nearest_spot_within(37.3, -86.2, []) is None


def test_location_and_bottom_structure_option_lists_are_nonempty():
    assert len(LOCATION_TYPES) > 5
    assert len(BOTTOM_STRUCTURE_OPTIONS) > 5
    assert len(TRANSITION_GRADE_OPTIONS) == 3
