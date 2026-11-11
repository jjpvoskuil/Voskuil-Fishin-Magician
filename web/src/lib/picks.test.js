import test from "node:test";
import assert from "node:assert/strict";
import { buildPicks, lureStats, similarity } from "./picks.js";
import { recommend } from "./lures.js";

const today = "2026-11-10";
let n = 0;
const row = (date, cat, fish, hours, extra = {}) => {
  const end = `${String(7 + Math.floor(hours)).padStart(2, "0")}:${String(Math.round((hours % 1) * 60)).padStart(2, "0")}:00`;
  return { trip_id: `t${n++}`, session_id: `s${n}`, trip_date: date, segment: "Morning", spot_id: "p1", spot_name: "Point", structure_type: "Main-lake point",
    water_clarity: "Green stained", fish_caught: String(fish), owner: "me@x", lure_used: cat,
    conditions: { lure_category: cat, lure_start_time: "07:00:00", lure_end_time: end, water_temp_f: 56, source: "spot_session", ...extra } };
};
const ctx = { water_temp_f: 55, water_clarity: "Green stained", segment_name: "Morning", structure_type: "Main-lake point", me: "me@x" };
const inv = ["chatterbait", "drop_shot", "football_jig", "suspending_jerkbait", "medium_diving_crankbait", "soft_swimbait", "swim_jig", "lipless_crankbait", "blade_bait"]
  .map((c, i) => ({ item_id: `i${i}`, brand: "B", description: `${c} Green Pumpkin`, category: c, quantity: "1" }));

test("similar days count more than distant ones", () => {
  const near = row("2026-11-03", "chatterbait", 1, 1), far = row("2026-07-03", "chatterbait", 1, 1, { water_temp_f: 86 });
  assert.ok(similarity(near, near.conditions, ctx, today) > 3 * similarity(far, far.conditions, ctx, today));
});

test("proven, steady and cold are earned from history; small samples shrink", () => {
  const trips = [];
  for (let i = 0; i < 8; i++) trips.push(row(`2026-11-0${(i % 9) + 1}`, "chatterbait", 4, 1));          // fast
  for (let i = 0; i < 10; i++) trips.push(row(`2026-10-${20 + i}`, "drop_shot", 1, 1.5));              // slow but always
  for (let i = 0; i < 6; i++) trips.push(row(`2026-10-${15 + i}`, "swim_jig", 0, 1));                  // dud
  trips.push(row("2026-11-09", "blade_bait", 3, 0.5));                                                   // one lucky stint
  const rec = recommend({ season: "late_fall", water_temp_f: 55, segment_name: "Morning", pressure_trend_24h: 0, structure_type: "Main-lake point", water_clarity: "Green stained", inventory: inv, trip_history: trips });
  const out = buildPicks(rec, { trips, inventory: inv, ctx, today });
  const tier = Object.fromEntries(out.picks.map((p) => [p.key, p.tier]));
  assert.equal(out.picks[0].key, "chatterbait"); assert.equal(tier.chatterbait, "proven");
  assert.equal(tier.drop_shot, "steady");
  assert.ok(!("swim_jig" in tier)); assert.ok(out.cold.some((c) => c.key === "swim_jig"));
  assert.notEqual(tier.blade_bait, "proven"); // 3 fish in 30 min isn't proof
  const { stats } = lureStats(trips, ctx, today);
  assert.ok(stats.blade_bait.rate < stats.chatterbait.rate);
  for (const p of out.picks) assert.ok(p.reasons.length >= 1);
});

test("no history → the seasonal pattern", () => {
  const rec = recommend({ season: "late_fall", water_temp_f: 55, segment_name: "Morning", pressure_trend_24h: 0, structure_type: "Main-lake point", water_clarity: "Green stained", inventory: inv, trip_history: [] });
  const out = buildPicks(rec, { trips: [], inventory: inv, ctx, today });
  assert.ok(out.picks.length >= 2);
  assert.ok(out.picks.every((p) => p.tier === "seasonal" || p.tier === "try"));
});
