// Reports engine: port of core/reports.py (parity: reports.test.js vs fixtures/reports.fixtures.json.gz from
// web/tools/make_report_fixtures.py). Any factor × any metric over filtered trips, plus the two history-lookup
// "predictions" (moon illumination the night before, forecast pressure trend). pandas semantics kept: rows whose
// factor is blank (None) drop out of the grouping; ordered factors show every value in their fixed order (values
// outside that list drop out); date factors show every day/week of the range; others sort by value, ties in key order.
import { moonPhase } from "./astro.js";
import { MAX_TRUSTED_SESSION_HOURS, MIN_SAMPLES_PER_SIDE, MIN_TRUSTED_SESSION_HOURS, parseConditions } from "./calibration.js";
import { weekBounds } from "./leaderboard.js";
import { LURE_PROFILES } from "./lures.js";
import { LIGHT_CONDITIONS, WATER_TEMP_BANDS, WIND_BAND_LABELS, waterTempBand } from "./onwater.js";
import { addDays, dayOfYear, dt, parseIso, pyRound, pySum } from "./py.js";
import { SEGMENTS, seasonStage } from "./scoring.js";
import { pressureTrendHpaPer24h } from "./weather.js";

export const PRESSURE_TREND_BANDS = ["Falling", "Steady", "Rising / High"];
export const MOON_BIN_WIDTH = 10;
export const MOON_BIN_ORDER = Array.from({ length: 10 }, (_, i) => `${i * 10}-${i * 10 + 10}%`);
export const WATER_TEMP_BUCKET = "water_temp_bucket", SECCHI_BUCKET = "secchi_bucket";
export const DEFAULT_TEMP_WIDTH = 2.0, DEFAULT_SECCHI_WIDTH = 0.5;
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export const FACTORS = [
  ["spot", "Spot"], ["structure_type", "Structure type"], ["water_color", "Water color (green / brown stain)"],
  [SECCHI_BUCKET, "Water clarity (Secchi ft, custom range)"], ["water_clarity", "Water clarity + color (as logged)"],
  ["lure", "Lure"], ["lure_category", "Lure type"], ["color", "Color"], ["technique", "Technique"], ["segment", "Time of day"],
  ["season", "Season"], ["light_condition", "Sky"], ["wind_band", "Wind"], ["wind_direction", "Wind direction"],
  ["precipitation", "Precipitation"], ["water_temp_band", "Water temp band"], [WATER_TEMP_BUCKET, "Water temp (custom range)"],
  ["pressure_trend_band", "Pressure trend"], ["moon_illumination_bin", "Moon % (night before)"], ["fish_activity", "Fish activity (reported)"],
  ["forage_activity", "Forage activity (reported)"], ["angler", "Angler"], ["day_of_week", "Day of week"], ["date", "Date (daily)"],
  ["week_start", "Date (weekly, Sun–Sat)"],
];
export const METRICS = [["total_fish", "Total fish caught"], ["fish_per_hour", "Fish per hour"], ["biggest_fish", "Biggest fish (lb)"],
  ["average_fish_weight", "Average fish weight (lb)"], ["trip_count", "# Trips"]];
export const SPECIES_METRICS = new Set(["total_fish", "biggest_fish", "average_fish_weight"]);
export const ORDER_HINTS = { segment: SEGMENTS, water_temp_band: WATER_TEMP_BANDS.map((b) => b[2]), pressure_trend_band: PRESSURE_TREND_BANDS,
  light_condition: LIGHT_CONDITIONS, wind_band: WIND_BAND_LABELS, moon_illumination_bin: MOON_BIN_ORDER, day_of_week: DAYS };
const DATE_FACTORS = new Set(["date", "week_start"]);
export const MIN_PREDICTION_SAMPLES = MIN_SAMPLES_PER_SIDE;

// ---- Python-exact little helpers
function parseDate(s) {
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(typeof s === "string" ? s : "");
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  if (d.getUTCMonth() !== +m[2] - 1 || d.getUTCDate() !== +m[3]) return null;
  return d.toISOString().slice(0, 10);
}
export function toFloat(v) {  // Python float(), NaN/inf → None
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "boolean") return v ? 1 : 0;
  const s = String(v ?? "").trim();
  return /^[+-]?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?$/i.test(s) ? Number(s) : null;
}
function pyInt(v) {  // Python int(): ints, floats truncate, whole-number text; else null
  if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : null;
  if (typeof v === "boolean") return v ? 1 : 0;
  return /^\s*[+-]?\d+\s*$/.test(String(v)) ? parseInt(v, 10) : null;
}
const fmtG = (x) => String(Number(x.toPrecision(6)));  // f"{x:g}" for the values used here
const catLabel = (c) => (c.lure_category ? LURE_PROFILES[c.lure_category]?.name || c.lure_category : null);
export function pressureBand(pt) { if (pt == null) return null; if (pt <= -1.5) return "Falling"; if (pt >= 2.0) return "Rising / High"; return "Steady"; }
export const moonPctNightBefore = (d) => { const p = parseIso(addDays(d, -1)); return pyRound(moonPhase(p + 18 * 3600e6).illumination_pct, 1); };
export function moonBin(pct) {
  if (pct == null) return null;
  const p = Math.max(0, Math.min(100, pct)), lo = Math.min(Math.floor(p / MOON_BIN_WIDTH) * MOON_BIN_WIDTH, 100 - MOON_BIN_WIDTH);
  return `${lo}-${lo + MOON_BIN_WIDTH}%`;
}
const bucketLabel = (unit) => (v, w) => { if (v == null || !(w > 0)) return null; const lo = Math.floor(v / w) * w; return `${fmtG(lo)}-${fmtG(lo + w)}${unit}`; };
export const tempBucketLabel = bucketLabel("°F"), secchiBucketLabel = bucketLabel(" ft");
function bucketAxis(values, w, label) {
  const v = values.filter((x) => x != null);
  if (!v.length || !(w > 0)) return [];
  const lo = Math.floor(Math.min(...v) / w) * w, hi = Math.floor(Math.max(...v) / w) * w, out = [];
  for (let b = lo; b <= hi + 1e-9; b += w) out.push(label(b, w));
  return out;
}
function timeSec(t) {
  const m = /^(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?$/.exec(typeof t === "string" ? t : "");
  if (!m || +m[1] > 23 || +m[2] > 59 || +(m[3] || 0) > 59) return null;
  return +m[1] * 3600 + +m[2] * 60 + +(m[3] || 0) + (m[4] ? +m[4].padEnd(6, "0") / 1e6 : 0);
}
function trustworthyHours(c) {
  if (c.times_estimated) return null;
  if (!c.lure_start_time || !c.lure_end_time) return null;
  const a = timeSec(c.lure_start_time), b = timeSec(c.lure_end_time);
  if (a == null || b == null) return null;
  const h = (b - a) / 3600;
  return h >= MIN_TRUSTED_SESSION_HOURS && h <= MAX_TRUSTED_SESSION_HOURS ? h : null;
}

function rowFactors(row) {
  const c = parseConditions(row), d = parseDate(row.trip_date), t = toFloat(c.water_temp_f), pt = toFloat(c.pressure_trend_24h);
  const moon = d ? moonPctNightBefore(d) : null;
  return [{
    trip_id: row.trip_id ?? null, date: d, week_start: d ? weekBounds(d)[0] : null, day_of_week: d ? DAYS[new Date(`${d}T00:00:00Z`).getUTCDay()] : null,
    angler: String(c.angler || "").trim() || "Unspecified", spot: row.spot_name || "Unknown location",
    structure_type: row.structure_type || "Unspecified", water_clarity: row.water_clarity || "Unspecified",
    water_color: String(c.stain_color || "").trim() || "Unspecified", secchi_ft: toFloat(c.secchi_ft),
    lure: row.lure_used || catLabel(c) || "Unspecified", lure_category: catLabel(c) || "Unspecified",
    color: row.color_used || "Unspecified", technique: row.technique_used || "Unspecified", segment: row.segment || "Unspecified",
    water_temp_f: t, water_temp_band: t != null ? waterTempBand(t).label : null,
    wind_band: c.wind_band || "Unspecified", wind_direction: c.wind_direction || "Unspecified", light_condition: c.light_condition || "Unspecified",
    precipitation: c.precipitation || "Unspecified", fish_activity: c.fish_activity || "Unspecified", forage_activity: c.forage_activity || "Unspecified",
    pressure_trend_24h: pt, pressure_trend_band: pressureBand(pt), avg_wind_mph: toFloat(c.avg_wind_mph),
    moon_illumination_pct: moon, moon_illumination_bin: moonBin(moon),
    season: d && t != null ? seasonStage(dayOfYear(d), t) : null,
    // new app: extra keys the custom-report filters use (not Python factors)
    _lure_type_key: c.lure_category || null, _spot_id: row.spot_id || null, _owner: row.owner || null,
  }, c];
}

/** {trips, fish}: one record per trip row (lure use) and one per fish record, each carrying every factor. */
export function buildReportsData(rows) {
  const trips = [], fish = [];
  for (const row of rows || []) {
    const [f, c] = rowFactors(row);
    let n = 0;
    if (Array.isArray(c.fish) && c.fish.length) {
      for (const x of c.fish) {
        if (!x || typeof x !== "object" || Array.isArray(x)) continue;
        let count = pyInt(x.count || 1); if (count == null) count = 1;
        n += count;
        fish.push({ ...f, species: String(x.species || "Unspecified").trim() || "Unspecified", count, weight_lb: toFloat(x.weight_lb), length_in: toFloat(x.length_in) });
      }
    } else { const v = toFloat(row.fish_caught || 0); n = v == null ? 0 : Math.trunc(v); }
    const big = row.biggest_fish_lb == null || row.biggest_fish_lb === "" ? null : toFloat(row.biggest_fish_lb);
    trips.push({ ...f, fish_caught: n, trustworthy_hours: trustworthyHours(c), biggest_fish_lb: big });
  }
  return { trips, fish };
}

const applyFilters = (rows, { from, to, anglers, segments }) => rows.filter((r) =>
  (!from || (r.date && r.date >= from)) && (!to || (r.date && r.date <= to)) && (!anglers?.length || anglers.includes(r.angler)) && (!segments?.length || segments.includes(r.segment)));

function dateAxis(from, to, weekly, today) {
  const end = to || today, start = from || addDays(end, -29), out = [];
  if (weekly) { for (let d = weekBounds(start)[0], e = weekBounds(end)[1]; d <= e; d = addDays(d, 7)) out.push(d); return out; }
  for (let d = start; d <= end; d = addDays(d, 1)) out.push(d);
  return out;
}

/** [{key, value, n}] — opts = {species, from, to, anglers, segments, tempWidth, secchiWidth, today} */
export function computeReport({ trips, fish }, factor, metric, opts = {}) {
  let t = applyFilters(trips, opts), f = applyFilters(fish, opts);
  if (opts.species && opts.species !== "All species" && SPECIES_METRICS.has(metric)) f = f.filter((x) => x.species === opts.species);
  const dyn = { [WATER_TEMP_BUCKET]: ["water_temp_f", opts.tempWidth || DEFAULT_TEMP_WIDTH, tempBucketLabel], [SECCHI_BUCKET]: ["secchi_ft", opts.secchiWidth || DEFAULT_SECCHI_WIDTH, secchiBucketLabel] }[factor];
  const key = dyn ? (r) => dyn[2](r[dyn[0]], dyn[1]) : (r) => r[factor];
  const groups = (rows) => { const m = new Map(); for (const r of rows) { const k = key(r); if (k == null) continue; (m.get(k) || m.set(k, []).get(k)).push(r); } return m; };
  let agg = new Map();  // key → {value, n}
  if (metric === "fish_per_hour") {
    for (const [k, rs] of groups(t.filter((r) => r.trustworthy_hours != null)))
      agg.set(k, { value: pySum(rs.map((r) => r.fish_caught)) / pySum(rs.map((r) => r.trustworthy_hours)), n: rs.filter((r) => r.trip_id != null).length });
  } else if (metric === "trip_count") {
    for (const [k, rs] of groups(t)) { const n = rs.filter((r) => r.trip_id != null).length; agg.set(k, { value: n, n }); }
  } else if (metric === "biggest_fish" || metric === "average_fish_weight") {
    for (const [k, rs] of groups(f.filter((r) => r.weight_lb != null))) {
      const w = rs.map((r) => r.weight_lb);
      agg.set(k, { value: metric === "biggest_fish" ? Math.max(...w) : pySum(w) / w.length, n: w.length });
    }
  } else if (opts.species && opts.species !== "All species") {
    for (const [k, rs] of groups(f)) agg.set(k, { value: rs.reduce((a, r) => a + r.count, 0), n: rs.length });
  } else {
    for (const [k, rs] of groups(t)) agg.set(k, { value: rs.reduce((a, r) => a + r.fish_caught, 0), n: rs.length });
  }
  const fill = (axis) => axis.map((k) => ({ key: k, value: agg.get(k)?.value ?? 0, n: agg.get(k)?.n ?? 0 }));
  if (DATE_FACTORS.has(factor)) return fill(dateAxis(opts.from, opts.to, factor === "week_start", opts.today || new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" })));
  if (ORDER_HINTS[factor]) return fill(ORDER_HINTS[factor]);
  if (dyn) return fill(bucketAxis(t.map((r) => r[dyn[0]]), dyn[1], dyn[2]));
  const keys = [...agg.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  return keys.map((k, i) => [k, i]).sort((a, b) => agg.get(b[0]).value - agg.get(a[0]).value || a[1] - b[1]).map(([k]) => ({ key: k, ...agg.get(k) }));
}

export const speciesOptions = ({ fish }) => [...new Set(fish.map((x) => x.species).filter((s) => s != null))].sort();

/** History lookup: what this metric was under the moon bucket of target (YYYY-MM-DD). */
export function predictByMoon(data, target, metric = "fish_per_hour", opts = {}) {
  const pct = moonPctNightBefore(target), bucket = moonBin(pct);
  const row = computeReport(data, "moon_illumination_bin", metric, opts).find((r) => r.key === bucket);
  const n = row ? row.n : 0;
  return { target_date: target, moon_illumination_pct: pct, moon_illumination_bucket: bucket, metric_key: metric,
    predicted_value: n > 0 ? row.value : null, n, low_sample: n > 0 && n < MIN_PREDICTION_SAMPLES };
}

function bundleCovers(bundle, at) {
  const ts = bundle?.hourly?.time;
  if (!ts || !ts.length) return false;
  const us = ts.map((s) => parseIso(s));
  if (us.some((x) => !Number.isFinite(x))) return false;
  return Math.min(...us) <= at - 24 * 3600e6 && at <= Math.max(...us);
}
/** History lookup by the forecast pressure trend at noon on target — only when the forecast actually covers it. */
export function predictByPressure(data, target, bundle, metric = "fish_per_hour", opts = {}) {
  const at = parseIso(target) + 12 * 3600e6, ok = bundleCovers(bundle, at);
  const pt = ok ? pressureTrendHpaPer24h(bundle, at) : null, band = ok ? pressureBand(pt) : null;
  let n = 0, v = null;
  if (ok) { const row = computeReport(data, "pressure_trend_band", metric, opts).find((r) => r.key === band); n = row ? row.n : 0; v = n > 0 ? row.value : null; }
  return { target_date: target, forecast_available: ok, pressure_trend_24h: pt, pressure_trend_band: band, metric_key: metric, predicted_value: v, n, low_sample: n > 0 && n < MIN_PREDICTION_SAMPLES };
}
export { dt };
