from pathlib import Path
from core.survey_points import (
    load_survey_points, survey_point_count, survey_file_count, clear_survey_cache,
)


def _write_csv(dir_path: Path, name: str, rows, header="X,Y,Depth(m)"):
    dir_path.mkdir(parents=True, exist_ok=True)
    lines = [header] + [",".join(str(v) for v in row) for row in rows]
    (dir_path / name).write_text("\n".join(lines) + "\n")


def test_empty_dir_returns_empty_arrays(tmp_path):
    clear_survey_cache()
    lat, lon, depth = load_survey_points(tmp_path / "nope")
    assert len(lat) == 0 and len(lon) == 0 and len(depth) == 0


def test_loads_and_converts_meters_to_feet(tmp_path):
    clear_survey_cache()
    _write_csv(tmp_path, "trip1.csv", [(-86.2100, 37.3000, 5.0)])
    lat, lon, depth = load_survey_points(tmp_path)
    assert len(lat) == 1
    assert lat[0] == 37.3000
    assert lon[0] == -86.2100
    assert abs(depth[0] - 5.0 * 3.28084) < 1e-6


def test_combines_multiple_files(tmp_path):
    clear_survey_cache()
    _write_csv(tmp_path, "trip1.csv", [(-86.21, 37.30, 4.0)])
    _write_csv(tmp_path, "trip2.csv", [(-86.22, 37.31, 6.0)])
    lat, lon, depth = load_survey_points(tmp_path)
    assert len(lat) == 2
    assert survey_point_count(tmp_path) == 2
    assert survey_file_count(tmp_path) == 2


def test_dedupes_near_identical_points(tmp_path):
    clear_survey_cache()
    _write_csv(tmp_path, "trip1.csv", [
        (-86.21000, 37.30000, 4.0),
        (-86.21000, 37.30000, 6.0),  # same rounded location - should average with the above
    ])
    lat, lon, depth = load_survey_points(tmp_path)
    assert len(lat) == 1
    assert abs(depth[0] - (5.0 * 3.28084)) < 1e-6  # average of 4.0 and 6.0 = 5.0m


def test_tolerant_of_yxz_column_order(tmp_path):
    clear_survey_cache()
    _write_csv(tmp_path, "trip1.csv", [(37.3000, -86.2100, 5.0)], header="Y,X,Depth(m)")
    lat, lon, depth = load_survey_points(tmp_path)
    assert len(lat) == 1
    assert lat[0] == 37.3000
    assert lon[0] == -86.2100


def test_skips_malformed_rows(tmp_path):
    clear_survey_cache()
    dir_path = tmp_path
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "trip1.csv").write_text("X,Y,Depth(m)\n-86.21,37.30,4.0\nnot,a,number\n-86.22,37.31,5.0\n")
    lat, lon, depth = load_survey_points(dir_path)
    assert len(lat) == 2
