// Per-group catch stats (punch #104 lure drop-downs on the Leaderboard, #105 My Stats). New app only — no Python
// original. Same row rules as the custom boards (lib/boards.js): a row's fish = its fish list (else fish_caught), its
// hours = lure stint ≥0.5 h when the stint was closed. A "use" = one outing (session) the thing was fished in;
// "success rate" = share of those outings in which it caught at least one fish.
import { parseConditions } from "./calibration.js";
import { lureHours } from "./history.js";
import { formatWeightLbOz } from "./leaderboard.js";
import { LURE_PROFILES } from "./lures.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MIN_STINT = 0.5, UNSPEC = "Unspecified";
const num = (v) => (typeof v === "number" ? (Number.isFinite(v) ? v : null) : v == null || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null);
const intCount = (v) => { const n = parseInt(v || 1, 10); return Number.isFinite(n) && n > 0 ? n : 1; };
const typeName = (k) => (k ? LURE_PROFILES[k]?.name || k : UNSPEC);

/** One normalized record per trip row. */
export function records(rows, spotNames = {}) {
  return (rows || []).map((r) => {
    const c = parseConditions(r), d = String(r.trip_date || "");
    const fish = Array.isArray(c.fish) && c.fish.length
      ? c.fish.filter((f) => f && typeof f === "object" && !Array.isArray(f)).map((f) => ({ species: String(f.species || "").trim() || UNSPEC, count: intCount(f.count), w: num(f.weight_lb), len: num(f.length_in) }))
      : [{ species: UNSPEC, count: Math.max(0, Math.trunc(num(r.fish_caught) || 0)), w: null, len: null }].filter((f) => f.count > 0);
    const t = num(c.water_temp_f), temp = t == null || c.water_temp_unreliable ? null : t;
    return {
      date: d, owner: r.owner || "", angler: String(c.angler || "").trim() || UNSPEC, outing: r.session_id || r.trip_id,
      lure: r.lure_used || (c.lure_category ? typeName(c.lure_category) : UNSPEC), color: String(r.color_used || "").trim() || UNSPEC,
      typeKey: c.lure_category || "", type: typeName(c.lure_category), spot: spotNames[r.spot_id] || r.spot_name || "Unknown location",
      structure: String(r.structure_type || "").trim() || UNSPEC, segment: r.segment || UNSPEC, temp, wind: c.wind_band || UNSPEC,
      hours: c.lure_end_time ? Math.max(lureHours(r), MIN_STINT) : 0, fish,
    };
  });
}

/** Ways to break the log down: [key, label, (record) => [sortKey, label] | null]. */
export const DIMENSIONS = [
  ["lure", "Lure", (x) => [x.lure, x.lure]],
  ["lure_type", "Lure type", (x) => [x.type, x.type]],
  ["color", "Color", (x) => [x.color, x.color]],
  ["spot", "Spot", (x) => [x.spot, x.spot]],
  ["structure", "Structure", (x) => [x.structure, x.structure]],
  ["segment", "Time of day", (x) => [x.segment, x.segment]],
  ["month", "Month", (x) => { const m = +x.date.slice(5, 7); return m ? [String(m).padStart(2, "0"), MONTHS[m - 1]] : null; }],
  ["temp", "Water temp", (x) => { if (x.temp == null) return null; const lo = Math.floor(x.temp / 5) * 5; return [String(lo).padStart(3, "0"), `${lo}–${lo + 4} °F`]; }],
  ["wind", "Wind", (x) => [x.wind, x.wind]],
  ["year", "Year", (x) => (x.date ? [x.date.slice(0, 4), x.date.slice(0, 4)] : null)],
];

const acc = () => ({ fish: 0, lbs: 0, weighed: 0, hours: 0, outings: new Set(), hit: new Set(), big: null, long: null, first: null, last: null, rows: 0 });
function add(a, x) {
  const n = x.fish.reduce((s, f) => s + f.count, 0);
  a.rows += 1; a.fish += n; a.hours += x.hours; a.outings.add(x.outing); if (n > 0) a.hit.add(x.outing);
  for (const f of x.fish) {
    if (f.w > 0) { a.lbs += f.w * f.count; a.weighed += f.count; if (!a.big || f.w > a.big.w) a.big = { ...f, date: x.date, angler: x.angler }; }
    if (f.len > 0 && (!a.long || f.len > a.long.len)) a.long = { ...f, date: x.date, angler: x.angler };
  }
  if (x.date) { if (!a.first || x.date < a.first) a.first = x.date; if (!a.last || x.date > a.last) a.last = x.date; }
}
/** Raw totals → the numbers shown. Also used by the custom boards (they keep their own filtered totals). */
export function derive({ fish, lbs, weighed, hours, uses, usesWithFish, biggest = null, longest = null, first = null, last = null }) {
  return { fish, lbs, weighed, hours, uses, usesWithFish, biggest, longest, first, last,
    lbsPerFish: weighed ? lbs / weighed : null, fishPerHour: hours > 0 ? fish / hours : null,
    fishPerUse: uses ? fish / uses : null, successRate: uses ? usesWithFish / uses : null };
}
const finish = (a) => derive({ fish: a.fish, lbs: a.lbs, weighed: a.weighed, hours: a.hours, uses: a.outings.size, usesWithFish: a.hit.size,
  biggest: a.big, longest: a.long, first: a.first, last: a.last });

/** Stats for a list of records (already filtered). */
export function summarize(recs) { const a = acc(); for (const x of recs) add(a, x); return finish(a); }

/** [{key, label, stats}] for one dimension, most fish first (then fish/hr, then name). */
export function breakdown(recs, dim) {
  const fn = DIMENSIONS.find(([k]) => k === dim)?.[2]; if (!fn) return [];
  const G = new Map();
  for (const x of recs) { const k = fn(x); if (!k) continue; const g = G.get(k[0]) || (G.set(k[0], { key: k[0], label: k[1], a: acc() }), G.get(k[0])); add(g.a, x); }
  const ordered = dim === "month" || dim === "temp" || dim === "year";
  return [...G.values()].map((g) => ({ key: g.key, label: g.label, stats: finish(g.a) }))
    .sort(ordered ? (p, q) => p.key.localeCompare(q.key) : (p, q) => q.stats.fish - p.stats.fish || (q.stats.fishPerHour ?? -1) - (p.stats.fishPerHour ?? -1) || p.label.localeCompare(q.label));
}

/** The stat tiles: [label, value, note?]. */
export function statTiles(s) {
  const pct = s.successRate == null ? "–" : `${Math.round(s.successRate * 100)}%`;
  return [
    ["Fish", String(s.fish)],
    ["Total weight", s.lbs > 0 ? formatWeightLbOz(s.lbs) : "–", s.weighed && s.weighed < s.fish ? `${s.weighed} of ${s.fish} weighed` : null],
    ["Lbs / fish", s.lbsPerFish == null ? "–" : `${s.lbsPerFish.toFixed(2)} lb`],
    ["Fish / hr", s.fishPerHour == null ? "–" : s.fishPerHour.toFixed(2), s.hours > 0 ? `${s.hours.toFixed(1)} h fished` : "no timed stints"],
    ["Fish / use", s.fishPerUse == null ? "–" : s.fishPerUse.toFixed(2), `${s.uses} use${s.uses === 1 ? "" : "s"}`],
    ["Success rate", pct, s.uses ? `${s.usesWithFish} of ${s.uses} with fish` : null],
    ["Biggest", s.biggest ? formatWeightLbOz(s.biggest.w) : "–", s.biggest ? s.biggest.species : null],
    ["Longest", s.longest ? `${s.longest.len.toFixed(1)} in` : "–", s.longest ? s.longest.species : null],
  ];
}
