// Lure recommendations. Port of core/lures.py + core/lure_history.py + core/videos.py — keep in step with them.
// The data tables (profiles, colors, presentations, forage notes, videos) come straight from the Python via
// tools/export_lure_data.py → data/lures.data.json; only the decision logic is hand-ported (parity: lures.test.js).
import DATA from "./data/lures.data.json" with { type: "json" };
import { thermoclineCaveat } from "./onwater.js";
import { median, pyFixed, pyRound } from "./py.js";
import { parseConditions, tripFishPerHour } from "./calibration.js";

export const { BASE_STAIN_OPTIONS, DEFAULT_BASE_STAIN, WATER_CLARITY_OPTIONS, STRUCTURE_TYPES, FORAGE_OPTIONS, DEFAULT_FORAGE,
  FORAGE_NOTES, FORAGE_LURE_BOOST, LURE_PROFILES, VIDEO_LIBRARY } = DATA;
export const MAX_OWNED_ITEMS_PER_BLOCK = 2, MAX_RECOMMENDED_DISPLAY = 3, MAX_GAP_DISPLAY = 3;
export const LIGHT_LOW = new Set(["Dawn", "Dusk", "Night"]);
export const REACTION_BAIT_KEYS = ["walking_topwater", "buzzbait", "chatterbait", "swim_jig", "lipless_crankbait", "spinnerbait"];
export const FINESSE_BAIT_KEYS = ["finesse_shaky_head", "drop_shot", "wacky_rig_senko", "football_jig"];
export const WIND_REACTION_THRESHOLD_MPH = 10.0, STRONG_HISTORY_MIN_TRIPS = 3, STRONG_HISTORY_CATCH_RATE = 0.6;
export const LURE_CATEGORY_OPTIONS = Object.entries(LURE_PROFILES).map(([k, p]) => [k, p.name]);
const STRIKE_UP_OFFSET_FT = [1.0, 2.0];

export const resolveWaterClarity = (baseStain, stirredUp) => (stirredUp ? "Muddy" : BASE_STAIN_OPTIONS.includes(baseStain) ? baseStain : DEFAULT_BASE_STAIN);

// ---------------------------------------------------------------- Python value helpers
/** Python int(x or 0); returns `bad` where Python raises */
function pyIntOr(v, bad) {
  if (v == null || v === "" || v === 0 || v === false) return 0;
  if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : bad;
  if (v === true) return 1;
  return /^\s*[+-]?\d+\s*$/.test(String(v)) ? parseInt(v, 10) : bad;
}
/** Python float(x) for text, or null where it raises */
function pyFloat(v) {
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return v ? 1 : 0;
  const s = String(v).trim().toLowerCase();
  if (/^[+-]?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?$/.test(s)) return Number(s);
  if (/^[+-]?(inf|infinity)$/.test(s)) return s.startsWith("-") ? -Infinity : Infinity;
  if (/^[+-]?nan$/.test(s)) return NaN;
  return null;
}
/** Python str() of a number taken from the data */
const pyNum = (s) => s;

// ---------------------------------------------------------------- videos (core/videos.py)
function quotePlus(s) {
  return Array.from(new TextEncoder().encode(s), (b) => {
    const c = String.fromCharCode(b);
    if (/[A-Za-z0-9_.\-~]/.test(c)) return c;
    if (c === " ") return "+";
    return `%${b.toString(16).toUpperCase().padStart(2, "0")}`;
  }).join("");
}
const searchFallback = (q) => ({ title: `Search YouTube for "${q}"`, url: `https://www.youtube.com/results?search_query=${quotePlus(`${q} bass fishing how to`)}` });
export const getVideosByKey = (key, displayName = "") => VIDEO_LIBRARY[key] || [searchFallback(displayName || key.replace(/_/g, " "))];
export function getVideosFor(text) {
  const t = text.toLowerCase();
  for (const [kw, key] of DATA.VIDEO_KEYWORD_MAP) {
    if (t.includes(kw)) return key && VIDEO_LIBRARY[key] ? VIDEO_LIBRARY[key] : [searchFallback(text.split(" (")[0])];
  }
  return [searchFallback(text.split(" (")[0])];
}

// ---------------------------------------------------------------- your own history (core/lure_history.py)
const LIGHT_LOW_SEGMENTS = new Set(["Dawn", "Dusk", "Night"]);
export const MIN_SIMILAR_TRIPS = 2, ITEM_FISH_PER_HOUR_MIN_TRIPS = 2;
function situationMatch(row, c, sit) {
  let score = 0, loc = false;
  if (sit.spot_id && row.spot_id === sit.spot_id) { score += 3; loc = true; }
  if (sit.structure_type && row.structure_type === sit.structure_type) { score += 2; loc = true; }
  if (sit.water_clarity && row.water_clarity === sit.water_clarity) score += 1;
  if (sit.low_light != null && row.segment) { if (LIGHT_LOW_SEGMENTS.has(row.segment) === sit.low_light) score += 1; }
  if (sit.water_temp_f != null) { const t = c.water_temp_f; if ((typeof t === "number" || typeof t === "boolean") && Math.abs(Number(t) - sit.water_temp_f) <= 10.0) score += 1; }
  return [score, loc];
}
export const catchRate = (r) => (r.similar_trips ? r.trips_with_fish / r.similar_trips : 0.0);
/** {category: {lure_category, similar_trips, trips_with_fish, total_fish, biggest_fish_lb, catch_rate}} */
export function lureTrackRecords(rows, sit, minSimilar = MIN_SIMILAR_TRIPS) {
  const by = new Map();
  for (const row of rows || []) {
    const c = parseConditions(row), cat = c.lure_category;
    if (!cat) continue;
    if (!situationMatch(row, c, sit)[1]) continue;
    if (!by.has(cat)) by.set(cat, { similar_trips: 0, trips_with_fish: 0, total_fish: 0, biggest: null });
    const r = by.get(cat); r.similar_trips += 1;
    const fish = pyIntOr(row.fish_caught, 0);
    if (fish > 0) { r.trips_with_fish += 1; r.total_fish += fish; }
    const raw = row.biggest_fish_lb, big = raw == null || raw === "" ? null : pyFloat(raw);
    if (big != null && (r.biggest == null || big > r.biggest)) r.biggest = big;
  }
  const out = {};
  for (const [cat, r] of by) {
    if (r.similar_trips < minSimilar) continue;
    out[cat] = { lure_category: cat, similar_trips: r.similar_trips, trips_with_fish: r.trips_with_fish, total_fish: r.total_fish, biggest_fish_lb: r.biggest };
    out[cat].catch_rate = catchRate(out[cat]);
  }
  return out;
}
export function trackRecordNote(rec, inPlan) {
  const big = rec.biggest_fish_lb ? `, best ${pyFixed(rec.biggest_fish_lb, 1)} lb` : "";
  const bit = `${rec.trips_with_fish} of ${rec.similar_trips} similar trips landed fish${big}`;
  return inPlan ? `📈 Your own history: ${bit} - a real, situation-matched track record for you on this lure.`
    : `📈 Your own history: ${bit} on this lure in similar spots/conditions before - not currently a top seasonal pick, but a personally-proven option worth considering even if it's not in your tackle box yet.`;
}
export function itemFishPerHour(rows, sit, label, minTrips = ITEM_FISH_PER_HOUR_MIN_TRIPS) {
  if (!label || !(rows && rows.length && sit && Object.keys(sit).length)) return null;
  const want = label.trim(), rates = [];
  for (const row of rows) {
    if ((row.lure_used || "").trim() !== want) continue;
    if (!situationMatch(row, parseConditions(row), sit)[1]) continue;
    const r = tripFishPerHour(row); if (r != null) rates.push(r);
  }
  return rates.length < minTrips ? null : median(rates);
}

// ---------------------------------------------------------------- depth
function targetDepthForFish(d, style) {
  if (style === "bottom") return [Math.max(0.0, d - 1), d];
  return [pyRound(Math.max(0.0, d - STRIKE_UP_OFFSET_FT[1]), 1), pyRound(Math.max(0.5, d - STRIKE_UP_OFFSET_FT[0]), 1)];
}
function depthMatchScore(p, d) {
  const [lo, hi] = p.depth_range_ft, style = p.vertical_style || "column";
  if (lo === 0 && hi === 0) return Math.max(0.0, d - 3);
  const [tlo, thi] = targetDepthForFish(d, style);
  if ((lo <= tlo && tlo <= hi) || (lo <= thi && thi <= hi) || (tlo <= lo && thi >= hi)) return 0.0;
  return Math.min(Math.abs(tlo - lo), Math.abs(tlo - hi), Math.abs(thi - lo), Math.abs(thi - hi));
}
function depthText(p, d = null) {
  const [lo, hi] = p.depth_range_ft, [loS, hiS] = p.depth_range_str, surface = lo === 0 && hi === 0;
  const base = surface ? (p.depth_style ? `Surface, ${p.depth_style}` : "Surface") : `${pyNum(loS)}-${pyNum(hiS)} ft, ${p.depth_style}`;
  if (d == null) return base;
  const f0 = (x) => pyFixed(x, 0);
  if (surface) return d > 6 ? `${base} (you're marking fish deeper, around ${f0(d)} ft - bass can rise several feet for topwater, but the bite gets tougher the deeper they're holding)`
    : `${base} (matches the shallow fish you're marking - bass strike up, so this is a good call)`;
  const style = p.vertical_style || "column";
  if (style === "bottom") {
    const [tlo, thi] = targetDepthForFish(d, style);
    if (lo <= d && d <= hi) return `${base} - count it down to about ${f0(tlo)}-${f0(thi)} ft before working it, right where you're marking fish`;
    if (d < lo) return `${base} - you're marking fish shallower (~${f0(d)} ft); don't let it fall all the way to bottom, work it in that upper zone instead`;
    return `${base} - you're marking fish deeper (~${f0(d)} ft); let it settle longer before working it`;
  }
  const [tlo, thi] = targetDepthForFish(d, style);
  if (d <= 2) return `${base} - fish are shallow; run this right at/just above their level`;
  if ((lo <= tlo && tlo <= hi) || (lo <= thi && thi <= hi)) return `${base} - target ~${f0(tlo)}-${f0(thi)} ft (1-2 ft above the ${f0(d)} ft you're marking - bass strike up more readily than down)`;
  if (d < lo) return `${base} - you're marking fish shallower (~${f0(d)} ft) than this bait's usual zone; slow down/shorten your count-down to get up in range`;
  return `${base} - you're marking fish deeper (~${f0(d)} ft); this bait tops out at ${f0(hi)} ft, so let it sink/slow-roll deeper, or lean on a deeper-running option instead`;
}

// ---------------------------------------------------------------- owned tackle
const STOP = new Set(["and", "the", "with", "back", "belly", "pattern", "skirt", "tip", "solid", "trailer", "blade", "tail"]);
const colorTokens = (t) => new Set(t ? (t.toLowerCase().match(/[a-z]+/g) || []).filter((w) => w.length >= 3 && !STOP.has(w)) : []);
function splitOwnedByColor(items, colors) {
  const want = new Set(); for (const c of colors) for (const w of colorTokens(c)) want.add(w);
  const matched = [], other = [];
  for (const it of items) { const tk = colorTokens(it.description || ""); ([...tk].some((w) => want.has(w)) ? matched : other).push(it); }
  return [matched, other];
}
export function itemLabel(it) {
  const label = [(it.brand || "").trim(), (it.description || "").trim()].filter(Boolean).join(" - ");
  return label || it.item_id || "";
}
function groupOwnedByCategory(inventory) {
  const g = {};
  for (const row of inventory || []) {
    const cat = (row.category || "").trim();
    if (!(cat in LURE_PROFILES)) continue;
    const qty = pyIntOr(row.quantity, 0);
    if (qty <= 0) continue;
    (g[cat] ||= []).push({ item_id: row.item_id ?? "", brand: row.brand ?? "", description: row.description ?? "", quantity: qty,
      sku: row.sku ?? "", image_url: row.image_url ?? "", image_filename: row.image_filename ?? "" });
  }
  return g;
}
export const findInventoryGaps = (inv) => { const o = groupOwnedByCategory(inv); return Object.keys(LURE_PROFILES).filter((k) => !(k in o)); };

function buildBlock(key, clarity, fishDepth = null, { note = "", owned = null, why = null, history = null, situation = null } = {}) {
  const p = LURE_PROFILES[key];
  const colors = p.colors[clarity] || p.colors[DEFAULT_BASE_STAIN];
  const trailer = p.trailer ? { type: p.trailer.type, colors: p.trailer.colors[clarity] || p.trailer.colors[DEFAULT_BASE_STAIN] } : null;
  const [matched, offColor] = owned ? splitOwnedByColor(owned, colors) : [[], []];
  for (const it of matched) it._item_fish_per_hour = history && history.length && situation ? itemFishPerHour(history, situation, itemLabel(it)) : null;
  const k = (it) => [it._item_fish_per_hour != null ? 1 : 0, it._item_fish_per_hour || 0.0];
  matched.sort((a, b) => { const [a1, a2] = k(a), [b1, b2] = k(b); return b1 - a1 || b2 - a2; });
  return { key, name: p.name, colors, trailer, depth: depthText(p, fishDepth), presentation: p.presentation,
    videos: getVideosByKey(p.video_key, p.name), note, owned_items: matched.slice(0, MAX_OWNED_ITEMS_PER_BLOCK),
    owned_off_color_items: offColor, why: [...(why || []), `Colors shown are Nolin's documented picks for ${clarity.toLowerCase()} water.`],
    get owned() { return this.owned_items.length > 0; } };
}

function promoteReaction(first, second, why, reason, lowLight) {
  const add = (k) => (why[k] ||= []).push(reason);
  const ef = REACTION_BAIT_KEYS.find((k) => first.includes(k));
  if (ef) return add(ef);
  const es = REACTION_BAIT_KEYS.find((k) => second.includes(k));
  if (es) { second.splice(second.indexOf(es), 1); first.unshift(es); return add(es); }
  const pick = lowLight ? "walking_topwater" : "chatterbait"; first.unshift(pick); add(pick);
}
function promoteFinesse(first, second, why, reason) {
  const e = FINESSE_BAIT_KEYS.find((k) => first.includes(k) || second.includes(k));
  if (e) { (why[e] ||= []).push(reason); return; }
  second.unshift("finesse_shaky_head"); (why.finesse_shaky_head ||= []).push(reason);
}

const SEASON_PLANS = {
  winter: [["suspending_jerkbait", "medium_diving_crankbait", "football_jig"], ["soft_swimbait", "blade_bait", "deep_diving_crankbait"],
    "Part of Nolin's documented winter pattern (rock/channel-swing structure, long-pause jerkbaits, 7-12 ft cranks).",
    "Cold water (<50F) - Nolin's own documented winter pattern (Omnia Fishing) targets rock piles/boulders near channel swings and deep-access points with long-pause jerkbaits and 7-12 ft crankbaits; a local Nolin guide's own paid tip content is literally titled 'Winter time cranking.'"],
  pre_spawn: [["medium_diving_crankbait", "texas_rig_worm", "lipless_crankbait"], ["squarebill_crankbait", "chatterbait", "football_jig"],
    "Part of Nolin's documented pre-spawn pattern (rip-rap/creek mouths, 7-12 ft cranks, Texas rigs).",
    "Pre-spawn (50-60F) - Nolin's documented pattern (Omnia Fishing) is rip-rap with stumps/laydowns and creek mouths with chunk rock, worked with 7-12 ft crankbaits and Texas rigs as fish stage before the move shallow."],
  spawn: [["texas_rig_creature", "finesse_shaky_head", "squarebill_crankbait"], ["wacky_rig_senko", "weightless_soft_plastic"],
    "Part of Nolin's documented spawn-window pattern (shallow bays/coves near rip-rap, Texas rigs pitched/flipped to cover).",
    "Spawn window (60-75F) - Nolin's documented pattern (Omnia Fishing) is protected shallow bays/coves with hard bottom near rip-rap, pitched/flipped with Texas rigs and shakey heads."],
  post_spawn_summer: [["finesse_shaky_head", "walking_topwater", "soft_swimbait"], ["spinnerbait", "swim_jig", "texas_rig_worm"],
    "Part of Nolin's documented post-spawn pattern (stumps/rip-rap near bridges, shakey heads/topwater/swimbaits as fish move toward summer haunts).",
    "Post-spawn recovery - Nolin's documented pattern (Omnia Fishing) is stumps/woody cover and rip-rap near bridges, worked with shakey heads, walking topwater, and small/medium swimbaits as fish move from spawning flats toward summer haunts."],
  fall_feed_up: [["popper", "texas_rig_worm", "buzzbait"], ["drop_shot", "squarebill_crankbait", "spinnerbait"],
    "Part of Nolin's documented fall feed-up pattern (laydowns/bluff walls, popping topwater/Texas rigs/drop shot as bass chase shad shallow).",
    "Fall feed-up - Nolin's documented pattern (Omnia Fishing) is laydowns/timber in pockets and bluff walls with woody cover, worked with popping topwater, Texas rigs, and drop shot as shad move shallow/into creeks and bass feed aggressively to follow."],
  late_fall: [["suspending_jerkbait", "medium_diving_crankbait", "soft_swimbait"], ["football_jig", "blade_bait", "lipless_crankbait"],
    "Part of a general late-fall pattern (bass following shad into creek arms and onto secondary points before winter).",
    "Late fall (post-turnover, ~50-58F) - bass group up on shad in creek arms and on secondary points before winter; jerkbaits, mid-depth cranks and swimbaits around bait, with a jig or blade bait when they slow down. This is a general late-fall approach, not a Nolin-specific published pattern."],
  fall_turnover: [["football_jig", "suspending_jerkbait", "blade_bait"], ["drop_shot", "lipless_crankbait", "deep_diving_crankbait"],
    "Fall turnover - oxygen/temp mixing makes bass location and mood unpredictable, so this leans on a spread of dependable options rather than one documented pattern.",
    "Fall turnover - oxygen/temp mixing makes bass location and mood unpredictable; added drop shot as a second choice for scattered, suspended fish (same deep-structure pattern that works Nolin's bluff walls/dam points per real angler reports, not turnover-specific on its own)."],
};
const STRUCTURE_NOTES = {
  "Main-lake point": "Fan-cast the point from shallow to deep, focus on the fastest breakline.",
  "Creek channel / ledge": "Idle/graph to find the ledge lip, then work baits parallel to it.",
  "Cove / pocket (shallow cover)": "Target isolated wood, laydowns, and grass clumps inside the cove.",
  "Flat": "Cover water efficiently - flats reward moving baits (spinnerbait, swim jig, crank).",
  "Standing timber": "Vertical presentations (jig, drop shot) worked tight to individual trees.",
  "Riprap / dam face": "Parallel casts down the rock, crawl a jig or crank to deflect off rip-rap. A real Nolin angler report also specifically describes bluff walls with channels nearby and deep points along the dam (~45 ft) as a drop-shot pattern for fish that won't commit to anything faster.",
  "Bridge piling": "Cast tight to pilings/riprap transitions; vertical jig the shady side.",
  "Boat dock": "Skip a jig or wacky worm under the dock into the shade line.",
};

/** The lure plan: {first_choice: [block], second_choice: [block], rationale: [text]}. */
export function recommend({ season, water_temp_f, segment_name, pressure_trend_24h, structure_type = "Main-lake point", water_clarity = "Brown stained",
  fish_depth_ft = null, forage = null, thermocline_ft = null, inventory = null, trip_history = null, spot_id = null,
  fish_activity = null, forage_activity = null, wind_mph = null }) {
  const lowLight = LIGHT_LOW.has(segment_name), rationale = [], why = {};
  if (fish_depth_ft != null) rationale.push(`You're marking fish around ${pyFixed(fish_depth_ft, 0)} ft - bass have upward-biased vision and an upward-hinging jaw, so they strike up more readily than down. Reaction/moving baits below are re-ordered and targeted to run 1-2 ft above that reading; bottom baits are targeted to count down to it.`);
  const caveat = thermoclineCaveat(thermocline_ft, fish_depth_ft);
  if (caveat) rationale.push(caveat);
  let first, second, seasonReason;
  if (season === "summer_peak") {
    if (lowLight) {
      first = ["walking_topwater", "buzzbait", "weightless_soft_plastic"]; second = ["popper", "swim_jig", "squarebill_crankbait"];
      seasonReason = "Low-light dawn/dusk window in summer - a real Nolin angler report specifically describes topwater 'jumps' with poppers and flukes at this time.";
      if (segment_name === "Night") rationale.push("KDFWR's own 2026 official Fishing Forecast calls out Nolin by name: 'During late spring through summer, best results are often at night' - the same real angler report also notes night fishing is productive here in summer.");
    } else {
      first = ["football_jig", "deep_diving_crankbait", "carolina_rig"]; second = ["drop_shot", "suspending_jerkbait", "lipless_crankbait"];
      seasonReason = "Part of Nolin's documented summer pattern (deep points/rock structure, deep cranks/football jigs/Carolina rigs).";
    }
    rationale.push("Summer heat - Nolin's documented pattern (Omnia Fishing) is main-lake points with deep-water access and rock structure, worked with 13 ft+ crankbaits, football jigs, and Carolina rigs outside low light.");
  } else {
    const plan = SEASON_PLANS[season] || SEASON_PLANS.fall_turnover;
    first = [...plan[0]]; second = [...plan[1]]; seasonReason = plan[2]; rationale.push(plan[3]);
  }
  for (const k of new Set([...first, ...second])) (why[k] ||= []).push(seasonReason);
  if (structure_type in STRUCTURE_NOTES) rationale.push(STRUCTURE_NOTES[structure_type]);
  const has = (keys) => keys.some((k) => first.includes(k) || second.includes(k));
  if (!has(["squarebill_crankbait", "lipless_crankbait", "deep_diving_crankbait", "medium_diving_crankbait"])
    && ["Riprap / dam face", "Bridge piling", "Flat", "Main-lake point", "Creek channel / ledge"].includes(structure_type) && season !== "winter") {
    const pick = water_temp_f >= 60 ? "squarebill_crankbait" : "lipless_crankbait";
    second.push(pick); (why[pick] ||= []).push(`Added - crankbaits are broadly effective on ${structure_type.toLowerCase()} structure regardless of season.`);
  }
  if (!has(["buzzbait", "walking_topwater", "popper", "hollow_body_frog"]) && lowLight && ["post_spawn_summer", "summer_peak", "fall_feed_up", "spawn"].includes(season)) {
    second.push("walking_topwater"); (why.walking_topwater ||= []).push("Added - worth a look in this low-light dawn/dusk window even outside its primary season.");
  }
  if (!first.includes("suspending_jerkbait") && !second.includes("suspending_jerkbait") && water_temp_f <= 68 && ["Clear", "Green stained", "Brown stained"].includes(water_clarity)) {
    second.push("suspending_jerkbait"); (why.suspending_jerkbait ||= []).push(`Added - jerkbaits shine in ${water_clarity.toLowerCase()} water under 68°F.`);
  }
  if (pressure_trend_24h <= -1.5) rationale.push("Falling pressure - bass are often more aggressive; reaction baits can shine.");
  else if (pressure_trend_24h >= 2.0) {
    if (!second.includes("finesse_shaky_head") && !first.includes("finesse_shaky_head")) second.unshift("finesse_shaky_head");
    (why.finesse_shaky_head ||= []).push("Added - high, stable pressure after a front usually means a tougher, slower bite.");
    rationale.push("High, stable pressure after a front - added a finesse bait for a tougher bite.");
  }
  if (forage && forage.length) {
    const boost = [];
    for (const f of forage) for (const k of FORAGE_LURE_BOOST[f] || []) if (!boost.includes(k)) boost.push(k);
    const covered = new Set([...first, ...second]);
    for (const k of boost) if (!covered.has(k)) { second.unshift(k); (why[k] ||= []).push(`Added to match forage you reported seeing (${forage.join(", ")}).`); break; }
    const notes = forage.filter((f) => f in FORAGE_NOTES).map((f) => FORAGE_NOTES[f]);
    if (notes.length) rationale.push(notes.join(" "));
  }
  if (fish_depth_ft != null && fish_depth_ft >= 6 && fish_depth_ft <= 12 && !first.includes("medium_diving_crankbait") && !second.includes("medium_diving_crankbait")) {
    for (const list of [first, second]) {
      const i = list.findIndex((k) => k === "squarebill_crankbait" || k === "deep_diving_crankbait");
      if (i >= 0) { list[i] = "medium_diving_crankbait"; (why.medium_diving_crankbait ||= []).push(`Swapped in - matches your ${pyFixed(fish_depth_ft, 0)} ft sonar reading better than the season's default crank depth.`); break; }
    }
  }
  const seen = new Set(), f1 = [], s1 = [];
  for (const k of first) if (!seen.has(k)) { f1.push(k); seen.add(k); }
  for (const k of second) if (!seen.has(k)) { s1.push(k); seen.add(k); }
  if (fish_depth_ft != null) {
    const by = (a, b) => depthMatchScore(LURE_PROFILES[a], fish_depth_ft) - depthMatchScore(LURE_PROFILES[b], fish_depth_ft);
    f1.sort(by); s1.sort(by);
  }
  const react = [];
  if (fish_activity === "Very active" || fish_activity === "Active") react.push(`fish activity was reported as ${fish_activity.toLowerCase()}`);
  if (forage_activity === "Active / schooling" || forage_activity === "Frenzied (busting bait)") react.push(`forage activity was reported as ${forage_activity.toLowerCase()}`);
  if (wind_mph != null && wind_mph >= WIND_REACTION_THRESHOLD_MPH) react.push(`wind is up around ${pyFixed(wind_mph, 0)} mph`);
  if (react.length) promoteReaction(f1, s1, why, `Moved to first choice - ${react.join(" and ")}; active fish and wind-chopped water both favor a fast, reaction bite.`, lowLight);
  const slow = [];
  if (fish_activity === "Sluggish" || fish_activity === "Inactive / shut down") slow.push(`fish activity was reported as ${fish_activity.toLowerCase()}`);
  if (forage_activity === "None seen") slow.push("no forage activity was seen");
  if (slow.length) promoteFinesse(f1, s1, why, `Added - ${slow.join(" and ")}; a slower, subtler presentation is worth a look.`);

  const situation = { spot_id, structure_type, water_clarity, low_light: lowLight, water_temp_f };
  const notes = {};
  if (trip_history && trip_history.length) {
    const recs = lureTrackRecords(trip_history, situation), picked = new Set([...f1, ...s1]);
    for (const k of picked) if (recs[k]) notes[k] = trackRecordNote(recs[k], true);
    const inject = Object.entries(recs).filter(([k, r]) => !picked.has(k) && r.trips_with_fish > 0).map(([, r]) => r)
      .sort((a, b) => b.catch_rate - a.catch_rate || b.similar_trips - a.similar_trips);
    for (const r of inject.slice(0, 2)) { s1.unshift(r.lure_category); notes[r.lure_category] = trackRecordNote(r, false); }
    const strong = Object.entries(recs).filter(([, r]) => r.similar_trips >= STRONG_HISTORY_MIN_TRIPS && r.catch_rate >= STRONG_HISTORY_CATCH_RATE);
    if (strong.length && f1.length) {
      let [bestKey, best] = strong[0];
      for (const [k, r] of strong) if (r.catch_rate > best.catch_rate || (r.catch_rate === best.catch_rate && r.similar_trips > best.similar_trips)) { bestKey = k; best = r; }
      if (f1[0] !== bestKey) {
        if (f1.includes(bestKey)) f1.splice(f1.indexOf(bestKey), 1); else if (s1.includes(bestKey)) s1.splice(s1.indexOf(bestKey), 1);
        f1.unshift(bestKey);
        (why[bestKey] ||= []).push("Promoted to your top pick - the strongest situation-matched track record in your trip log right now.");
        notes[bestKey] = `📈 Promoted to your top pick: ${best.trips_with_fish} of ${best.similar_trips} similar trips landed fish - your strongest real track record for this exact situation.`;
      }
    }
  }
  const owned = groupOwnedByCategory(inventory);
  const mk = (k) => buildBlock(k, water_clarity, fish_depth_ft, { note: notes[k] || "", owned: owned[k] || null, why: why[k] || null, history: trip_history, situation });
  const first_choice = f1.map(mk), second_choice = s1.map(mk);
  if (Object.keys(owned).length) { const o = (a, b) => (b.owned ? 1 : 0) - (a.owned ? 1 : 0); first_choice.sort(o); second_choice.sort(o); }
  return { first_choice, second_choice, rationale };
}

/** Top owned picks for today + the best not-owned "gaps", in the same ranking. */
export function curateRecommendation(rec, inventory = null) {
  const ranked = [...new Set([...rec.first_choice, ...rec.second_choice].map((b) => b.key))];
  const byKey = {}; for (const b of [...rec.first_choice, ...rec.second_choice]) byKey[b.key] = b;
  const gaps = new Set(findInventoryGaps(inventory));
  return { recommended: ranked.filter((k) => !gaps.has(k)).slice(0, MAX_RECOMMENDED_DISPLAY).map((k) => byKey[k]),
    gaps: ranked.filter((k) => gaps.has(k)).slice(0, MAX_GAP_DISPLAY).map((k) => byKey[k]), rationale: rec.rationale };
}

export function guessCategoryFromText(...texts) {
  const combined = texts.filter(Boolean).join(" ").toLowerCase();
  if (!combined) return "";
  for (const [cat, phrases] of DATA.CATEGORY_KEYWORD_RULES) if (phrases.some((p) => combined.includes(p))) return cat;
  return "";
}
const TRAILER_ELIGIBLE = new Set(["texas_rig_creature", "weightless_soft_plastic"]);
export function isTrailerEligible(item) {
  if (!TRAILER_ELIGIBLE.has(item.category)) return false;
  const t = `${item.brand ?? ""} ${item.description ?? ""}`.toLowerCase();
  return !["worm", "senko", "trd", "stick bait", "stickbait"].some((k) => t.includes(k));
}
