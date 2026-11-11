// Trip History logic (old pages/4_Trip_History.py, pure parts): group trip rows into sessions, split each session into
// "legs" (one location under one set of conditions — a mid-session move or conditions update starts a new leg),
// filter, and the edits that keep fish_caught/biggest_fish_lb consistent with the fish list.
import { parseConditions } from "./calibration.js";
import { LURE_PROFILES } from "./lures.js";
import { resolveWaterClarity } from "./onwater.js";

export const LEG_CONDITION_KEYS = ["water_temp_f", "secchi_ft", "stain_color", "stirred_up", "wind_band", "wind_direction",
  "light_condition", "precipitation", "fish_depth_ft", "forage_seen", "fish_activity", "forage_activity"];
const stable = (v) => JSON.stringify(v === undefined ? null : v);

export const lureTypeLabel = (c) => (c.lure_category ? LURE_PROFILES[c.lure_category]?.name || c.lure_category : "Unspecified / manual entry");
const groupKey = (r) => ((r.session_id || "").trim() ? r.session_id.trim() : `solo:${r.trip_id}`);
const memberSort = (r) => parseConditions(r).lure_start_time || r.logged_at || "";
const legKey = (r) => { const c = parseConditions(r); return [r.spot_id || r.spot_name || "", ...LEG_CONDITION_KEYS.map((k) => stable(c[k]))].join("\u0001"); };
const hm = (t) => { if (!t) return null; const [h, m] = t.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };

export function legTimeSpan(rows) {
  const cs = rows.map(parseConditions), starts = cs.map((c) => c.lure_start_time).filter(Boolean).sort();
  if (!starts.length) return "";
  if (cs.some((c) => !c.lure_end_time)) return `${hm(starts[0])} – still open`;
  return `${hm(starts[0])} – ${hm(cs.map((c) => c.lure_end_time).sort().pop())}`;
}

/** One object per session, newest first. spotName(id) gives the current saved name for a spot id. */
export function buildSessions(trips, spotName = () => null) {
  const groups = new Map();
  for (const r of trips || []) { const k = groupKey(r); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(r); }
  const out = [];
  for (const [key, members] of groups) {
    const rows = [...members].sort((a, b) => (memberSort(a) < memberSort(b) ? -1 : memberSort(a) > memberSort(b) ? 1 : 0));
    const first = rows[0], c0 = parseConditions(first);
    const legMap = new Map();
    for (const r of rows) { const k = legKey(r); if (!legMap.has(k)) legMap.set(k, []); legMap.get(k).push(r); }
    const legs = [...legMap.values()].map((lr) => ({ rows: lr, spot_id: lr[0].spot_id || "", location: spotName(lr[0].spot_id) || lr[0].spot_name || "Unknown location",
      segment: lr[0].segment, structure_type: lr[0].structure_type, time_span: legTimeSpan(lr) }));
    const fish = rows.flatMap((r) => { const f = parseConditions(r).fish; return Array.isArray(f) ? f : []; });
    const weights = rows.map((r) => Number(r.biggest_fish_lb)).filter((w) => w > 0);
    out.push({
      key, rows, date: first.trip_date || null, angler: c0.angler || "", owner: first.owner || "",
      legs, locations: [...new Set(legs.map((l) => l.location))], segments: [...new Set(legs.map((l) => l.segment).filter(Boolean))],
      fish_total: rows.reduce((a, r) => a + (parseInt(r.fish_caught, 10) || 0), 0), biggest: weights.length ? Math.max(...weights) : null,
      species: [...new Set(fish.map((f) => f.species).filter(Boolean))],
      lure_types: new Set(rows.map((r) => lureTypeLabel(parseConditions(r)))), lures: new Set(rows.map((r) => r.lure_used).filter(Boolean)),
      start: memberSort(first), open: rows.some((r) => !parseConditions(r).lure_end_time && parseConditions(r).source === "spot_session"),
    });
  }
  return out.sort((a, b) => ((b.date || "") + b.start).localeCompare((a.date || "") + a.start));
}

/** f = {from, to, mine (email|null), anglers[], segments[], locations[], lureTypes[], lures[]} — empty list = no filter. */
export function matches(s, f) {
  if (f.from && (!s.date || s.date < f.from)) return false;
  if (f.to && (!s.date || s.date > f.to)) return false;
  if (f.mine && s.owner !== f.mine) return false;
  const any = (list, have) => !list?.length || list.some((x) => (have instanceof Set ? have.has(x) : have.includes(x)));
  return any(f.anglers, [s.angler]) && any(f.segments, s.segments) && any(f.locations, s.locations) && any(f.lureTypes, s.lure_types) && any(f.lures, s.lures);
}

/** Totals for a list of sessions. */
export function summarize(sessions) {
  const hours = sessions.reduce((a, s) => a + s.rows.reduce((b, r) => b + lureHours(r), 0), 0);
  return { sessions: sessions.length, fish: sessions.reduce((a, s) => a + s.fish_total, 0), hours };
}
export function lureHours(r) {
  const c = parseConditions(r); if (!c.lure_start_time || !c.lure_end_time) return 0;
  const m = (t) => { const [h, mm, ss] = t.split(":").map(Number); return h * 60 + mm + (ss || 0) / 60; };
  const d = m(c.lure_end_time) - m(c.lure_start_time); return d > 0 ? d / 60 : 0;
}

/** fish_caught / biggest_fish_lb from a fish list (same math as Spot Session). */
export function fishTotals(fish) {
  if (!fish?.length) return { fish_caught: 0, biggest_fish_lb: null };
  const ws = fish.map((f) => f.weight_lb).filter((w) => w);
  return { fish_caught: fish.reduce((a, f) => a + (f.count || 1), 0), biggest_fish_lb: ws.length ? Math.max(...ws) : null };
}

/** Apply a leg edit to each of its rows. edit = {segment, spot_id, spot_name, structure_type, cond (shared values),
 *  changed (fields you changed), lures: {trip_id: {lure_used, color_used, technique_used, notes, lure_category,
 *  trailer_used, trailer_name, trailer_color, fish | fish_caught+biggest_fish_lb}}}. Predicted score stays as recorded. */
export function applyLegEdit(rows, edit, date) {
  const clarity = resolveWaterClarity(edit.cond.secchi_ft ?? 2.5, edit.cond.stain_color, !!edit.cond.stirred_up);
  return rows.map((r) => {
    const c = parseConditions(r), le = edit.lures[r.trip_id] || {};
    const sources = { ...(c.field_sources || {}) }; for (const k of edit.changed || []) sources[k] = "you";
    const cond = { ...c, ...edit.cond, field_sources: Object.keys(sources).length ? sources : c.field_sources,
      lure_category: le.lure_category !== undefined ? le.lure_category : c.lure_category,
      trailer_used: le.trailer_used ?? c.trailer_used, trailer_name: le.trailer_used === false ? null : le.trailer_name ?? c.trailer_name,
      trailer_color: le.trailer_used === false ? null : le.trailer_color ?? c.trailer_color };
    const structured = Array.isArray(c.fish) && c.source === "spot_session";
    let totals = { fish_caught: r.fish_caught, biggest_fish_lb: r.biggest_fish_lb };
    if (structured && le.fish) { cond.fish = le.fish; totals = fishTotals(le.fish); }
    else if (!structured && le.fish_caught !== undefined) totals = { fish_caught: le.fish_caught, biggest_fish_lb: le.biggest_fish_lb ?? null };
    const { conditions_json, ...rest } = r;
    return { ...rest, trip_date: date || r.trip_date, segment: edit.segment ?? r.segment, spot_id: edit.spot_id ?? r.spot_id, spot_name: edit.spot_name ?? r.spot_name,
      structure_type: edit.structure_type ?? r.structure_type, water_clarity: clarity, lure_used: le.lure_used ?? r.lure_used, color_used: le.color_used ?? r.color_used,
      technique_used: le.technique_used ?? r.technique_used, notes: le.notes ?? r.notes, ...totals, conditions: cond };
  });
}
