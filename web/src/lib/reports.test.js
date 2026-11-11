// Parity: reports.js vs core/reports.py (fixtures from web/tools/make_report_fixtures.py, TZ=UTC).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import * as R from "./reports.js";

const FX = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/reports.fixtures.json.gz", import.meta.url))).toString());
const near = (a, b, path) => {
  if (typeof a === "number" && typeof b === "number") { assert.ok(Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b)), `${path}: ${a} vs ${b}`); return; }
  if (a && b && typeof a === "object") { assert.deepEqual(Object.keys(a).sort(), Object.keys(b).sort(), path); for (const k of Object.keys(b)) near(a[k], b[k], `${path}.${k}`); return; }
  assert.equal(a, b, path);
};
const data = R.buildReportsData(FX.rows);

test("reports: every factor × metric with filters", () => {
  for (const [i, c] of FX.cases.entries()) {
    const got = R.computeReport(data, c.factor, c.metric, c.opts);
    assert.equal(got.length, c.out.length, `case ${i} ${c.factor}/${c.metric} length`);
    got.forEach((r, j) => near(r, c.out[j], `case ${i} ${c.factor}/${c.metric} [${j}]`));
  }
});
test("reports: moon + pressure history lookups, labels, species", () => {
  const bundle = { hourly: FX.bundle };
  for (const p of FX.preds) {
    near(R.predictByMoon(data, p.date, p.metric), p.moon, `moon ${p.date} ${p.metric}`);
    near(R.predictByPressure(data, p.date, bundle, p.metric), p.pressure, `pressure ${p.date} ${p.metric}`);
  }
  for (const [p, b] of FX.moon_bins) assert.equal(R.moonBin(p), b);
  for (const [v, w, t, s] of FX.labels) { assert.equal(R.tempBucketLabel(v, w), t); assert.equal(R.secchiBucketLabel(v, w), s); }
  assert.deepEqual(R.speciesOptions(data), FX.species);
});
