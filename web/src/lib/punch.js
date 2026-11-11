// Punch list helpers (old core/dev_tasks.py + Deercast's DevPage): numbered items, statuses, sorting and the
// "Copy for Claude" text a new session can work from.
export const STATUSES = ["Open", "In progress", "Done", "Won't do"];
export const PRIORITIES = ["High", "Medium", "Low"];
export const KINDS = ["Bug", "Change", "Idea"];
export const PAGES = ["Today", "Forecast", "Session", "Map", "Trip History", "Leaderboard", "Reports", "Tackle Box", "Punch list", "More",
  "General / whole app", "Data / backend (not page-specific)"];
/** screen title → punch page name */
export const pageFor = (title) => ({ "7-Day Forecast": "Forecast", "Spot Session": "Session", "Lake Map": "Map", "Lake setup": "Forecast" }[title] || (PAGES.includes(title) ? title : "General / whole app"));

export const titleOf = (p) => p.title || String(p.description || "").split(/\n/)[0].slice(0, 120);
export const canEdit = (p, me) => !!me && (me.role === "admin" || p.owner === me.email);
const pr = (p) => { const i = PRIORITIES.indexOf(p.priority); return i < 0 ? 1 : i; };
export const sortItems = (items) => [...items].sort((a, b) => STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status) || pr(a) - pr(b) || b.task_no - a.task_no);

export function contextLine(c) {
  if (!c) return "";
  return [c.screen && `screen: ${c.screen}${c.kicker ? ` (${c.kicker})` : ""}`, c.where && `at ${c.where}`, c.theme && `${c.theme} mode`, c.build && `build ${c.build}`, c.device].filter(Boolean).join(" · ");
}

/** Ready-to-paste note for a Claude session. */
export function exportText(items, { includeDone = false, today = new Date().toISOString().slice(0, 10) } = {}) {
  const open = sortItems(items.filter((p) => p.status === "Open" || p.status === "In progress"));
  const lines = [`Fishin Magician punch list (copied ${today}) — ${open.length} open. Repo jjpvoskuil/Voskuil-Fishin-Magician; work them by number.`, ""];
  for (const p of open) {
    lines.push(`#${p.task_no} [${p.status} · ${p.priority || "Medium"}${p.kind ? ` · ${p.kind}` : ""} · ${p.page || "General"}] ${titleOf(p)}`);
    const det = p.title ? p.description : String(p.description || "").split(/\n/).slice(1).join("\n");
    if (det && det.trim() && det.trim() !== titleOf(p)) lines.push(`   ${det.trim().replace(/\n+/g, "\n   ")}`);
    if (p.context) lines.push(`   (${contextLine(p.context)})`);
    lines.push(`   — ${p.author || "?"}, ${String(p.created_at || "").slice(0, 10)}`);
  }
  if (includeDone) {
    const done = items.filter((p) => p.status === "Done" || p.status === "Won't do").sort((a, b) => b.task_no - a.task_no).slice(0, 25);
    if (done.length) { lines.push("", "Recently closed:"); for (const p of done) lines.push(`#${p.task_no} [${p.status}] ${titleOf(p)}`); }
  }
  return lines.join("\n");
}
