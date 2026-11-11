// Spot Session rules: what starting, logging a fish, changing/adding a lure, moving, ending and canceling save.
// Port of pages/6_Spot_Session.py's data logic (the rows are the same shape as the old trip_log.csv), with the
// 11-10 speed-ups John approved: conditions pre-filled (each field tagged with where its value came from in
// conditions.field_sources), GPS spot pick, "same lures as last time", quick fish logging, edit-while-fishing.
// One trip row per lure fished; a session is open while any of its rows has no lure_end_time.
import * as astro from "./astro.js";
import { cloudProxyForLightCondition, lightConditionForCloudPct, precipitationOptionForForecast, precipitationProxy,
  resolveWaterClarity, windBand, windDirectionForDegrees, windMphForBand } from "./onwater.js";
import { dayOfYear, dateOf, isoNaive, parts } from "./py.js";
import { manualSegmentScore, realtimeContextFromBundle, seasonStage, segmentTimeRanges, SEGMENTS } from "./scoring.js";
import { estimateWaterTempF, hourlyRowsForDate } from "./weather.js";
import { parseConditions } from "./calibration.js";
import { LURE_PROFILES } from "./lures.js";

export const FISH_ACTIVITY_OPTIONS = ["Inactive / shut down", "Sluggish", "Moderate", "Active", "Very active"];
export const FORAGE_ACTIVITY_OPTIONS = ["None seen", "Sparse / scattered", "Moderate", "Active / schooling", "Frenzied (busting bait)"];
export const RETRIEVE_SPEED_OPTIONS = ["Slow", "Medium", "Fast"];
export const RETRIEVE_STYLE_OPTIONS = ["Straight retrieve (no action)", "Twitch", "Jerk", "Stop-and-go", "Slow-roll", "Burn (fast retrieve)", "Hop / drag (bottom contact)", "Deadstick (no movement)"];
export const FISH_SPECIES_OPTIONS = ["Largemouth Bass", "White Bass", "Crappie", "Smallmouth Bass", "Walleye", "Catfish", "Other (type in species)"];
export const HIT_TYPE_OPTIONS = ["Hard hit", "Light hit", "Double tap", "Swallowed", "Fouled", "Surface hit"];
export const WEIGHT_LB_OPTIONS = [...Array.from({ length: 11 }, (_, i) => i), "10+"];
export const WEIGHT_OZ_OPTIONS = Array.from({ length: 16 }, (_, i) => i);
export const LENGTH_OPTIONS = ["<12", ...Array.from({ length: 15 }, (_, i) => i + 12), "26+"];
/** Fields of a session's conditions, and the default when nothing better is known (old app's defaults). */
export const CONDITION_FIELDS = {
  water_temp_f: 85.0, secchi_ft: 2.5, stain_color: "Green stained", stirred_up: false, wind_band: "Light Ripple", wind_direction: "SW",
  light_condition: "Partly Cloudy", precipitation: "None", forage_seen: ["Threadfin Shad"], fish_activity: "Moderate", forage_activity: "Moderate", fish_depth_ft: 8.0,
};
const PER_LURE_KEYS = new Set(["lure_category", "trailer_used", "trailer_name", "trailer_color", "trailer_category", "lure_start_time", "lure_end_time", "fish", "source"]);
/** fields that come from the water (worth reusing from someone else's session at the lake today) */
const WATER_FIELDS = ["water_temp_f", "secchi_ft", "stain_color", "stirred_up", "forage_seen", "fish_depth_ft"];

export const newTripId = () => Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, "0")).join("");
const hhmmss = (us) => isoNaive(us).slice(11); // "07:41:05" (+ .ffffff when present)
export const weightLbForDropdown = (lb, oz) => (String(lb).trim() === "10+" ? 10.5 : Math.round((Math.max(Number(lb) || 0, 0) + Math.max(Number(oz) || 0, 0) / 16) * 1e4) / 1e4);
export const lengthInForDropdown = (c) => (c === "<12" ? 11.0 : c === "26+" ? 27.0 : Number(c));

/** Time of day for a moment (old _guess_segment): the forecast's windows when available, else fixed hours. */
export function guessSegment(at, segRanges) {
  if (segRanges) {
    for (const n of SEGMENTS) { const w = segRanges[n]; if (w && w[0] <= at && at < w[1]) return n; }
    if (segRanges.Dawn && at < segRanges.Dawn[0]) return "Night";
  }
  const h = parts(at).h;
  return h < 7 ? "Dawn" : h < 11 ? "Morning" : h < 14 ? "Midday" : h < 18 ? "Afternoon" : h < 20 ? "Dusk" : "Night";
}

/** Conditions pre-filled from the forecast at `at` (old _weather_defaults), each with its source. */
export function weatherDefaults(bundle, d, at) {
  const v = {}, src = {};
  if (!bundle) return { values: v, sources: src };
  try { const t = estimateWaterTempF(bundle, d, dayOfYear(d)); if (t) { v.water_temp_f = Math.round(t * 10) / 10; src.water_temp_f = "estimate"; } } catch { /* none */ }
  const rows = hourlyRowsForDate(bundle, d);
  if (rows.length) {
    const near = rows.reduce((b, r) => (Math.abs(r.time - at) < Math.abs(b.time - at) ? r : b), rows[0]);
    if (near.windspeed_10m != null) { v.wind_band = windBand(near.windspeed_10m).label; src.wind_band = "forecast"; }
    if (near.winddirection_10m != null) { v.wind_direction = windDirectionForDegrees(near.winddirection_10m); src.wind_direction = "forecast"; }
    if (near.cloudcover != null) { v.light_condition = lightConditionForCloudPct(near.cloudcover); src.light_condition = "forecast"; }
    v.precipitation = precipitationOptionForForecast(near.precipitation, near.precipitation_probability); src.precipitation = "forecast";
  }
  return { values: v, sources: src };
}

/** Water-side conditions someone logged at the lake today (latest session start), to reuse. */
export function sharedWaterConditions(trips, d) {
  let best = null;
  for (const t of trips || []) {
    if (t.trip_date !== d) continue;
    const c = parseConditions(t); if (c.source !== "spot_session") continue;
    if (!best || (t.logged_at || "") > (best.t.logged_at || "")) best = { t, c };
  }
  if (!best) return { values: {}, sources: {} };
  const values = {}, sources = {}, who = best.c.angler || "another angler";
  for (const f of WATER_FIELDS) {
    const own = best.c.field_sources?.[f];
    if (best.c[f] == null || (own && own !== "you")) continue; // only reuse values a person actually entered
    values[f] = best.c[f]; sources[f] = `shared:${who}`;
  }
  return { values, sources };
}

/** Merge defaults → forecast → shared-from-today → what you entered. Returns {values, sources}. */
export function mergeConditions(...layers) {
  const values = { ...CONDITION_FIELDS }, sources = Object.fromEntries(Object.keys(CONDITION_FIELDS).map((k) => [k, "default"]));
  for (const l of layers) for (const [k, v] of Object.entries(l.values || {})) { values[k] = v; sources[k] = l.sources?.[k] || "you"; }
  return { values, sources };
}

/** Score + derived values for a set of conditions (old _compute_scoring). */
export function computeScoring(cond, d, bundle, at, segment, { spotId = null, locAdj = {}, weights = null } = {}) {
  const water_clarity = resolveWaterClarity(cond.secchi_ft ?? 2.5, cond.stain_color, cond.stirred_up || false);
  const water_temp_f = cond.water_temp_f ?? 85.0;
  const season = seasonStage(dayOfYear(d), water_temp_f);
  const avg_cloud_pct = cloudProxyForLightCondition(cond.light_condition || "Partly Cloudy");
  const avg_wind_mph = windMphForBand(cond.wind_band || "Light Ripple");
  const [total_precip_in, max_precip_prob_pct] = precipitationProxy(cond.precipitation || "None");
  const rt = realtimeContextFromBundle(bundle, segment, d, { at_time: at });
  const loc = spotId ? locAdj[`${spotId}|${segment}`] : null;
  const score = manualSegmentScore({ segment_name: segment, season, avg_cloud_pct, avg_wind_mph, total_precip_in, max_precip_prob_pct,
    pressure_trend_24h: rt.pressure_trend_24h, solunar_overlap: rt.solunar_overlap, at_time: at, water_temp_f, water_clarity,
    forage_present: Boolean(cond.forage_seen && cond.forage_seen.length), location_adjustment: loc ? loc.adjustment : 0.0, location_adjustment_n: loc ? loc.n : null, weights });
  return { water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score };
}

/** The session-wide conditions every lure row carries (old _build_base_conditions + field_sources). */
export function baseConditions(cond, sources, s, startTime, segment, angler) {
  return { ...cond, field_sources: { ...sources }, avg_cloud_pct: s.avg_cloud_pct, avg_wind_mph: s.avg_wind_mph,
    pressure_trend_24h: s.rt ? s.rt.pressure_trend_24h : null, moon_near_new_full: s.score ? s.score.moon.is_new_or_full_window : null,
    moon_phase: s.score ? s.score.moon.name : null, start_time: startTime, segment_name: segment, wind_band_logged: cond.wind_band, angler: angler || null };
}

/** A new trip row for one lure. */
export function lureRow({ base, lure, at, session, spot, structure, clarity, segment, predicted, owner }) {
  const tr = lure.trailer || null;
  return {
    trip_id: newTripId(), logged_at: new Date().toISOString().replace("Z", ""), trip_date: session.date, segment, spot_id: spot.spot_id, spot_name: spot.name,
    structure_type: structure, water_clarity: clarity, lure_used: lure.label, color_used: "", technique_used: "", fish_caught: 0, biggest_fish_lb: null,
    predicted_score: predicted, notes: "", session_id: session.id, owner,
    conditions: { ...base, lure_category: lure.category ?? null, trailer_used: tr != null, trailer_name: tr ? tr.label : null, trailer_color: tr ? tr.color : null,
      trailer_category: tr ? tr.category : null, item_id: lure.item_id ?? null, lure_start_time: hhmmss(at), lure_end_time: null, fish: [], source: "spot_session" },
  };
}

/** Recount fish_caught / biggest_fish_lb from the fish list (old _record_fish / _remove_fish). */
export function withFish(row, fish) {
  const ws = fish.map((f) => f.weight_lb).filter((w) => w);
  return { ...row, fish_caught: fish.reduce((a, f) => a + (f.count || 1), 0), biggest_fish_lb: ws.length ? Math.max(...ws) : null, conditions: { ...row.conditions, fish } };
}
export const retireRow = (row, at) => ({ ...row, conditions: { ...row.conditions, lure_end_time: hhmmss(at) } });
export const endRows = (rows, at) => rows.map((r) => ({ ...r, conditions: { ...r.conditions, session_end_time: hhmmss(at), lure_end_time: r.conditions.lure_end_time || hhmmss(at) } }));

export function newFish({ species, speciesOther = "", weightLb = null, lengthIn = null, hitTypes = [], retrieveStyle = null, retrieveSpeed = null, at }) {
  const sp = species === "Other (type in species)" && speciesOther.trim() ? speciesOther.trim() : species;
  return { species: sp, species_other: speciesOther || null, count: 1, weight_lb: weightLb || null, length_in: lengthIn || null, hit_types: hitTypes,
    retrieve_speed: retrieveSpeed, retrieve_style: retrieveStyle, caught_at: hhmmss(at) };
}

/** Group spot-session rows into sessions (old _session_group_key). */
export function sessionKey(t, c = parseConditions(t)) {
  if (c.session_id || t.session_id) return t.session_id || c.session_id;
  return c.start_time ? `${t.trip_date}|${c.start_time}|${c.angler}` : null;
}
/** Open sessions: [{key, angler, rows (oldest first)}], newest first. */
export function openSessions(trips) {
  const groups = new Map();
  for (const t of trips || []) {
    const c = parseConditions(t); if (c.source !== "spot_session") continue;
    const k = sessionKey(t, c); if (!k) continue;
    if (!groups.has(k)) groups.set(k, []); groups.get(k).push(t);
  }
  const out = [];
  for (const [key, rows] of groups) {
    if (!rows.some((r) => !parseConditions(r).lure_end_time)) continue;
    rows.sort((a, b) => (a.logged_at || "").localeCompare(b.logged_at || ""));
    out.push({ key, angler: (parseConditions(rows[0]).angler || "").trim(), owner: rows[0].owner, rows });
  }
  return out.sort((a, b) => (b.rows[0].logged_at || "").localeCompare(a.rows[0].logged_at || ""));
}
/** My open session (by sign-in email, or by angler name for imported rows). */
export const myOpenSession = (trips, me) => openSessions(trips).find((s) => s.owner === me.email || (!s.owner && s.angler.toLowerCase() === (me.name || "").toLowerCase())) || null;

/** Lures from my most recent finished session, as stubs to re-add. */
export function lastSessionLures(trips, me, inventory) {
  const mine = (trips || []).filter((t) => (t.owner === me.email || parseConditions(t).angler === me.name) && parseConditions(t).source === "spot_session");
  if (!mine.length) return [];
  const latest = mine.reduce((b, t) => ((t.logged_at || "") > (b.logged_at || "") ? t : b));
  const key = sessionKey(latest), seen = new Set(), out = [];
  for (const t of mine.filter((x) => sessionKey(x) === key).sort((a, b) => (a.logged_at || "").localeCompare(b.logged_at || ""))) {
    if (seen.has(t.lure_used)) continue; seen.add(t.lure_used);
    const c = parseConditions(t), item = (inventory || []).find((i) => i.item_id === c.item_id || itemLabel(i) === t.lure_used);
    out.push({ label: t.lure_used, category: c.lure_category ?? item?.category ?? null, item_id: item?.item_id ?? c.item_id ?? null,
      trailer: c.trailer_used ? { label: c.trailer_name, color: c.trailer_color, category: c.trailer_category, item_id: null } : null });
  }
  return out;
}
export function itemLabel(it) { const l = [(it.brand || "").trim(), (it.description || "").trim()].filter(Boolean).join(" - "); return l || it.item_id || "Unnamed item"; }
/** Whether a lure can take a trailer (old lure_can_take_trailer): yes unless its profile says it never does. */
export function canTakeTrailer(item) { const p = item ? LURE_PROFILES[item.category] : null; return !p || p.trailer != null; }
export const sessionConditions = (row) => Object.fromEntries(Object.entries(parseConditions(row)).filter(([k]) => !PER_LURE_KEYS.has(k)));

/** Nearest saved spot within maxM metres of a GPS fix, or null. */
export function nearestSpot(spots, lat, lon, maxM = 300) {
  let best = null;
  for (const s of spots || []) {
    const la = Number(s.lat), lo = Number(s.lon); if (!Number.isFinite(la) || !Number.isFinite(lo)) continue;
    const dy = (la - lat) * 111320, dx = (lo - lon) * 111320 * Math.cos((lat * Math.PI) / 180), d = Math.hypot(dx, dy);
    if (d <= maxM && (!best || d < best.d)) best = { spot: s, d };
  }
  return best;
}
export { dateOf, astro };

/** Soft plastics can be rigged several ways, and the rig is what the lure picks learn from — so a session lets you say
 *  how this one is rigged (the Roboworm sessions were drop shot but got logged as wacky; corrected 2026-11-10). */
export const SOFT_PLASTIC_RIGS = ["drop_shot", "wacky_rig_senko", "finesse_shaky_head", "texas_rig_worm", "texas_rig_creature", "carolina_rig", "weightless_soft_plastic"];
export const isSoftPlastic = (category) => SOFT_PLASTIC_RIGS.includes(category);
export const withRig = (row, category) => ({ ...row, conditions: { ...row.conditions, lure_category: category } });

/** When a session started: its saved start_time, else the earliest lure start (older rows didn't save start_time). */
export function sessionStartTime(rows) {
  const cs = rows.map((r) => parseConditions(r));
  return cs.find((c) => c.start_time)?.start_time || cs.map((c) => c.lure_start_time).filter(Boolean).sort()[0] || null;
}
