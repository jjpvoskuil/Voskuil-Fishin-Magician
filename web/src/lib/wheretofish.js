// Reports → "Where to fish" + the Lake Map's "Like today's lake" filter (John 11-20). New app only.
// Each outing (session, ≥0.5 h) gets a lake condition (lib/lakectx.js). Spots are ranked by fish/hr in the chosen
// conditions, shrunk 2 h toward the average for those conditions (same rule as the map's heat), with spot types
// summarized and the types we've hardly tried called out.
import { outings } from "./o2catch.js";
import { PHASE_LABEL, tempBand } from "./lakectx.js";
import { milesFromDam, uplakeFloorFt } from "./oxygen.js";

const SHRINK = 2, LIKE_TEMP = 6;

/** Outings with spot, phase, temp, band. ctx = lakeContext(waterLog). */
export function conditionedOutings(trips, ctx, opts = {}, spots = null) {
  const tempOf = new Map(), S = spots ? Object.fromEntries(spots.map((s) => [s.spot_id, s])) : null;
  for (const r of trips || []) { const id = `${r.owner}|${r.session_id || r.trip_id}`; const t = ctx.rowTemp(r); if (t != null && !tempOf.has(id)) tempOf.set(id, t); }
  return outings(trips, opts).map((o) => {
    const c = ctx.on(o.date), temp = tempOf.get(o.key) ?? c.surface_f ?? null;
    const sp = S?.[o.spot_id], mi = sp ? milesFromDam(Number(sp.lat), Number(sp.lon)) : null;
    const floor = c.floor_ft == null ? null : uplakeFloorFt(c.floor_ft, Number.isFinite(mi) ? mi : 0);
    return { ...o, phase: c.phase, temp, band: tempBand(temp), measured: c.measured, floor };
  });
}

/** Does an outing match the condition filter? cond = {phase?, band?, like?: {phase, temp}} */
export function matches(o, cond = {}) {
  if (cond.like) {
    if (o.phase !== cond.like.phase) return false;
    if (cond.like.temp != null && o.temp != null && Math.abs(o.temp - cond.like.temp) > LIKE_TEMP) return false;
    return true;
  }
  if (cond.phase && o.phase !== cond.phase) return false;
  if (cond.band && o.band !== cond.band) return false;
  return true;
}

/** Report: {base, spots: [{spot_id, name, type, outings, hours, fish, rate, raw, heat}], types: [...], untried: [type], n} */
export function whereToFish(trips, spots, ctx, { cond = {}, from = "", to = "", owner = null } = {}) {
  const S = Object.fromEntries((spots || []).map((s) => [s.spot_id, s]));
  const list = conditionedOutings(trips, ctx, { from, to, owner }, spots).filter((o) => matches(o, cond));
  const F = list.reduce((s, o) => s + o.fish, 0), H = list.reduce((s, o) => s + o.hours, 0), base = H > 0 ? F / H : 0;
  const agg = (keyOf) => { const by = new Map();
    for (const o of list) { const k = keyOf(o); if (k == null) continue; const a = by.get(k) || { key: k, outings: 0, hours: 0, fish: 0, last: null };
      a.outings++; a.hours += o.hours; a.fish += o.fish; if (o.fish && (!a.last || o.date > a.last)) a.last = o.date; by.set(k, a); }
    return [...by.values()].map((a) => { const rate = (a.fish + SHRINK * base) / (a.hours + SHRINK);
      return { ...a, raw: a.hours > 0 ? a.fish / a.hours : null, rate, heat: base > 0 ? rate / base : 1 }; }).sort((a, b) => b.rate - a.rate); };
  const spotRows = agg((o) => o.spot_id).map((a) => ({ ...a, spot_id: a.key, name: S[a.key]?.name || "Unknown spot", type: S[a.key]?.location_type || "Unspecified" }));
  const types = agg((o) => S[o.spot_id]?.location_type || "Unspecified");
  const triedTypes = new Set(types.filter((t) => t.outings >= 3).map((t) => t.key));
  const allTypes = [...new Set((spots || []).map((s) => s.location_type).filter(Boolean))];
  return { base, n: list.length, hours: H, fish: F, spots: spotRows, types, untried: allTypes.filter((t) => !triedTypes.has(t)) };
}

/** Lake Map: the same filter applied to trip rows (spotStats takes a row predicate). */
export function rowFilter(trips, ctx, cond) {
  const ok = new Set(conditionedOutings(trips, ctx).filter((o) => matches(o, cond)).map((o) => o.key));
  return (r) => ok.has(`${r.owner}|${r.session_id || r.trip_id}`);
}

export const likeLabel = (like) => (like ? `${PHASE_LABEL[like.phase] || like.phase}${like.temp != null ? `, ${Math.round(like.temp - LIKE_TEMP)}–${Math.round(like.temp + LIKE_TEMP)} °F water` : ""}` : "");
