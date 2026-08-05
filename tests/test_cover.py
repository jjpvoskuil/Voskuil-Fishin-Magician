from pathlib import Path
from core.cover import load_cover_cells, cover_cell_count, get_cover_at


def _write_csv(path: Path, rows):
    header = "lat,lon,dominant_class,wooded_frac,cleared_frac,water_frac,n_px"
    lines = [header] + [",".join(str(v) for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")


def test_missing_file_returns_empty_list(tmp_path):
    assert load_cover_cells(tmp_path / "nope.csv") == []
    assert cover_cell_count(tmp_path / "nope.csv") == 0


def test_loads_cells(tmp_path):
    csv_path = tmp_path / "cover.csv"
    _write_csv(csv_path, [
        (37.3000, -86.2100, "wooded", 0.9, 0.1, 0.0, 400),
        (37.3100, -86.2200, "cleared", 0.0, 1.0, 0.0, 300),
    ])
    cells = load_cover_cells(csv_path)
    assert len(cells) == 2
    assert cells[0]["dominant_class"] == "wooded"
    assert cells[0]["wooded_frac"] == 0.9
    assert cover_cell_count(csv_path) == 2


def test_skips_malformed_rows(tmp_path):
    csv_path = tmp_path / "cover.csv"
    csv_path.write_text(
        "lat,lon,dominant_class,wooded_frac,cleared_frac,water_frac,n_px\n"
        "37.30,-86.21,wooded,0.9,0.1,0.0,400\n"
        "not,a,valid,row,here,,\n"
        "37.31,-86.22,cleared,0.0,1.0,0.0,300\n"
    )
    cells = load_cover_cells(csv_path)
    assert len(cells) == 2


def test_get_cover_at_finds_nearby_cell(tmp_path):
    csv_path = tmp_path / "cover.csv"
    _write_csv(csv_path, [(37.3000, -86.2100, "wooded", 1.0, 0.0, 0.0, 500)])
    hit = get_cover_at(37.3000, -86.2100, max_dist_m=50.0, path=csv_path)
    assert hit is not None
    assert hit["dominant_class"] == "wooded"
    assert hit["distance_m"] < 5.0


def test_get_cover_at_returns_none_when_too_far(tmp_path):
    csv_path = tmp_path / "cover.csv"
    _write_csv(csv_path, [(37.3000, -86.2100, "wooded", 1.0, 0.0, 0.0, 500)])
    assert get_cover_at(37.5000, -86.5000, max_dist_m=50.0, path=csv_path) is None


def test_default_repo_csv_loads_without_error():
    cells = load_cover_cells()
    assert len(cells) > 0
    assert all(-90 <= c["lat"] <= 90 for c in cells)
    assert all(-180 <= c["lon"] <= 180 for c in cells)
    assert all(c["dominant_class"] in ("wooded", "cleared", "water") for c in cells)
