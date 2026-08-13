from datetime import date, datetime, timedelta

from core.forecast_freeze import apply_freeze, read_frozen_segments
from core.scoring import SegmentForecast


def _make_day(the_date, segment_defs, overall=5.0):
    """segment_defs: list of (name, start, end, score) - builds a minimal
    fake object with just the attributes apply_freeze()/its caller touch."""
    class _FakeDay:
        pass

    day = _FakeDay()
    day.the_date = the_date
    day.overall_score = overall
    day.segments = [
        SegmentForecast(name=name, start=start, end=end, score=score, solunar_overlap=None, notes=[], breakdown=[])
        for name, start, end, score in segment_defs
    ]
    return day


def test_segment_still_in_progress_is_left_untouched(tmp_path):
    path = tmp_path / "freeze.csv"
    d = date(2026, 8, 13)
    now = datetime(2026, 8, 13, 10, 0)
    day = _make_day(d, [("Midday", datetime(2026, 8, 13, 9, 0), datetime(2026, 8, 13, 14, 0), 6.0)])

    newly_frozen = apply_freeze(day, now=now, path=path)

    assert newly_frozen == []
    assert day.segments[0].score == 6.0
    assert read_frozen_segments(d, path) == {}


def test_segment_that_just_ended_gets_frozen_on_first_call(tmp_path):
    path = tmp_path / "freeze.csv"
    d = date(2026, 8, 13)
    now = datetime(2026, 8, 13, 10, 0)
    day = _make_day(d, [("Dawn", datetime(2026, 8, 13, 5, 0), datetime(2026, 8, 13, 7, 0), 8.5)])

    newly_frozen = apply_freeze(day, now=now, path=path)

    assert newly_frozen == ["Dawn"]
    assert day.segments[0].score == 8.5  # unchanged on the freezing call itself
    frozen = read_frozen_segments(d, path)
    assert frozen["Dawn"]["score"] == 8.5


def test_already_frozen_segment_overrides_a_freshly_recomputed_score(tmp_path):
    path = tmp_path / "freeze.csv"
    d = date(2026, 8, 13)
    now = datetime(2026, 8, 13, 10, 0)

    day1 = _make_day(d, [("Dawn", datetime(2026, 8, 13, 5, 0), datetime(2026, 8, 13, 7, 0), 8.5)])
    apply_freeze(day1, now=now, path=path)

    # Simulate a later page load: the weather bundle refreshed and score_day()
    # now computes a DIFFERENT score for the same, already-past segment.
    later_now = datetime(2026, 8, 13, 11, 0)
    day2 = _make_day(d, [("Dawn", datetime(2026, 8, 13, 5, 0), datetime(2026, 8, 13, 7, 0), 3.2)])

    newly_frozen = apply_freeze(day2, now=later_now, path=path)

    assert newly_frozen == []  # nothing NEW frozen this call
    assert day2.segments[0].score == 8.5  # locked to the original frozen value, not 3.2


def test_overall_score_recomputed_when_a_frozen_value_overrides_a_fresh_one(tmp_path):
    path = tmp_path / "freeze.csv"
    d = date(2026, 8, 13)
    now = datetime(2026, 8, 13, 10, 0)

    day1 = _make_day(d, [
        ("Dawn", datetime(2026, 8, 13, 5, 0), datetime(2026, 8, 13, 7, 0), 8.0),
        ("Morning", datetime(2026, 8, 13, 7, 0), datetime(2026, 8, 13, 11, 0), 6.0),
    ], overall=7.0)
    apply_freeze(day1, now=now, path=path)  # freezes Dawn at 8.0; Morning still in progress

    # A later run: Morning has now ended too, and the weather refresh changed
    # what score_day() computes for the already-frozen Dawn segment (it
    # shouldn't matter - Dawn stays 8.0) as well as a fresh Morning score.
    later_now = datetime(2026, 8, 13, 12, 0)
    day2 = _make_day(d, [
        ("Dawn", datetime(2026, 8, 13, 5, 0), datetime(2026, 8, 13, 7, 0), 2.0),  # would-be new value, must be ignored
        ("Morning", datetime(2026, 8, 13, 7, 0), datetime(2026, 8, 13, 11, 0), 4.0),
    ], overall=3.0)
    newly_frozen = apply_freeze(day2, now=later_now, path=path)

    assert newly_frozen == ["Morning"]
    assert day2.segments[0].score == 8.0  # Dawn: reapplied frozen value
    assert day2.segments[1].score == 4.0  # Morning: freshly frozen this call, unchanged
    # overall_score recomputed from the corrected segment list (8.0, 4.0), not
    # left at the stale 3.0 score_day() would have produced from (2.0, 4.0).
    assert day2.overall_score == 6.0


def test_freeze_prunes_rows_from_a_different_date(tmp_path):
    path = tmp_path / "freeze.csv"
    yesterday = date(2026, 8, 12)
    today = date(2026, 8, 13)

    day_y = _make_day(yesterday, [("Night", datetime(2026, 8, 12, 21, 0), datetime(2026, 8, 13, 5, 0), 5.0)])
    apply_freeze(day_y, now=datetime(2026, 8, 13, 6, 0), path=path)
    assert read_frozen_segments(yesterday, path) != {}

    day_t = _make_day(today, [("Dawn", datetime(2026, 8, 13, 5, 0), datetime(2026, 8, 13, 7, 0), 7.0)])
    apply_freeze(day_t, now=datetime(2026, 8, 13, 8, 0), path=path)

    # Freezing something for `today` prunes the stale `yesterday` row.
    assert read_frozen_segments(yesterday, path) == {}
    assert read_frozen_segments(today, path)["Dawn"]["score"] == 7.0


def test_notes_and_breakdown_round_trip_through_the_freeze_file(tmp_path):
    path = tmp_path / "freeze.csv"
    d = date(2026, 8, 13)
    now = datetime(2026, 8, 13, 10, 0)
    day = _make_day(d, [])
    day.segments = [SegmentForecast(
        name="Dawn", start=datetime(2026, 8, 13, 5, 0), end=datetime(2026, 8, 13, 7, 0),
        score=8.5, solunar_overlap="major", notes=["Overcast skies help."],
        breakdown=[("Base", 5.0, "Starting point")],
    )]

    apply_freeze(day, now=now, path=path)
    frozen = read_frozen_segments(d, path)["Dawn"]

    assert frozen["notes"] == ["Overcast skies help."]
    assert frozen["breakdown"] == [("Base", 5.0, "Starting point")]
    assert frozen["solunar_overlap"] == "major"
