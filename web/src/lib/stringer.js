// "The Stringer" — the Leaderboard's season highlight reel. Port of core/stringer.py (parity: stringer.test.js vs
// fixtures/stringer.fixtures.json.gz from web/tools/make_stringer_fixtures.py). pandas semantics kept: groupby keys
// come out sorted, descending sorts keep ties in that order (the fixtures force pandas' stable sort to match),
// idxmax = first max, groupby "first" = first non-blank value.
import { parseConditions } from "./calibration.js";
import { formatWeightLbOz } from "./leaderboard.js";
import { LURE_PROFILES } from "./lures.js";
import { pyFixed, pySum } from "./py.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const TOP_N = 10;
const UNSPECIFIED = "Unspecified";

const num = (v) => (typeof v === "number" ? (Number.isFinite(v) ? v : null) : v == null || v === "" ? null
  : /^\s*[+-]?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?\s*$/i.test(String(v)) ? Number(v) : null);
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const sortedKeys = (m) => [...m.keys()].sort(cmp);
/** stable descending sort by f (ties keep their current order — pandas with kind="stable") */
const desc = (arr, f) => arr.map((x, i) => [x, i]).sort((a, b) => f(b[0]) - f(a[0]) || a[1] - b[1]).map(([x]) => x);

/** "Aug 13" (with year when asked: "Aug 13, 2025") */
export function formatDateShort(d, withYear = false) {
  if (!d) return "";
  const [y, m, day] = d.split("-").map(Number);
  return `${MONTHS[m - 1]} ${day}${withYear ? `, ${y}` : ""}`;
}
export const formatWeight = (w) => formatWeightLbOz(w) || "–";

function parseDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s ?? "").trim());
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3] ? m[0] : null;
}
const sessionKey = (row) => { const s = String(row.session_id ?? "").trim(); return s ? `s:${s}` : `t:${row.trip_id}`; };
function pyInt(v) {  // Python int(): whole-number text or number, else null
  if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : null;
  if (typeof v === "boolean") return v ? 1 : 0;
  return /^\s*[+-]?\d+\s*$/.test(String(v)) ? parseInt(v, 10) : null;
}

/** One pass: fish (one per catch record) + trips (one per lure use). */
export function buildFrames(rows, spotNameById = {}) {
  const fish = [], trips = [];
  for (const row of rows) {
    const cond = parseConditions(row);
    const trip_id = row.trip_id ?? null, date = parseDate(row.trip_date);
    const angler = String(cond.angler || "").trim() || UNSPECIFIED;
    const cat = cond.lure_category, catLabel = cat ? LURE_PROFILES[cat]?.name || cat : null;
    const lure = row.lure_used || catLabel || UNSPECIFIED;
    const color = String(row.color_used || "").trim() || UNSPECIFIED;
    const spot = spotNameById[row.spot_id] || row.spot_name || "Unknown location";
    const session_key = sessionKey(row);
    let n = 0;
    if (Array.isArray(cond.fish) && cond.fish.length) {
      for (const f of cond.fish) {
        if (!f || typeof f !== "object" || Array.isArray(f)) continue;
        let count = pyInt(f.count || 1); count = count == null ? 1 : Math.max(count, 1);
        n += count;
        fish.push({ trip_id, date, angler, lure, color, spot, session_key, count,
          species: String(f.species || UNSPECIFIED).trim() || UNSPECIFIED, weight_lb: num(f.weight_lb), length_in: num(f.length_in) });
      }
    } else {
      const v = num(row.fish_caught || 0); n = v == null ? 0 : Math.trunc(v);
    }
    trips.push({ trip_id, date, angler, lure, color, spot, session_key, fish_count: n });
  }
  return { fish, trips };
}

const dateSpan = (trips) => { const d = trips.map((t) => t.date).filter(Boolean).sort(); return d.length ? [d[0], d[d.length - 1], new Set(d).size] : null; };

export function seasonLabel(trips, withYear = false) {
  const s = dateSpan(trips); if (!s) return null;
  const [lo, hi] = s, yr = withYear && lo.slice(0, 4) !== hi.slice(0, 4);
  return lo === hi ? formatDateShort(lo, withYear) : `${formatDateShort(lo, yr)} – ${formatDateShort(hi, yr)}`;
}
const joinNames = (n) => (!n.length ? "" : n.length === 1 ? n[0] : `${n.slice(0, -1).join(", ")} & ${n[n.length - 1]}`);
function sumBy(rows, key, val = (r) => r.count) {
  const m = new Map();
  for (const r of rows) m.set(key(r), (m.get(key(r)) || 0) + val(r));
  return m;
}
const daysBetween = (lo, hi) => Math.round((Date.parse(`${hi}T00:00:00Z`) - Date.parse(`${lo}T00:00:00Z`)) / 864e5);

/** The ring's cyclable stats: days on the water, top-spot share, top-species share (each only when the data is there). */
export function heroStates(fish, trips, withYear = false) {
  const out = [], s = dateSpan(trips);
  if (s) {
    const [lo, hi, distinct] = s, total = daysBetween(lo, hi) + 1;
    out.push({ title: "Days on the Water", legend: "Days fished", value: distinct, total,
      desc: `${distinct} of ${total} days, ${seasonLabel(trips, withYear) || ""}`, sec_label: "Trips logged", sec_value: String(trips.length) });
  }
  if (fish.length) {
    const bySpot = sumBy(fish, (f) => f.spot), spots = sortedKeys(bySpot);
    const totalFish = [...bySpot.values()].reduce((a, b) => a + b, 0);
    if (totalFish > 0) {
      let top = spots[0]; for (const k of spots) if (bySpot.get(k) > bySpot.get(top)) top = k;
      const w = fish.filter((f) => f.spot === top && f.weight_lb != null).map((f) => f.weight_lb);
      out.push({ title: `${top} Share`, legend: "Catches there", value: bySpot.get(top), total: totalFish,
        desc: `${bySpot.get(top)} of ${totalFish} catches this season`, sec_label: "Best fish landed there", sec_value: w.length ? formatWeight(Math.max(...w)) : "–" });
    }
    const bySp = sumBy(fish, (f) => f.species), sp = desc(sortedKeys(bySp), (k) => bySp.get(k));
    if (totalFish > 0) {
      const rest = sp.slice(1, 4);
      out.push({ title: `${sp[0]} Share`, legend: "Of all catches", value: bySp.get(sp[0]), total: totalFish,
        desc: `${bySp.get(sp[0])} of ${totalFish}${rest.length ? ` — rest are ${joinNames(rest)}` : ""}`, sec_label: "Species logged", sec_value: String(sp.length) });
    }
  }
  return out;
}

const row = (primary, secondary, n, tag = null) => ({ primary, secondary, num: n, tag });

export function biggestFish(fish) {
  return desc(fish.filter((f) => f.weight_lb != null), (f) => f.weight_lb).slice(0, TOP_N)
    .map((f) => row(formatWeight(f.weight_lb), `${f.species} · ${f.lure} · ${f.spot} · ${f.angler} · ${formatDateShort(f.date)}`, formatWeight(f.weight_lb)));
}
export function longestFish(fish) {
  return desc(fish.filter((f) => f.length_in != null), (f) => f.length_in).slice(0, TOP_N)
    .map((f) => row(f.weight_lb != null ? `${f.species} · ${formatWeight(f.weight_lb)}` : f.species,
      `${f.lure} · ${f.spot} · ${f.angler} · ${formatDateShort(f.date)}`, `${pyFixed(f.length_in, 1)} in`));
}
export function topAnglers(fish) {
  if (!fish.length) return [];
  const g = new Map();
  for (const f of fish) { const e = g.get(f.angler) || { c: 0, w: [] }; e.c += f.count; e.w.push((f.weight_lb ?? 0) * f.count); g.set(f.angler, e); }
  return desc(sortedKeys(g), (k) => g.get(k).c).slice(0, TOP_N).map((a) => {
    const { c } = g.get(a), w = pySum(g.get(a).w);
    return row(a, w > 0 ? `${formatWeight(w)} total · ${pyFixed(w / c, 2)} lb avg` : `${c} fish logged, no weight data yet`, `${c} fish`);
  });
}
export function hotLures(fish, trips) {
  if (!fish.length || !trips.length) return [];
  const k = (r) => JSON.stringify([r.lure, r.color]);
  const counts = sumBy(fish, k), uses = sumBy(trips.filter((t) => t.trip_id != null), k, () => 1);
  for (const t of trips) if (!uses.has(k(t))) uses.set(k(t), 0);
  const keys = sortedKeys(new Map([...counts, ...uses])).filter((x) => counts.has(x) && uses.has(x) && counts.get(x) > 0);
  const lk = (x) => JSON.parse(x);
  keys.sort((a, b) => { const [la, ca] = lk(a), [lb, cb] = lk(b); return cmp(la, lb) || cmp(ca, cb); });
  return desc(keys, (x) => counts.get(x)).slice(0, TOP_N).map((x) => {
    const [lure, color] = lk(x), u = uses.get(x), rate = u ? counts.get(x) / u : 0;
    return row(lure, `${color} · ${u} use${u === 1 ? "" : "s"} · ${pyFixed(rate, 2)} / use`, `${counts.get(x)} fish`, u < 3 ? `${u} use sample` : null);
  });
}
export function topSpots(fish) {
  if (!fish.length) return [];
  const totals = sumBy(fish, (f) => f.spot), best = new Map();
  for (const f of fish) if (f.weight_lb != null && (!best.has(f.spot) || f.weight_lb > best.get(f.spot).weight_lb)) best.set(f.spot, f);
  return desc(sortedKeys(best), (s) => best.get(s).weight_lb).slice(0, TOP_N)
    .map((s) => row(s, `${totals.get(s) || 0} fish landed here · best by ${best.get(s).angler}`, formatWeight(best.get(s).weight_lb)));
}
export function topSessions(trips) {
  const g = new Map();
  for (const t of trips) {
    const e = g.get(t.session_key) || { total: 0, date: null, spot: null, angler: null };
    e.total += t.fish_count; e.date ??= t.date; e.spot ??= t.spot; e.angler ??= t.angler; g.set(t.session_key, e);
  }
  return desc(sortedKeys(g).filter((k) => g.get(k).total > 0), (k) => g.get(k).total).slice(0, TOP_N).map((k) => {
    const e = g.get(k);
    return row(e.date ? `${formatDateShort(e.date)} outing` : "Undated outing", `${e.spot} · ${e.angler}`, `${e.total} fish`);
  });
}

export const CATEGORIES = [
  ["biggest", "Biggest Fish", "sorted by weight", (f) => biggestFish(f)],
  ["anglers", "Top Anglers", "sorted by fish caught", (f) => topAnglers(f)],
  ["lures", "Hot Lures", "sorted by fish caught", (f, t) => hotLures(f, t)],
  ["spots", "Top Spots", "sorted by biggest fish", (f) => topSpots(f)],
  ["longest", "Longest Fish", "sorted by length", (f) => longestFish(f)],
  ["sessions", "Top Sessions", "sorted by fish per outing", (f, t) => topSessions(t)],
];

/** [date, fish that day] for every calendar day lo..hi (zero-filled). */
export function dailyActivitySeries(fish, lo, hi) {
  if (!lo || !hi) return [];
  const tot = sumBy(fish.filter((f) => f.date), (f) => f.date), out = [];
  for (let t = Date.parse(`${lo}T00:00:00Z`), end = Date.parse(`${hi}T00:00:00Z`); t <= end; t += 864e5) {
    const d = new Date(t).toISOString().slice(0, 10); out.push([d, tot.get(d) || 0]);
  }
  return out;
}
export function speciesMix(fish, topN = 5) {
  const g = sumBy(fish, (f) => f.species);
  return desc(sortedKeys(g), (k) => g.get(k)).slice(0, topN).map((k) => [k, g.get(k)]);
}
