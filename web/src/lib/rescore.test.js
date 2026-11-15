import { test } from "node:test";
import assert from "node:assert/strict";
import { gunzipSync } from "node:zlib";
import { readFileSync } from "node:fs";
import { ARCHIVE_URL, HIST_FORECAST_URL, mergeBundles, plan, requestUrl, rescoreDays } from "./rescore.js";
import { scoreCheck, fishedDates } from "./scorecheck.js";
import { scoreDay } from "./scoring.js";

const fx = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/engine.fixtures.json.gz", import.meta.url))));
const bundle = fx.bundles.find((b) => b.anchor === "2026-11-10").bundle;

test("plan: one request per year, 6 days lead, archive API before 2022, never past yesterday", () => {
  const p = plan(["2021-06-05", "2021-07-01", "2025-05-02", "2026-11-14", "2026-11-15"], "2026-11-15");
  assert.deepEqual(p, [
    { url: ARCHIVE_URL, start: "2021-05-30", end: "2021-07-01" },
    { url: HIST_FORECAST_URL, start: "2025-04-26", end: "2025-05-02" },
    { url: HIST_FORECAST_URL, start: "2026-11-08", end: "2026-11-14" }]);
  assert.ok(!requestUrl(p[0]).includes("precipitation_probability"));
  assert.match(requestUrl(p[2]), /start_date=2026-11-08&end_date=2026-11-14/);
  assert.match(requestUrl(p[2]), /precipitation_probability/);
});
test("merge + rescore gives the same day score as the engine on the full bundle", async () => {
  const days = bundle.daily.time.map((t) => t.slice(0, 10));
  const d = days[8];   // a day with ≥6 days of history before it
  const half = (k, a, b) => Object.fromEntries(Object.entries(bundle[k]).map(([v, col]) => [v, col.slice(a, b)]));
  const nH = bundle.hourly.time.findIndex((t) => t.startsWith(days[5]));
  const parts = [{ hourly: half("hourly", 0, nH), daily: half("daily", 0, 5) }, { hourly: half("hourly", nH), daily: half("daily", 5) }];
  const merged = mergeBundles(parts);
  assert.equal(scoreDay(merged, d).overall_score, scoreDay(bundle, d).overall_score);
  const fetchFn = async () => ({ ok: true, json: async () => bundle });
  const out = await rescoreDays([d, "2001-01-01"], { solunar_bonus: 0 }, { today: "2030-01-01", fetchFn });
  assert.equal(out.scores[d].base, scoreDay(bundle, d).overall_score);
  assert.deepEqual(out.missing, ["2001-01-01"]); assert.equal(out.failed, 0);
  const bad = await rescoreDays(["2019-03-01"], null, { today: "2030-01-01", fetchFn: async () => ({ ok: false, status: 500 }) });
  assert.equal(bad.failed, 1); assert.deepEqual(bad.missing, ["2019-03-01"]);
});
test("scoreCheck with re-scored day scores covers days that had no saved score", () => {
  const T = (id, date, fish, score) => ({ trip_id: id, session_id: id, trip_date: date, fish_caught: String(fish), predicted_score: score, segment: "Morning",
    conditions: { lure_start_time: "07:00:00", lure_end_time: "09:00:00" } });
  const trips = [T("a", "2025-05-01", 4, null), T("b", "2025-05-03", 1, 7.5), T("c", "2025-05-04", 0, null)];
  assert.deepEqual(fishedDates(trips), ["2025-05-01", "2025-05-03", "2025-05-04"]);
  assert.equal(scoreCheck(trips).days.length, 1);
  const re = scoreCheck(trips, { dayScore: { "2025-05-01": 8, "2025-05-03": 5, "2025-05-04": 3 } });
  assert.deepEqual(re.days.map((d) => [d.score, d.rate]), [[8, 2], [5, 0.5], [3, 0]]);
});
