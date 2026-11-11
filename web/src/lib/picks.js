// Lure picks v2 (John 11-10; new app only — the old app keeps core/lures.py's picks). recommend() (lures.js) still
// gives the Nolin seasonal pattern; this layer ranks by what has actually caught fish for you in similar conditions:
// every logged lure stretch counts, weighted by how alike its day was (water temp, time of year, clarity, time of day,
// structure, spot, wind) and how recent it was, then shrunk toward your average so a single lucky hour can't dominate.
import { parseConditions } from "./calibration.js";
import { buildBlock, groupOwnedByCategory, LURE_PROFILES } from "./lures.js";
import { lureHours } from "./history.js";

export const SHRINK_HOURS = 2;          // pseudo-hours of "average" mixed into every lure's rate
export const PROVEN_MIN_HOURS = 2;      // similarity-weighted hours before a lure can be "Proven"
export const COLD_MIN_HOURS = 2.5;      // ... before "no fish" counts as not producing
export const MIN_STINT_HOURS = 0.5;     // a logged lure stretch counts as at least this long (some were logged at the end, so
                                        // their times are seconds apart — e.g. 16 ChatterBait fish "in 0.2 h" this fall)
const LOW_LIGHT = new Set(["Dawn", "Dusk", "Night"]);
const dayNum = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 864e5;
const doy = (iso) => dayNum(iso) - Date.UTC(+iso.slice(0, 4), 0, 1) / 864e5;
const gauss = (d, s) => Math.exp(-0.5 * (d / s) ** 2);

/** How much a past lure stretch should count for today's situation (0..~1.4). */
export function similarity(row, c, ctx, today) {
  let w = 1;
  const temp = c.water_temp_unreliable ? null : c.water_temp_f; // fall trips logged from memory etc. (marked by hand)
  w *= temp != null && ctx.water_temp_f != null ? 0.3 + 0.7 * gauss(Number(temp) - ctx.water_temp_f, 10) : 0.7;
  const dd = Math.abs(doy(row.trip_date) - doy(today)), circ = Math.min(dd, 365 - dd);
  w *= 0.08 + 0.92 * gauss(circ, 35);                                         // time of year (any year)
  w *= 0.35 + 0.65 * 0.5 ** ((dayNum(today) - dayNum(row.trip_date)) / 540); // recent seasons count more
  if (ctx.water_clarity) w *= row.water_clarity === ctx.water_clarity ? 1 : 0.65;
  if (ctx.segment_name) w *= row.segment === ctx.segment_name ? 1 : LOW_LIGHT.has(row.segment) === LOW_LIGHT.has(ctx.segment_name) ? 0.8 : 0.6;
  if (ctx.structure_type) w *= row.structure_type === ctx.structure_type ? 1 : 0.75;
  if (ctx.spot_id && row.spot_id === ctx.spot_id) w *= 2; // the spot you're fishing counts double (John 11-10)
  if (ctx.wind_band && c.wind_band) w *= c.wind_band === ctx.wind_band ? 1 : 0.85;
  // default = everyone's catches count the same; "Just me" (ctx.me set) leans on your own trips
  if (ctx.me && row.owner) w *= row.owner.toLowerCase() === ctx.me.toLowerCase() ? 1 : 0.35;
  return w;
}

/** Per lure type: weighted fish/hours + plain totals + best day. */
export function lureStats(trips, ctx, today) {
  const out = {}; let WF = 0, WH = 0, H = 0;
  for (const r of trips || []) {
    if (!r.trip_date || r.trip_date > today) continue;
    const c = parseConditions(r), k = c.lure_category;
    if (!k || !LURE_PROFILES[k] || !c.lure_end_time) continue;
    const h = Math.max(lureHours(r), MIN_STINT_HOURS);
    const f = parseInt(r.fish_caught, 10) || 0, w = similarity(r, c, ctx, today);
    const s = (out[k] ||= { key: k, wf: 0, wh: 0, fish: 0, hours: 0, sessions: new Set(), days: {}, last_fish: null, sess: {} });
    const sk = r.session_id || r.trip_id, se = (s.sess[sk] ||= { w: 0, fish: 0 }); se.w = Math.max(se.w, w); se.fish += f;
    s.wf += w * f; s.wh += w * h; s.fish += f; s.hours += h; s.sessions.add(r.session_id || r.trip_id); WF += w * f; WH += w * h; H += h;
    if (w >= 0.35) { const d = (s.days[`${r.trip_date}|${r.spot_name || ""}`] ||= { date: r.trip_date, spot: r.spot_name, fish: 0 }); d.fish += f; }
    if (f > 0 && (!s.last_fish || r.trip_date > s.last_fish)) s.last_fish = r.trip_date;
  }
  const base = WH > 0 ? WF / WH : 0, avgW = H > 0 ? WH / H : 1;
  // eff = "similar hours": weighted hours rescaled so an average past stretch counts hour-for-hour
  for (const s of Object.values(out)) {
    s.eff = s.wh / avgW;
    s.rate = (s.wf / avgW + SHRINK_HOURS * base) / (s.eff + SHRINK_HOURS);
    s.best = Object.values(s.days).sort((a, b) => b.fish - a.fish || b.date.localeCompare(a.date))[0] || null;
    const ss = Object.values(s.sess), sw = ss.reduce((a, x) => a + x.w, 0);
    s.hit_share = sw > 0 ? ss.reduce((a, x) => a + (x.fish > 0 ? x.w : 0), 0) / sw : 0; // similarity-weighted share of sessions with ≥1 fish
    s.sessions = s.sessions.size; delete s.days; delete s.sess;
  }
  return { stats: out, base };
}

const md = (d) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const f1 = (x) => (Math.round(x * 10) / 10).toFixed(1);

/** {picks: [{key, tier, reasons[], block}], cold: [{key, name, text}], base} for the situation recommend() was run on.
 *  ctx = {water_temp_f, water_clarity, segment_name, structure_type, spot_id, wind_band, me, fish_depth_ft}. */
export function buildPicks(rec, { trips, inventory, ctx, today }) {
  const { stats, base } = lureStats(trips, ctx, today);
  const owned = groupOwnedByCategory(inventory), ownsAny = Object.keys(owned).length > 0;
  const has = (k) => !ownsAny || !!owned[k];
  const recBlocks = Object.fromEntries([...rec.first_choice, ...rec.second_choice].map((b) => [b.key, b]));
  // your matching items; if none match the chart's colors, show what you own in other colors rather than nothing
  const block = (k) => { const b = recBlocks[k] || buildBlock(k, ctx.water_clarity || "Green stained", ctx.fish_depth_ft ?? null, { owned: owned[k] || null });
    return b.owned_items.length ? b : { ...b, owned_items: (b.owned_off_color_items || []).slice(0, 2), off_color: true }; };
  // "not producing" = plenty of similar time and it rarely catches anything (slow-but-steady baits aren't cold)
  const cold = Object.values(stats).filter((s) => s.eff >= COLD_MIN_HOURS && (s.wf === 0 || (s.rate < base * 0.5 && s.hit_share < 0.4)));
  const coldKeys = new Set(cold.map((s) => s.key));
  const taken = new Set(), picks = [], avgLabel = ctx.me ? "your average" : "everyone's average";
  const evidence = (s) => `all-time with it${ctx.me ? "" : " (everyone)"}: ${s.fish} fish, ${Math.round(s.hours)} h, ${s.sessions} session${s.sessions === 1 ? "" : "s"}`;

  // 1. Proven: best similarity-weighted rates with real evidence, above your average
  const proven = Object.values(stats).filter((s) => s.eff >= PROVEN_MIN_HOURS && s.wf > 0 && s.rate > base * 1.2 && has(s.key) && !coldKeys.has(s.key))
    .sort((a, b) => b.rate - a.rate).slice(0, 3);
  for (const s of proven) {
    taken.add(s.key);
    picks.push({ key: s.key, tier: "proven", rate: s.rate, block: block(s.key), reasons: [
      `${f1(s.rate)} fish/hr in conditions like these (${avgLabel}: ${f1(base)}); ${evidence(s)}.`,
      s.best && s.best.fish > 0 ? `Best similar day: ${md(s.best.date)}${s.best.spot ? ` at ${s.best.spot}` : ""}, ${s.best.fish} fish.` : null,
      recBlocks[s.key] ? "Also fits the Nolin pattern for right now." : null].filter(Boolean) });
  }
  // 2. Steady: not the fastest, but catches fish in most similar sessions (e.g. the drop shot)
  const steady = Object.values(stats).filter((s) => !taken.has(s.key) && !coldKeys.has(s.key) && has(s.key) && s.eff >= 6 && s.sessions >= 5 && ((s.hit_share >= 0.6 && s.rate >= base * 0.8) || (s.hit_share >= 0.75 && s.rate >= base * 0.4)))
    .sort((a, b) => b.hit_share - a.hit_share || b.rate - a.rate).slice(0, 1);
  for (const s of steady) {
    taken.add(s.key);
    picks.push({ key: s.key, tier: "steady", rate: s.rate, block: block(s.key), reasons: [
      `Caught fish in ${Math.round(s.hit_share * 100)}% of similar sessions — a steady producer when the faster baits stall.`,
      `${f1(s.rate)} fish/hr in conditions like these; ${evidence(s)}.`] });
  }
  // 3. Seasonal: the documented pattern's first choices you haven't already got
  for (const b of rec.first_choice) {
    if (picks.filter((p) => p.tier === "seasonal").length >= 2) break;
    if (taken.has(b.key) || coldKeys.has(b.key) || !has(b.key)) continue;
    const s = stats[b.key]; taken.add(b.key);
    picks.push({ key: b.key, tier: "seasonal", rate: s?.rate ?? null, block: block(b.key), reasons: [
      (b.why || []).find((w) => !w.startsWith("Colors shown")) || "Part of Nolin's documented pattern for this season and water.",
      s && s.eff >= 0.5 ? `Record in similar conditions: ${f1(s.rate)} fish/hr (${evidence(s)}).` : "Little history for it in conditions like these yet."].filter(Boolean) });
  }
  // 4. Worth a try: fits the situation, barely fished in conditions like these, not a known dud
  const tryKey = [...rec.second_choice.map((b) => b.key), ...rec.first_choice.map((b) => b.key)]
    .find((k) => !taken.has(k) && !coldKeys.has(k) && has(k) && (!stats[k] || stats[k].eff < 2.5));
  if (tryKey) {
    taken.add(tryKey);
    picks.push({ key: tryKey, tier: "try", rate: stats[tryKey]?.rate ?? null, block: block(tryKey), reasons: [
      (recBlocks[tryKey]?.why || []).find((w) => !w.startsWith("Colors shown")) || "Fits today's water and structure.",
      stats[tryKey] ? `Only ${f1(stats[tryKey].hours)} h logged with it in anything like this — give it 20–30 minutes.` : "You haven't logged it in conditions like these — give it 20–30 minutes."] });
  }
  // fill up to 4 from what's left of the pattern if history was thin
  for (const b of [...rec.first_choice, ...rec.second_choice]) {
    if (picks.length >= 4) break;
    if (taken.has(b.key) || coldKeys.has(b.key) || !has(b.key)) continue;
    taken.add(b.key); picks.push({ key: b.key, tier: "seasonal", rate: stats[b.key]?.rate ?? null, block: block(b.key), reasons: [(b.why || []).find((w) => !w.startsWith("Colors shown")) || "Fits the Nolin pattern for right now."] });
  }
  return { picks, base, cold: cold.filter((s) => has(s.key)).sort((a, b) => b.eff - a.eff).slice(0, 3)
    .map((s) => ({ key: s.key, name: LURE_PROFILES[s.key].name, text: s.fish === 0 ? `0 fish in ${f1(s.hours)} h in similar conditions` : `${f1(s.rate)} fish/hr — well under the ${f1(base)} average here` })) };
}
