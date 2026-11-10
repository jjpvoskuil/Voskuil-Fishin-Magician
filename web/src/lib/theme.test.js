import { test } from "node:test";
import assert from "node:assert/strict";
import { autoTheme, resolveTheme } from "./theme.js";

const LAT = 37.33, LON = -86.17; // Nolin Lake; Nov 4 2026 sunrise ≈ 6:13 CST, sunset ≈ 4:44 CST
const at = (iso) => new Date(iso);

test("dark before sunrise+30, light midday, dark from sunset-30", () => {
  assert.equal(autoTheme(LAT, LON, at("2026-11-04T12:30:00Z")).theme, "dark");   // 6:30 AM
  assert.equal(autoTheme(LAT, LON, at("2026-11-04T12:55:00Z")).theme, "light");  // 6:55 AM
  assert.equal(autoTheme(LAT, LON, at("2026-11-04T22:00:00Z")).theme, "light");  // 4:00 PM
  assert.equal(autoTheme(LAT, LON, at("2026-11-04T22:25:00Z")).theme, "dark");   // 4:25 PM
  assert.equal(autoTheme(LAT, LON, at("2026-11-05T03:00:00Z")).theme, "dark");   // 9 PM
});

test("manual override lasts until the next automatic switch; a fixed choice sticks", () => {
  const noon = at("2026-11-04T18:00:00Z");
  const until = autoTheme(LAT, LON, noon).next.getTime();
  assert.equal(resolveTheme({ mode: "dark", until }, LAT, LON, noon).theme, "dark");
  assert.equal(resolveTheme({ mode: "dark", until }, LAT, LON, at("2026-11-04T22:30:00Z")).manual, false);
  assert.equal(resolveTheme({ mode: "light", until: null }, LAT, LON, at("2026-11-05T03:00:00Z")).theme, "light");
  assert.equal(resolveTheme({ mode: "auto" }, LAT, LON, noon).theme, "light");
});
