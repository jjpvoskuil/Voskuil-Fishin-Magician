// Parity tests for lures.js against core/lures.py. Fixtures: TZ=UTC python3 web/tools/make_lure_fixtures.py
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import * as L from "./lures.js";

const FX = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/lures.fixtures.json.gz", import.meta.url))));
const clone = (x) => JSON.parse(JSON.stringify(x));
function same(a, e, p = "$") {
  if (e === null || e === undefined) return assert.ok(a == null, `${p}: expected null, got ${JSON.stringify(a)}`);
  if (typeof e === "number") return assert.ok(typeof a === "number" && Math.abs(a - e) <= 1e-9 * Math.max(1, Math.abs(e)), `${p}: ${a} vs ${e}`);
  if (Array.isArray(e)) { assert.ok(Array.isArray(a), `${p}: expected array`); assert.equal(a.length, e.length, `${p} length`); e.forEach((x, i) => same(a[i], x, `${p}[${i}]`)); return; }
  if (typeof e === "object") { for (const k of Object.keys(e)) same(a?.[k], e[k], `${p}.${k}`); return; }
  assert.equal(a, e, p);
}

test("recommend() matches Python in 700 situations", () => {
  FX.cases.forEach((c, i) => {
    const inv = c.inv === "none" ? null : c.inv === "some" ? clone(FX.inventory.slice(0, 20)) : clone(FX.inventory);
    const r = L.recommend({ ...c.args, inventory: inv, trip_history: c.hist === "none" ? null : FX.trips });
    same(r, c.r, `case#${i}`);
    const cur = L.curateRecommendation(r, inv);
    assert.deepEqual([cur.recommended.map((b) => b.key), cur.gaps.map((b) => b.key)], c.cur, `curate#${i}`);
  });
});

test("tackle gaps, category guesses, videos, trailers", () => {
  assert.deepEqual(L.findInventoryGaps(FX.inventory), FX.gaps);
  for (const [t, g] of FX.guess) assert.equal(L.guessCategoryFromText(t), g, t);
  for (const [t, v] of FX.videos_for) same(L.getVideosFor(t), v, t);
  for (const [it, ok] of FX.trailer) assert.equal(L.isTrailerEligible(it), ok, JSON.stringify(it));
});

import * as B from "./leaderboard.js";
const one = (s) => (s && s.species instanceof Map ? { ...s, species: Object.fromEntries(s.species) } : s);
const plain = (stats) => stats.map(one);
const plainAwards = (a) => Object.fromEntries(Object.entries(a).map(([k, v]) => [k, one(v)]));
test("leaderboard: activity, awards, tables, lb-oz", () => {
  for (const [w, t] of FX.lb_oz) assert.equal(B.formatWeightLbOz(w), t, String(w));
  for (const b of FX.board) {
    assert.deepEqual(B.weekBounds(b.today), b.week_bounds);
    const day = B.buildDailyActivity(FX.board_rows, b.today), week = B.buildWeeklyActivity(FX.board_rows, b.today);
    same(plain(day), b.day, `day ${b.today}`); same(plain(week), b.week, `week ${b.today}`);
    same(plainAwards(B.dailyAwards(day)), b.awards_day, `awards_day ${b.today}`); same(plainAwards(B.dailyAwards(week)), b.awards_week, `awards_week ${b.today}`);
    same(B.leaderboardTableRows(day), b.table_day); same(B.leaderboardTableRows(week), b.table_week); same(B.grandTotal(week), b.total_week);
  }
});
