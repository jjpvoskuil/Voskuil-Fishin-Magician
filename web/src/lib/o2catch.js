// Reports → "Oxygen & catch" (John 11-20): our outings matched to the Army Corps dam-site oxygen profiles. New app only.
// Profiles = the Corps file (lib/data/corps_profiles.json, tools/corps_profiles.py) + every fm_water_quality row that
// carries a full `profile` (logged twice a day by deercast-data's water-quality job), so it fills in by itself.
// For each outing (session): hours = first lure in → last lure out (≥0.5 h to count), fish = every fish logged,
// conditions = interpolated between the Corps profiles before and after (both within GAP days), else the nearest one
// within NEAR days, else unmatched. The 5 mg/L floor is scaled for how far up the lake the spot is (oxygen.js).
import CORPS from "./data/corps_profiles.json" with { type: "json" };
import { parseConditions } from "./calibration.js";
import { floorFromProfile, milesFromDam, uplakeFloorFt } from "./oxygen.js";

const GAP = 24, NEAR = 10, MIN_H = 0.5;
const toMin = (t) => { const m = /^(\d{2}):(\d{2})(?::(\d{2}))?/.exec(t || ""); return m ? +m[1] * 60 + +m[2] + (+m[3] || 0) / 60 : null; };
const num = (v) => { const n = typeof v === "number" ? v : parseFloat(v); return Number.isFinite(n) ? n : null; };
const dayNo = (d) => Date.parse(`${d}T12:00:00Z`) / 864e5;

/** One summary per profile date: floor (5 mg/L; bottom depth when never below), surface DO/°F, top-bottom °F, phase. */
export function summarizeProfile(date, rows) {
  const r = [...rows].filter((x) => x.do_mg_l != null).sort((a, b) => a.depth_ft - b.depth_ft);
  if (r.length < 3) return null;
  const bottom = r[r.length - 1].depth_ft, f = floorFromProfile(r, 5), temps = r.filter((x) => x.temp_f != null);
  const dT = temps.length >= 2 ? temps[0].temp_f - temps[temps.length - 1].temp_f : null;
  const stratified = dT != null && dT >= 3.6; // 2 °C
  const phase = stratified ? "stratified" : r[0].do_mg_l < 5 || (f != null && f < 40) ? "turnover" : "mixed";
  return { date, floor_ft: f == null ? bottom : f, surface_do: r[0].do_mg_l, surface_f: temps[0]?.temp_f ?? null, dT, phase };
}

/** All profiles (Corps file + logged), one per date, oldest first. */
export function allProfiles(waterLog = []) {
  const by = new Map();
  for (const w of waterLog || []) {
    if (!Array.isArray(w.profile) || w.profile.length < 3) continue;
    const date = String(w.observed_at || "").slice(0, 10);
    const s = summarizeProfile(date, w.profile.map((x) => ({ depth_ft: num(x.depth_ft), temp_f: num(x.water_temp_f ?? x.temp_f), do_mg_l: num(x.do_mg_l) })));
    if (s) by.set(date, s);
  }
  for (const p of CORPS.profiles) { const s = summarizeProfile(p.date, p.rows); if (s) by.set(p.date, s); } // the Corps file wins
  return [...by.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** Lake conditions for a date from the profiles around it, or null. */
export function conditionsOn(date, profiles) {
  const t = dayNo(date);
  let before = null, after = null;
  for (const p of profiles) { const d = dayNo(p.date); if (d <= t) before = p; else { after = p; break; } }
  const near = [before, after].filter(Boolean).sort((a, b) => Math.abs(dayNo(a.date) - t) - Math.abs(dayNo(b.date) - t))[0];
  if (!near || Math.abs(dayNo(near.date) - t) > NEAR && !(before && after && t - dayNo(before.date) <= GAP && dayNo(after.date) - t <= GAP)) return null;
  if (before && after && t - dayNo(before.date) <= GAP && dayNo(after.date) - t <= GAP && before.phase === "stratified" && after.phase === "stratified") {
    const k = (t - dayNo(before.date)) / (dayNo(after.date) - dayNo(before.date)), lerp = (a, b) => (a == null || b == null ? a ?? b : a + k * (b - a));
    return { ...near, floor_ft: lerp(before.floor_ft, after.floor_ft), surface_do: lerp(before.surface_do, after.surface_do), surface_f: lerp(before.surface_f, after.surface_f), phase: "stratified", from: [before.date, after.date] };
  }
  return { ...near, from: [near.date] };
}

/** Outings: [{date, owner, spot_id, hours, fish, fish_depth}] (closed sessions with ≥0.5 h). */
export function outings(trips, { from = "", to = "", owner = null } = {}) {
  const by = new Map();
  for (const r of trips || []) {
    const d = r.trip_date; if (!d || (from && d < from) || (to && d > to)) continue;
    if (owner && (r.owner || "").toLowerCase() !== owner.toLowerCase()) continue;
    const c = parseConditions(r); if (!c.lure_end_time) continue;
    const id = `${r.owner}|${r.session_id || r.trip_id}`;
    const o = by.get(id) || { date: d, owner: r.owner, spots: {}, lo: null, hi: null, fish: 0, depths: [] };
    const fl = Array.isArray(c.fish) ? c.fish.filter((f) => f && typeof f === "object") : [];
    o.fish += fl.length ? fl.reduce((s, f) => s + (parseInt(f.count || 1, 10) || 1), 0) : parseInt(r.fish_caught, 10) || 0;
    const a = toMin(c.lure_start_time), b = toMin(c.lure_end_time);
    if (a != null && b != null && b > a) { o.lo = o.lo == null ? a : Math.min(o.lo, a); o.hi = o.hi == null ? b : Math.max(o.hi, b); }
    if (r.spot_id) o.spots[r.spot_id] = (o.spots[r.spot_id] || 0) + 1;
    const fd = num(c.fish_depth_ft); if (fd != null && fd > 0 && !c.fish_depth_unreliable && c.electronics !== false) o.depths.push(fd);
    by.set(id, o);
  }
  return [...by.values()].map((o) => {
    const ds = [...o.depths].sort((a, b) => a - b);
    return { date: o.date, owner: o.owner, spot_id: Object.entries(o.spots).sort((a, b) => b[1] - a[1])[0]?.[0] || null,
      hours: o.lo != null ? (o.hi - o.lo) / 60 : 0, fish: o.fish, fish_depth: ds.length ? ds[Math.floor((ds.length - 1) / 2)] : null };
  }).filter((o) => o.hours >= MIN_H).sort((a, b) => a.date.localeCompare(b.date));
}

const POS = [["well", "6+ ft above"], ["above", "2–6 ft above"], ["at", "At floor ±2 ft"], ["below", "2+ ft below"]];
const PHASES = [["stratified", "Summer layers"], ["turnover", "Turnover"], ["mixed", "Mixed"]];
const FLOOR_BANDS = [[0, 10, "Under 10 ft"], [10, 12, "10–12 ft"], [12, 15, "12–15 ft"], [15, 20, "15–20 ft"], [20, 999, "20 ft or deeper"]];
const group = (list, keys, keyOf) => keys.map(([key, label]) => {
  const g = list.filter((o) => keyOf(o) === key), hours = g.reduce((s, o) => s + o.hours, 0), fish = g.reduce((s, o) => s + o.fish, 0);
  return { key, label, outings: g.length, hours, fish, rate: hours >= MIN_H ? fish / hours : null, zero: g.length ? g.filter((o) => !o.fish).length / g.length : null };
});

/** The whole report. spots = [{spot_id, lat, lon}]. */
export function o2Catch(trips, { spots = [], waterLog = [], from = "", to = "", owner = null } = {}) {
  const profiles = allProfiles(waterLog), S = Object.fromEntries((spots || []).map((s) => [s.spot_id, s]));
  const all = outings(trips, { from, to, owner }), matched = [];
  for (const o of all) {
    const c = conditionsOn(o.date, profiles); if (!c) continue;
    const s = S[o.spot_id], miles = s ? milesFromDam(num(s.lat), num(s.lon)) : null;
    const floor = c.phase === "stratified" ? uplakeFloorFt(c.floor_ft, Number.isFinite(miles) ? miles : 0) : null;
    const rel = floor != null && o.fish_depth != null ? o.fish_depth - floor : null;
    matched.push({ ...o, phase: c.phase, dam_floor: c.floor_ft, floor, miles, surface_do: c.surface_do, surface_f: c.surface_f, rel,
      pos: rel == null ? null : rel < -6 ? "well" : rel < -2 ? "above" : rel <= 2 ? "at" : "below", from: c.from });
  }
  const strat = matched.filter((o) => o.phase === "stratified");
  const wk = new Map();
  for (const o of matched) {
    const d = new Date(`${o.date}T12:00:00Z`), mon = new Date(d - ((d.getUTCDay() + 6) % 7) * 864e5).toISOString().slice(0, 10);
    const w = wk.get(mon) || { week: mon, outings: 0, hours: 0, fish: 0, floors: [], phases: {} };
    w.outings++; w.hours += o.hours; w.fish += o.fish; if (o.floor != null) w.floors.push(o.floor); w.phases[o.phase] = (w.phases[o.phase] || 0) + 1; wk.set(mon, w);
  }
  const weeks = [...wk.values()].sort((a, b) => a.week.localeCompare(b.week)).map((w) => ({ week: w.week, outings: w.outings, hours: w.hours, fish: w.fish,
    rate: w.hours >= MIN_H ? w.fish / w.hours : null, floor: w.floors.length ? w.floors.reduce((a, b) => a + b, 0) / w.floors.length : null,
    phase: Object.entries(w.phases).sort((a, b) => b[1] - a[1])[0][0] }));
  const marked = strat.filter((o) => o.pos);
  return {
    profiles, outings: all.length, matched: matched.length, unmatched: all.length - matched.length,
    span: matched.length ? [matched[0].date, matched[matched.length - 1].date] : null,
    byPhase: group(matched, PHASES, (o) => o.phase),
    byPosition: group(marked, POS, (o) => o.pos), marked: marked.length,
    byFloor: group(strat, FLOOR_BANDS.map(([a, , l]) => [a, l]), (o) => FLOOR_BANDS.find(([a, b]) => o.floor >= a && o.floor < b)?.[0]),
    medianMarkedVsFloor: marked.length ? [...marked.map((o) => o.rel)].sort((a, b) => a - b)[Math.floor((marked.length - 1) / 2)] : null,
    weeks,
  };
}
