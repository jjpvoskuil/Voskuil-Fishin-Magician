from core.bathymetry import get_depth_at_ft, infer_structure_type, contour_lines, lake_center
from core.lures import STRUCTURE_TYPES


def test_depth_at_verified_anchors_is_reasonable():
    dam_depth = get_depth_at_ft(37.2783, -86.2475)
    assert dam_depth is not None and dam_depth > 50  # dam should be modeled deep

    dog_creek_depth = get_depth_at_ft(37.3191, -86.1341)
    assert dog_creek_depth is not None and dog_creek_depth < dam_depth  # upstream arm shallower


def test_depth_outside_modeled_area_is_none():
    assert get_depth_at_ft(38.0, -87.0) is None


def test_infer_structure_type_returns_known_category():
    for lat, lon in [(37.2783, -86.2475), (37.3191, -86.1341), (37.3526, -86.1325)]:
        assert infer_structure_type(lat, lon) in STRUCTURE_TYPES


def test_contour_lines_produced_and_ordered():
    levels = contour_lines()
    assert len(levels) > 0
    depths = [l["depth_ft"] for l in levels]
    assert depths == sorted(depths)
    for level in levels:
        assert all(len(path) >= 2 for path in level["paths"])


def test_lake_center_within_expected_bounds():
    lat, lon = lake_center()
    assert 37.2 < lat < 37.5
    assert -86.35 < lon < -86.05
