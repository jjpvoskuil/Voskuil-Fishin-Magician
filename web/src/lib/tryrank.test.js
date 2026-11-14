import { test } from "node:test";
import assert from "node:assert/strict";
import { kindStats, rankTries } from "./tryrank.js";

const tries = [
  { lat: 37.30, lon: -86.20, kind: "flat", score: 9, emin: 500, emax: 510 },
  { lat: 37.31, lon: -86.21, kind: "point", score: 6, emin: 485, emax: 512 },
  { lat: 37.32, lon: -86.22, kind: "point", score: 3, emin: 480, emax: 512 },
  { lat: 37.33, lon: -86.23, kind: "swing", score: 7, emin: 492, emax: 495 },
];

test("no trip log: structure score decides", () => {
  const r = rankTries(tries, { spots: [], stats: { base: 0, spots: {} } });
  assert.deepEqual(r.map((t) => t.score > 0 && t.kind + t.rank), ["flat1", "swing2", "point3", "point4"]);
  assert.equal(r[0].n, 4);
});

test("dry at today's level drops out", () => {
  const r = rankTries(tries, { spots: [], stats: { base: 0, spots: {} }, level: 496 });
  assert.deepEqual(r.map((t) => t.kind).sort(), ["point", "point", "swing"]);   // flat bottom 500 ft = dry; swing 4 ft deep stays
});

test("a kind that produces moves up; a hot spot nearby helps", () => {
  const spots = [{ spot_id: "a", name: "Hot Point", lat: 37.3202, lon: -86.2201, location_type: "Main-lake point" },
    { spot_id: "b", name: "Dead Flat", lat: 37.40, lon: -86.30, location_type: "Flat" }];
  const stats = { base: 1, spots: { a: { fish: 30, hours: 10, heat: 2.5 }, b: { fish: 0, hours: 10, heat: 0.3 } } };
  const ks = kindStats(spots, stats);
  assert.ok(ks.point.mult > 1.5 && ks.flat.mult < 0.5);
  const r = rankTries(tries, { spots, stats });
  assert.deepEqual(r.slice(0, 2).map((t) => t.kind), ["point", "point"]);   // points produce here → both points lead
  const nearHot = r.find((t) => t.lat === 37.32);
  assert.ok(nearHot.parts.nearby > 1.5 && nearHot.reasons.some((x) => x.includes("Hot Point")));
  assert.equal(r[r.length - 1].kind, "flat");
});
