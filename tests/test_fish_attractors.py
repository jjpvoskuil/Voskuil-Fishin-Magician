from pathlib import Path
from core.fish_attractors import load_fish_attractors, fish_attractor_count, fish_attractor_type_counts


def _write_csv(path: Path, rows):
    header = "ident,lat,lon,structure_type"
    lines = [header] + [",".join(str(v) for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")


def test_missing_file_returns_empty_list(tmp_path):
    assert load_fish_attractors(tmp_path / "nope.csv") == []
    assert fish_attractor_count(tmp_path / "nope.csv") == 0


def test_loads_attractors(tmp_path):
    csv_path = tmp_path / "attractors.csv"
    _write_csv(csv_path, [
        ("NRL001", 37.3000, -86.2100, "Brush"),
        ("NRL002", 37.3100, -86.2200, "Christmas Trees"),
    ])
    attractors = load_fish_attractors(csv_path)
    assert len(attractors) == 2
    assert attractors[0]["ident"] == "NRL001"
    assert attractors[0]["structure_type"] == "Brush"
    assert fish_attractor_count(csv_path) == 2


def test_skips_malformed_rows(tmp_path):
    csv_path = tmp_path / "attractors.csv"
    csv_path.write_text(
        "ident,lat,lon,structure_type\n"
        "NRL001,37.30,-86.21,Brush\n"
        "not,a,valid,row\n"
        "NRL002,37.31,-86.22,Rock\n"
    )
    attractors = load_fish_attractors(csv_path)
    assert len(attractors) == 2


def test_type_counts(tmp_path):
    csv_path = tmp_path / "attractors.csv"
    _write_csv(csv_path, [
        ("NRL001", 37.3000, -86.2100, "Brush"),
        ("NRL002", 37.3100, -86.2200, "Brush"),
        ("NRL003", 37.3200, -86.2300, "Rock"),
    ])
    counts = fish_attractor_type_counts(csv_path)
    assert counts == {"Brush": 2, "Rock": 1}


def test_default_repo_csv_loads_without_error():
    attractors = load_fish_attractors()
    assert len(attractors) > 0
    assert all(-90 <= a["lat"] <= 90 for a in attractors)
    assert all(-180 <= a["lon"] <= 180 for a in attractors)
    assert all(a["ident"] for a in attractors)
    assert all(a["structure_type"] for a in attractors)
