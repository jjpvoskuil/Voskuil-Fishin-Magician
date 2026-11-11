// Freeze each time-of-day score once its window has ended, so later forecasts can't rewrite what the day "was".
// Port of core/forecast_freeze.apply_freeze (parity: engine.test.js). Frozen rows live in fm_score_freeze.
import { aggregateDayOverall } from "./scoring.js";
import { isoNaive } from "./py.js";
import { lakeNowNaive } from "./weather.js";

/** Applies existing freezes to `day` (in place) and returns the rows to save for windows that just ended.
 *  frozen: rows for day.the_date [{segment_name, score, solunar_overlap, notes, breakdown}] */
export function applyFreeze(day, frozen, now = lakeNowNaive()) {
  const byName = new Map((frozen || []).filter((r) => r.the_date == null || r.the_date === day.the_date).map((r) => [r.segment_name, r]));
  const newRows = []; let changed = false;
  for (const seg of day.segments) {
    if (seg.end > now) continue;
    const f = byName.get(seg.name);
    if (f && typeof f.score === "number" && Number.isFinite(f.score)) {
      if (seg.score !== f.score) changed = true;
      seg.score = f.score; seg.solunar_overlap = f.solunar_overlap || null; seg.notes = f.notes || []; seg.breakdown = (f.breakdown || []).map((x) => [...x]);
    } else {
      newRows.push({ the_date: day.the_date, segment_name: seg.name, score: seg.score, solunar_overlap: seg.solunar_overlap || "", notes: seg.notes, breakdown: seg.breakdown, frozen_at: isoNaive(now) });
    }
  }
  if (changed) [day.overall_score, day.overall_breakdown] = aggregateDayOverall(day.segments);
  return newRows;
}
