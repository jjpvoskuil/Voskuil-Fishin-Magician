// Custom leaderboards (John 11-11): Measure × Ranked by × Filters, computed from the trip log on the phone.
// A typed question ("most lbs of bass caught on a jerkbait") is turned into the same spec by the fm-board-ask Edge
// Function (Claude) — it only picks the settings; every number here comes from the trip log.
import { parseConditions } from "./calibration.js";
import { lureHours } from "./history.js";
import { formatWeightLbOz } from "./leaderboard.js";
import { LURE_PROFILES } from "./lures.js";
import { SEGMENTS } from "./scoring.js";

export const MEASURES = [["fish", "Fish caught"], ["lbs", "Total weight"], ["biggest", "Biggest fish"], ["longest", "Longest fish"],
  ["avg_weight", "Average weight"], ["fish_per_hour", "Fish per hour"], ["outings", "Outings"]];
export const GROUPS = [["angler", "Angler"], ["lure", "Lure"], ["lure_type", "Lure type"], ["color", "Color"], ["spot", "Spot"],
  ["month", "Month"], ["segment", "Time of day"], ["species", "Species"], ["year", "Year"], ["outing", "Outing"], ["fish", "Each fish"], ["none", "Everything together"]];
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export { SEGMENTS };
const MIN_STINT = 0.5, MAX_ROWS = 25, UNSPEC = "Unspecified";
const BLACK_BASS = /largemouth|smallmouth|spotted|kentucky|^bass$/i;

const num = (v) => (typeof v === "number" ? (Number.isFinite(v) ? v : null) : v == null || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null);
const intCount = (v) => { const n = parseInt(v || 1, 10); return Number.isFinite(n) && n > 0 ? n : 1; };
const typeName = (k) => (k ? LURE_PROFILES[k]?.name || k : UNSPEC);
const md = (d) => (d ? `${MONTHS[+d.slice(5, 7) - 1]} ${+d.slice(8, 10)}, ${d.slice(0, 4)}` : "");
const lbs = (w) => formatWeightLbOz(w) || "–";

/** A spec from anywhere (saved board, Claude) cut down to known values. */
export function cleanSpec(s = {}, choices = {}) {
  const one = (v, list, d) => (list.some(([k]) => k === v) ? v : d);
  const strs = (v, allowed) => (Array.isArray(v) ? v.map(String).filter((x) => !allowed || allowed.includes(x)).slice(0, 40) : []);
  const t = (v) => { const n = num(v); return n == null ? null : Math.max(30, Math.min(100, n)); };
  const date = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(String(v || "")) ? v : "");
  const out = {
    title: String(s.title || "").slice(0, 80), measure: one(s.measure, MEASURES, "fish"), by: one(s.by, GROUPS, "angler"),
    species: strs(s.species, choices.species), lure_types: strs(s.lure_types, Object.keys(LURE_PROFILES)), spots: strs(s.spots, choices.spots),
    anglers: strs(s.anglers, choices.anglers), segments: strs(s.segments, SEGMENTS),
    months: (Array.isArray(s.months) ? s.months : []).map(Number).filter((m) => m >= 1 && m <= 12),
    temp_min: t(s.temp_min), temp_max: t(s.temp_max), lure_text: String(s.lure_text || "").slice(0, 40), color_text: String(s.color_text || "").slice(0, 40),
    from: date(s.from), to: date(s.to), period: ["year", "30", "all"].includes(s.period) ? s.period : "", who: ["all", "me"].includes(s.who) ? s.who : "",
  };
  if (out.by === "fish" && !["biggest", "longest"].includes(out.measure)) out.by = "none";
  if (out.by === "species" && out.measure === "fish_per_hour") out.measure = "fish";
  return out;
}

/** The values the filters can pick from, taken from the trip log. */
export function choicesFrom(rows, spotNames = {}) {
  const sp = new Set(), an = new Set(), sl = new Set(), types = new Set();
  for (const r of rows || []) {
    const c = parseConditions(r);
    an.add(String(c.angler || "").trim() || UNSPEC);
    sl.add(spotNames[r.spot_id] || r.spot_name || "Unknown location");
    if (c.lure_category && LURE_PROFILES[c.lure_category]) types.add(c.lure_category);
    if (Array.isArray(c.fish)) for (const f of c.fish) if (f && typeof f === "object") sp.add(String(f.species || "").trim() || UNSPEC);
  }
  const s = (x) => [...x].sort((a, b) => a.localeCompare(b));
  return { species: s(sp), anglers: s(an), spots: s(sl), lure_types: s(types).map((k) => [k, typeName(k)]) };
}
export const blackBass = (species) => species.filter((s) => BLACK_BASS.test(s));

/** Rows for a spec: [{primary, secondary, num, tag}] best first, plus totals. rows = already cut to period / angler. */
export function runBoard(rows, spec, spotNames = {}) {
  const sp = new Set(spec.species), lt = new Set(spec.lure_types), sl = new Set(spec.spots), an = new Set(spec.anglers), sg = new Set(spec.segments), mo = new Set(spec.months);
  const lureQ = spec.lure_text.trim().toLowerCase(), colorQ = spec.color_text.trim().toLowerCase();
  const G = new Map(), fishRows = [];
  let total = { fish: 0, trips: 0 };
  const grp = (key, label) => G.get(key) || (G.set(key, { label, fish: 0, w: 0, weighed: 0, big: null, long: null, hours: 0, outings: new Set(), trips: 0, sub: new Map() }), G.get(key));
  for (const r of rows || []) {
    const c = parseConditions(r), d = String(r.trip_date || "");
    if (spec.from && d < spec.from) continue;
    if (spec.to && d > spec.to) continue;
    const angler = String(c.angler || "").trim() || UNSPEC, spot = spotNames[r.spot_id] || r.spot_name || "Unknown location";
    const type = typeName(c.lure_category), lure = r.lure_used || (c.lure_category ? type : UNSPEC), color = String(r.color_used || "").trim() || UNSPEC;
    if (lt.size && !lt.has(c.lure_category)) continue;
    if (sl.size && !sl.has(spot)) continue;
    if (an.size && !an.has(angler)) continue;
    if (sg.size && !sg.has(r.segment)) continue;
    if (mo.size && !mo.has(+d.slice(5, 7))) continue;
    if (lureQ && !`${lure} ${type}`.toLowerCase().includes(lureQ)) continue;
    if (colorQ && !color.toLowerCase().includes(colorQ)) continue;
    if (spec.temp_min != null || spec.temp_max != null) {
      const t = num(c.water_temp_f);
      if (t == null || c.water_temp_unreliable || (spec.temp_min != null && t < spec.temp_min) || (spec.temp_max != null && t > spec.temp_max)) continue;
    }
    // the fish on this row that pass the species filter (old rows without a fish list only count with no species filter)
    let fish = Array.isArray(c.fish) && c.fish.length
      ? c.fish.filter((f) => f && typeof f === "object" && !Array.isArray(f)).map((f) => ({ species: String(f.species || "").trim() || UNSPEC, count: intCount(f.count), w: num(f.weight_lb), len: num(f.length_in) }))
      : (sp.size ? [] : [{ species: UNSPEC, count: Math.max(0, Math.trunc(num(r.fish_caught) || 0)), w: null, len: null }].filter((f) => f.count > 0));
    if (sp.size) fish = fish.filter((f) => sp.has(f.species));
    const hours = c.lure_end_time ? Math.max(lureHours(r), MIN_STINT) : 0, outing = r.session_id || r.trip_id;
    const ctx = { date: d, angler, spot, lure, color, type };
    const keyOf = (f) => {
      switch (spec.by) {
        case "angler": return [angler, angler]; case "lure": return [lure, lure]; case "lure_type": return [type, type];
        case "color": return [color, color]; case "spot": return [spot, spot]; case "segment": return [r.segment || UNSPEC, r.segment || UNSPEC];
        case "month": { const m = +d.slice(5, 7); return m ? [String(m).padStart(2, "0"), MONTHS[m - 1]] : ["99", "Undated"]; }
        case "year": return [d.slice(0, 4) || "Undated", d.slice(0, 4) || "Undated"];
        case "outing": return [outing, `${md(d) || "Undated"} · ${spot}`];
        case "species": return [f ? f.species : UNSPEC, f ? f.species : UNSPEC];
        default: return ["all", "Everything"];
      }
    };
    total.trips += 1;
    const touched = new Set();
    for (const f of fish) {
      total.fish += f.count;
      if (spec.by === "fish") { fishRows.push({ ...f, ...ctx }); continue; }
      const [k, label] = keyOf(f), g = grp(k, label);
      g.fish += f.count; if (f.w > 0) { g.w += f.w * f.count; g.weighed += f.count; }
      if (f.w > 0 && (!g.big || f.w > g.big.w)) g.big = { ...f, ...ctx };
      if (f.len > 0 && (!g.long || f.len > g.long.len)) g.long = { ...f, ...ctx };
      if (spec.by === "outing") g.sub.set(angler, true);
      if (!touched.has(k)) { touched.add(k); g.hours += hours; g.trips += 1; g.outings.add(outing); }
    }
    if (spec.by !== "species" && spec.by !== "fish") {  // trips with no (matching) fish still count their hours and outing
      const [k, label] = keyOf(null);
      if (!touched.has(k)) {
        const g = grp(k, label); g.hours += hours; g.trips += 1; g.outings.add(outing); if (spec.by === "outing") g.sub.set(angler, true);
      }
    }
  }

  const fishLine = (f) => [f.species, f.lure, f.spot, f.angler, md(f.date)].filter(Boolean).join(" · ");
  if (spec.by === "fish") {
    const key = spec.measure === "longest" ? "len" : "w";
    const list = fishRows.filter((f) => f[key] > 0).sort((a, b) => b[key] - a[key]).slice(0, MAX_ROWS);
    return { rows: list.map((f) => ({ primary: f.species, secondary: fishLine(f).split(" · ").slice(1).join(" · "), num: key === "len" ? `${f.len.toFixed(1)} in` : lbs(f.w), tag: null })), total };
  }
  const val = { fish: (g) => g.fish, lbs: (g) => g.w, biggest: (g) => g.big?.w ?? -1, longest: (g) => g.long?.len ?? -1,
    avg_weight: (g) => (g.weighed ? g.w / g.weighed : -1), fish_per_hour: (g) => (g.hours > 0 ? g.fish / g.hours : -1), outings: (g) => g.outings.size }[spec.measure];
  const list = [...G.values()].filter((g) => val(g) > 0 || (spec.measure === "fish_per_hour" && g.hours > 0))
    .sort((a, b) => val(b) - val(a) || b.fish - a.fish || a.label.localeCompare(b.label)).slice(0, MAX_ROWS);
  const out = list.map((g) => {
    const extra = spec.by === "outing" ? ` · ${[...g.sub.keys()].join(", ")}` : "";
    switch (spec.measure) {
      case "lbs": return { primary: g.label, secondary: `${g.fish} fish · ${g.weighed} weighed${extra}`, num: lbs(g.w), tag: null };
      case "biggest": return { primary: g.label, secondary: fishLine(g.big), num: lbs(g.big.w), tag: null };
      case "longest": return { primary: g.label, secondary: fishLine(g.long), num: `${g.long.len.toFixed(1)} in`, tag: null };
      case "avg_weight": return { primary: g.label, secondary: `${g.weighed} weighed fish · ${lbs(g.w)} total${extra}`, num: `${(g.w / g.weighed).toFixed(2)} lb`, tag: g.weighed < 3 ? "small sample" : null };
      case "fish_per_hour": return { primary: g.label, secondary: `${g.fish} fish in ${g.hours.toFixed(1)} h${extra}`, num: `${(g.fish / g.hours).toFixed(2)} / hr`, tag: g.hours < 2 ? "under 2 h" : null };
      case "outings": return { primary: g.label, secondary: `${g.fish} fish · ${g.hours.toFixed(1)} h${extra}`, num: `${g.outings.size} outing${g.outings.size === 1 ? "" : "s"}`, tag: null };
      default: return { primary: g.label, secondary: `${g.w > 0 ? `${lbs(g.w)} · ` : ""}${g.outings.size} outing${g.outings.size === 1 ? "" : "s"}${extra}`, num: `${g.fish} fish`, tag: null };
    }
  });
  return { rows: out, total };
}

/** Plain-words summary of a spec, e.g. "Total weight by Angler · Largemouth, Spotted · Suspending Jerkbait". */
export function describeSpec(s) {
  const name = (list, k) => list.find(([x]) => x === k)?.[1] || k;
  const bits = [];
  if (s.species.length) bits.push(s.species.join(", "));
  if (s.lure_types.length) bits.push(s.lure_types.map(typeName).join(", "));
  if (s.lure_text.trim()) bits.push(`lure "${s.lure_text.trim()}"`);
  if (s.color_text.trim()) bits.push(`color "${s.color_text.trim()}"`);
  if (s.spots.length) bits.push(s.spots.join(", "));
  if (s.anglers.length) bits.push(s.anglers.join(", "));
  if (s.segments.length) bits.push(s.segments.join(", "));
  if (s.months.length) bits.push(s.months.map((m) => MONTHS[m - 1]).join(", "));
  if (s.temp_min != null || s.temp_max != null) bits.push(`water ${s.temp_min ?? "any"}–${s.temp_max ?? "any"} °F`);
  if (s.from || s.to) bits.push(`${s.from || "start"} to ${s.to || "now"}`);
  const head = s.by === "none" ? name(MEASURES, s.measure) : `${name(MEASURES, s.measure)} by ${name(GROUPS, s.by).toLowerCase()}`;
  return [head, ...bits].join(" · ");
}
