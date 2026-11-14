// Forecast score vs fish caught (punch-list #99, Matthew 2026-11-14) — new app only.
//
// Every trip row keeps predicted_score: the app's score for that time-of-day segment when the lure went in the water.
// For each day fished:
//   score = the mean of the distinct (session, segment) scores that day (so 5 lures in one morning count once),
//   fish  = all fish logged that day,
//   hours = angler-hours on the water: each session's first lure start → last lure end (lures fished side by side
//           don't add up), summed over sessions; days without lure times still count fish but not hours.
// Then days are grouped by whole score points, and a Pearson correlation says how closely score and catch move together.
import { parseConditions } from "./calibration.js";

const toMin = (t) => { const m = /^(\d{2}):(\d{2})(?::(\d{2}))?/.exec(t || ""); return m ? +m[1] * 60 + +m[2] + (+m[3] || 0) / 60 : null; };
const num = (v) => { const n = typeof v === "number" ? v : parseFloat(v); return Number.isFinite(n) ? n : null; };

/** [{date, score, fish, hours, rate, sessions}] oldest first, for days with at least one forecast score. */
export function scoreDays(trips, { from = "", to = "", owner = null } = {}) {
  const days = {};
  for (const r of trips || []) {
    const d = r.trip_date; if (!d || (from && d < from) || (to && d > to)) continue;
    if (owner && (r.owner || "").toLowerCase() !== owner.toLowerCase()) continue;
    const c = parseConditions(r);
    if (c.source === "spot_session" && !c.lure_end_time) continue;            // still on the water
    const day = (days[d] ||= { date: d, fish: 0, scores: new Map(), sessions: new Map() });
    day.fish += parseInt(r.fish_caught, 10) || 0;
    const sid = r.session_id || r.trip_id, p = num(r.predicted_score);
    if (p != null) day.scores.set(`${sid}|${r.segment || ""}`, p);
    const a = toMin(c.lure_start_time), b = toMin(c.lure_end_time);
    const s = day.sessions.get(sid) || { lo: null, hi: null };
    if (a != null && b != null && b > a) { s.lo = s.lo == null ? a : Math.min(s.lo, a); s.hi = s.hi == null ? b : Math.max(s.hi, b); }
    day.sessions.set(sid, s);
  }
  return Object.values(days).filter((d) => d.scores.size).map((d) => {
    const sc = [...d.scores.values()], hours = [...d.sessions.values()].reduce((h, s) => h + (s.lo != null ? (s.hi - s.lo) / 60 : 0), 0);
    return { date: d.date, score: sc.reduce((a, b) => a + b, 0) / sc.length, fish: d.fish, hours, rate: hours >= 0.5 ? d.fish / hours : null, sessions: d.sessions.size };
  }).sort((a, b) => a.date.localeCompare(b.date));
}

/** Pearson r, or null with fewer than 5 pairs or no spread. */
export function pearson(xs, ys) {
  const n = xs.length; if (n < 5) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : null;
}

/** Days grouped by whole score points (≤3 together, 9+ together): [{key, label, days, fish, hours, fishPerDay, rate}]. */
export function scoreBands(days) {
  const band = (s) => Math.max(3, Math.min(9, Math.floor(s)));
  const m = new Map();
  for (const d of days) { const k = band(d.score), b = m.get(k) || { key: k, days: 0, fish: 0, hours: 0 }; b.days++; b.fish += d.fish; b.hours += d.hours; m.set(k, b); }
  return [...m.values()].sort((a, b) => a.key - b.key).map((b) => ({ ...b, label: b.key === 3 ? "Under 4" : b.key === 9 ? "9 and up" : `${b.key}–${b.key + 1}`,
    fishPerDay: b.fish / b.days, rate: b.hours >= 0.5 ? b.fish / b.hours : null }));
}

/** Plain-words read of r. */
export function describeR(r) {
  if (r == null) return "Not enough days yet to say.";
  const a = Math.abs(r), dir = r > 0 ? "higher scores have come with more fish" : "higher scores have come with FEWER fish";
  if (a < 0.1) return "No real link so far — the score hasn't tracked the catch.";
  return `${a < 0.3 ? "A weak" : a < 0.5 ? "A moderate" : "A strong"} link: ${dir}.`;
}

export function scoreCheck(trips, opts) {
  const days = scoreDays(trips, opts), withRate = days.filter((d) => d.rate != null);
  return { days, bands: scoreBands(days), rFish: pearson(days.map((d) => d.score), days.map((d) => d.fish)),
    rRate: pearson(withRate.map((d) => d.score), withRate.map((d) => d.rate)), rateDays: withRate.length };
}
