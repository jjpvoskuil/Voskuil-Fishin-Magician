// Spot Session rules: what starting, logging a fish, changing/adding a lure, moving, ending and canceling save.
// Port of pages/6_Spot_Session.py's data logic (the rows are the same shape as the old trip_log.csv), with the
// 11-10 speed-ups John approved: conditions pre-filled (each field tagged with where its value came from in
// conditions.field_sources), GPS spot pick, "same lures as last time", quick fish logging, edit-while-fishing.
// One trip row per lure fished; a session is open while any of its rows has no lure_end_time.
import * as astro from "./astro.js";
import { cloudProxyForLightCondition, lightConditionForCloudPct, precipitationOptionForForecast, precipitationProxy,
  resolveWaterClarity, windBand, windDirectionForDegrees, windMphForBand } from "./onwater.js";
import { dayOfYear, dateOf, isoNaive, parseIso, parts } from "./py.js";
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
export const SOFT_PLASTIC_RIGS = ["drop_shot", "ned_rig", "wacky_rig_senko", "finesse_shaky_head", "texas_rig_worm", "texas_rig_creature", "carolina_rig", "weightless_soft_plastic"];
export const isSoftPlastic = (category) => SOFT_PLASTIC_RIGS.includes(category);
export const withRig = (row, category) => ({ ...row, conditions: { ...row.conditions, lure_category: category } });

/** When a session started: its saved start_time, else the earliest lure start (older rows didn't save start_time). */
export function sessionStartTime(rows) {
  const cs = rows.map((r) => parseConditions(r));
  return cs.find((c) => c.start_time)?.start_time || cs.map((c) => c.lure_start_time).filter(Boolean).sort()[0] || null;
}

/* ---------------------------------------------------------------- fishing together (John 11-10)
 * Anglers in the same boat share one set of conditions. A session joins another by storing that session's id as its
 * conditions.group_id; the group is the anchor session plus every open session pointing at it. Every start, move or
 * conditions change stamps conditions_set_at; each member's phone follows the newest change in the group. */
const COND_KEYS = Object.keys(CONDITION_FIELDS);
export const groupIdOf = (rows) => (rows?.length ? sessionConditions(rows[rows.length - 1]).group_id || null : null);

/** Other open sessions in my group (or that I could be grouped with by id). */
export function groupMembers(trips, mySessionId, groupId) {
  if (!groupId) return [];
  return openSessions(trips).filter((s) => s.key !== mySessionId && (s.key === groupId || s.rows.some((r) => parseConditions(r).group_id === groupId)));
}

/** The current conditions of an open session: its open lures' shared fields + spot + when they were set. */
export function currentConditions(s) {
  const open = s.rows.filter((r) => !parseConditions(r).lure_end_time), r = open[open.length - 1] || s.rows[s.rows.length - 1], c = sessionConditions(r);
  return { values: Object.fromEntries(COND_KEYS.map((k) => [k, c[k] ?? CONDITION_FIELDS[k]])), set_at: c.conditions_set_at || `${r.trip_date}T${c.start_time || "00:00:00"}`,
    spot_id: r.spot_id, spot_name: r.spot_name, angler: s.angler, group_id: c.group_id || null, session_id: s.key };
}

/** The newest conditions among group members, or null. */
export function newestInGroup(members) {
  let best = null;
  for (const m of members) { const c = currentConditions(m); if (!best || c.set_at > best.set_at) best = c; }
  return best;
}

/** Same conditions and spot? (then following would change nothing) */
export function sameConditions(a, b) {
  return a.spot_id === b.spot_id && COND_KEYS.every((k) => JSON.stringify(a.values[k] ?? null) === JSON.stringify(b.values[k] ?? null));
}

/** Move/condition change for an open session (old _relocate_active_session): small fixes in the first 10 minutes of the
 *  current lures update them in place; otherwise current lures are closed and reopened under the new conditions, so
 *  every row's conditions stay true for the time it covers. Returns {next, changed}. */
export function relocateRows(rows, { newBase, spot, structure, clarity, segment, predicted, owner, now }) {
  const open = rows.filter((r) => !r.conditions.lure_end_time);
  const young = open.every((r) => now - parseIso(`${r.trip_date}T${r.conditions.lure_start_time.slice(0, 8)}`) < 10 * 60e6);
  if (spot.spot_id === open[0]?.spot_id && young) {
    const changed = open.map((r) => ({ ...r, segment, water_clarity: clarity, predicted_score: predicted,
      conditions: { ...newBase, ...Object.fromEntries(Object.entries(r.conditions).filter(([k]) => PER_LURE_KEYS.has(k) || k === "item_id")) } }));
    return { next: rows.map((r) => changed.find((c) => c.trip_id === r.trip_id) || r), changed };
  }
  const closed = open.map((r) => retireRow(r, now));
  const reopened = open.map((r) => lureRow({ base: newBase, lure: { label: r.lure_used, category: r.conditions.lure_category, item_id: r.conditions.item_id,
    trailer: r.conditions.trailer_used ? { label: r.conditions.trailer_name, color: r.conditions.trailer_color, category: r.conditions.trailer_category } : null },
    at: now, session: { id: r.session_id, date: r.trip_date }, spot, structure, clarity, segment, predicted, owner }));
  return { next: [...rows.map((r) => closed.find((c) => c.trip_id === r.trip_id) || r), ...reopened], changed: [...closed, ...reopened] };
}

/** How someone's open session is going (Today card, Watch view, the line in your own live session). now = naive µs. */
export function liveSummary(s, now) {
  const rows = s.rows, cs = rows.map(parseConditions), cur = currentConditions(s);
  const fish = rows.flatMap((r, i) => (Array.isArray(cs[i].fish) ? cs[i].fish.map((f) => ({ ...f, lure: r.lure_used, category: cs[i].lure_category })) : []))
    .sort((a, b) => (b.caught_at || "").localeCompare(a.caught_at || ""));
  const total = fish.reduce((a, f) => a + (f.count || 1), 0), weights = fish.map((f) => Number(f.weight_lb) || 0);
  const start = cs.find((c) => c.start_time)?.start_time || cs.map((c) => c.lure_start_time).filter(Boolean).sort()[0] || "00:00:00";
  const mins = Math.max(0, Math.round((now - parseIso(`${rows[0].trip_date}T${start.slice(0, 8)}`)) / 60e6));
  const lures = rows.map((r, i) => ({ label: r.lure_used, category: cs[i].lure_category, fish: Number(r.fish_caught) || 0, open: !cs[i].lure_end_time,
    from: cs[i].lure_start_time, to: cs[i].lure_end_time }));
  const spots = [...new Set(rows.map((r) => r.spot_name).filter(Boolean))];
  return { key: s.key, angler: s.angler || "Someone", owner: s.owner, spot: cur.spot_name, spots, start, mins, total, biggest: Math.max(0, ...weights) || null,
    perHour: mins >= 15 ? total / (mins / 60) : null, latest: fish[0] || null, fish, lures, cond: cur.values, segment: rows[rows.length - 1].segment,
    predicted: rows[rows.length - 1].predicted_score, grouped: !!cur.group_id && !cur.group_id.startsWith("solo:") };
}
export const durationText = (mins) => (mins >= 60 ? `${Math.floor(mins / 60)} h ${mins % 60} m` : `${mins} m`);
