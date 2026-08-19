"""
Personal catch-history signal for core.lures.recommend() - punch-list #37.

Prompted directly by the angler: "the recommendation is based on the data
in the app plus known information about the lake and real bass fishing
experience on the lake ... lets influence the lure choice by my actual
experience ... take into account where the lure was used in the past, that
success, and where it is planned to be used." This module is the "my actual
experience" half of that ask (core.lures.py's rewritten season/structure
rules, sourced from real Nolin Lake fishing reports, are the other half -
see the source citations in recommend()'s season branches there).

Deliberately conservative, matching this app's existing core.calibration.py
precedent for the score-weight nudging: requires a minimum number of
REASONABLY SIMILAR past trips (not just any trip that ever used a given
lure category anywhere, anytime) before that lure category gets any boost
at all, and even then this only ever ADDS a signal on top of the
season/structure/pressure rules that already decide the base
recommendation - it never removes or overrides them.

"Similar" is a weighted match against the CURRENT situation (structure
type, water clarity, low-light segment, water temp, and - the strongest
signal - the exact same spot, when known) rather than a flat "have you
ever caught anything on this lure" average across the whole lake. This is
what lets a lure you don't currently own but have genuinely caught fish on
before, in a similar spot/situation, surface as a personally-proven
suggestion - independent of tackle-box ownership, which is exactly the
"particularly if it is a lure I don't have in my tackle box" case the
angler called out.

No dependency on core.lures (kept deliberately one-directional - core.lures
imports this module, not the other way around) so this stays a small,
easily-testable, storage-format-only module.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Optional

# Mirrors core.lures.LIGHT_LOW - duplicated rather than imported to avoid a
# circular import (core.lures imports this module). This is Streamlit's own
# fixed segment-name vocabulary (Dawn/Morning/Midday/Afternoon/Dusk/Night),
# extremely unlikely to change independently of core.lures' own copy.
_LIGHT_LOW_SEGMENTS = {"Dawn", "Dusk", "Night"}

# A trip only ever counts toward a lure's track record if it shares LOCATION
# with the current situation - the same spot, or (when no specific spot is
# known, e.g. the 7-Day Forecast page) at least the same structure type. This
# is a hard requirement, not just one contributor to a blended score: the
# angler was explicit about this - "take into account where the lure was
# used in the past ... and where it is planned to be used" - so a trip that
# only happens to share a water-clarity reading or a similar water temp,
# with zero location signal, should never count on its own no matter how
# many secondary factors happen to line up.

# How many situation-matching trips a lure category needs before its track
# record counts for anything - the angler asked for this to be "cautious"
# given how small the trip log still is; one lucky fish shouldn't promote a
# lure on its own. Mirrors core.calibration.py's own "wait for a minimum
# sample before touching anything" philosophy (that module uses 4 per side
# for a binary on/off comparison; this one uses a smaller floor since it's
# gating a single count, not comparing two groups).
MIN_SIMILAR_TRIPS = 2

# Point weights for each dimension a past trip can match the current
# situation on. Weighted toward "where" (exact spot, then structure type)
# since that's the strongest repeatable signal - bass relate to structure
# far more consistently than to a specific cloud-cover reading from one
# afternoon - matching the angler's own framing: "where the lure was used
# in the past ... and where it is planned to be used."
SAME_SPOT_POINTS = 3
SAME_STRUCTURE_POINTS = 2
SAME_WATER_CLARITY_POINTS = 1
SAME_LIGHT_LEVEL_POINTS = 1
CLOSE_WATER_TEMP_POINTS = 1
CLOSE_WATER_TEMP_BAND_F = 10.0


@dataclass
class LureTrackRecord:
    lure_category: str
    similar_trips: int
    trips_with_fish: int
    total_fish: int
    biggest_fish_lb: Optional[float]

    @property
    def catch_rate(self) -> float:
        return self.trips_with_fish / self.similar_trips if self.similar_trips else 0.0


def _situation_match_score(row: dict, row_conditions: dict, situation: dict) -> tuple:
    """Returns (score, location_matched). `location_matched` is True only if
    this trip shares a spot or structure type with `situation` - the hard
    gate lure_track_records() below requires. `score` adds a few secondary
    points for water clarity/light-level/water-temp similarity on top of
    that - not currently used to gate anything (a location match alone is
    enough to count), just carried through in case a future caller wants to
    rank matches by how close a fit they are, not just count them.
    `situation` keys (all optional - a missing one just can't contribute):
    spot_id, structure_type, water_clarity, low_light (bool), water_temp_f."""
    score = 0
    location_matched = False
    if situation.get("spot_id") and row.get("spot_id") == situation["spot_id"]:
        score += SAME_SPOT_POINTS
        location_matched = True
    if situation.get("structure_type") and row.get("structure_type") == situation["structure_type"]:
        score += SAME_STRUCTURE_POINTS
        location_matched = True
    if situation.get("water_clarity") and row.get("water_clarity") == situation["water_clarity"]:
        score += SAME_WATER_CLARITY_POINTS
    if situation.get("low_light") is not None:
        row_segment = row.get("segment")
        if row_segment:
            row_low_light = row_segment in _LIGHT_LOW_SEGMENTS
            if row_low_light == situation["low_light"]:
                score += SAME_LIGHT_LEVEL_POINTS
    if situation.get("water_temp_f") is not None:
        row_temp = row_conditions.get("water_temp_f")
        if isinstance(row_temp, (int, float)):
            if abs(row_temp - situation["water_temp_f"]) <= CLOSE_WATER_TEMP_BAND_F:
                score += CLOSE_WATER_TEMP_POINTS
    return score, location_matched


def lure_track_records(
    trip_rows: list, situation: dict, min_similar_trips: int = MIN_SIMILAR_TRIPS,
) -> dict:
    """{lure_category: LureTrackRecord} for every lure category with at
    least `min_similar_trips` past trips that share LOCATION (same spot, or
    same structure type when no spot is known) with `situation` - see
    _situation_match_score's docstring for why this is a hard requirement,
    not just one contributor among several. Rows with unparseable/missing
    conditions_json, no lure_category tag, or with no location match at all
    don't count - this is deliberately a small, high-confidence subset of
    the trip log, not a lake-wide average.

    `trip_rows` is the raw list of dicts core.storage.read_all_trips()
    returns (or any equivalent list of dicts with the same field names -
    this module never touches the filesystem itself)."""
    by_category: dict = {}
    for row in trip_rows or []:
        try:
            conditions = json.loads(row.get("conditions_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        lure_category = conditions.get("lure_category")
        if not lure_category:
            continue
        _score, location_matched = _situation_match_score(row, conditions, situation)
        if not location_matched:
            continue

        rec = by_category.setdefault(lure_category, {
            "similar_trips": 0, "trips_with_fish": 0, "total_fish": 0, "biggest": None,
        })
        rec["similar_trips"] += 1
        try:
            fish_caught = int(row.get("fish_caught") or 0)
        except (TypeError, ValueError):
            fish_caught = 0
        if fish_caught > 0:
            rec["trips_with_fish"] += 1
            rec["total_fish"] += fish_caught
        try:
            big = row.get("biggest_fish_lb")
            big = float(big) if big not in (None, "") else None
        except (TypeError, ValueError):
            big = None
        if big is not None and (rec["biggest"] is None or big > rec["biggest"]):
            rec["biggest"] = big

    result = {}
    for lure_category, rec in by_category.items():
        if rec["similar_trips"] < min_similar_trips:
            continue
        result[lure_category] = LureTrackRecord(
            lure_category=lure_category,
            similar_trips=rec["similar_trips"],
            trips_with_fish=rec["trips_with_fish"],
            total_fish=rec["total_fish"],
            biggest_fish_lb=rec["biggest"],
        )
    return result


def track_record_note(record: LureTrackRecord, in_plan_already: bool) -> str:
    """Plain-language rationale sentence for one lure's LureBlock.note field -
    see core.ui.render_lure_block, which now renders this. Deliberately
    states the raw numbers (not just a vague "proven pick") so the angler can
    judge the strength of the signal themselves, same "show your work"
    principle as the rest of this app's score breakdowns."""
    big_bit = f", best {record.biggest_fish_lb:.1f} lb" if record.biggest_fish_lb else ""
    catch_bit = f"{record.trips_with_fish} of {record.similar_trips} similar trips landed fish{big_bit}"
    if in_plan_already:
        return f"📈 Your own history: {catch_bit} - a real, situation-matched track record for you on this lure."
    return (
        f"📈 Your own history: {catch_bit} on this lure in similar spots/conditions before - not currently "
        f"a top seasonal pick, but a personally-proven option worth considering even if it's not in your "
        f"tackle box yet."
    )
