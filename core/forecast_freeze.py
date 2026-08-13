"""
Freezes each day's segment scores once their time window has fully passed,
so the 7-Day Forecast page's live-updating scores (which intentionally
shift as the weather forecast/actuals for a day change - see
core.scoring.score_day()) stop changing for a segment once "right now" has
moved past that segment's end time. Without this, a segment like this
morning's "Dawn" window would keep silently reflecting whatever the latest
weather refresh says, hours after that window closed - which reads as the
past changing after the fact, not what a forecast score should do once
it's no longer a forecast.

Only today's date can ever have a mix of past and future segments - every
other day pages/1_7_Day_Forecast.py shows is entirely in the future, since
core.scoring.score_week() always starts at today (see that function) - so
this only ever needs to track one date's worth of frozen segments at a
time; rows for any other date are pruned on write.

A row is written the first time a segment is observed to have ended -
whatever score was computed at that exact moment becomes permanent, and
every later page load for that same (date, segment) reuses it instead of
recomputing. Same git-commit-back pattern as core/storage.py and its
siblings (core/lure_inventory.py, core/lake_spots.py) so a frozen score
survives Streamlit Cloud restarts/redeploys, not just the current server
process's lifetime - without that, a sleep/wake cycle (routine on
Streamlit Community Cloud) would silently lose every freeze and defeat the
whole point.
"""
from __future__ import annotations
import csv
import json
from datetime import date
from pathlib import Path
from typing import Optional

from .scoring import lake_now_naive

REPO_ROOT = Path(__file__).resolve().parent.parent
FREEZE_PATH = REPO_ROOT / "data" / "segment_score_freeze.csv"

FIELDNAMES = [
    "the_date", "segment_name", "score", "solunar_overlap", "notes_json", "breakdown_json", "frozen_at",
]


def ensure_file_exists(path: Path = FREEZE_PATH):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def _read_all_rows(path: Path = FREEZE_PATH) -> list:
    ensure_file_exists(path)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write_all_rows(rows: list, path: Path = FREEZE_PATH):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def read_frozen_segments(d: date, path: Path = FREEZE_PATH) -> dict:
    """{segment_name: {"score", "solunar_overlap", "notes", "breakdown"}}
    for every segment already frozen for this date. Empty if none yet."""
    target = d.isoformat()
    frozen = {}
    for row in _read_all_rows(path):
        if row.get("the_date") != target:
            continue
        try:
            score = float(row["score"])
        except (TypeError, ValueError):
            continue
        try:
            notes = json.loads(row.get("notes_json") or "[]")
        except json.JSONDecodeError:
            notes = []
        try:
            breakdown = [tuple(item) for item in json.loads(row.get("breakdown_json") or "[]")]
        except json.JSONDecodeError:
            breakdown = []
        frozen[row["segment_name"]] = {
            "score": score,
            "solunar_overlap": row.get("solunar_overlap") or None,
            "notes": notes,
            "breakdown": breakdown,
        }
    return frozen


def apply_freeze(day_forecast, now=None, path: Path = FREEZE_PATH) -> list:
    """Mutates day_forecast.segments IN PLACE: any segment whose window has
    fully ended (end <= now) gets either (a) its already-frozen values
    reapplied, overriding whatever score_day() just (re)computed for it, or
    (b) - if this is the first time it's been seen past - a new permanent
    row written capturing its CURRENT score/notes/solunar_overlap/
    breakdown, which becomes that segment's frozen value from now on.
    Segments still in progress or upcoming (end > now) are left completely
    untouched, so the "scores update live as the forecast changes" behavior
    the angler wants for anything not yet past keeps working exactly as
    before.

    Prunes any rows for a date other than day_forecast.the_date on write,
    since only one date is ever relevant (see module docstring) - keeps
    this file from growing without bound.

    Returns the list of segment names newly frozen this call (empty most
    of the time - freezing only happens right as a window closes), so the
    caller knows whether a git commit is worth making; no write happens at
    all if this list would be empty.
    """
    now = now or lake_now_naive()
    d = day_forecast.the_date
    already_frozen = read_frozen_segments(d, path)
    newly_frozen_names = []
    new_rows_for_today = []
    any_segment_changed = False

    for seg in day_forecast.segments:
        if seg.end > now:
            continue  # still current or upcoming - stays live, untouched
        frozen = already_frozen.get(seg.name)
        if frozen is not None:
            # Already-passed segment we've seen before - reapply its
            # locked-in values instead of whatever score_day() just
            # recomputed from the latest weather refresh.
            if seg.score != frozen["score"]:
                any_segment_changed = True
            seg.score = frozen["score"]
            seg.solunar_overlap = frozen["solunar_overlap"]
            seg.notes = frozen["notes"]
            seg.breakdown = frozen["breakdown"]
        else:
            # First time this segment has been observed as past - lock in
            # whatever score_day() just computed for it, right now. Its
            # score isn't changing on THIS run (nothing to override it
            # with yet), so no need to flag any_segment_changed here.
            new_rows_for_today.append({
                "the_date": d.isoformat(),
                "segment_name": seg.name,
                "score": seg.score,
                "solunar_overlap": seg.solunar_overlap or "",
                "notes_json": json.dumps(seg.notes),
                "breakdown_json": json.dumps(seg.breakdown),
                "frozen_at": now.isoformat(),
            })
            newly_frozen_names.append(seg.name)

    if any_segment_changed:
        # A past segment's score just got overridden back to its frozen
        # value, which score_day()'s freshly computed overall_score (the
        # plain average of all segment scores, before this override ran)
        # no longer reflects - recompute it the same way score_day() does,
        # from the now-correct (mix of frozen-past + live-future) segment
        # scores, so the day-level number a reader sees stays consistent
        # with the segment cards underneath it.
        avg = sum(s.score for s in day_forecast.segments) / len(day_forecast.segments)
        day_forecast.overall_score = round(max(1.0, min(10.0, avg)), 1)

    if new_rows_for_today:
        # Keep only today's rows (existing + new) - anything for another
        # date is stale by definition (see module docstring) and dropped.
        existing_today_rows = [r for r in _read_all_rows(path) if r.get("the_date") == d.isoformat()]
        _write_all_rows(existing_today_rows + new_rows_for_today, path)

    return newly_frozen_names
