// On-the-water condition vocabularies and conversions. Port of core/onwater.py + core/thermocline.py.
// Wind/visibility band gaps (e.g. 3.5 mph) fall through to the LAST band exactly as in the Python — kept for parity.
import { pyFixed } from "./py.js";

export const WATER_CLARITY_OPTIONS = ["Clear", "Green stained", "Brown stained", "Muddy"];
export const LIGHT_CONDITIONS = ["Clear / Sunny", "Mostly Clear", "Partly Cloudy", "Mostly Cloudy", "Overcast"];
export const LIGHT_CONDITION_INFO = {
  "Clear / Sunny": { range: "0/8 oktas (~0% cloud)", detail: "No clouds, or so few they don't matter." },
  "Mostly Clear": { range: "1-2/8 oktas (~10-25%)", detail: "A few scattered clouds, mostly open sky." },
  "Partly Cloudy": { range: "3-4/8 oktas (~35-50%)", detail: "A mix of sun and clouds, roughly half and half." },
  "Mostly Cloudy": { range: "5-7/8 oktas (~60-90%)", detail: "Sun mostly blocked, patches of blue at most." },
  "Overcast": { range: "8/8 oktas (100%)", detail: "Solid cloud deck, no direct sun anywhere." },
};
const CLOUD_PROXY = { "Clear / Sunny": 5.0, "Mostly Clear": 20.0, "Partly Cloudy": 45.0, "Mostly Cloudy": 75.0, "Overcast": 95.0 };
export const cloudProxyForLightCondition = (c) => CLOUD_PROXY[c] ?? 40.0;
export function lightConditionForCloudPct(p) {
  if (p == null) return LIGHT_CONDITIONS[2];
  if (p <= 12.5) return "Clear / Sunny";
  if (p <= 32.5) return "Mostly Clear";
  if (p <= 60.0) return "Partly Cloudy";
  if (p <= 85.0) return "Mostly Cloudy";
  return "Overcast";
}

export const WIND_BANDS = [[0.0, 3.0, "Glassy", "Mirror surface intact."], [4.0, 9.0, "Light Ripple", "Breaks the surface mirror."],
  [10.0, 16.0, "Moderate Chop / Action Trigger", "Generates shoreward current."], [17.0, Infinity, "Heavy / Turbulent", "Bank turbidity, bait dislocation."]];
const bandOf = (bands, x) => { for (const [lo, hi, label, detail] of bands) if (lo <= x && x <= hi) return { label, detail }; const l = bands[bands.length - 1]; return { label: l[2], detail: l[3] }; };
export const windBand = (mph) => bandOf(WIND_BANDS, mph);
export const WIND_BAND_LABELS = WIND_BANDS.map((b) => b[2]);
const WIND_PROXY = Object.fromEntries(WIND_BANDS.map(([lo, hi, label]) => [label, (lo + Math.min(hi, 25.0)) / 2]));
export const windMphForBand = (label) => WIND_PROXY[label] ?? 6.5;
export const WIND_DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "Variable", "Calm"];
const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
export function windDirectionForDegrees(deg) {
  if (deg == null) return "Variable";
  return COMPASS[Math.floor(((((deg % 360) + 360) % 360) + 22.5) / 45) % 8];
}

export const VISIBILITY_BANDS = [[4.0, Infinity, "Clear", "Sight-dominated hunting."], [1.5, 4.0, "Stained", "Power-fishing window."], [0.0, 1.5, "Dirty / Muddy", "Lateral line / vibration / scent take over."]];
export function visibilityBand(secchi) { for (const [lo, hi, label, detail] of VISIBILITY_BANDS) if (lo <= secchi && secchi <= hi) return { label, detail }; return { label: "Clear", detail: VISIBILITY_BANDS[0][3] }; }
export const STAIN_COLOR_OPTIONS = ["Green stained", "Brown stained"];
export function resolveWaterClarity(secchi, stainColor = null, stirredUp = false) {
  if (stirredUp) return "Muddy";
  const band = visibilityBand(secchi).label;
  if (band === "Clear") return "Clear";
  if (band === "Dirty / Muddy") return "Muddy";
  if (STAIN_COLOR_OPTIONS.includes(stainColor)) return stainColor;
  return "Brown stained";
}

// lo <= t < hi, except "Summer Stratified" includes 84.0 — no gaps (fixed in both Python and JS on 2026-11-10)
export const WATER_TEMP_BANDS = [[-Infinity, 50.0, "Cold / Lethargic", "Digestion 48-72+ hrs; no fast chase."], [50.0, 63.0, "Pre-Spawn Transition", "Accelerating metabolism, staging."],
  [63.0, 77.0, "Peak Optimal Prime", "Maximum feeding efficiency."], [77.0, 84.0, "Summer Stratified", "High metabolism, shallow O2 drop."], [84.0, Infinity, "Extreme Thermal Load", "Severe oxygen stress."]];
export function waterTempBand(t) {
  for (const [, hi, label, detail] of WATER_TEMP_BANDS) if (t < hi || (label === "Summer Stratified" && t === hi)) return { label, detail };
  const l = WATER_TEMP_BANDS[WATER_TEMP_BANDS.length - 1]; return { label: l[2], detail: l[3] };
}

export const PRECIPITATION_OPTIONS = ["None", "Light rain", "Steady rain", "Heavy rain / storm"];
const PRECIP_PROXY = { "None": [0.0, 0.0], "Light rain": [0.3, 40.0], "Steady rain": [0.8, 70.0], "Heavy rain / storm": [1.5, 95.0] };
export const precipitationProxy = (p) => PRECIP_PROXY[p] ?? [0.0, 0.0];
export function precipitationOptionForForecast(inches, prob) {
  inches = inches || 0.0; prob = prob || 0.0;
  if (inches >= 1.15 || prob >= 82.5) return "Heavy rain / storm";
  if (inches >= 0.55 || prob >= 55.0) return "Steady rain";
  if (inches >= 0.15 || prob >= 20.0) return "Light rain";
  return "None";
}

// ---------------------------------------------------------------- thermocline (core/thermocline.py)
const THERMO = { 5: [8.0, 12.0], 6: [11.0, 15.0], 7: [13.0, 17.0], 8: [14.0, 19.0], 9: [17.0, 25.0] };
export const NO_STRATIFICATION_DEFAULT_FT = 60.0;
export const estimateThermoclineBandFt = (ds) => THERMO[Number(ds.slice(5, 7))] || null;
export function estimateThermoclineFt(ds) { const b = estimateThermoclineBandFt(ds); return b ? Math.round(((b[0] + b[1]) / 2) * 10) / 10 : null; }
export const defaultThermoclineInputFt = (ds) => estimateThermoclineFt(ds) ?? NO_STRATIFICATION_DEFAULT_FT;
export function thermoclineCaveat(thermo, fishDepth) {
  if (thermo == null || fishDepth == null) return null;
  if (fishDepth > thermo) return `Heads up: ${pyFixed(fishDepth, 0)} ft is below the thermocline depth you've set (~${pyFixed(thermo, 0)} ft) - water that deep is usually too oxygen-depleted to hold active bass. That reading may be another species or fish just passing through; consider targeting suspended fish nearer the thermocline itself instead.`;
  return null;
}
