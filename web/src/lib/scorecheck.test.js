import { test } from "node:test";
import assert from "node:assert/strict";
import { describeR, pearson, scoreBands, scoreCheck, scoreDays } from "./scorecheck.js";

const row = (d, sid, seg, score, fish, a, b, extra = {}) => ({ trip_date: d, session_id: sid, segment: seg, predicted_score: score, fish_caught: String(fish),
  owner: "j@x", conditions: { lure_start_time: a, lure_end_time: b, source: "spot_session", ...extra } });

test("a day: distinct session/segment scores averaged, side-by-side lures don't double the hours", () => {
  const days = scoreDays([
    row("2026-10-01", "s1", "Morning", "6.0", 2, "07:00:00", "09:00:00"),
    row("2026-10-01", "s1", "Morning", "6.0", 1, "07:00:00", "08:00:00"),   // second lure, same time
    row("2026-10-01", "s2", "Evening", 8, 3, "17:00:00", "18:00:00"),
    row("2026-10-02", "s3", "Morning", "", 4, "07:00:00", "08:00:00"),      // no score → day dropped
  ]);
  assert.equal(days.length, 1);
  const d = days[0];
  assert.equal(d.score, 7); assert.equal(d.fish, 6); assert.equal(d.hours, 3); assert.equal(d.rate, 2); assert.equal(d.sessions, 2);
});

test("open lures and other anglers are left out when asked", () => {
  const days = scoreDays([row("2026-10-01", "s1", "Morning", 5, 2, "07:00:00", null), row("2026-10-01", "s2", "Morning", 5, 1, "07:00:00", "08:00:00", {})],
    { owner: "someone@else" });
  assert.equal(days.length, 0);
});

test("bands, correlation and the plain-words read", () => {
  const trips = [];
  for (let i = 0; i < 8; i++) trips.push(row(`2026-09-${10 + i}`, `s${i}`, "Morning", 3 + i, i, "07:00:00", "09:00:00"));
  const out = scoreCheck(trips);
  assert.equal(out.days.length, 8);
  assert.ok(out.rFish > 0.99 && out.rRate > 0.99);
  assert.deepEqual(scoreBands(out.days).map((b) => b.label), ["Under 4", "4–5", "5–6", "6–7", "7–8", "8–9", "9 and up"]);
  assert.equal(scoreBands(out.days).at(-1).days, 2);   // 9 and 10 together
  assert.equal(pearson([1, 2, 3], [1, 2, 3]), null);
  assert.match(describeR(0.6), /strong/); assert.match(describeR(0.05), /No real link/); assert.match(describeR(-0.4), /FEWER/);
});
