// Ranking the ⭐ "spots to try" (punch-list #101, Matthew 2026-11-14).
//
// A spot to try comes from the lake's shape (tools/build_contours.py): a point, a steep break / bluff, an old channel
// swing or a flat by deep water, with a structure score. To give the model's best picks an order, each one gets:
//   1. structure  — its own score, relative to the strongest one on the lake;
//   2. kind       — how that KIND of structure has produced in the trip log under the map's Hot-spots filter (time of
//                   day, time of year, everyone / just me): saved spots are grouped by their type (Main-lake point →
//                   point, Rock face / bluff → break, Creek channel / ledge → swing, Flat → flat), fish per hour
//                   shrunk toward the lake average (4 h), as a multiple of that average;
//   3. nearby     — the heat of saved spots within 600 m (closer counts more), shrunk toward average;
//   4. water      — at today's lake level the area must hold water; spots that would be (almost) dry drop out.
// rank = structure^0.4 × kind^0.4 × nearby^0.2. With no trip log, kind and nearby are 1 and structure decides.

export const KIND_OF_TYPE = { "Main-lake point": "point", "Secondary / pocket point": "point", "Rock face / bluff": "break",
  "Creek channel / ledge": "swing", "Flat": "flat" };
const KIND_SHRINK_H = 4, NEAR_M = 600, MIN_DEPTH_FT = 3;

const metersApart = (a, b) => { const k = Math.cos((a.lat * Math.PI) / 180); return Math.hypot((a.lat - b.lat) * 111320, (a.lon - b.lon) * 111320 * k); };

/** How each kind of structure has produced: {kind: {fish, hours, mult}} from spotStats() output + the saved spots. */
export function kindStats(spots, stats) {
  const out = {}, base = stats?.base || 0;
  for (const s of spots || []) {
    const kind = KIND_OF_TYPE[s.location_type]; const st = stats?.spots?.[s.spot_id];
    if (!kind || !st) continue;
    const k = (out[kind] ||= { fish: 0, hours: 0 }); k.fish += st.fish; k.hours += st.hours;
  }
  for (const k of Object.values(out)) k.mult = base > 0 ? (k.fish + KIND_SHRINK_H * base) / (k.hours + KIND_SHRINK_H) / base : 1;
  return out;
}

/** Distance-weighted heat of saved spots near a point (1 = lake average), and the nearest producing one. */
function nearbyHeat(t, spots, stats) {
  let w = 0, sum = 0, best = null;
  for (const s of spots || []) {
    const st = stats?.spots?.[s.spot_id]; if (!st || st.hours < 1) continue;
    const d = metersApart(t, { lat: +s.lat, lon: +s.lon }); if (!(d <= NEAR_M)) continue;
    const wt = (1 - d / NEAR_M) * Math.min(1, st.hours / 4);
    w += wt; sum += wt * st.heat;
    if (!best || st.heat > best.heat) best = { name: s.name, heat: st.heat, d };
  }
  return { heat: (sum + 1) / (w + 1), best };   // shrunk toward 1 with one "average" pseudo-spot
}

/** [{...t, rank, n, score, parts: {structure, kind, nearby}, reasons: []}] best first; dry spots left out.
 *  level = today's lake level (ft) or null. */
export function rankTries(tries, { spots, stats, level = null } = {}) {
  const list = (tries || []).filter((t) => level == null || level - t.emin >= MIN_DEPTH_FT);
  if (!list.length) return [];
  const top = Math.max(...list.map((t) => t.score || 0)) || 1;
  const kinds = kindStats(spots, stats);
  const out = list.map((t) => {
    const structure = Math.max(0.05, (t.score || 0) / top);
    const k = kinds[t.kind], kind = k ? k.mult : 1;
    const near = nearbyHeat(t, spots, stats);
    const score = structure ** 0.4 * kind ** 0.4 * near.heat ** 0.2;
    const reasons = [];
    if (k && k.hours >= 1) reasons.push(`${KIND_LABEL[t.kind]} have produced ${k.mult >= 1.05 ? `${k.mult.toFixed(1)}× the lake average` : k.mult <= 0.95 ? `below average (${k.mult.toFixed(1)}×)` : "about average"} for this filter (${k.fish} fish in ${Math.round(k.hours)} h)`);
    else reasons.push(`No logged fishing on ${KIND_LABEL[t.kind].toLowerCase()} for this filter yet`);
    if (near.best && near.best.heat >= 1.2) reasons.push(`Near ${near.best.name}, a hot spot for this filter (${Math.round(near.best.d)} m away)`);
    else if (near.best && near.best.heat <= 0.7) reasons.push(`${near.best.name} nearby has been cold for this filter`);
    reasons.push(structure >= 0.75 ? "One of the strongest structure reads on the lake" : structure >= 0.45 ? "Good structure read" : "Smaller structure");
    return { ...t, score, parts: { structure, kind, nearby: near.heat }, reasons };
  }).sort((a, b) => b.score - a.score);
  out.forEach((t, i) => { t.rank = i + 1; t.n = out.length; });
  return out;
}
const KIND_LABEL = { point: "Points", break: "Steep breaks / bluffs", swing: "Channel swings", flat: "Flats by deep water" };
