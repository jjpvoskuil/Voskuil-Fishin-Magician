import test from "node:test";
import assert from "node:assert/strict";
import { applyLegEdit, buildSessions, fishTotals, legTimeSpan, matches, summarize } from "./history.js";

const base = { water_temp_f: 60, secchi_ft: 3, stain_color: "Green stained", stirred_up: false, wind_band: "Calm", wind_direction: "N",
  light_condition: "Sunny", precipitation: "None", fish_depth_ft: null, forage_seen: [], fish_activity: "Moderate", forage_activity: "Moderate" };
const row = (id, sid, spot, start, end, fish, extra = {}) => ({ trip_id: id, session_id: sid, trip_date: "2026-11-01", segment: "Morning", spot_id: spot, spot_name: spot,
  structure_type: "Main-lake point", water_clarity: "Clear", lure_used: `Lure ${id}`, fish_caught: String(fish.length), owner: "j@x.com",
  conditions: { ...base, angler: "John", source: "spot_session", fish, lure_category: "drop_shot", lure_start_time: start, lure_end_time: end, ...extra } });

test("sessions group by session_id and split into legs on a move or conditions change", () => {
  const trips = [
    row("a", "s1", "P1", "07:00:00", "08:00:00", [{ species: "Largemouth Bass", weight_lb: 2 }]),
    row("b", "s1", "P1", "07:30:00", "08:00:00", []),
    row("c", "s1", "P2", "08:00:00", "09:15:00", [{ species: "Spotted Bass", weight_lb: 1.5 }, { species: "Largemouth Bass" }]),
    row("d", "s1", "P2", "09:15:00", "10:00:00", [], { wind_band: "Moderate Chop" }),
    row("e", "", "P3", "06:00:00", "06:30:00", []),
  ];
  const [s1, solo] = [buildSessions(trips).find((s) => s.key === "s1"), buildSessions(trips).find((s) => s.key === "solo:e")];
  assert.equal(s1.legs.length, 3);
  assert.deepEqual(s1.locations, ["P1", "P2"]);
  assert.equal(s1.fish_total, 3);
  assert.equal(s1.legs[0].time_span, "7:00 AM – 8:00 AM");
  assert.deepEqual(s1.species.sort(), ["Largemouth Bass", "Spotted Bass"]);
  assert.ok(solo);
  assert.equal(summarize([s1]).fish, 3);
  assert.equal(summarize([s1]).hours, 1 + 0.5 + 1.25 + 0.75);
});

test("open lure → still open", () => {
  assert.equal(legTimeSpan([row("a", "s", "P", "06:05:00", null, [])]), "6:05 AM – still open");
});

test("filters", () => {
  const [s] = buildSessions([row("a", "s1", "P1", "07:00:00", "08:00:00", [])]);
  assert.ok(matches(s, { from: "2026-10-01", to: "2026-11-30" }));
  assert.ok(!matches(s, { from: "2026-11-02" }));
  assert.ok(!matches(s, { mine: "other@x.com" }));
  assert.ok(matches(s, { lureTypes: ["Drop Shot"], locations: ["P1"], segments: ["Morning"] }));
  assert.ok(!matches(s, { lureTypes: ["Ned Rig"] }));
});

test("edit keeps totals consistent and marks changed fields as yours", () => {
  const r = row("a", "s1", "P1", "07:00:00", "08:00:00", [{ species: "Largemouth Bass", weight_lb: 2 }]);
  const fish = [{ species: "Largemouth Bass", weight_lb: 2 }, { species: "Largemouth Bass", weight_lb: 3.25, count: 2 }];
  const [e] = applyLegEdit([r], { segment: "Dawn", cond: { ...base, secchi_ft: 0.5 }, changed: ["secchi_ft"], lures: { a: { fish, lure_category: "ned_rig" } } }, "2026-11-02");
  assert.equal(e.fish_caught, 3); assert.equal(e.biggest_fish_lb, 3.25);
  assert.equal(e.conditions.lure_category, "ned_rig");
  assert.equal(e.conditions.field_sources.secchi_ft, "you");
  assert.equal(e.trip_date, "2026-11-02"); assert.equal(e.segment, "Dawn");
  assert.equal(e.water_clarity, "Muddy");
  assert.deepEqual(fishTotals([]), { fish_caught: 0, biggest_fish_lb: null });
});
