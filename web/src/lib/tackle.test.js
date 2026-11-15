import { test } from "node:test";
import assert from "node:assert/strict";
import { groupByType, tackleSummary } from "./tackle.js";

test("tackle summary: per-type and overall lures / in stock / out", () => {
  const items = [
    { item_id: "a", category: "suspending_jerkbait", quantity: "3" },
    { item_id: "b", category: "suspending_jerkbait", quantity: "0" },
    { item_id: "c", category: "drop_shot", quantity: "12" },
    { item_id: "d", category: "", quantity: "1" },
    { item_id: "e", category: "suspending_jerkbait", quantity: "" },
    { item_id: "f", category: "drop_shot", quantity: "-2" },
  ];
  const s = tackleSummary(groupByType(items));
  assert.equal(s.types, 3); assert.equal(s.lures, 6); assert.equal(s.inStock, 16); assert.equal(s.out, 3);
  const jb = s.rows.find((r) => r.key === "suspending_jerkbait");
  assert.deepEqual([jb.lures, jb.inStock, jb.out], [3, 3, 2]);
  assert.equal(s.rows.at(-1).key, "");   // "No type set" stays last
  assert.deepEqual(tackleSummary([]), { rows: [], types: 0, lures: 0, inStock: 0, out: 0 });
});
