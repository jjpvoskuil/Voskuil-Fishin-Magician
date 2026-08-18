import tempfile
from datetime import datetime
from pathlib import Path

from core.lake_water_quality import SurfaceWaterQuality
from core.water_quality_log import append_if_new, read_log, parsed_log, FIELDNAMES


def _tmp_log_path() -> Path:
    d = tempfile.mkdtemp()
    return Path(d) / "water_quality_log.csv"


def _reading(observed_at="2026-08-06T14:00:00", water_temp_f=86.5, do_mg_l=10.66, do_saturation_pct=147.0):
    return SurfaceWaterQuality(
        observed_at=datetime.fromisoformat(observed_at),
        water_temp_f=water_temp_f, do_mg_l=do_mg_l, do_saturation_pct=do_saturation_pct,
    )


def test_read_log_creates_the_file_with_a_header_if_missing():
    path = _tmp_log_path()
    assert not path.exists()
    rows = read_log(path)
    assert rows == []
    assert path.exists()


def test_append_if_new_appends_and_returns_true_for_a_genuinely_new_reading():
    path = _tmp_log_path()
    added = append_if_new(_reading(), path)
    assert added is True
    rows = read_log(path)
    assert len(rows) == 1
    assert rows[0]["observed_at"] == "2026-08-06T14:00:00"
    assert rows[0]["water_temp_f"] == "86.5"


def test_append_if_new_is_a_noop_for_a_reading_already_logged():
    path = _tmp_log_path()
    append_if_new(_reading(), path)
    added_again = append_if_new(_reading(), path)
    assert added_again is False
    assert len(read_log(path)) == 1


def test_append_if_new_adds_a_second_row_for_a_genuinely_different_survey_date():
    path = _tmp_log_path()
    append_if_new(_reading(observed_at="2026-08-06T14:00:00"), path)
    added = append_if_new(_reading(observed_at="2026-08-20T13:30:00", water_temp_f=83.1), path)
    assert added is True
    assert len(read_log(path)) == 2


def test_parsed_log_returns_real_datetime_and_float_types():
    path = _tmp_log_path()
    append_if_new(_reading(), path)
    parsed = parsed_log(path)
    assert len(parsed) == 1
    assert isinstance(parsed[0]["observed_at"], datetime)
    assert isinstance(parsed[0]["water_temp_f"], float)
    assert parsed[0]["water_temp_f"] == 86.5
    assert parsed[0]["do_mg_l"] == 10.66


def test_parsed_log_skips_a_corrupted_row_instead_of_raising():
    path = _tmp_log_path()
    append_if_new(_reading(), path)
    # Simulate a partially-written/corrupted row appended alongside a good one.
    with open(path, "a", newline="") as f:
        f.write("not-a-date,not-a-number,10.0,100.0\n")
    parsed = parsed_log(path)
    assert len(parsed) == 1  # the corrupted row is skipped, not raised on
    assert parsed[0]["water_temp_f"] == 86.5


def test_field_order_matches_fieldnames_constant():
    path = _tmp_log_path()
    append_if_new(_reading(), path)
    with open(path) as f:
        header = f.readline().strip().split(",")
    assert header == FIELDNAMES
