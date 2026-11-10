// Today/This Week fishing activity, awards and per-angler tables. Port of core/daily_leaderboard.py and
// activity_log.format_weight_lb_oz (parity: lures.test.js "leaderboard").
import { parseConditions } from "./calibration.js";
import { addDays, pySum, roundHalfEven } from "./py.js";

const isNum = (v) => typeof v === "number" && Number.isFinite(v);
function pyFloatOrNull(v) {
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return v ? 1 : 0;
  const s = String(v ?? "").trim();
  return /^[+-]?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?$/i.test(s) ? Number(s) : null;
}
function pyIntOrNull(v) {
  if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : null;
  if (typeof v === "boolean") return v ? 1 : 0;
  return /^\s*[+-]?\d+\s*$/.test(String(v)) ? parseInt(v, 10) : null;
}
const fishCount = (f) => { const n = pyIntOrNull(f.count || 1); return n == null ? 1 : Math.max(n, 1); };
const fishWeight = (f) => { const w = pyFloatOrNull(f.weight_lb || 0); return w == null ? 0.0 : w; };

/** 3.53 → "3 lb 8 oz" (nearest ounce); "" for blank/zero/bad */
export function formatWeightLbOz(weight) {
  const w = weight == null || weight === "" ? null : pyFloatOrNull(weight);
  if (w == null || Number.isNaN(w) || w <= 0) return "";
  const total = roundHalfEven(w * 16), lb = Math.floor(total / 16), oz = total % 16;
  if (lb && oz) return `${lb} lb ${oz} oz`;
  return lb ? `${lb} lb` : `${oz} oz`;
}

/** Anglers with a Spot Session open right now. */
export function activeAnglers(rows) {
  const out = new Set();
  for (const row of rows) {
    const c = parseConditions(row);
    if (c.source !== "spot_session") continue;
    const a = (c.angler || "").trim();
    if (!a || c.session_end_time) continue;
    out.add(a);
  }
  return out;
}

export function buildPeriodActivity(rows, startIso, endIso) {
  const active = activeAnglers(rows), stats = new Map();
  const get = (a) => { if (!stats.has(a)) stats.set(a, { angler: a, active: active.has(a), fish_count: 0, total_weight_lb: 0.0, biggest_fish: null, species: new Map() }); return stats.get(a); };
  for (const a of active) get(a);
  const sp = (s, name) => { if (!s.species.has(name)) s.species.set(name, { species: name, count: 0, biggest_weight_lb: 0.0, total_weight_lb: 0.0 }); return s.species.get(name); };
  for (const row of rows) {
    const td = row.trip_date || "";
    if (!(startIso <= td && td <= endIso)) continue;
    const c = parseConditions(row), angler = (c.angler || "").trim();
    if (!angler) continue;
    const s = get(angler), fish = c.fish;
    if (Array.isArray(fish) && fish.length) {
      for (const f of fish) {
        if (!f || typeof f !== "object" || Array.isArray(f)) continue;
        const species = (f.species || "Unspecified").trim() || "Unspecified", count = fishCount(f), weight = fishWeight(f), total = weight * count;
        const x = sp(s, species); x.count += count; x.total_weight_lb += total; if (weight > x.biggest_weight_lb) x.biggest_weight_lb = weight;
        s.fish_count += count; s.total_weight_lb += total;
        if (weight > 0 && (s.biggest_fish == null || weight > s.biggest_fish.weight_lb)) s.biggest_fish = { species, weight_lb: weight };
      }
    } else {
      const fc = pyFloatOrNull(row.fish_caught || 0), n = fc == null || !Number.isFinite(fc) ? 0 : Math.trunc(fc);
      if (n) { const x = sp(s, "Unspecified"); x.count += n; s.fish_count += n; }
      const raw = row.biggest_fish_lb, big = raw == null || raw === "" ? null : pyFloatOrNull(raw);
      if (big && (s.biggest_fish == null || big > s.biggest_fish.weight_lb)) s.biggest_fish = { species: "Unspecified", weight_lb: big };
    }
  }
  return [...stats.values()].sort((a, b) => (a.active === b.active ? 0 : a.active ? -1 : 1) || b.fish_count - a.fish_count || (a.angler.toLowerCase() < b.angler.toLowerCase() ? -1 : a.angler.toLowerCase() > b.angler.toLowerCase() ? 1 : 0));
}
export const speciesSorted = (s) => [...s.species.values()].sort((a, b) => b.count - a.count || (a.species.toLowerCase() < b.species.toLowerCase() ? -1 : a.species.toLowerCase() > b.species.toLowerCase() ? 1 : 0));
export const buildDailyActivity = (rows, today) => buildPeriodActivity(rows, today, today);
/** Sunday–Saturday week containing `today` */
export function weekBounds(today) {
  const dow = new Date(`${today}T00:00:00Z`).getUTCDay(); // 0 = Sunday
  const start = addDays(today, -dow);
  return [start, addDays(start, 6)];
}
export const buildWeeklyActivity = (rows, today) => { const [s, e] = weekBounds(today); return buildPeriodActivity(rows, s, e); };

export function dailyAwards(stats) {
  const withFish = stats.filter((s) => s.fish_count > 0);
  let biggest = null;
  for (const s of withFish) { if (s.biggest_fish == null) continue; if (biggest == null || s.biggest_fish.weight_lb > biggest.weight_lb) biggest = { ...s.biggest_fish, angler: s.angler }; }
  const maxBy = (k) => withFish.reduce((m, s) => (m == null || s[k] > m[k] ? s : m), null);
  return { biggest_fish: biggest, top_angler_weight: maxBy("total_weight_lb"), top_bag_count: maxBy("fish_count") };
}
export const grandTotal = (stats) => ({ fish_count: stats.reduce((a, s) => a + s.fish_count, 0), total_weight_lb: pySum(stats.map((s) => s.total_weight_lb)) });

export function leaderboardTableRows(stats) {
  const rows = [];
  for (const s of stats) {
    if (s.fish_count === 0) continue;
    let first = true;
    for (const x of speciesSorted(s)) {
      rows.push({ Angler: first ? s.angler : "", Species: x.species, "# Fish": x.count, Largest: formatWeightLbOz(x.biggest_weight_lb) || "-", Total: formatWeightLbOz(x.total_weight_lb) || "-" });
      first = false;
    }
    rows.push({ Angler: "Subtotal", Species: "", "# Fish": s.fish_count, Largest: "", Total: formatWeightLbOz(s.total_weight_lb) || "-" });
  }
  const t = grandTotal(stats);
  if (t.fish_count > 0) rows.push({ Angler: "All anglers - total", Species: "", "# Fish": t.fish_count, Largest: "", Total: formatWeightLbOz(t.total_weight_lb) || "-" });
  return rows;
}
export { isNum };
