// Re-score every day fished with TODAY's scoring engine (John 11-15: forecast score for the day vs fish/hr over all of
// our history). The scores saved on trip rows came from whatever version of the engine ran then (and older days have
// none), so here each day fished gets a fresh scoreDay() from archived weather:
//   - Open-Meteo Historical Forecast API (archived forecasts, same variables as the live forecast incl. rain chance;
//     2022 on). Earlier days fall back to the ERA5 Archive API, which has no rain-chance column (counted as 0).
//   - one request per calendar year with fished days, starting 6 days early (water-temp trend + 24 h pressure trend).
// Two scores per day: with the default weights (the untuned engine — a fair test) and with today's tuned weights
// (calibrateWeights learns from these same catches, so its fit to them is flattered).
import { DAILY_VARS, HOURLY_VARS, LAKE_LAT, LAKE_LON, LAKE_TZ } from "./weather.js";
import { scoreDay } from "./scoring.js";

export const HIST_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast";
export const ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive";
export const HIST_FORECAST_FROM = "2022-01-01";
const LEAD_DAYS = 6;
const addDays = (d, n) => new Date(Date.parse(`${d}T12:00:00Z`) + n * 864e5).toISOString().slice(0, 10);

/** The requests needed for these dates: [{url, start, end}] (one per year, archive API before 2022). */
export function plan(dates, today) {
  const years = {};
  for (const d of dates) (years[d.slice(0, 4)] ||= []).push(d);
  const yesterday = addDays(today, -1);
  return Object.values(years).map((ds) => {
    ds.sort(); const start = addDays(ds[0], -LEAD_DAYS), end = ds[ds.length - 1] > yesterday ? yesterday : ds[ds.length - 1];
    return { url: ds[ds.length - 1] < HIST_FORECAST_FROM ? ARCHIVE_URL : HIST_FORECAST_URL, start, end };
  }).filter((p) => p.start <= p.end);
}

export function requestUrl({ url, start, end }) {
  const hourly = url === ARCHIVE_URL ? HOURLY_VARS.filter((v) => v !== "precipitation_probability") : HOURLY_VARS;
  return `${url}?${new URLSearchParams({ latitude: LAKE_LAT, longitude: LAKE_LON, hourly: hourly.join(","), daily: DAILY_VARS.join(","),
    timezone: LAKE_TZ, start_date: start, end_date: end, temperature_unit: "fahrenheit", windspeed_unit: "mph", precipitation_unit: "inch" })}`;
}

/** Join year bundles into one (arrays concatenated; a missing column is filled with nulls). */
export function mergeBundles(parts) {
  const out = { hourly: { time: [] }, daily: { time: [] } };
  for (const kind of ["hourly", "daily"]) {
    const vars = kind === "hourly" ? HOURLY_VARS : DAILY_VARS;
    for (const v of vars) out[kind][v] = [];
    for (const p of parts) {
      const t = p[kind]?.time || [];
      out[kind].time.push(...t);
      for (const v of vars) { const col = p[kind]?.[v]; out[kind][v].push(...(col || t.map(() => null))); }
    }
  }
  return out;
}

/** {date: {base, tuned, segments}} for the dates that the bundle covers. */
export function scoreDates(bundle, dates, tunedWeights) {
  const out = {};
  for (const d of dates) {
    try {
      const base = scoreDay(bundle, d, null), tuned = tunedWeights ? scoreDay(bundle, d, tunedWeights) : base;
      out[d] = { base: base.overall_score, tuned: tuned.overall_score, season: base.season };
    } catch { /* no weather for that day */ }
  }
  return out;
}

const memo = new Map();   // url → bundle promise, for this visit to the app (past weather doesn't change)
/** Fetch what's needed and score. Returns {scores, missing: [dates without weather], failed: n requests that failed}. */
export async function rescoreDays(dates, tunedWeights, { today, fetchFn = fetch } = {}) {
  const parts = [], reqs = plan(dates, today);
  let failed = 0;
  await Promise.all(reqs.map(async (r) => {
    const u = requestUrl(r);
    if (!memo.has(u)) memo.set(u, fetchFn(u).then((res) => { if (!res.ok) throw new Error(`Open-Meteo answered ${res.status}`); return res.json(); }));
    try { parts.push(await memo.get(u)); } catch { memo.delete(u); failed++; }
  }));
  parts.sort((a, b) => String(a.daily?.time?.[0]).localeCompare(String(b.daily?.time?.[0])));
  const scores = parts.length ? scoreDates(mergeBundles(parts), dates, tunedWeights) : {};
  return { scores, missing: dates.filter((d) => !scores[d]), failed };
}
