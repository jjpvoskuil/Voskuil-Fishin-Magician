// Lake Map numbers: how "hot" each saved spot is from the trip log, filtered by time of day, time of year and angler,
// plus each spot's best lures and best time of day. Rates are shrunk toward the lake-wide average (2 h), so a spot
// with one lucky stint doesn't glow red.
import { parseConditions } from "./calibration.js";
import { lureHours } from "./history.js";
import { LURE_PROFILES } from "./lures.js";

export const SEASONS = { any: "Any time", now: "This time of year", spring: "Spring (Mar–May)", summer: "Summer (Jun–Aug)", fall: "Fall (Sep–Nov)", winter: "Winter (Dec–Feb)" };
const SEASON_MONTHS = { spring: [3, 4, 5], summer: [6, 7, 8], fall: [9, 10, 11], winter: [12, 1, 2] };
const SHRINK = 2, MIN_STINT = 0.5;
const doy = (iso) => (Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) - Date.UTC(+iso.slice(0, 4), 0, 1)) / 864e5;

/** Does a trip row pass the filters? f = {segments: [], season: key, owner: email|null}, today = "YYYY-MM-DD". */
export function passes(r, f, today) {
  if (f.owner && (r.owner || "").toLowerCase() !== f.owner.toLowerCase()) return false;
  if (f.segments?.length && !f.segments.includes(r.segment)) return false;
  if (f.season && f.season !== "any") {
    if (f.season === "now") { const d = Math.abs(doy(r.trip_date) - doy(today)); if (Math.min(d, 365 - d) > 30) return false; }
    else if (!SEASON_MONTHS[f.season].includes(+r.trip_date.slice(5, 7))) return false;
  }
  return true;
}

/** {base, spots: {spot_id: {fish, hours, sessions, rate, heat (rate/base), lures: [{key, name, fish, rate}], bestSegment, last}}} */
export function spotStats(trips, f, today) {
  const by = {}; let F = 0, H = 0;
  for (const r of trips || []) {
    if (!r.spot_id || !r.trip_date || r.trip_date > today || !passes(r, f, today)) continue;
    const c = parseConditions(r); if (!c.lure_end_time && c.source === "spot_session") continue; // still fishing
    const h = Math.max(lureHours(r), MIN_STINT), fish = parseInt(r.fish_caught, 10) || 0;
    const s = (by[r.spot_id] ||= { fish: 0, hours: 0, sessions: new Set(), cats: {}, segs: {}, last: null });
    s.fish += fish; s.hours += h; s.sessions.add(r.session_id || r.trip_id); F += fish; H += h;
    if (c.lure_category) { const k = (s.cats[c.lure_category] ||= { fish: 0, hours: 0 }); k.fish += fish; k.hours += h; }
    if (r.segment) { const g = (s.segs[r.segment] ||= { fish: 0, hours: 0 }); g.fish += fish; g.hours += h; }
    if (fish && (!s.last || r.trip_date > s.last)) s.last = r.trip_date;
  }
  const base = H > 0 ? F / H : 0, spots = {};
  for (const [id, s] of Object.entries(by)) {
    const rate = (s.fish + SHRINK * base) / (s.hours + SHRINK);
    const lures = Object.entries(s.cats).filter(([, v]) => v.fish > 0).map(([k, v]) => ({ key: k, name: LURE_PROFILES[k]?.name || k, fish: v.fish, rate: v.fish / v.hours }))
      .sort((a, b) => b.fish - a.fish || b.rate - a.rate).slice(0, 3);
    const segs = Object.entries(s.segs).filter(([, v]) => v.hours >= 1).map(([k, v]) => [k, v.fish / v.hours]).sort((a, b) => b[1] - a[1]);
    spots[id] = { fish: s.fish, hours: s.hours, sessions: s.sessions.size, rate, heat: base > 0 ? rate / base : 1, lures, bestSegment: segs[0]?.[0] || null, last: s.last };
  }
  return { base, spots };
}

/** Pin color by heat: no data gray; cold blue → average yellow → hot red. */
export function heatColor(st) {
  if (!st || st.hours < 1) return "#8a918b";
  const h = st.heat;
  return h >= 1.6 ? "#d7301f" : h >= 1.2 ? "#fc8d59" : h >= 0.85 ? "#fdcc5c" : h >= 0.6 ? "#91bfdb" : "#4575b4";
}
export const HEAT_LEGEND = [["#d7301f", "Hot"], ["#fc8d59", "Warm"], ["#fdcc5c", "Average"], ["#91bfdb", "Cool"], ["#4575b4", "Cold"], ["#8a918b", "Not enough data"]];
