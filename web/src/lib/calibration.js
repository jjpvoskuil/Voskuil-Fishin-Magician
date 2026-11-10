// Learns from logged trips: nudges the scoring weights and per-spot/per-segment adjustments, plus the moon-vs-dawn
// tables used by Reports. Port of core/calibration.py (parity tests: engine.test.js). Trip rows have the same
// fields as the old trip_log.csv; conditions come from row.conditions (object) or row.conditions_json (text).
import { SYNODIC_MONTH, illuminationPctForAge, moonPhase } from "./astro.js";
import { DEFAULT_WEIGHTS } from "./scoring.js";
import { addDays, at, median, pyRound } from "./py.js";

export const MIN_SAMPLES_PER_SIDE = 4, MAX_NUDGE_FRACTION = 0.35;
export const MIN_TRUSTED_SESSION_HOURS = 5 / 60, MAX_TRUSTED_SESSION_HOURS = 6.0;
export const LOCATION_MIN_SAMPLES = MIN_SAMPLES_PER_SIDE, LOCATION_ADJUSTMENT_CAP = 1.0, LOCATION_SHRINKAGE_PRIOR = 6;
export const MORNING_SEGMENTS = ["Dawn", "Morning"];
export const DAYS_IN_LUNAR_CYCLE = Math.trunc(SYNODIC_MONTH) + 1;

/** Always an object (like storage.parse_conditions). */
export function parseConditions(row) {
  if (row.conditions && typeof row.conditions === "object" && !Array.isArray(row.conditions)) return row.conditions;
  try { const p = JSON.parse(row.conditions_json || "{}"); return p && typeof p === "object" && !Array.isArray(p) ? p : {}; } catch { return {}; }
}
/** Python int() of a CSV field: whole-number text or number, else null (=ValueError). */
function pyInt(v) {
  if (v == null || v === "") return 0;
  if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : null;
  if (typeof v === "boolean") return v ? 1 : 0;
  return /^\s*[+-]?\d+\s*$/.test(String(v)) ? parseInt(v, 10) : null;
}
/** time.fromisoformat → seconds since midnight, or null */
function timeSeconds(s) {
  const m = /^(\d{2})(?::(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?$/.exec(String(s));
  if (!m || +m[1] > 23 || +(m[2] || 0) > 59 || +(m[3] || 0) > 59) return null;
  return +m[1] * 3600 + +(m[2] || 0) * 60 + +(m[3] || 0) + (m[4] ? +m[4].padEnd(6, "0") / 1e6 : 0);
}

function factorFlags(c) {
  const pt = c.pressure_trend_24h || 0;
  return {
    pressure_falling: pt <= -1.5,
    pressure_high_stable_post_front: pt >= 2.0,
    moon_new_full_bonus: Boolean(c.moon_near_new_full || false),
    cloud_overcast_bonus: (c.avg_cloud_pct || 0) >= 60,
    wind_sweet_spot_bonus: (c.avg_wind_mph || 0) >= 4 && (c.avg_wind_mph || 0) <= 14,
  };
}

/** Fish per hour for a trustworthy-duration lure row, else null. */
export function tripFishPerHour(row) {
  const c = parseConditions(row);
  if (c.times_estimated) return null;
  const start = c.lure_start_time, end = c.lure_end_time;
  if (!start || !end) return null;
  const t0 = timeSeconds(start), t1 = timeSeconds(end);
  if (t0 == null || t1 == null) return null;
  const hours = (t1 - t0) / 3600.0;
  if (!(MIN_TRUSTED_SESSION_HOURS <= hours && hours <= MAX_TRUSTED_SESSION_HOURS)) return null;
  const caught = pyInt(row.fish_caught);
  if (caught == null || caught < 0) return null;
  return caught / hours;
}

export function calibrateWeights(rows) {
  const weights = { ...DEFAULT_WEIGHTS };
  if (!rows || !rows.length) return weights;
  const rates = rows.map(tripFishPerHour), valid = rates.filter((r) => r != null);
  if (!valid.length) return weights;
  const baseline = median(valid);
  if (baseline <= 0) return weights;
  const buckets = Object.fromEntries(Object.keys(factorFlags({})).map((k) => [k, { on: [], off: [] }]));
  rows.forEach((row, i) => {
    if (rates[i] == null) return;
    for (const [f, on] of Object.entries(factorFlags(parseConditions(row)))) buckets[f][on ? "on" : "off"].push(rates[i]);
  });
  for (const [f, b] of Object.entries(buckets)) {
    if (b.on.length < MIN_SAMPLES_PER_SIDE || b.off.length < MIN_SAMPLES_PER_SIDE) continue;
    const lift = Math.max(-1.0, Math.min(1.0, (median(b.on) - median(b.off)) / baseline));
    const def = DEFAULT_WEIGHTS[f] ?? 0, cap = def !== 0 ? Math.abs(def) * MAX_NUDGE_FRACTION : 0.5;
    weights[f] = pyRound(def + Math.max(-cap, Math.min(cap, lift * cap)), 3);
  }
  return weights;
}

/** {"spotId|Segment": {adjustment, n, spot_name, spot_id, segment}} */
export function locationAdjustments(rows) {
  const bySeg = new Map(), byCell = new Map(), names = new Map(), all = [];
  for (const row of rows) {
    const rate = tripFishPerHour(row);
    if (rate == null) continue;
    const seg = row.segment, spot = row.spot_id;
    if (!seg || !spot) continue;
    if (!bySeg.has(seg)) bySeg.set(seg, []); bySeg.get(seg).push(rate);
    const k = `${spot}|${seg}`; if (!byCell.has(k)) byCell.set(k, []); byCell.get(k).push(rate);
    if (!names.has(spot)) names.set(spot, row.spot_name || spot);
    all.push(rate);
  }
  if (!all.length) return {};
  const overall = median(all);
  if (overall <= 0) return {};
  const out = {};
  for (const [k, rates] of byCell) {
    const n = rates.length; if (n < LOCATION_MIN_SAMPLES) continue;
    const [spot, seg] = k.split("|"), segRates = bySeg.get(seg);
    if (segRates.length < LOCATION_MIN_SAMPLES) continue;
    const lift = Math.max(-1.0, Math.min(1.0, (median(rates) - median(segRates)) / overall));
    const adj = pyRound(lift * LOCATION_ADJUSTMENT_CAP * (n / (n + LOCATION_SHRINKAGE_PRIOR)), 3);
    if (adj === 0) continue;
    out[k] = { adjustment: adj, n, spot_name: names.get(spot), spot_id: spot, segment: seg };
  }
  return out;
}

const dayOfCycleForDate = (d) => Math.trunc(moonPhase(at(addDays(d, -1), 18)).age_days);
const validDate = (s) => typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(`${s}T00:00:00Z`)) && new Date(`${s}T00:00:00Z`).toISOString().startsWith(s);

export function moonIlluminationDawnRates(rows, since = null, until = null) {
  let order;
  if (until != null) {
    order = []; const seen = new Set();
    for (let d = since; d <= until; d = addDays(d, 1)) { const c = dayOfCycleForDate(d); if (!seen.has(c)) { seen.add(c); order.push(c); } }
  } else order = Array.from({ length: DAYS_IN_LUNAR_CYCLE }, (_, i) => i);
  const buckets = new Map(order.map((d) => [d, []]));
  for (const row of rows) {
    if (!MORNING_SEGMENTS.includes(row.segment)) continue;
    const rate = tripFishPerHour(row); if (rate == null) continue;
    const td = row.trip_date; if (!td || !validDate(td)) continue;
    if (since != null && td < since) continue;
    if (until != null && td > until) continue;
    const c = dayOfCycleForDate(td); if (!buckets.has(c)) continue;
    buckets.get(c).push(rate);
  }
  return order.map((d) => ({ day_of_cycle: d, illumination_pct: pyRound(illuminationPctForAge(d), 1), median: buckets.get(d).length ? median(buckets.get(d)) : null, n: buckets.get(d).length }));
}

export function dailyDawnMorningCatch(rows, since, until) {
  const fish = new Map();
  for (const row of rows) {
    if (!MORNING_SEGMENTS.includes(row.segment)) continue;
    const td = row.trip_date; if (!td || !validDate(td)) continue;
    if (!(since <= td && td <= until)) continue;
    const n = pyInt(row.fish_caught); if (n == null) continue;
    fish.set(td, (fish.get(td) || 0) + n);
  }
  const out = [];
  for (let d = since; d <= until; d = addDays(d, 1)) {
    const dt = new Date(`${d}T00:00:00Z`);
    const label = `${dt.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" })} ${dt.getUTCMonth() + 1}/${String(dt.getUTCDate()).padStart(2, "0")}`;
    out.push({ date: d, label, fish: fish.get(d) || 0, illumination_pct: pyRound(illuminationPctForAge(dayOfCycleForDate(d)), 1) });
  }
  return out;
}
