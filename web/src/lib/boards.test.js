// Custom boards (new app only — no Python original): spec cleaning + the numbers on small hand-made trip logs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { blackBass, choicesFrom, cleanSpec, describeSpec, runBoard } from "./boards.js";

const T = (id, date, angler, cat, fish, extra = {}) => ({ trip_id: id, session_id: extra.sid || id, trip_date: date, lure_used: extra.lure || "", color_used: extra.color || "",
  spot_name: extra.spot || "Dam Point", segment: extra.seg || "Morning", fish_caught: String(fish.reduce((a, f) => a + (f.count || 1), 0)), owner: `${angler}@x`,
  conditions: { angler, lure_category: cat, fish, lure_start_time: "07:00:00", lure_end_time: extra.end || "09:00:00", water_temp_f: extra.temp ?? 55 } });
const LM = (w, len = null) => ({ species: "Largemouth", weight_lb: w, length_in: len }), SP = (w) => ({ species: "Spotted", weight_lb: w }), WB = (w) => ({ species: "White Bass", weight_lb: w });
const rows = [
  T("a", "2026-11-01", "John", "suspending_jerkbait", [LM(3.5, 18), LM(2), SP(1.5)], { lure: "Rapala Shadow Rap" }),
  T("b", "2026-11-02", "Matthew", "suspending_jerkbait", [LM(4.25, 19.5), WB(1)], { lure: "Megabass Vision 110" }),
  T("c", "2026-11-02", "Matthew", "chatterbait", [LM(2.5), LM(2.5)], { lure: "Z-Man ChatterBait", end: "08:00:00" }),
  T("d", "2026-11-03", "John", "suspending_jerkbait", [], { lure: "Rapala Shadow Rap", temp: 48 }),
  T("e", "2026-10-03", "Alex", "drop_shot", [{ species: "Largemouth", weight_lb: null, count: 3 }], { seg: "Dusk" }),
];
const ch = choicesFrom(rows);

test("boards: the user's example — most lbs of bass on a jerkbait, by angler", () => {
  const spec = cleanSpec({ measure: "lbs", by: "angler", species: blackBass(ch.species), lure_types: ["suspending_jerkbait"] }, ch);
  assert.deepEqual(spec.species, ["Largemouth", "Spotted"]);  // white bass isn't a black bass
  const { rows: r } = runBoard(rows, spec);
  assert.deepEqual(r.map((x) => [x.primary, x.num]), [["John", "7 lb"], ["Matthew", "4 lb 4 oz"]]);
  assert.match(describeSpec(spec), /^Total weight by angler · Largemouth, Spotted · Suspending Jerkbait/);
});
test("boards: fish per hour counts fishless hours; filters", () => {
  const { rows: r } = runBoard(rows, cleanSpec({ measure: "fish_per_hour", by: "angler" }, ch));
  // John: 3 fish in 4 h (trip d caught nothing); Matthew: 4 in 3 h; Alex 3 in 2 h
  assert.deepEqual(r.map((x) => [x.primary, x.num]), [["Alex", "1.50 / hr"], ["Matthew", "1.33 / hr"], ["John", "0.75 / hr"]]);
  const warm = runBoard(rows, cleanSpec({ measure: "fish", by: "none", temp_min: 50 }, ch)).rows;
  assert.equal(warm[0].num, "10 fish");  // trip d (48 °F) has no fish anyway
  assert.deepEqual(runBoard(rows, cleanSpec({ measure: "outings", by: "angler", temp_max: 50 }, ch)).rows.map((x) => [x.primary, x.num]), [["John", "1 outing"]]);
  const dusk = runBoard(rows, cleanSpec({ measure: "fish", by: "lure_type", segments: ["Dusk"] }, ch)).rows;
  assert.deepEqual(dusk.map((x) => x.primary), ["Drop Shot"]);
});
test("boards: biggest by each fish, longest, avg weight sample tag, by month", () => {
  const big = runBoard(rows, cleanSpec({ measure: "biggest", by: "fish" }, ch)).rows;
  assert.deepEqual(big.slice(0, 2).map((x) => x.num), ["4 lb 4 oz", "3 lb 8 oz"]);
  assert.equal(runBoard(rows, cleanSpec({ measure: "longest", by: "none" }, ch)).rows[0].num, "19.5 in");
  const avg = runBoard(rows, cleanSpec({ measure: "avg_weight", by: "lure" }, ch)).rows;
  assert.equal(avg.find((x) => x.primary === "Megabass Vision 110").tag, "small sample");
  const mo = runBoard(rows, cleanSpec({ measure: "fish", by: "month" }, ch)).rows;
  assert.deepEqual(mo.map((x) => [x.primary, x.num]), [["Nov", "7 fish"], ["Oct", "3 fish"]]);
});
test("boards: cleanSpec throws out unknown values", () => {
  const s = cleanSpec({ measure: "nope", by: "fish", species: ["Unicorn", "Spotted"], lure_types: ["x"], months: [0, 11, 13], temp_min: 5, from: "last week" }, ch);
  assert.equal(s.measure, "fish"); assert.equal(s.by, "none"); assert.deepEqual(s.species, ["Spotted"]); assert.deepEqual(s.lure_types, []);
  assert.deepEqual(s.months, [11]); assert.equal(s.temp_min, 30); assert.equal(s.from, "");
});
