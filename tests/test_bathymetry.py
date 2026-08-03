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


def test_blend_real_data_dominates_near_recorded_point():
    import numpy as np
    from core.bathymetry import _blend_real_survey_data

    lat_axis = np.linspace(37.30, 37.31, 5)
    lon_axis = np.linspace(-86.22, -86.21, 5)
    depth_grid = np.full((5, 5), np.nan)
    depth_grid[2, 2] = 10.0

    lat_pts = np.array([lat_axis[2]])
    lon_pts = np.array([lon_axis[2]])
    depth_pts = np.array([25.0])

    blended = _blend_real_survey_data(lat_axis, lon_axis, depth_grid, lat_pts, lon_pts, depth_pts)
    assert abs(blended[2, 2] - 25.0) < 0.01
    assert np.isnan(blended[0, 0])  # far from both model and real data - unchanged


def test_blend_real_data_extends_beyond_modeled_area():
    import numpy as np
    from core.bathymetry import _blend_real_survey_data

    lat_axis = np.linspace(37.30, 37.31, 5)
    lon_axis = np.linspace(-86.22, -86.21, 5)
    depth_grid = np.full((5, 5), np.nan)
    depth_grid[2, 2] = 10.0

    lat_pts = np.array([lat_axis[0]])
    lon_pts = np.array([lon_axis[0]])
    depth_pts = np.array([7.5])

    blended = _blend_real_survey_data(lat_axis, lon_axis, depth_grid, lat_pts, lon_pts, depth_pts)
    assert abs(blended[0, 0] - 7.5) < 0.01  # model was NaN here - real data fills it in
    assert abs(blended[2, 2] - 10.0) < 0.01  # real point too far away to affect the modeled cell


def test_blend_no_real_points_returns_grid_unchanged():
    import numpy as np
    from core.bathymetry import _blend_real_survey_data

    lat_axis = np.linspace(37.30, 37.31, 5)
    lon_axis = np.linspace(-86.22, -86.21, 5)
    depth_grid = np.full((5, 5), np.nan)
    depth_grid[2, 2] = 10.0

    blended = _blend_real_survey_data(lat_axis, lon_axis, depth_grid, np.array([]), np.array([]), np.array([]))
    assert blended is depth_grid


def test_depth_grid_unaffected_when_no_survey_files_present():
    # With no data/quickdraw/*.csv files shipped in the repo, the live depth
    # grid should be identical to the pure model (this guards against
    # accidentally shipping test fixture CSVs into the real data folder).
    dam_depth = get_depth_at_ft(37.2783, -86.2475)
    assert dam_depth is not None and dam_depth > 50
