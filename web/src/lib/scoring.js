// Bass activity score (1-10) per time-of-day segment and per day. Port of core/scoring.py — keep in step with it;
// parity tests in engine.test.js compare against fixtures generated from the Python (tools/make_engine_fixtures.py).
// Breakdown rows are [label, delta, detail], exactly as the Python builds them.
import * as astro from "./astro.js";
import { waterTempBand } from "./onwater.js";
import { DAY, HOUR, addDays, at, clamp, dayOfYear, pmod, pyFixed, pyRound, pySum, tdDiv, titleWords } from "./py.js";
import { LAKE_LAT, LAKE_LON, LAKE_TZ_UTC_OFFSET_HOURS, dailyRowForDate, estimateWaterTempF, hourlyRowsForDate, lakeNowNaive, pressureTrendHpaPer24h } from "./weather.js";

export const SEGMENTS = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"];
export const DEFAULT_WEIGHTS = {
  pressure_falling: 1.5, pressure_high_stable_post_front: -1.5, pressure_rising_slow: -0.4,
  moon_new_full_bonus: 0.6, moon_quarter_penalty: -0.5, moon_dawn_new_bonus: 0.85, moon_dawn_full_penalty: -0.5,
  cloud_overcast_bonus: 1.0, cloud_clear_sky_penalty: -0.8, wind_sweet_spot_bonus: 0.5, wind_calm_or_high_penalty: -0.5,
  season_spring_fall_bonus: 1.3, season_summer_midday_penalty: -1.5, season_winter_penalty: -1.0, storm_penalty: -3.0,
  solunar_major_bonus: 0.6, solunar_minor_bonus: 0.3, precip_light_rain_bonus: 0.6,
  water_temp_cold_penalty: -1.0, water_temp_prespawn_bonus: 0.3, water_temp_prime_bonus: 1.0, water_temp_hot_floor_penalty: -1.5,
  water_clarity_stained_bonus: 0.4, water_clarity_muddy_penalty: -0.3, forage_present_bonus: 0.3,
};
export const WATER_TEMP_HOT_START_F = 80.0, WATER_TEMP_HOT_FLOOR_F = 93.0;
const STORM_WARNING = "Storms/heavy rain possible - check local radar and lightning before heading out.";

function waterTempHotPenalty(t, w) {
  if (t <= WATER_TEMP_HOT_START_F) return 0.0;
  const frac = Math.min(1.0, (t - WATER_TEMP_HOT_START_F) / (WATER_TEMP_HOT_FLOOR_F - WATER_TEMP_HOT_START_F));
  return pyRound(w.water_temp_hot_floor_penalty * frac, 3);
}
function dawnMoonIlluminationDelta(moon, w) {
  const illum = astro.illuminationPctForAge(pmod(moon.age_days - 1.0, astro.SYNODIC_MONTH));
  const bonus = w.moon_dawn_new_bonus, penalty = w.moon_dawn_full_penalty;
  const d = pyRound(bonus - (bonus - penalty) * (illum / 100.0), 3);
  return [d, `Moon was ~${pyFixed(illum, 0)}% illuminated last night - dawn/morning activity has tracked better on darker nights this season.`];
}

export function seasonStage(doy, t) {
  if (t < 50) return "winter";
  if (t >= 50 && t < 60) return "pre_spawn";
  if (t >= 60 && t < 75 && doy >= 60 && doy <= 150) return "spawn";
  if (t >= 80) return "summer_peak";
  if (t >= 75 && t < 80) return "post_spawn_summer";
  if (t < 65 && doy > 250) return "fall_turnover";
  return "fall_feed_up";
}
export function effectiveSeasonAndTemp(day, override = null) {
  if (override == null) return [day.season, day.water_temp_f];
  return [seasonStage(dayOfYear(day.the_date), override), override];
}

/** [name, start, end] in naive µs for one day's six windows. */
export function segmentWindows(sunrise, sunset) {
  const dawnStart = sunrise - HOUR, dawnEnd = sunrise + HOUR, duskStart = sunset - HOUR, duskEnd = sunset + HOUR;
  const third = tdDiv(duskStart - dawnEnd, 3);
  const morningEnd = dawnEnd + third, middayEnd = dawnEnd + 2 * third;
  return [["Dawn", dawnStart, dawnEnd], ["Morning", dawnEnd, morningEnd], ["Midday", morningEnd, middayEnd],
    ["Afternoon", middayEnd, duskStart], ["Dusk", duskStart, duskEnd], ["Night", duskEnd, dawnStart + DAY]];
}
const overlaps = (a0, a1, b0, b1) => a0 < b1 && b0 < a1;
const clamp10 = (v) => clamp(v, 1.0, 10.0);

/** Day overall = each factor's delta averaged across all segments (not the segment scores averaged). */
export function aggregateDayOverall(segments) {
  if (!segments.length) return [5.0, []];
  const n = segments.length, sums = new Map(), counts = new Map();
  for (const seg of segments) for (const [label, delta] of seg.breakdown) {
    if (!sums.has(label)) { sums.set(label, 0.0); counts.set(label, 0); }
    sums.set(label, sums.get(label) + delta); counts.set(label, counts.get(label) + 1);
  }
  const breakdown = []; let raw = 0.0;
  for (const [label, sum] of sums) {
    const avg = pyRound(sum / n, 2); raw += avg;
    const k = counts.get(label);
    breakdown.push([label, avg, k === n ? `Applied consistently across all ${n} time-of-day windows today.`
      : `Averaged across all ${n} time-of-day windows today - only actually applied in ${k} of them.`]);
  }
  return [pyRound(clamp10(raw), 1), breakdown];
}

export function segmentScore(name, pTrend, moon, overlap, avgCloud, avgWind, season, totalPrecip, maxPrecipProb, w,
  { water_temp_f = null, water_clarity = null, forage_present = null, location_adjustment = 0.0, location_adjustment_n = null } = {}) {
  let score = 5.0; const notes = [], breakdown = [["Base", 5.0, "Starting point before any factors below."]];
  const add = (label, d, note, show = true) => { score += d; if (show) notes.push(note); breakdown.push([label, d, note]); };
  if (pTrend <= -1.5) add("Pressure trend", w.pressure_falling, "Falling pressure ahead of a front - bite often turns on.");
  else if (pTrend >= 2.0) add("Pressure trend", w.pressure_high_stable_post_front, "High, rising pressure post-front - expect a tougher, slower bite.");
  else if (0.3 < pTrend && pTrend < 2.0) add("Pressure trend", w.pressure_rising_slow, "Slowly rising pressure.", false);
  if (name === "Dawn" || name === "Morning") { const [d, note] = dawnMoonIlluminationDelta(moon, w); if (d !== 0) add("Moon phase", d, note); }
  else if (moon.is_new_or_full_window) add("Moon phase", w.moon_new_full_bonus, `${moon.name} - near new/full moon, per solunar lore (mixed real-world evidence).`);
  else if (moon.is_quarter_window) add("Moon phase", w.moon_quarter_penalty, `${moon.name} - near a quarter moon, traditionally the slowest solunar window.`);
  if (overlap === "major") add("Solunar", w.solunar_major_bonus, "Overlaps a solunar major period.");
  else if (overlap === "minor") add("Solunar", w.solunar_minor_bonus, "Overlaps a solunar minor period.");
  if (avgCloud >= 60) add("Cloud cover", w.cloud_overcast_bonus, "Overcast skies - fish often roam and feed more actively/shallow.");
  else if (avgCloud <= 25) add("Cloud cover", w.cloud_clear_sky_penalty, "Clear/bright ('bluebird') skies - classic tough-bite pattern, especially midday.");
  if (avgWind >= 4 && avgWind <= 14) add("Wind", w.wind_sweet_spot_bonus, "Light-moderate wind/chop - good for reaction baits and windblown banks.");
  else if (avgWind < 2 || avgWind > 20) add("Wind", w.wind_calm_or_high_penalty, "Dead calm or very strong wind.", false);
  if (["spawn", "pre_spawn", "fall_feed_up"].includes(season)) add("Season", w.season_spring_fall_bonus, `${titleWords(season)} - typically more active feeding.`, false);
  if (season === "summer_peak" && (name === "Midday" || name === "Afternoon")) add("Season", w.season_summer_midday_penalty, "Summer heat - fish likely pushed to deeper, cooler structure midday.");
  if (season === "winter") add("Season", w.season_winter_penalty, "Winter - slower metabolism.", false);
  if (totalPrecip > 1.0 || maxPrecipProb > 85) add("Precipitation", w.storm_penalty, "Storm-level rain - unfavorable, and unsafe to be out in.", false);
  else if (totalPrecip > 0 && totalPrecip <= 0.5 && maxPrecipProb <= 70) add("Precipitation", w.precip_light_rain_bonus, "Light rain - often triggers more active, less wary feeding.");
  if (water_temp_f != null) {
    const band = waterTempBand(water_temp_f).label;
    const key = { "Cold / Lethargic": "water_temp_cold_penalty", "Pre-Spawn Transition": "water_temp_prespawn_bonus", "Peak Optimal Prime": "water_temp_prime_bonus" }[band];
    if (key) add("Water temperature", w[key], `Water temp is in the ${band} range.`);
    else { const d = waterTempHotPenalty(water_temp_f, w); if (d !== 0) add("Water temperature", d, `Water temp ~${pyFixed(water_temp_f, 0)}F - heat/oxygen-stress penalty grows the closer it gets to ${pyFixed(WATER_TEMP_HOT_FLOOR_F, 0)}F.`); }
  }
  if (water_clarity != null) {
    if (water_clarity === "Green stained" || water_clarity === "Brown stained") add("Water clarity", w.water_clarity_stained_bonus, "Stained water - the classic power-fishing window.");
    else if (water_clarity === "Muddy") add("Water clarity", w.water_clarity_muddy_penalty, "Muddy water - tougher to trigger reaction strikes on sight alone.");
  }
  if (forage_present) add("Forage", w.forage_present_bonus, "Forage observed nearby - active bait often means active predators.");
  if (location_adjustment) {
    const nPart = location_adjustment_n ? ` (based on ${location_adjustment_n} logged trips here)` : "";
    add("Location", location_adjustment, `${location_adjustment > 0 ? "Outperforms" : "Underperforms"} other spots at this time of day, per your own trip log${nPart}.`);
  }
  return [pyRound(clamp10(score), 1), notes, breakdown];
}

function solunarOverlap(sol, start, end) {
  let o = null;
  for (const [a, b] of sol.major_periods) if (overlaps(start, end, a, b)) o = "major";
  if (o == null) for (const [a, b] of sol.minor_periods) if (overlaps(start, end, a, b)) o = "minor";
  return o;
}

/** One day's forecast. Throws if the bundle has no data for d. */
export function scoreDay(bundle, d, weights = null, lat = LAKE_LAT, lon = LAKE_LON) {
  const w = { ...DEFAULT_WEIGHTS, ...(weights || {}) }, warnings = [];
  const daily = dailyRowForDate(bundle, d), hourly = hourlyRowsForDate(bundle, d);
  if (!daily || !hourly.length) throw new Error(`No weather data available for ${d}`);
  const { sunrise, sunset } = daily, doy = dayOfYear(d);
  const waterTemp = estimateWaterTempF(bundle, d, doy), season = seasonStage(doy, waterTemp);
  const pTrend = pressureTrendHpaPer24h(bundle, at(d, 12));
  const moon = astro.moonPhase(at(d, 18));
  const sol = astro.solunarTimes(d, lat, lon, LAKE_TZ_UTC_OFFSET_HOURS);
  const n = Math.max(hourly.length, 1);
  const avgCloud = pySum(hourly.filter((r) => r.cloudcover != null).map((r) => r.cloudcover)) / n;
  const avgWind = pySum(hourly.filter((r) => r.windspeed_10m != null).map((r) => r.windspeed_10m)) / n;
  const maxPrecipProb = Math.max(...hourly.map((r) => r.precipitation_probability || 0));
  const totalPrecip = pySum(hourly.map((r) => r.precipitation || 0));
  if (totalPrecip > 1.0 || maxPrecipProb > 85) warnings.push(STORM_WARNING);
  const segments = segmentWindows(sunrise, sunset).map(([name, start, end]) => {
    const overlap = solunarOverlap(sol, start, end);
    const segTrend = pressureTrendHpaPer24h(bundle, start + tdDiv(end - start, 2));
    const [score, notes, breakdown] = segmentScore(name, segTrend, moon, overlap, avgCloud, avgWind, season, totalPrecip, maxPrecipProb, w, { water_temp_f: waterTemp });
    return { name, start, end, score, solunar_overlap: overlap, notes, breakdown, pressure_trend_24h: pyRound(segTrend, 2) };
  });
  const [overall, overallBreakdown] = aggregateDayOverall(segments);
  return {
    the_date: d, overall_score: overall, water_temp_f: waterTemp, season, moon, pressure_trend_24h: pyRound(pTrend, 2),
    sunrise, sunset, segments, warnings, overall_breakdown: overallBreakdown,
    weather_summary: { avg_cloud_pct: pyRound(avgCloud, 0), avg_wind_mph: pyRound(avgWind, 1), max_precip_prob_pct: maxPrecipProb,
      total_precip_in: pyRound(totalPrecip, 2), temp_hi_f: daily.temperature_2m_max ?? null, temp_lo_f: daily.temperature_2m_min ?? null },
  };
}

/** Score from conditions entered on the water (Spot Session). */
export function manualSegmentScore({ segment_name, season, avg_cloud_pct, avg_wind_mph, total_precip_in = 0.0, max_precip_prob_pct = 0.0,
  pressure_trend_24h = 0.0, moon = null, solunar_overlap = null, weights = null, at_time = null, water_temp_f = null,
  water_clarity = null, forage_present = null, location_adjustment = 0.0, location_adjustment_n = null }) {
  const w = { ...DEFAULT_WEIGHTS, ...(weights || {}) };
  moon = moon || astro.moonPhase(at_time ?? lakeNowNaive());
  const [score, notes, breakdown] = segmentScore(segment_name, pressure_trend_24h, moon, solunar_overlap, avg_cloud_pct, avg_wind_mph,
    season, total_precip_in, max_precip_prob_pct, w, { water_temp_f, water_clarity, forage_present, location_adjustment, location_adjustment_n });
  const warnings = total_precip_in > 1.0 || max_precip_prob_pct > 85 ? [STORM_WARNING] : [];
  return { score, notes, moon, warnings, breakdown };
}

export function segmentTimeRanges(bundle, d) {
  if (!bundle) return null;
  try {
    const daily = dailyRowForDate(bundle, d);
    if (!daily || !daily.sunrise || !daily.sunset) return null;
    return Object.fromEntries(segmentWindows(daily.sunrise, daily.sunset).map(([n, s, e]) => [n, [s, e]]));
  } catch { return null; }
}

export function realtimeContextFromBundle(bundle, segmentName, d, { lat = LAKE_LAT, lon = LAKE_LON, tz = LAKE_TZ_UTC_OFFSET_HOURS, at_time = null } = {}) {
  const result = { pressure_trend_24h: 0.0, solunar_overlap: null };
  if (!bundle) return result;
  try { result.pressure_trend_24h = pyRound(pressureTrendHpaPer24h(bundle, at_time ?? lakeNowNaive()), 2); } catch { /* keep 0 */ }
  try {
    const win = segmentTimeRanges(bundle, d)?.[segmentName];
    if (win) result.solunar_overlap = solunarOverlap(astro.solunarTimes(d, lat, lon, tz), win[0], win[1]);
  } catch { /* keep null */ }
  return result;
}

export function scoreWeek(bundle, start, days = 7, weights = null) {
  const out = [];
  for (let i = 0; i < days; i++) { try { out.push(scoreDay(bundle, addDays(start, i), weights)); } catch (e) { if (!/^No weather data/.test(e.message)) throw e; } }
  return out;
}
