import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { floorFromProfile, milesFromDam, oxygenOutlook, parseDamProfile, seasonFor, uplakeFloorFt } from "./oxygen.js";

const real = readFileSync(new URL("./fixtures/usace_nrr_2026-11-12.html", import.meta.url), "utf8");

test("parses the latest full dam profile from the real Corps page (tailwater row ignored)", () => {
  const p = parseDamProfile(real);
  assert.equal(p.observed_at, "2026-11-12T08:00:00");
  assert.equal(p.rows.length, 19);
  assert.deepEqual(p.rows[0], { depth_ft: 0, temp_f: 64.4, do_mg_l: 4.33 });
  assert.equal(p.rows[18].do_mg_l, 0.73);
});

test("oxygen floor: interpolated, 0 when surface low, null when fine to bottom", () => {
  const aug = [{ depth_ft: 10, do_mg_l: 8.14 }, { depth_ft: 15, do_mg_l: 0.69 }]; // Corps 2025-08-08 at the dam
  assert.equal(floorFromProfile([{ depth_ft: 0, do_mg_l: 8.4 }, ...aug]), 12.1);
  assert.equal(floorFromProfile(parseDamProfile(real).rows), 0);
  assert.equal(floorFromProfile(parseDamProfile(real).rows, 3), 38.2); // matches the Corps file analysis
  assert.equal(floorFromProfile([{ depth_ft: 0, do_mg_l: 9 }, { depth_ft: 40, do_mg_l: 7 }]), null);
});

test("seasonal table and up-lake scaling", () => {
  assert.equal(seasonFor("2027-07-04").floor_ft, 17.7);
  assert.equal(seasonFor("2027-01-10"), null);
  assert.equal(uplakeFloorFt(17.1, 0), 17.1);
  assert.equal(uplakeFloorFt(17.1, 10.4), 11.5);
  assert.equal(uplakeFloorFt(17.1, 30), 11.5);
  assert.ok(Math.abs(milesFromDam(37.350833, -86.081389) - 10.4) < 0.1); // Corps station NRR20005
});

test("outlook: fresh profile beats the typical year; stale falls back", () => {
  const p = parseDamProfile(real);
  const o = oxygenOutlook("2026-11-18", p);
  assert.equal(o.kind, "low"); assert.equal(o.source, "profile"); assert.match(o.detail, /about 38 ft/); assert.ok(o.warning);
  const stale = oxygenOutlook("2027-07-20", p);
  assert.equal(stale.source, "typical"); assert.equal(stale.headline, "~17 ft"); assert.equal(stale.warning, null);
  assert.equal(oxygenOutlook("2027-10-20", null).kind, "unsettled");
  assert.equal(oxygenOutlook("2027-02-01", null).kind, "ok");
  assert.equal(oxygenOutlook("2027-04-05", null).headline, "Not limited");
});
