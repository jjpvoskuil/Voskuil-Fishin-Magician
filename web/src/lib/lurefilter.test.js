import { test } from "node:test";
import assert from "node:assert/strict";
import { colorFamiliesIn, colorOf, inColorFamily, inTypeFamily, typeFamiliesIn } from "./lurefilter.js";

const L = (category, description) => ({ category, description });
test("lure filters: color part, type + color families", () => {
  assert.equal(colorOf(L("drop_shot", "FAT Straight Worm - Margarita Mutilator, 6in")), "Margarita Mutilator");
  assert.equal(colorOf(L("x", "Moontalker")), "Moontalker");
  const sq = L("squarebill_crankbait", "KVD 1.5 - Sexy Shad"), rt = L("lipless_crankbait", "Rat-L-Trap - Chrome Blue"), js = L("suspending_jerkbait", "Shadow Rap - Ghost Shad");
  assert.ok(inTypeFamily(sq, "Crankbaits") && inTypeFamily(rt, "Crankbaits") && !inTypeFamily(js, "Crankbaits"));
  assert.ok(inColorFamily(sq, "Chartreuse") && inColorFamily(sq, "Shad & white"));  // sexy shad is both
  assert.ok(inColorFamily(rt, "Chrome & metallic") && inColorFamily(rt, "Black & blue") && !inColorFamily(js, "Chartreuse"));
  assert.deepEqual(typeFamiliesIn([sq, js]), ["Crankbaits", "Jerkbaits"]);
  assert.ok(!colorFamiliesIn([js]).includes("Chartreuse"));
});
