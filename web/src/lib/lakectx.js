// Lake condition per date and per outing, shared by "Where to fish" (lib/wheretofish.js), "Fish depth"
// (lib/fishdepth.js) and the Lake Map's "Like today's lake" filter. New app only (John 11-20).
// phase = the Army Corps dam profiles around that date (lib/o2catch.js: stratified / turnover / mixed), else a
// calendar guess; temp = the water temp logged on the outing (when the boat's electronics were in use), else the
// Corps surface temperature, else null.
import { parseConditions } from "./calibration.js";
import { allProfiles, conditionsOn } from "./o2catch.js";
import { seasonFor } from "./oxygen.js";

export const PHASE_LABEL = { stratified: "Summer layers", turnover: "Turnover", mixed: "Mixed (cool water)" };
export const TEMP_BANDS = [[85, 999, "85 °F +"], [80, 85, "80–85 °F"], [75, 80, "75–80 °F"], [70, 75, "70–75 °F"], [60, 70, "60–70 °F"], [50, 60, "50–60 °F"], [-99, 50, "Under 50 °F"]];
export const tempBand = (t) => (t == null ? null : TEMP_BANDS.find(([a, b]) => t >= a && t < b)?.[2] ?? null);
const num = (v) => { const n = typeof v === "number" ? v : parseFloat(v); return Number.isFinite(n) ? n : null; };

/** Calendar guess when no Corps profile is near: Jun–Sep layered, Oct–mid-Nov turnover, else mixed. */
export function guessPhase(date) {
  const m = +date.slice(5, 7), s = seasonFor(date);
  if (m >= 6 && m <= 9) return "stratified";
  if (s && s.crash_pct >= 15) return "turnover";
  if (m === 5 && s && s.floor_ft < 45) return "stratified";
  return "mixed";
}

/** ctx(waterLog) → { profiles, on(date) → {phase, surface_f, floor_ft|null, measured}, rowTemp(row, date) } */
export function lakeContext(waterLog = []) {
  const profiles = allProfiles(waterLog), cache = new Map();
  const on = (date) => {
    if (!cache.has(date)) {
      const c = conditionsOn(date, profiles);
      cache.set(date, c ? { phase: c.phase, surface_f: c.surface_f, floor_ft: c.phase === "stratified" ? c.floor_ft : null, measured: true }
        : { phase: guessPhase(date), surface_f: null, floor_ft: null, measured: false });
    }
    return cache.get(date);
  };
  const rowTemp = (r) => {
    const c = parseConditions(r), t = num(c.water_temp_f);
    if (t != null && !c.water_temp_unreliable && c.electronics !== false) return t;
    return on(r.trip_date).surface_f ?? null;
  };
  return { profiles, on, rowTemp };
}

/** Today's lake for "Like today": a Corps profile ≤10 days old (else the calendar guess) + a temperature
 *  (that profile's surface, else the app's water-temp estimate passed in). */
export function todayLake(ctx, today, estTempF = null) {
  const c = ctx.on(today);
  return { phase: c.phase, temp: c.measured && c.surface_f != null ? c.surface_f : estTempF, measured: c.measured };
}
