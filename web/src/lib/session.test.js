// Spot Session rules (lib/session.js): fish counting, ending, grouping open sessions, condition sources, GPS pick.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as S from "./session.js";
import { parseIso } from "./py.js";

const me = { email: "john@x.com", name: "John" };
const row = (id, extra = {}, cond = {}) => ({ trip_id: id, trip_date: "2026-11-10", logged_at: `2026-11-10T13:0${id.length}:00`, session_id: "s1", owner: me.email,
  lure_used: `Lure ${id}`, fish_caught: 0, biggest_fish_lb: null, ...extra, conditions: { source: "spot_session", angler: "John", lure_start_time: "07:00:00", lure_end_time: null, fish: [], ...cond } });

test("fish recount: count, biggest, removal", () => {
  let r = row("a");
  r = S.withFish(r, [{ species: "Largemouth Bass", count: 1, weight_lb: 2.5 }, { species: "Spotted", count: 2, weight_lb: null }]);
  assert.equal(r.fish_caught, 3); assert.equal(r.biggest_fish_lb, 2.5);
  r = S.withFish(r, []); assert.equal(r.fish_caught, 0); assert.equal(r.biggest_fish_lb, null);
});

test("weights/lengths from the dropdowns (old activity_log helpers)", () => {
  assert.equal(S.weightLbForDropdown(2, 8), 2.5); assert.equal(S.weightLbForDropdown("10+", 4), 10.5); assert.equal(S.weightLbForDropdown(0, 3), 0.1875);
  assert.equal(S.lengthInForDropdown("<12"), 11.0); assert.equal(S.lengthInForDropdown("26+"), 27.0); assert.equal(S.lengthInForDropdown(15), 15);
});

test("open sessions, mine vs others, ending", () => {
  const other = { ...row("x", { owner: "matt@x.com", session_id: "s2" }), conditions: { ...row("x").conditions, angler: "Matthew" } };
  const trips = [row("a"), row("bb", {}, { lure_end_time: "08:00:00" }), other];
  const open = S.openSessions(trips);
  assert.equal(open.length, 2);
  assert.equal(S.myOpenSession(trips, me).rows.length, 2);
  const ended = S.endRows(S.myOpenSession(trips, me).rows, parseIso("2026-11-10T10:15:00"));
  assert.ok(ended.every((r) => r.conditions.session_end_time === "10:15:00"));
  assert.equal(ended[1].conditions.lure_end_time, "08:00:00"); // already-retired lure keeps its own end
  assert.equal(S.openSessions([...ended, other]).length, 1);
});

test("condition layers keep where each value came from", () => {
  const m = S.mergeConditions({ values: { wind_band: "Glassy", water_temp_f: 57.2 }, sources: { wind_band: "forecast", water_temp_f: "estimate" } },
    { values: { water_temp_f: 55 }, sources: { water_temp_f: "you" } });
  assert.equal(m.values.water_temp_f, 55); assert.equal(m.sources.water_temp_f, "you");
  assert.equal(m.sources.wind_band, "forecast"); assert.equal(m.sources.secchi_ft, "default");
  // only values a person entered are shared with the next angler today
  const shared = S.sharedWaterConditions([{ trip_date: "2026-11-10", logged_at: "x", conditions: { source: "spot_session", angler: "Matt", water_temp_f: 54, secchi_ft: 3, field_sources: { water_temp_f: "you", secchi_ft: "default" } } }], "2026-11-10");
  assert.deepEqual(shared.values, { water_temp_f: 54 }); assert.equal(shared.sources.water_temp_f, "shared:Matt");
});

test("segment guess without a forecast uses the old fixed hours", () => {
  assert.equal(S.guessSegment(parseIso("2026-11-10T06:30"), null), "Dawn");
  assert.equal(S.guessSegment(parseIso("2026-11-10T12:00"), null), "Midday");
  assert.equal(S.guessSegment(parseIso("2026-11-10T21:00"), null), "Night");
  const ranges = { Dawn: [parseIso("2026-11-10T05:40"), parseIso("2026-11-10T07:40")] };
  assert.equal(S.guessSegment(parseIso("2026-11-10T05:00"), ranges), "Night");
  assert.equal(S.guessSegment(parseIso("2026-11-10T06:00"), ranges), "Dawn");
});

test("nearest saved spot by GPS", () => {
  const spots = [{ spot_id: "a", name: "A", lat: 37.328, lon: -86.140 }, { spot_id: "b", name: "B", lat: 37.300, lon: -86.170 }];
  assert.equal(S.nearestSpot(spots, 37.3285, -86.1405).spot.spot_id, "a");
  assert.equal(S.nearestSpot(spots, 37.35, -86.10), null);
});

test("fishing together: members, newest conditions, follow without loops", async () => {
  const S = await import("./session.js");
  const mk = (id, sid, owner, angler, extra = {}) => ({ trip_id: id, session_id: sid, trip_date: "2026-11-10", logged_at: "2026-11-10T07:00:00", spot_id: "p1", spot_name: "Point",
    owner, conditions: { ...S.CONDITION_FIELDS, source: "spot_session", angler, lure_start_time: "07:00:00", lure_end_time: null, start_time: "07:00:00", fish: [], ...extra } });
  const matt = mk("m1", "sM", "m@x", "Matthew", { conditions_set_at: "2026-11-10T07:00:00", water_temp_f: 58 });
  const john = mk("j1", "sJ", "j@x", "John", { group_id: "sM", conditions_set_at: "2026-11-10T07:00:00", water_temp_f: 58 });
  const alex = mk("a1", "sA", "a@x", "Alex");
  const trips = [matt, john, alex];
  assert.deepEqual(S.groupMembers(trips, "sJ", "sM").map((s) => s.key), ["sM"]);
  assert.deepEqual(S.groupMembers(trips, "sM", "sM").map((s) => s.key), ["sJ"]); // the anchor sees who joined
  assert.equal(S.groupMembers(trips, "sA", "sA").length, 0);
  // Matthew changes the water temp later → newest; John's identical-timestamp copy is not "newer"
  const matt2 = { ...matt, conditions: { ...matt.conditions, water_temp_f: 56, conditions_set_at: "2026-11-10T08:00:00" } };
  const newest = S.newestInGroup(S.groupMembers([matt2, john], "sJ", "sM"));
  assert.equal(newest.values.water_temp_f, 56); assert.equal(newest.set_at, "2026-11-10T08:00:00");
  assert.ok(!S.sameConditions(newest, S.currentConditions(S.openSessions([john])[0])));
  assert.ok(S.sameConditions(S.currentConditions(S.openSessions([matt])[0]), S.currentConditions(S.openSessions([john])[0]))); // same spot + values (group/angler ignored)
});

test("relocateRows: in place when young, split when older or moved", async () => {
  const S = await import("./session.js");
  const { parseIso } = await import("./py.js");
  const r = { trip_id: "t1", session_id: "s", trip_date: "2026-11-10", spot_id: "p1", spot_name: "Point", lure_used: "Jig", conditions: { ...S.CONDITION_FIELDS, source: "spot_session",
    lure_category: "football_jig", lure_start_time: "07:00:00", lure_end_time: null, fish: [{ species: "Largemouth Bass" }] } };
  const newBase = { ...S.CONDITION_FIELDS, water_temp_f: 50 };
  const args = (now, spot) => ({ newBase, spot, structure: "Main-lake point", clarity: "Clear", segment: "Morning", predicted: 6, owner: "j@x", now });
  const young = S.relocateRows([r], args(parseIso("2026-11-10T07:05:00"), { spot_id: "p1", name: "Point" }));
  assert.equal(young.next.length, 1); assert.equal(young.next[0].conditions.water_temp_f, 50); assert.equal(young.next[0].conditions.fish.length, 1);
  const old = S.relocateRows([r], args(parseIso("2026-11-10T08:00:00"), { spot_id: "p1", name: "Point" }));
  assert.equal(old.next.length, 2); assert.equal(old.next[0].conditions.lure_end_time, "08:00:00"); assert.equal(old.next[1].conditions.water_temp_f, 50);
  const moved = S.relocateRows([r], args(parseIso("2026-11-10T07:05:00"), { spot_id: "p2", name: "Cove" }));
  assert.equal(moved.next.length, 2); assert.equal(moved.next[1].spot_id, "p2");
});
