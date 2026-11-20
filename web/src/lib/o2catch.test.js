import test from "node:test";
import assert from "node:assert/strict";
import { allProfiles, conditionsOn, o2Catch, outings, summarizeProfile } from "./o2catch.js";

const row = (o) => ({ trip_date: o.d, owner: o.who || "a@x", session_id: o.s, spot_id: "sp", fish_caught: String(o.f || 0),
  conditions: { lure_start_time: o.a || "07:00:00", lure_end_time: o.b || "09:00:00", fish_depth_ft: o.fd ?? null, fish: [] } });
const spots = [{ spot_id: "sp", lat: 37.2792, lon: -86.2469 }]; // at the dam: no up-lake scaling

test("profile summaries from the Corps file", () => {
  const p = allProfiles();
  assert.ok(p.length >= 13);
  const aug21 = p.find((x) => x.date === "2026-08-21");
  assert.equal(aug21.phase, "stratified"); assert.equal(aug21.floor_ft, 12.6);
  assert.equal(p.find((x) => x.date === "2026-10-28").phase, "turnover");
  assert.equal(p.find((x) => x.date === "2026-11-12").phase, "turnover");
  assert.equal(summarizeProfile("x", [{ depth_ft: 0, temp_f: 50, do_mg_l: 9 }, { depth_ft: 40, temp_f: 49.5, do_mg_l: 8.5 }, { depth_ft: 80, temp_f: 49, do_mg_l: 8 }]).phase, "mixed");
});

test("conditions interpolate between stratified profiles, else nearest within 10 days", () => {
  const p = allProfiles();
  const c = conditionsOn("2026-08-13", p); // Aug 6 13.3 → Aug 21 12.6
  assert.deepEqual(c.from, ["2026-08-06", "2026-08-21"]);
  assert.ok(Math.abs(c.floor_ft - (13.3 + (7 / 15) * (12.6 - 13.3))) < 0.01);
  assert.equal(conditionsOn("2026-10-30", p).phase, "turnover");
  assert.equal(conditionsOn("2026-12-30", p), null);
  assert.equal(conditionsOn("2026-04-01", p), null);
});

test("logged profiles (fm_water_quality.profile) extend the record", () => {
  const log = [{ observed_at: "2027-06-10T08:00:00", profile: [{ depth_ft: 0, water_temp_f: 80, do_mg_l: 9 }, { depth_ft: 10, water_temp_f: 78, do_mg_l: 7 }, { depth_ft: 20, water_temp_f: 68, do_mg_l: 2 }] }];
  const p = allProfiles(log); const j = p.find((x) => x.date === "2027-06-10");
  assert.equal(j.phase, "stratified"); assert.equal(j.floor_ft, 14);
});

test("outings and the report", () => {
  const trips = [
    row({ d: "2026-08-21", s: "1", f: 2, fd: 12, a: "06:00:00", b: "07:00:00" }), row({ d: "2026-08-21", s: "1", f: 1, a: "06:30:00", b: "08:00:00" }),
    row({ d: "2026-09-08", s: "2", f: 9, fd: 8, b: "10:00:00" }),          // 3 h, 8 ft vs 16 ft floor → well above
    row({ d: "2026-10-28", s: "3", f: 0, b: "08:00:00" }),
    row({ d: "2026-08-22", s: "4", f: 5, b: "07:10:00" }),                 // 10 min: too short
    { ...row({ d: "2026-08-23", s: "5" }), conditions: { lure_start_time: "07:00:00" } }, // still on the water
  ];
  const o = outings(trips); assert.equal(o.length, 3);
  assert.deepEqual(o[0], { date: "2026-08-21", owner: "a@x", spot_id: "sp", hours: 2, fish: 3, fish_depth: 12 });
  const r = o2Catch(trips, { spots });
  assert.equal(r.matched, 3);
  const st = r.byPhase.find((x) => x.key === "stratified"); assert.equal(st.outings, 2); assert.equal(st.fish, 12); assert.equal(st.rate, 12 / 5);
  assert.equal(r.byPhase.find((x) => x.key === "turnover").outings, 1);
  assert.equal(r.byPosition.find((x) => x.key === "at").outings, 1);   // 12 ft vs 12.6 ft floor
  assert.equal(r.byPosition.find((x) => x.key === "well").outings, 1);
  assert.equal(r.weeks.length, 3);
  assert.equal(o2Catch(trips, { spots, owner: "b@x" }).matched, 0);
});
