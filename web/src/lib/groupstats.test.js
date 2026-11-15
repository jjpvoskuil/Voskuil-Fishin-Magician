import { test } from "node:test";
import assert from "node:assert/strict";
import { breakdown, records, statTiles, summarize } from "./groupstats.js";
import { cleanSpec, runBoard } from "./boards.js";

const T = (id, sid, date, lure, color, fish, extra = {}) => ({ trip_id: id, session_id: sid, trip_date: date, lure_used: lure, color_used: color,
  spot_name: extra.spot || "Dam Point", segment: extra.seg || "Morning", structure_type: extra.st || "Point", owner: extra.owner || "j@x",
  fish_caught: String(fish.reduce((a, f) => a + (f.count || 1), 0)),
  conditions: { angler: extra.angler || "John", lure_category: extra.cat || "suspending_jerkbait", fish, lure_start_time: "07:00:00", lure_end_time: extra.end ?? "09:00:00", water_temp_f: extra.temp ?? 55 } });
const LM = (w, len = null) => ({ species: "Largemouth", weight_lb: w, length_in: len });
const rows = [
  T("a", "s1", "2026-11-01", "Shadow Rap", "Ghost", [LM(3), LM(2, 17)]),
  T("b", "s1", "2026-11-01", "Shadow Rap", "Ghost", [LM(1)], { spot: "Ben's Point", end: "07:10:00" }),   // second leg, same outing; 10 min → 0.5 h
  T("c", "s2", "2026-11-03", "Shadow Rap", "Ghost", []),
  T("d", "s3", "2026-11-04", "Shadow Rap", "Ghost", [{ species: "Largemouth", weight_lb: null, count: 2 }], { temp: 49, seg: "Dusk" }),
  T("e", "s3", "2026-11-04", "ChatterBait", "White", [LM(4)], { cat: "chatterbait", st: "Flat" }),
];

test("summarize: weight, per fish, per hour, uses = outings, success rate", () => {
  const s = summarize(records(rows).filter((x) => x.lure === "Shadow Rap"));
  assert.equal(s.fish, 5); assert.equal(s.lbs, 6); assert.equal(s.weighed, 3); assert.equal(s.lbsPerFish, 2);
  assert.equal(s.hours, 6.5); assert.equal(s.uses, 3); assert.equal(s.usesWithFish, 2);
  assert.equal(s.fishPerUse.toFixed(2), "1.67"); assert.equal(Math.round(s.successRate * 100), 67);
  assert.equal(s.biggest.w, 3); assert.equal(s.longest.len, 17); assert.deepEqual([s.first, s.last], ["2026-11-01", "2026-11-04"]);
  const tiles = Object.fromEntries(statTiles(s).map(([k, v, n]) => [k, [v, n]]));
  assert.deepEqual(tiles["Success rate"], ["67%", "2 of 3 with fish"]);
  assert.deepEqual(tiles["Total weight"], ["6 lb", "3 of 5 weighed"]);
});
test("breakdown: most fish first; months/temps in order; unreliable temps skipped", () => {
  const recs = records(rows);
  assert.deepEqual(breakdown(recs, "lure").map((g) => [g.label, g.stats.fish]), [["Shadow Rap", 5], ["ChatterBait", 1]]);
  assert.deepEqual(breakdown(recs, "structure").map((g) => g.label), ["Point", "Flat"]);
  assert.deepEqual(breakdown(recs, "temp").map((g) => g.label), ["45–49 °F", "55–59 °F"]);
  assert.deepEqual(breakdown(recs, "spot").map((g) => [g.label, g.stats.uses]), [["Dam Point", 3], ["Ben's Point", 1]]);
  assert.deepEqual(breakdown([], "lure"), []); assert.deepEqual(breakdown(recs, "nope"), []);
});
test("custom boards carry the same stats per row (filters applied)", () => {
  const r = runBoard(rows, cleanSpec({ measure: "fish", by: "lure" }, {})).rows;
  assert.equal(r[0].primary, "Shadow Rap");
  const s = r[0].stats;
  assert.deepEqual([s.fish, s.uses, s.usesWithFish, s.hours, s.lbs], [5, 3, 2, 6.5, 6]);
  const warm = runBoard(rows, cleanSpec({ measure: "fish", by: "lure", temp_min: 50 }, {})).rows[0].stats;
  assert.deepEqual([warm.fish, warm.uses], [3, 2]);   // the 49 °F outing is filtered out
});
