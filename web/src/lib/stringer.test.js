// Parity: stringer.js vs core/stringer.py (fixtures from web/tools/make_stringer_fixtures.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import * as S from "./stringer.js";

const FX = JSON.parse(gunzipSync(readFileSync(new URL("./fixtures/stringer.fixtures.json.gz", import.meta.url))).toString());

test("stringer: frames, hero ring, six ranked tabs, activity, species mix", () => {
  for (const [i, c] of FX.cases.entries()) {
    const { fish, trips } = S.buildFrames(c.rows, FX.spots);
    const ds = trips.map((t) => t.date).filter(Boolean).sort();
    assert.equal(S.seasonLabel(trips), c.out.season, `season ${i}`);
    assert.deepEqual(S.heroStates(fish, trips), c.out.hero, `hero ${i}`);
    for (const [k, , , b] of S.CATEGORIES) assert.deepEqual(b(fish, trips), c.out.cats[k], `${k} ${i}`);
    assert.deepEqual(S.dailyActivitySeries(fish, ds[0], ds[ds.length - 1]), c.out.daily, `daily ${i}`);
    assert.deepEqual(S.speciesMix(fish), c.out.mix, `mix ${i}`);
  }
});
