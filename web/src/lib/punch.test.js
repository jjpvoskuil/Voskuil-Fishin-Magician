import { test } from "node:test";
import assert from "node:assert/strict";
import { canEdit, exportText, pageFor, sortItems, titleOf } from "./punch.js";

const items = [
  { task_no: 2, status: "Done", description: "Old fixed thing", priority: "Medium" },
  { task_no: 98, status: "Open", description: "UX redesign phase 3\nmore words", priority: "Medium", page: "General / whole app", author: "John", created_at: "2026-10-01T10:00:00", owner: "j@x" },
  { task_no: 99, status: "Open", title: "Bigger + Fish button", description: "Hard to hit with gloves on.", priority: "High", kind: "Change", page: "Session", author: "Matthew",
    created_at: "2026-11-11T09:00:00", owner: "m@x", context: { screen: "Spot Session", where: "#session", build: "Nov 11, 9:00 AM" } },
  { task_no: 100, status: "In progress", description: "Thing", priority: "Low", owner: "j@x" },
];
test("punch: titles, sort, permissions, page names", () => {
  assert.equal(titleOf(items[1]), "UX redesign phase 3");
  assert.deepEqual(sortItems(items).map((p) => p.task_no), [99, 98, 100, 2]);
  assert.ok(canEdit(items[2], { email: "m@x", role: "member" })); assert.ok(!canEdit(items[1], { email: "m@x", role: "member" }));
  assert.ok(canEdit(items[1], { email: "z@x", role: "admin" }));
  assert.equal(pageFor("Spot Session"), "Session"); assert.equal(pageFor("Leaderboard"), "Leaderboard"); assert.equal(pageFor("Odd"), "General / whole app");
});
test("punch: Copy for Claude text", () => {
  const t = exportText(items, { today: "2026-11-11" });
  assert.match(t, /^Fishin Magician punch list \(copied 2026-11-11\) — 3 open\./);
  assert.match(t, /#99 \[Open · High · Change · Session\] Bigger \+ Fish button\n {3}Hard to hit with gloves on\.\n {3}\(screen: Spot Session · at #session · build Nov 11, 9:00 AM\)\n {3}— Matthew, 2026-11-11/);
  assert.match(t, /#98 \[Open · Medium · General \/ whole app\] UX redesign phase 3\n {3}more words/);
  assert.ok(!t.includes("#2 ")); assert.match(exportText(items, { includeDone: true }), /Recently closed:\n#2 \[Done\] Old fixed thing/);
});
