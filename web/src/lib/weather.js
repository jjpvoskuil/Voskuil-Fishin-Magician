// Weather: fetch the Open-Meteo forecast and read it. Port of core/weather.py (parity tests: engine.test.js).
// A "bundle" is the raw Open-Meteo {hourly, daily} object, exactly as the Python keeps it.
import { DAY, addDays, dateOf, dayOfYear, parseIso, pyRound, pySum } from "./py.js";

export const LAKE_LAT = 37.2783, LAKE_LON = -86.2475, LAKE_TZ = "America/Chicago";
export const LAKE_TZ_UTC_OFFSET_HOURS = -5; // the Python uses CDT all year for solunar times — kept for parity
export const OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast";
export const HOURLY_VARS = ["temperature_2m", "surface_pressure", "cloudcover", "windspeed_10m", "winddirection_10m", "precipitation_probability", "precipitation"];
export const DAILY_VARS = ["sunrise", "sunset", "temperature_2m_max", "temperature_2m_min"];
export const WATER_TEMP_TREND_PAST_DAYS = 5;
export const HOME_TREND_CHART_PAST_DAYS = 14;

/** Today's date at the lake ("YYYY-MM-DD"). */
export function lakeToday(now = new Date()) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: LAKE_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
/** Lake wall-clock time now, as naive µs (like scoring.lake_now_naive()). */
export function lakeNowNaive(now = new Date()) {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: LAKE_TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  const p = Object.fromEntries(f.formatToParts(now).map((x) => [x.type, x.value]));
  return parseIso(`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`) + (now.getMilliseconds() * 1000);
}

/** Fetch the forecast (3 tries on network/429/5xx errors, like the Python). */
export async function fetchForecast(days = 7, { lat = LAKE_LAT, lon = LAKE_LON, fetchFn = fetch, sleep = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
  const params = new URLSearchParams({
    latitude: lat, longitude: lon, hourly: HOURLY_VARS.join(","), daily: DAILY_VARS.join(","), timezone: LAKE_TZ,
    forecast_days: Math.min(Math.max(days, 1), 16), past_days: Math.max(WATER_TEMP_TREND_PAST_DAYS, HOME_TREND_CHART_PAST_DAYS),
    temperature_unit: "fahrenheit", windspeed_unit: "mph", precipitation_unit: "inch",
  });
  let last;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) await sleep([1500, 3000][attempt - 1]);
    try {
      const r = await fetchFn(`${OPEN_METEO_URL}?${params}`);
      if (!r.ok) { const e = new Error(`Open-Meteo answered ${r.status}`); if (r.status !== 429 && r.status < 500) throw Object.assign(e, { fatal: true }); last = e; continue; }
      const j = await r.json();
      return { hourly: j.hourly || {}, daily: j.daily || {} };
    } catch (e) { if (e.fatal) throw e; last = e; }
  }
  throw last;
}

const cache = new WeakMap();
/** parsed hourly times (µs), cached per bundle */
function hourlyTimes(bundle) {
  let c = cache.get(bundle);
  if (!c) { c = (bundle.hourly.time || []).map(parseIso); cache.set(bundle, c); }
  return c;
}

export function hourlyRowsForDate(bundle, d) {
  const times = hourlyTimes(bundle), rows = [];
  times.forEach((t, i) => {
    if (dateOf(t) !== d) return;
    const row = { time: t };
    for (const v of HOURLY_VARS) { const vals = bundle.hourly[v] || []; row[v] = i < vals.length ? vals[i] : null; }
    rows.push(row);
  });
  return rows;
}

export function dailyRowForDate(bundle, d) {
  const times = bundle.daily.time || [];
  for (let i = 0; i < times.length; i++) {
    if (dateOf(parseIso(times[i])) !== d) continue;
    const row = { date: d };
    for (const v of DAILY_VARS) {
      const vals = bundle.daily[v] || [];
      let val = i < vals.length ? vals[i] : null;
      if ((v === "sunrise" || v === "sunset") && val) val = parseIso(val);
      row[v] = val ?? null;
    }
    return row;
  }
  return null;
}

/** hPa change over the 24 h before atTime (naive µs), nearest hourly readings. */
export function pressureTrendHpaPer24h(bundle, atTime) {
  const times = hourlyTimes(bundle), pressures = bundle.hourly.surface_pressure || [];
  if (!times.length || !pressures.length) return 0.0;
  const nearest = (target) => { let best = 0, bd = Infinity; times.forEach((t, i) => { const d = Math.abs(t - target); if (d < bd) { bd = d; best = i; } }); return best; };
  const iNow = nearest(atTime), iPrev = nearest(atTime - DAY);
  const pNow = iNow < pressures.length ? pressures[iNow] : null, pPrev = iPrev < pressures.length ? pressures[iPrev] : null;
  if (pNow == null || pPrev == null) return 0.0;
  return pNow - pPrev;
}

/** Surface water temperature estimate (°F): recent air highs blended with a seasonal curve. */
export function estimateWaterTempF(bundle, d, doy = dayOfYear(d)) {
  const times = (bundle.daily.time || []).map((t) => dateOf(parseIso(t)));
  const highs = bundle.daily.temperature_2m_max || [];
  const start = addDays(d, -WATER_TEMP_TREND_PAST_DAYS);
  const vals = [];
  times.forEach((dd, i) => { if (start <= dd && dd < d && i < highs.length && highs[i] != null) vals.push(highs[i]); });
  const highAvg = vals.length ? pySum(vals) / vals.length : null;
  const seasonal = 60 + 27 * Math.sin(2 * Math.PI * (doy - 124) / 365.0);
  if (highAvg == null) return pyRound(seasonal, 1);
  return pyRound(0.45 * (highAvg - 3) + 0.55 * seasonal, 1);
}
