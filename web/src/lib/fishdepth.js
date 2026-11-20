// Reports → "Fish depth" + the depth lure advice uses when nobody has entered one (John 11-20). New app only.
// Marked depth = the fish depth logged on an outing (median of its rows; not when the boat was stored or flagged
// unreliable). Bands are 3 ft wide. expectedDepth() = where fish were marked on PRODUCTIVE outings in conditions
// like the ones asked about: each outing weighted by water temp (σ 6 °F), time of year (σ 21 days, any year), same
// lake phase ×1 / other ×0.25, times its fish/hr; weighted median; needs ≥4 similar outings; kept above the
// day's oxygen floor.
import { conditionedOutings } from "./wheretofish.js";
import { PHASE_LABEL } from "./lakectx.js";

export const DEPTH_BANDS = [[0, 6, "6 ft or less"], [6, 9, "7–9 ft"], [9, 12, "10–12 ft"], [12, 15, "13–15 ft"], [15, 999, "16 ft +"]];
const bandOf = (d) => DEPTH_BANDS.find(([a, b]) => d > a && d <= b) || DEPTH_BANDS[0];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor((s.length - 1) / 2)] : null; };
const doy = (iso) => (Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) - Date.UTC(+iso.slice(0, 4), 0, 1)) / 864e5;

const rateRows = (list) => DEPTH_BANDS.map(([a, , label]) => {
  const g = list.filter((o) => bandOf(o.fish_depth)[0] === a), h = g.reduce((s, o) => s + o.hours, 0), f = g.reduce((s, o) => s + o.fish, 0);
  return { key: String(a), label, outings: g.length, hours: h, fish: f, rate: h >= 0.5 ? f / h : null };
});

/** Report: {marked, byBand, byMonth: [{month, label, outings, median, best, floor}], byTemp, byPhase} */
export function fishDepth(trips, ctx, { from = "", to = "", owner = null, spots = null } = {}) {
  const list = conditionedOutings(trips, ctx, { from, to, owner }, spots).filter((o) => o.fish_depth != null);
  const best = (g) => rateRows(g).filter((b) => b.outings >= 3 && b.rate != null).sort((a, b) => b.rate - a.rate)[0] || null;
  const group = (keyOf, order) => { const by = new Map(); for (const o of list) { const k = keyOf(o); if (k == null) continue; (by.get(k) || by.set(k, []).get(k)).push(o); }
    return [...by.entries()].sort((a, b) => order(a[0], b[0])).map(([k, g]) => {
      const fl = g.map((o) => o.floor).filter((x) => x != null);
      return { key: k, outings: g.length, median: median(g.map((o) => o.fish_depth)), best: best(g), floor: fl.length ? median(fl) : null, catchMedian: median(g.filter((o) => o.fish > 0).map((o) => o.fish_depth)) };
    }); };
  const byMonth = group((o) => +o.date.slice(5, 7), (a, b) => a - b).map((m) => ({ ...m, label: MON[m.key - 1] }));
  const tOrder = ["Under 50 °F", "50–60 °F", "60–70 °F", "70–75 °F", "75–80 °F", "80–85 °F", "85 °F +"];
  const byTemp = group((o) => o.band, (a, b) => tOrder.indexOf(a) - tOrder.indexOf(b)).map((m) => ({ ...m, label: m.key }));
  const byPhase = group((o) => o.phase, (a, b) => a.localeCompare(b)).map((m) => ({ ...m, label: PHASE_LABEL[m.key] || m.key }));
  return { marked: list.length, byBand: rateRows(list), byMonth, byTemp, byPhase };
}

/** Where fish were marked on productive outings in similar conditions → {depth_ft, n, label} or null.
 *  at = {date, tempF?, phase?, floorFt?} */
export function expectedDepth(trips, ctx, at, { owner = null } = {}) {
  const list = conditionedOutings(trips, ctx, { owner }).filter((o) => o.fish_depth != null && o.date < at.date);
  const phase = at.phase || ctx.on(at.date).phase, t0 = doy(at.date);
  const w = [];
  for (const o of list) {
    let k = o.phase === phase ? 1 : 0.25;
    const dd = Math.abs(doy(o.date) - t0), d = Math.min(dd, 365 - dd); k *= Math.exp(-0.5 * (d / 21) ** 2);
    if (at.tempF != null && o.temp != null) k *= Math.exp(-0.5 * ((o.temp - at.tempF) / 6) ** 2);
    if (k < 0.05) continue;
    w.push({ o, k, kr: k * (o.fish / o.hours) });
  }
  const similar = w.reduce((s, x) => s + x.k, 0);
  if (w.length < 4 || similar < 3) return null;
  const pts = w.filter((x) => x.kr > 0).sort((a, b) => a.o.fish_depth - b.o.fish_depth), tot = pts.reduce((s, x) => s + x.kr, 0);
  if (!pts.length) return null;
  let acc = 0, depth = pts[pts.length - 1].o.fish_depth;
  for (const x of pts) { acc += x.kr; if (acc >= tot / 2) { depth = x.o.fish_depth; break; } }
  let capped = false;
  if (at.floorFt != null && depth > at.floorFt - 1) { depth = Math.max(3, Math.round(at.floorFt - 1)); capped = true; }
  return { depth_ft: Math.round(depth), n: w.length, similar: Math.round(similar), capped,
    label: `Your log: fish marked around ${Math.round(depth)} ft on good outings in conditions like these (${w.length} similar outings${capped ? ", kept above today's oxygen floor" : ""}).` };
}

/** Lure plan text says "you're marking" for an entered depth; for the log's depth say so instead. */
export function relabelDepth(rec) {
  const fix = (s) => s.replace(/You're marking fish/g, "Your log puts fish").replace(/you're marking fish/g, "your log puts fish").replace(/you're marking/g, "your log expects");
  const walk = (v) => (typeof v === "string" ? fix(v) : Array.isArray(v) ? v.map(walk) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)])) : v);
  return rec ? walk(rec) : rec;
}

/** A lure plan built with the log's depth: relabeled, with the "why" line first. */
export function withLogDepth(rec, exp) {
  if (!rec || !exp) return rec;
  const r = relabelDepth(rec);
  return { ...r, rationale: [exp.label, ...r.rationale] };
}
