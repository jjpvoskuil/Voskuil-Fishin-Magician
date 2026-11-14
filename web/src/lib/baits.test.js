import { test } from "node:test";
import assert from "node:assert/strict";
import { defaultRigFor, inventoryTypeOptions, rigIdOf, rigKey, servesKeys, styleOf, toInventoryCategory } from "./baits.js";
import { groupOwnedByCategory, guessCategoryFromText } from "./lures.js";
import { canTakeTrailer, isSoftPlastic } from "./session.js";

test("old rig types map to bait styles", () => {
  assert.equal(styleOf("drop_shot"), "sp_worm");
  assert.equal(styleOf("texas_rig_creature"), "sp_creature");
  assert.equal(styleOf("weightless_soft_plastic"), "sp_fluke");
  assert.equal(styleOf("soft_swimbait"), "sp_paddle_tail");
  assert.equal(styleOf("ned_rig"), "sp_trd");
  assert.equal(styleOf("sp_fluke"), "sp_fluke");
  assert.equal(styleOf("underspin"), null);
  assert.equal(styleOf("football_jig"), null);
});

test("rig + style -> engine key, and back", () => {
  assert.equal(rigKey("texas", "sp_worm"), "texas_rig_worm");
  assert.equal(rigKey("texas", "sp_creature"), "texas_rig_creature");
  assert.equal(rigKey("drop_shot", "sp_creature"), "drop_shot");
  assert.equal(rigKey("ned", "sp_trd"), "ned_rig");
  assert.equal(rigKey("underspin", "sp_paddle_tail"), "underspin");
  assert.equal(rigIdOf("texas_rig_creature"), "texas");
  assert.equal(rigIdOf("finesse_shaky_head"), "shaky_head");
  assert.equal(rigIdOf("crankbait"), null);
});

test("default rig: last time fished, else old type, else the style's usual", () => {
  const trips = [
    { trip_date: "2026-10-01", conditions: { item_id: "w1", lure_category: "texas_rig_worm", lure_start_time: "08:00:00" } },
    { trip_date: "2026-11-01", conditions: JSON.stringify({ item_id: "w1", lure_category: "drop_shot", lure_start_time: "07:00:00" }) },
  ];
  assert.equal(defaultRigFor({ item_id: "w1", category: "sp_worm" }, trips), "drop_shot");
  assert.equal(defaultRigFor({ item_id: "x", category: "finesse_shaky_head" }, trips), "shaky_head");
  assert.equal(defaultRigFor({ item_id: "x", category: "sp_fluke" }, []), "weightless");
  assert.equal(defaultRigFor({ item_id: "x", category: "sp_trd" }, []), "ned");
  assert.equal(defaultRigFor({ item_id: "x", brand: "Roboworm", description: "FAT Straight Worm", category: "sp_worm" }, []), "drop_shot");
  assert.equal(defaultRigFor({ item_id: "x", brand: "Yamamoto", description: "Senko 5in", category: "sp_worm" }, []), "wacky");
  assert.equal(defaultRigFor({ item_id: "x", brand: "Berkley", description: "Power Worm 7in", category: "sp_worm" }, []), "texas");
});

test("a worm counts as owning its rigs; hard baits are unchanged", () => {
  const g = groupOwnedByCategory([{ item_id: "w", category: "sp_worm", quantity: "1" }, { item_id: "j", category: "football_jig", quantity: "1" },
    { item_id: "z", category: "sp_trd", quantity: "0" }]);
  assert.deepEqual(Object.keys(g).sort(), ["carolina_rig", "drop_shot", "finesse_shaky_head", "football_jig", "texas_rig_worm", "wacky_rig_senko"]);
  assert.deepEqual(servesKeys("nonsense"), []);
});

test("new lure types are tagged from text", () => {
  assert.equal(guessCategoryFromText("Blakemore", "Yum Runner Underspin - Bombshell"), "underspin");
  assert.equal(guessCategoryFromText("River2Sea", "S-Waver Swimbait - Party Crasher"), "hard_swimbait");
  assert.equal(guessCategoryFromText("Z-Man", "Diezel MinnowZ paddle tail"), "soft_swimbait");
  assert.equal(toInventoryCategory(guessCategoryFromText("Roboworm", "FAT Straight Worm")), "sp_worm");
  assert.equal(toInventoryCategory(guessCategoryFromText("Zoom", "Salty Super Fluke")), "sp_fluke");
  assert.equal(toInventoryCategory("spinnerbait"), "spinnerbait");
});

test("tackle-box type list: styles + hard baits, old rig only for an item that has one", () => {
  const keys = inventoryTypeOptions("").map(([k]) => k);
  for (const k of ["sp_worm", "sp_creature", "sp_fluke", "sp_paddle_tail", "sp_trd", "underspin", "hard_swimbait", "football_jig"]) assert.ok(keys.includes(k), k);
  for (const k of ["drop_shot", "texas_rig_worm", "ned_rig", "soft_swimbait"]) assert.ok(!keys.includes(k), k);
  assert.ok(inventoryTypeOptions("drop_shot").some(([k]) => k === "drop_shot"));
});

test("soft plastics ask the rig question, not the trailer one", () => {
  assert.equal(canTakeTrailer({ category: "sp_creature" }), false);
  assert.equal(canTakeTrailer({ category: "football_jig" }), true);
  assert.ok(isSoftPlastic("drop_shot"));
  assert.ok(isSoftPlastic("underspin", "sp_paddle_tail"));
  assert.ok(!isSoftPlastic("underspin"));
});
