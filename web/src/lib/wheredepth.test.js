import test from "node:test";
import assert from "node:assert/strict";
import { lakeContext, guessPhase, todayLake } from "./lakectx.js";
import { conditionedOutings, rowFilter, whereToFish } from "./wheretofish.js";
import { expectedDepth, fishDepth, relabelDepth, withLogDepth } from "./fishdepth.js";
import { spotStats } from "./spotstats.js";

const row = (o) => ({ trip_date: o.d, owner: o.who || "a@x", session_id: o.s, spot_id: o.sp || "A", fish_caught: String(o.f || 0), segment: "Dawn",
  conditions: { lure_start_time: "06:00:00", lure_end_time: o.b || "08:00:00", fish_depth_ft: o.fd ?? null, water_temp_f: o.t ?? null, fish: [], ...(o.c || {}) } });
const spots = [{ spot_id: "A", name: "Alpha", location_type: "Main-lake point", lat: 37.2792, lon: -86.2469 }, { spot_id: "B", name: "Bravo", location_type: "Creek channel / ledge", lat: 37.2792, lon: -86.2469 }];
const ctx = lakeContext([]);

test("lake context: Corps phase, calendar guess, temps", () => {
  assert.equal(ctx.on("2026-08-21").phase, "stratified"); assert.equal(ctx.on("2026-08-21").floor_ft, 12.6);
  assert.equal(ctx.on("2026-10-28").phase, "turnover");
  assert.equal(guessPhase("2027-07-04"), "stratified"); assert.equal(guessPhase("2027-10-20"), "turnover"); assert.equal(guessPhase("2027-01-15"), "mixed");
  assert.equal(ctx.on("2027-07-04").measured, false);
  assert.equal(ctx.rowTemp(row({ d: "2026-08-21", t: 84 })), 84);
  assert.equal(ctx.rowTemp(row({ d: "2026-08-21", t: 84, c: { water_temp_unreliable: true } })), 86.5); // Corps surface 30.3 °C
  assert.deepEqual(todayLake(ctx, "2027-07-04", 81), { phase: "stratified", temp: 81, measured: false });
});

test("where to fish: ranks spots in a condition, shrinks thin data, flags hardly-tried kinds", () => {
  const trips = [row({ d: "2026-08-21", s: "1", f: 6, t: 85 }), row({ d: "2026-08-22", s: "2", f: 4, t: 84 }), row({ d: "2026-08-23", s: "3", sp: "B", f: 1, t: 85 }),
    row({ d: "2026-10-28", s: "4", sp: "B", f: 3, t: 68 })];
  const all = whereToFish(trips, spots, ctx, { cond: { phase: "stratified" } });
  assert.equal(all.n, 3); assert.equal(all.spots[0].name, "Alpha"); assert.equal(all.spots[0].raw, 10 / 4);
  assert.ok(all.spots[1].rate > all.spots[1].raw); // pulled up toward the average
  assert.deepEqual(all.untried, ["Main-lake point", "Creek channel / ledge"]); // both < 3 outings
  const turn = whereToFish(trips, spots, ctx, { cond: { phase: "turnover" } }); assert.equal(turn.spots[0].name, "Bravo");
  const like = whereToFish(trips, spots, ctx, { cond: { like: { phase: "stratified", temp: 70 } } }); assert.equal(like.n, 0); // 84–85 °F is > 6 °F away
  const pred = rowFilter(trips, ctx, { like: { phase: "stratified", temp: 84 } });
  const st = spotStats(trips, { season: "like", pred }, "2026-12-01");
  assert.deepEqual(Object.keys(st.spots).sort(), ["A", "B"]); assert.equal(st.spots.B.fish, 1);
});

test("fish depth: bands, months, default 8 ft skipped, expected depth capped by the floor, relabel", () => {
  const trips = [];
  for (let i = 0; i < 6; i++) trips.push(row({ d: `2026-08-${10 + i}`, s: `g${i}`, f: 6, fd: 10, t: 85 }));
  for (let i = 0; i < 3; i++) trips.push(row({ d: `2026-08-${20 + i}`, s: `b${i}`, f: 0, fd: 16, t: 85 }));
  trips.push(row({ d: "2026-08-25", s: "x", f: 2, fd: 8, t: 85, c: { field_sources: { fish_depth_ft: "default" } } }));
  const o = conditionedOutings(trips, ctx, {}, spots); assert.equal(o.find((x) => x.key === "a@x|x").fish_depth, null);
  const r = fishDepth(trips, ctx, { spots });
  assert.equal(r.marked, 9); assert.equal(r.byBand.find((b) => b.label === "10–12 ft").rate, 3);
  assert.equal(r.byMonth[0].label, "Aug"); assert.equal(r.byMonth[0].best.label, "10–12 ft");
  const e = expectedDepth(trips, ctx, { date: "2027-08-15", tempF: 85 });
  assert.equal(e.depth_ft, 10); assert.equal(e.capped, false);
  assert.equal(expectedDepth(trips, ctx, { date: "2027-08-15", tempF: 85, floorFt: 9 }).depth_ft, 8);
  assert.equal(expectedDepth(trips, ctx, { date: "2027-02-15", tempF: 45 }), null);
  const rec = { rationale: ["You're marking fish around 10 ft - bass"], first_choice: [{ depth: "target ~8-9 ft (1-2 ft above the 10 ft you're marking - bass" }], second_choice: [] };
  const w = withLogDepth(rec, e);
  assert.match(w.rationale[0], /^Your log: fish marked around 10 ft/); assert.equal(w.rationale[1], "Your log puts fish around 10 ft - bass");
  assert.match(w.first_choice[0].depth, /the 10 ft your log expects/);
  assert.equal(relabelDepth(null), null);
});
