// Parity tests: the JavaScript engine must give the same answers as the Python reference (core/*.py).
// Fixtures: TZ=UTC python3 web/tools/make_engine_fixtures.py (synthetic weather + trips only).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import * as astro from "./astro.js";
import * as ow from "./onwater.js";
import * as sc from "./scoring.js";
import * as cal from "./calibration.js";
import { estimateWaterTempF, pressureTrendHpaPer24h } from "./weather.js";
import { parseIso, pyFixed, pyRound, roundHalfEven } from "./py.js";

const FX = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/engine.fixtures.json.gz", import.meta.url))));
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** deep-compare actual (JS) with expected (Python JSON): numbers to 1e-9, Python datetimes vs JS µs to 2 µs */
function same(actual, expected, path = "$") {
  if (expected === null || expected === undefined) { assert.ok(actual === null || actual === undefined, `${path}: expected null, got ${JSON.stringify(actual)}`); return; }
  if (typeof expected === "string" && ISO.test(expected) && typeof actual === "number") {
    assert.ok(Math.abs(actual - parseIso(expected)) <= 2, `${path}: time ${expected} vs ${actual}`); return;
  }
  if (typeof expected === "number") {
    assert.equal(typeof actual, "number", `${path}: expected number ${expected}, got ${JSON.stringify(actual)}`);
    assert.ok(Math.abs(actual - expected) <= 1e-9 * Math.max(1, Math.abs(expected)), `${path}: ${actual} vs ${expected}`); return;
  }
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${path}: expected array`);
    assert.equal(actual.length, expected.length, `${path}: length ${actual.length} vs ${expected.length}`);
    expected.forEach((e, i) => same(actual[i], e, `${path}[${i}]`)); return;
  }
  if (typeof expected === "object") {
    for (const k of Object.keys(expected)) same(actual?.[k], expected[k], `${path}.${k}`);
    return;
  }
  assert.equal(actual, expected, path);
}

test("python rounding helpers", () => {
  assert.equal(pyFixed(0.5, 0), "0"); assert.equal(pyFixed(1.5, 0), "2"); assert.equal(pyFixed(2.5, 0), "2");
  assert.equal(pyFixed(0.125, 2), "0.12"); assert.equal(pyFixed(0.375, 2), "0.38"); assert.equal(pyFixed(2.675, 2), "2.67");
  assert.equal(pyRound(-2.5), -2); assert.equal(pyRound(1.005, 2), 1.0); assert.equal(roundHalfEven(2.5), 2); assert.equal(roundHalfEven(3.5), 4);
});

test("default weights match", () => same(sc.DEFAULT_WEIGHTS, FX.weights));

test("moon phase", () => { for (const c of FX.moon) same(astro.moonPhase(parseIso(c.t)), c.r, `moon ${c.t}`); });

test("solunar times", () => { for (const c of FX.solunar) same(astro.solunarTimes(c.d, 37.2783, -86.2475, c.tz), c.r, `solunar ${c.d}`); });

test("on-the-water bands and conversions", () => {
  for (const [t, l] of FX.water_temp_band) assert.equal(ow.waterTempBand(t).label, l, `temp ${t}`);
  for (const [doy, t, s] of FX.season_stage) assert.equal(sc.seasonStage(doy, t), s, `season ${doy} ${t}`);
  for (const [m, l] of FX.wind_band) assert.equal(ow.windBand(m).label, l, `wind ${m}`);
  for (const [d, l] of FX.wind_dir) assert.equal(ow.windDirectionForDegrees(d), l, `dir ${d}`);
  for (const [c, l] of FX.light) assert.equal(ow.lightConditionForCloudPct(c), l, `light ${c}`);
  for (const [s, c, st, l] of FX.clarity) assert.equal(ow.resolveWaterClarity(s, c, st), l, `clarity ${s} ${c} ${st}`);
  for (const [i, p, l] of FX.precip_opt) assert.equal(ow.precipitationOptionForForecast(i, p), l, `precip ${i} ${p}`);
  for (const [d, band, def] of FX.thermo) { same(ow.estimateThermoclineBandFt(d), band, `thermo ${d}`); assert.equal(ow.defaultThermoclineInputFt(d), def); }
  for (const [th, fd, s] of FX.thermo_caveat) assert.equal(ow.thermoclineCaveat(th, fd), s);
});

test("segment scores (500 combinations)", () => {
  FX.segment.forEach((c, i) => {
    const r = sc.manualSegmentScore({ ...c.args, weights: c.weights, at_time: parseIso(c.at) });
    same(r, c.r, `segment#${i}`);
  });
});

test("whole forecasts from weather bundles", () => {
  for (const b of FX.bundles) {
    const tag = `${b.anchor}/${b.style}`;
    same(sc.scoreWeek(b.bundle, b.anchor, 8), b.week, `week ${tag}`);
    same(sc.scoreWeek(b.bundle, b.anchor, 3, { pressure_falling: 1.8, season_spring_fall_bonus: 1.0 }), b.week_w, `week_w ${tag}`);
    for (const [t, v] of b.trend) same(pressureTrendHpaPer24h(b.bundle, parseIso(t)), v, `trend ${tag} ${t}`);
    for (const [d, v] of b.water) same(estimateWaterTempF(b.bundle, d), v, `water ${tag} ${d}`);
    for (const [seg, t, v] of b.rt) same(sc.realtimeContextFromBundle(b.bundle, seg, b.anchor, { at_time: parseIso(t) }), v, `rt ${tag} ${seg}`);
  }
});

test("calibration from trips", () => {
  same(FX.trips.map(cal.tripFishPerHour), FX.trip_rate, "trip_rate");
  same(cal.calibrateWeights(FX.trips), FX.calibrated, "calibrated");
  same(cal.calibrateWeights(FX.trips.slice(0, 25)), FX.calibrated_small, "calibrated_small");
  const loc = cal.locationAdjustments(FX.trips);
  assert.deepEqual(Object.keys(loc), Object.keys(FX.location));
  same(loc, FX.location, "location");
  same(cal.moonIlluminationDawnRates(FX.trips), FX.dawn_rates_all, "dawn_rates_all");
  same(cal.moonIlluminationDawnRates(FX.trips, "2026-08-10", "2026-09-25"), FX.dawn_rates_window, "dawn_rates_window");
  same(cal.dailyDawnMorningCatch(FX.trips, "2026-08-25", "2026-09-14"), FX.daily_catch, "daily_catch");
});

import * as lake from "./lake.js";
test("lake level + USACE water quality parsing", () => {
  same(lake.parseLakeLevel(FX.usgs.payload), FX.usgs.latest);
  same(lake.parseLakeLevels(FX.usgs.payload), FX.usgs.history);
  same(lake.parseSurfaceWaterQuality(FX.usace.html), FX.usace.r);
  assert.throws(() => lake.parseSurfaceWaterQuality("<tr><td>x</td></tr>"), { message: FX.usace_missing });
  for (const [t, v] of FX.do_sat) same(lake.doSaturationConcentrationMgL(t, 515.0), v);
});

import { applyFreeze } from "./freeze.js";
test("score freezing", () => {
  const b = FX.bundles.find((x) => x.anchor === "2026-11-10").bundle;
  for (const c of FX.freeze) {
    const day = sc.scoreDay(b, "2026-11-10");
    const rows = applyFreeze(day, c.frozen, parseIso(c.now));
    assert.deepEqual(rows.map((r) => r.segment_name), c.names, c.now);
    same(rows.map((r) => ({ segment_name: r.segment_name, score: r.score })), c.saved, `saved ${c.now}`);
    same(day, c.day, `day ${c.now}`);
  }
});
