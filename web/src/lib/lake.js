// Lake level (USGS) and the Army Corps surface water-quality survey. Port of core/lake_level.py +
// core/lake_water_quality.py (parity: engine.test.js). USGS can be called straight from the phone; the USACE page
// can't (no CORS), so it is fetched through the fm-usace-wq Supabase Edge Function and parsed here.
import { pyRound } from "./py.js";

export const USGS_SITE_ID = "03310900", USGS_LAKE_ELEVATION_PARAM_CD = "62614";
export const USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/";
export const NORMAL_SUMMER_POOL_FT = 515.0;
export const USACE_WQ_REPORT_URL = "https://www.lrl-wc.usace.army.mil/reports/wq/NRR.html";
export const SURFACE_STATION_NAME = "Dam Site";

/** {elevation_ft, observed_at (ISO text with offset, as USGS gives it), site_name}[] from a USGS IV payload */
export function parseLakeLevels(payload, siteId = USGS_SITE_ID) {
  const series = payload.value.timeSeries[0];
  const siteName = series.sourceInfo.siteName, values = series.values[0].value;
  if (!values.length) throw new Error(`USGS site ${siteId} returned no lake elevation readings.`);
  return values.map((v) => ({ elevation_ft: pyRound(parseFloat(v.value), 2), observed_at: v.dateTime.replace(/\.000(?=[+-]\d\d:\d\d$)/, ""), site_name: siteName }));
}
export const parseLakeLevel = (payload, siteId) => { const all = parseLakeLevels(payload, siteId); return all[all.length - 1]; };

export async function fetchLakeLevels(days = 1, fetchFn = fetch) {
  const q = new URLSearchParams({ sites: USGS_SITE_ID, format: "json", period: `P${Math.max(Math.trunc(days), 1)}D`, parameterCd: USGS_LAKE_ELEVATION_PARAM_CD });
  const r = await fetchFn(`${USGS_IV_URL}?${q}`);
  if (!r.ok) throw new Error(`USGS answered ${r.status}`);
  return parseLakeLevels(await r.json());
}

export function doSaturationConcentrationMgL(tC, elevationFt) {
  const cs = 14.652 - 0.41022 * tC + 0.0079910 * tC ** 2 - 0.000077774 * tC ** 3;
  return cs * (1 - 2.25577e-5 * (elevationFt * 0.3048)) ** 5.25588;
}

const ROW = /<tr>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<\/tr>/gi;
/** First "Dam Site" 0 ft row → {observed_at (naive ISO), water_temp_f, do_mg_l, do_saturation_pct, station} */
export function parseSurfaceWaterQuality(html) {
  for (const m of html.matchAll(ROW)) {
    const [, station, when, depth, tempC, doMg] = m;
    if (station.trim() !== SURFACE_STATION_NAME || depth.trim() !== "0") continue;
    const w = /^(\d{4})(\d{2})(\d{2}), (\d{2})(\d{2})$/.exec(when.trim());
    if (!w) throw new Error(`bad USACE date: ${when}`);
    const t = parseFloat(tempC.trim()), d = parseFloat(doMg.trim());
    if (Number.isNaN(t) || Number.isNaN(d)) throw new Error("bad USACE reading");
    const cs = doSaturationConcentrationMgL(t, NORMAL_SUMMER_POOL_FT);
    return { observed_at: `${w[1]}-${w[2]}-${w[3]}T${w[4]}:${w[5]}:00`, water_temp_f: pyRound(t * 9 / 5 + 32, 1), do_mg_l: d,
      do_saturation_pct: cs ? pyRound((d / cs) * 100, 1) : 0.0, station: SURFACE_STATION_NAME };
  }
  throw new Error(`Couldn't find a '${SURFACE_STATION_NAME}' surface (0 ft) row in the USACE water-quality report.`);
}
