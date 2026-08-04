from pathlib import Path
from core.historic_bathymetry import load_historic_points, historic_point_count


def _write_csv(path: Path, rows, header="lat,lon,depth_ft"):
    lines = [header] + [",".join(str(v) for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")


def test_missing_file_returns_empty_arrays(tmp_path):
    lat, lon, depth = load_historic_points(tmp_path / "nope.csv")
    assert len(lat) == 0 and len(lon) == 0 and len(depth) == 0


def test_loads_points(tmp_path):
    csv_path = tmp_path / "historic.csv"
    _write_csv(csv_path, [(37.3000, -86.2100, 20.0), (37.3100, -86.2200, 0.0)])
    lat, lon, depth = load_historic_points(csv_path)
    assert len(lat) == 2
    assert lat[0] == 37.3000
    assert lon[0] == -86.2100
    assert depth[0] == 20.0
    assert historic_point_count(csv_path) == 2


def test_skips_malformed_rows(tmp_path):
    csv_path = tmp_path / "historic.csv"
    csv_path.write_text("lat,lon,depth_ft\n37.30,-86.21,20\nnot,a,number\n37.31,-86.22,5\n")
    lat, lon, depth = load_historic_points(csv_path)
    assert len(lat) == 2


def test_default_repo_csv_loads_without_error():
    lat, lon, depth = load_historic_points()
    assert len(lat) == len(lon) == len(depth)
    assert len(lat) > 0
    assert all(-90 <= v <= 90 for v in lat)
    assert all(-180 <= v <= 180 for v in lon)
    assert all(d >= 0 for d in depth)
