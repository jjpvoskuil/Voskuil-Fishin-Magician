// Small helpers that make JavaScript behave exactly like the Python reference code (core/*.py), so the ported
// engine gives the same answers. Times: the Python uses "naive" wall-clock datetimes (lake local time, no zone).
// Here a naive datetime is a Number of MICROseconds since 1970-01-01 00:00 on that wall clock (as if UTC), because
// Python's timedelta keeps microseconds and rounds them half-to-even; a date is a "YYYY-MM-DD" string.

export const US = 1, MS = 1e3, SEC = 1e6, MIN = 60e6, HOUR = 3600e6, DAY = 86400e6;

/** Python's % (result has the sign of the divisor). */
export const pmod = (a, b) => ((a % b) + b) % b;

/** Round to the nearest integer, ties to even (Python round() / timedelta rounding). */
export function roundHalfEven(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/** Python f"{x:.{n}f}": correctly rounded from the exact binary value, exact ties to even. */
export function pyFixed(x, n = 0) {
  if (!Number.isFinite(x)) return String(x);
  const exact = Math.abs(x).toFixed(100);              // exact decimal expansion of the double
  const dot = exact.indexOf(".");
  const tail = exact.slice(dot + 1 + n);
  let s = Math.abs(x).toFixed(n);
  if (/^50*$/.test(tail)) {                           // an exact tie: JS rounds away from zero, Python to even
    const kept = exact.slice(0, dot + 1 + n).replace(/\.$/, "");
    const lastDigit = Number(kept.replace(".", "").slice(-1));
    if (lastDigit % 2 === 0) s = kept;               // already even → round down
  }
  const neg = x < 0 || Object.is(x, -0);
  return (neg && Number(s) !== 0 ? "-" : neg ? "-" : "") + s;
}

/** Python round(x, n) for floats. */
export const pyRound = (x, n = 0) => (x == null ? x : Number(pyFixed(x, n)));

/** statistics.median */
export function median(xs) {
  const s = [...xs].sort((a, b) => a - b), n = s.length;
  if (!n) throw new Error("median of empty list");
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

/** Python 3.12+ built-in sum() of floats: Neumaier compensated summation (plain += can differ in the last bit). */
export function pySum(xs) {
  let s = 0.0, c = 0.0, any = false;
  for (const x of xs) {
    any = true;
    const t = s + x;
    if (Math.abs(s) >= Math.abs(x)) c += (s - t) + x; else c += (x - t) + s;
    s = t;
  }
  return any ? s + c : 0;
}

export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
/** "fall_feed_up" → "Fall Feed Up" (Python str.title() after replacing _) */
export const titleWords = (s) => s.replace(/_/g, " ").toLowerCase().replace(/(^|[^a-z])([a-z])/g, (m, a, b) => a + b.toUpperCase());

// ---------------------------------------------------------------- naive datetimes (µs) and dates ("YYYY-MM-DD")
export const dt = (y, mo, d, h = 0, mi = 0, s = 0, us = 0) => Date.UTC(y, mo - 1, d, h, mi, s) * 1000 + us;
/** datetime.fromisoformat for "YYYY-MM-DD", "YYYY-MM-DDTHH:MM", "…:SS", "…:SS.ffffff" (naive) */
export function parseIso(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?$/.exec(s);
  if (!m) throw new Error(`bad datetime: ${s}`);
  return dt(+m[1], +m[2], +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0), m[7] ? +m[7].padEnd(6, "0") : 0);
}
const p2 = (n) => String(n).padStart(2, "0");
/** datetime.isoformat() of a naive datetime */
export function isoNaive(us) {
  const ms = Math.floor(us / 1000), frac = pmod(us, SEC);
  const d = new Date(ms);
  const base = `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}T${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}:${p2(d.getUTCSeconds())}`;
  return frac ? `${base}.${String(frac).padStart(6, "0")}` : base;
}
export const dateOf = (us) => isoNaive(us).slice(0, 10);
export const parts = (us) => { const d = new Date(Math.floor(us / 1000)); return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes(), s: d.getUTCSeconds() }; };
export const dateStart = (ds) => parseIso(ds);
export const at = (ds, h = 0, mi = 0) => parseIso(ds) + h * HOUR + mi * MIN;
export const addDays = (ds, n) => dateOf(parseIso(ds) + n * DAY);
export const dayOfYear = (ds) => Math.round((parseIso(ds) - parseIso(`${ds.slice(0, 4)}-01-01`)) / DAY) + 1;
export const monthOf = (ds) => Number(ds.slice(5, 7));
/** timedelta / k and timedelta * f (microseconds, rounded half to even, like Python) */
export const tdDiv = (us, k) => roundHalfEven(us / k);
export const tdMul = (us, f) => roundHalfEven(us * f);
