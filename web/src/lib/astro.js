// Moon phase + solunar times. Port of core/astro.py — keep in step with it (parity tests: astro.test.js).
// Times are naive microseconds (lib/py.js). moonPhase() takes a UTC instant; the Python passes lake-local naive
// datetimes here, which its server (UTC) treats as UTC — the port does the same on purpose, for identical answers.
import { DAY, HOUR, MIN, dateOf, pmod, parts, tdMul } from "./py.js";

export const SYNODIC_MONTH = 29.530588861;
export const REF_NEW_MOON_JD = 2451550.1;
const PHASE_NAMES = [[0.0, 0.033, "New Moon"], [0.033, 0.25, "Waxing Crescent"], [0.25, 0.283, "First Quarter"],
  [0.283, 0.467, "Waxing Gibbous"], [0.467, 0.533, "Full Moon"], [0.533, 0.717, "Waning Gibbous"],
  [0.717, 0.75, "Last Quarter"], [0.75, 0.967, "Waning Crescent"], [0.967, 1.001, "New Moon"]];

export function illuminationPctForAge(ageDays) {
  const fraction = pmod(ageDays, SYNODIC_MONTH) / SYNODIC_MONTH;
  return (1 - Math.cos(2 * Math.PI * fraction)) / 2 * 100;
}

export function julianDay(us) {
  let { y, mo: m, d, h, mi, s } = parts(us);
  const dd = d + h / 24.0 + mi / 1440.0 + s / 86400.0;
  if (m <= 2) { y -= 1; m += 12; }
  const a = Math.floor(y / 100), b = 2 - a + Math.floor(a / 4);
  return Math.trunc(365.25 * (y + 4716)) + Math.trunc(30.6001 * (m + 1)) + dd + b - 1524.5;
}

export function moonPhase(us) {
  const jd = julianDay(us);
  const age = pmod(jd - REF_NEW_MOON_JD, SYNODIC_MONTH);
  const fraction = age / SYNODIC_MONTH;
  const illum = illuminationPctForAge(age);
  const name = PHASE_NAMES.find(([lo, hi]) => lo <= fraction && fraction < hi)[2];
  const nearNew = age <= 2 || age >= SYNODIC_MONTH - 2;
  const nearFull = Math.abs(age - SYNODIC_MONTH / 2) <= 2;
  const nearQ1 = Math.abs(age - SYNODIC_MONTH / 4) <= 2, nearQ3 = Math.abs(age - 3 * SYNODIC_MONTH / 4) <= 2;
  return { age_days: age, fraction, illumination_pct: illum, name, is_new_or_full_window: nearNew || nearFull, is_quarter_window: nearQ1 || nearQ3 };
}

const d2r = (d) => d * Math.PI / 180.0;
function moonRadec(jd) {
  const T = (jd - 2451545.0) / 36525.0;
  const Lp = 218.316 + 481267.881 * T;
  const M = d2r(pmod(134.963 + 477198.867 * T, 360)), Msun = d2r(pmod(357.529 + 35999.050 * T, 360));
  const D = d2r(pmod(297.850 + 445267.111 * T, 360)), F = d2r(pmod(93.272 + 483202.017 * T, 360));
  let lon = Lp + 6.289 * Math.sin(M) - 1.274 * Math.sin(M - 2 * D) + 0.658 * Math.sin(2 * D) - 0.186 * Math.sin(Msun)
    - 0.059 * Math.sin(2 * M - 2 * D) - 0.057 * Math.sin(M - 2 * D + Msun) + 0.053 * Math.sin(M + 2 * D)
    + 0.046 * Math.sin(2 * D - Msun) + 0.041 * Math.sin(M - Msun) - 0.035 * Math.sin(D) - 0.031 * Math.sin(M + Msun)
    - 0.015 * Math.sin(2 * F - 2 * D) + 0.011 * Math.sin(M - 4 * D);
  let lat = 5.128 * Math.sin(F) + 0.281 * Math.sin(M + F) - 0.278 * Math.sin(F - M) - 0.173 * Math.sin(2 * D - F)
    + 0.055 * Math.sin(2 * D + F - M) + 0.046 * Math.sin(2 * D - F - M) + 0.033 * Math.sin(F + 2 * M) + 0.017 * Math.sin(2 * D - M + F);
  lon = d2r(pmod(lon, 360)); lat = d2r(lat);
  const eps = d2r(23.439291 - 0.0130042 * T);
  const ra = Math.atan2(Math.sin(lon) * Math.cos(eps) - Math.tan(lat) * Math.sin(eps), Math.cos(lon));
  const dec = Math.asin(Math.sin(lat) * Math.cos(eps) + Math.cos(lat) * Math.sin(eps) * Math.sin(lon));
  return [pmod(ra, 2 * Math.PI), dec];
}
function gmstHours(jd) {
  const T = (jd - 2451545.0) / 36525.0;
  const g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T ** 3 / 38710000.0;
  return pmod(g, 360) / 15.0;
}
function moonAltitude(us, latDeg, lonDeg) {
  const jd = julianDay(us), [ra, dec] = moonRadec(jd);
  const lst = pmod(gmstHours(jd) + lonDeg / 15.0, 24.0);
  const H = d2r(lst * 15.0) - ra, latR = d2r(latDeg);
  return Math.asin(Math.sin(latR) * Math.sin(dec) + Math.cos(latR) * Math.cos(dec) * Math.cos(H)) * 180 / Math.PI;
}
function hourAngleDeg(us, lonDeg) {
  const jd = julianDay(us), [ra] = moonRadec(jd);
  const lst = pmod(gmstHours(jd) + lonDeg / 15.0, 24.0);
  const H = (lst * 15.0) - (ra * 180 / Math.PI);
  return pmod(H + 180, 360) - 180;
}

/** Moonrise/transit/set/underfoot (lake-local naive µs or null) + major/minor periods, for a local date. */
export function solunarTimes(dateLocal, latDeg, lonDeg, tzOffsetHours) {
  const start = Date.parse(`${dateLocal}T00:00:00Z`) * 1000 - tzOffsetHours * HOUR;
  const step = 5 * MIN, nSteps = Math.trunc((30 * HOUR) / step);
  const h0 = 0.125;
  const samples = [];
  let t = start;
  for (let i = 0; i < nSteps; i++) { samples.push([t, moonAltitude(t, latDeg, lonDeg), hourAngleDeg(t, lonDeg)]); t += step; }
  const inWindow = (x) => dateOf(x + tzOffsetHours * HOUR) === dateLocal;
  let rise = null, set = null, transit = null, underfoot = null;
  for (let i = 0; i < samples.length - 1; i++) {
    const [t0, a0, ha0] = samples[i], [t1, a1, ha1] = samples[i + 1];
    if (a0 < h0 && h0 <= a1 && inWindow(t0)) rise = t0 + tdMul(t1 - t0, a1 !== a0 ? (h0 - a0) / (a1 - a0) : 0);
    if (a0 >= h0 && h0 > a1 && inWindow(t0)) set = t0 + tdMul(t1 - t0, a0 !== a1 ? (a0 - h0) / (a0 - a1) : 0);
    if (ha0 < 0 && 0 <= ha1 && inWindow(t0)) transit = t0 + tdMul(t1 - t0, ha1 !== ha0 ? (0 - ha0) / (ha1 - ha0) : 0);
    if (ha0 < 180 && 180 <= ha1 + 360 && Math.abs(ha0) > 170 && Math.abs(ha1) > 170 && ha0 * ha1 < 0) underfoot = t0 + tdMul(t1 - t0, 0.5);
  }
  const loc = (x) => (x == null ? null : x + tzOffsetHours * HOUR);
  const [r, s, tr, u] = [loc(rise), loc(set), loc(transit), loc(underfoot)];
  const majors = [], minors = [];
  if (tr != null) majors.push([tr - HOUR, tr + HOUR]);
  if (u != null) majors.push([u - HOUR, u + HOUR]);
  if (r != null) minors.push([r - 30 * MIN, r + 30 * MIN]);
  if (s != null) minors.push([s - 30 * MIN, s + 30 * MIN]);
  return { moonrise: r, moon_transit: tr, moonset: s, moon_underfoot: u, major_periods: majors, minor_periods: minors };
}
export { DAY };
