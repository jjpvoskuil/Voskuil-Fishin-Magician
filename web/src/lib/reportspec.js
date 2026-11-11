// Report settings (stock, saved, or picked by Claude from a typed request) → rows via lib/reports.js.
// Spec = {title, factor, metric, species, from, to, period, who, anglers, segments, lure_types, spots, tempWidth, secchiWidth}.
import { LURE_PROFILES } from "./lures.js";
import { buildReportsData, computeReport, FACTORS, METRICS, SECCHI_BUCKET, SPECIES_METRICS, WATER_TEMP_BUCKET } from "./reports.js";
import { SEGMENTS } from "./scoring.js";

export const STOCK = [
  { id: "segment", title: "Best time of day", factor: "segment", metric: "fish_per_hour" },
  { id: "pressure", title: "Pressure trend", factor: "pressure_trend_band", metric: "fish_per_hour" },
  { id: "moon", title: "Moon (night before)", factor: "moon_illumination_bin", metric: "fish_per_hour" },
  { id: "temp", title: "Water temperature", factor: WATER_TEMP_BUCKET, metric: "fish_per_hour", tempWidth: 2 },
  { id: "sky", title: "Sky", factor: "light_condition", metric: "fish_per_hour" },
  { id: "wind", title: "Wind", factor: "wind_band", metric: "fish_per_hour" },
  { id: "lure_type", title: "Lure types", factor: "lure_category", metric: "total_fish" },
  { id: "color", title: "Colors", factor: "color", metric: "total_fish" },
  { id: "spot", title: "Spots", factor: "spot", metric: "fish_per_hour" },
  { id: "weekly", title: "Fish by week", factor: "week_start", metric: "total_fish" },
];
const FK = FACTORS.map(([k]) => k), MK = METRICS.map(([k]) => k);
export const factorName = (k) => FACTORS.find(([x]) => x === k)?.[1] || k;
export const metricName = (k) => METRICS.find(([x]) => x === k)?.[1] || k;

export function cleanReportSpec(s = {}, choices = {}) {
  const strs = (v, allowed) => (Array.isArray(v) ? v.map(String).filter((x) => !allowed || allowed.includes(x)).slice(0, 40) : []);
  const date = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(String(v || "")) ? v : "");
  const w = (v, lo, hi, d) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? Math.max(lo, Math.min(hi, n)) : d; };
  const out = {
    title: String(s.title || "").slice(0, 80), factor: FK.includes(s.factor) ? s.factor : "segment", metric: MK.includes(s.metric) ? s.metric : "fish_per_hour",
    species: choices.species?.includes(s.species) ? s.species : "", from: date(s.from), to: date(s.to),
    period: ["year", "90", "30", "all"].includes(s.period) ? s.period : "", who: ["all", "me"].includes(s.who) ? s.who : "",
    anglers: strs(s.anglers, choices.anglers), segments: strs(s.segments, SEGMENTS), lure_types: strs(s.lure_types, Object.keys(LURE_PROFILES)),
    spots: strs(s.spots, choices.spots), tempWidth: w(s.tempWidth, 0.5, 10, 2), secchiWidth: w(s.secchiWidth, 0.25, 5, 0.5),
  };
  if (!SPECIES_METRICS.has(out.metric)) out.species = "";
  return out;
}

const lakeToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
const minus = (d, n) => new Date(Date.parse(`${d}T12:00:00Z`) - n * 864e5).toISOString().slice(0, 10);
/** The date window a spec covers: its own from/to, else its period, else the screen's period. */
export function windowFor(spec, screenPeriod, today = lakeToday()) {
  if (spec.from || spec.to) return { from: spec.from, to: spec.to || today };
  const p = spec.period || screenPeriod;
  if (p === "all") return { from: "", to: today };
  return { from: p === "year" ? `${today.slice(0, 4)}-01-01` : minus(today, (p === "90" ? 90 : 30) - 1), to: today };
}

/** rows (trip log) → {rows: [{key, label, value, n, text}], data} for a spec. who/me cut by owner; lure types + spots are
 *  new-app filters applied to the trips first; the rest goes to computeReport exactly like the old page. */
export function runReport(trips, spec, { screenPeriod = "year", screenWho = "all", me = "", today } = {}) {
  const who = spec.who || screenWho, win = windowFor(spec, screenPeriod, today);
  const rows = (trips || []).filter((r) => (who !== "me" || r.owner === me));
  let data = buildReportsData(rows);
  if (spec.lure_types.length || spec.spots.length) {
    const keep = (r) => (!spec.lure_types.length || spec.lure_types.includes(r._lure_type_key)) && (!spec.spots.length || spec.spots.includes(r.spot));
    data = { trips: data.trips.filter(keep), fish: data.fish.filter(keep) };
  }
  const out = computeReport(data, spec.factor, spec.metric, { species: spec.species || null, from: win.from, to: win.to,
    anglers: spec.anglers, segments: spec.segments, tempWidth: spec.tempWidth, secchiWidth: spec.secchiWidth, today: today || lakeToday() });
  const label = (k) => (spec.factor === "date" || spec.factor === "week_start" ? shortDate(k, spec.factor === "week_start") : k);
  return { rows: out.map((r) => ({ ...r, label: label(r.key), text: fmtValue(spec.metric, r.value, r.n) })), data, win };
}
const M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const shortDate = (d, wk) => `${wk ? "Wk of " : ""}${M[+d.slice(5, 7) - 1]} ${+d.slice(8, 10)}`;
export function fmtValue(metric, v, n) {
  if (!n) return "–";
  if (metric === "fish_per_hour") return `${v.toFixed(2)}/hr`;
  if (metric === "biggest_fish" || metric === "average_fish_weight") return `${v.toFixed(2)} lb`;
  return String(Math.round(v));
}
/** What n counts, for the table header. */
export const nName = (metric) => (["fish_per_hour", "trip_count"].includes(metric) || (metric === "total_fish") ? "trips" : "fish");

export function describeReport(s, typeNames = {}) {
  const bits = [`${metricName(s.metric)} by ${factorName(s.factor).toLowerCase()}`];
  if (s.factor === WATER_TEMP_BUCKET) bits.push(`${s.tempWidth}° steps`);
  if (s.factor === SECCHI_BUCKET) bits.push(`${s.secchiWidth} ft steps`);
  if (s.species) bits.push(s.species);
  if (s.lure_types.length) bits.push(s.lure_types.map((k) => typeNames[k] || LURE_PROFILES[k]?.name || k).join(", "));
  if (s.spots.length) bits.push(s.spots.join(", "));
  if (s.anglers.length) bits.push(s.anglers.join(", "));
  if (s.segments.length) bits.push(s.segments.join(", "));
  if (s.from || s.to) bits.push(`${s.from || "start"} to ${s.to || "now"}`);
  return bits.join(" · ");
}
