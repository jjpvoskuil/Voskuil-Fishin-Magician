// Where bass-safe oxygen runs out at Nolin, from the Army Corps' own depth profiles.
// SEASON = Corps Louisville District temp/DO profiles at the dam (station NRR20001), 1989–2026, ~1,000 profiles at
// 5-ft steps (file Nolin_Temp_DO_Data.xlsx, from the Corps, 2026-11-20). Per half-month: the "oxygen floor" (shallowest
// depth where DO falls below 5 mg/L, interpolated; a profile with 5+ all the way down counts as the bottom, 90-95 ft),
// as median / 25th / 75th percentile, the thermocline median (only where >80% of profiles were stratified), the % of
// profiles where even the SURFACE was under 5 mg/L (the fall turnover crash), and how many profiles.
// Up-lake: typical August floor 17.1 ft at the dam, 14.4 ft 3.4 mi up, 13.2 ft 5.4 mi up, 11.5 ft 10.4 mi up.
// The live USACE report page (fetched by fm-usace-wq) lists the latest full dam profile, so a fresh one wins.

export const OXYGEN_OK_MG_L = 5.0;
// [month, half (1 = days 1-15, 2 = 16-end), floor median, p25, p75, thermocline median|null, surface-crash %, profiles]
export const SEASON = [
  [4, 1, 90.0, 79.0, 95.0, null, 0.0, 27],
  [4, 2, 80.2, 72.0, 95.0, 25.5, 0.0, 31],
  [5, 1, 55.0, 37.4, 70.6, 17.5, 0.0, 71],
  [5, 2, 26.5, 20.6, 35.0, 15.5, 0.0, 64],
  [6, 1, 17.8, 13.6, 24.4, 15.5, 0.0, 80],
  [6, 2, 16.5, 14.0, 22.4, 15.5, 0.0, 68],
  [7, 1, 17.7, 14.1, 21.1, 16.5, 1.3, 75],
  [7, 2, 17.2, 14.3, 20.7, 17.5, 2.7, 75],
  [8, 1, 17.0, 15.0, 20.3, 20.5, 4.1, 73],
  [8, 2, 17.9, 15.5, 20.8, 22.5, 1.3, 77],
  [9, 1, 20.4, 16.3, 23.2, 25.5, 2.8, 72],
  [9, 2, 26.2, 21.1, 29.7, 31.5, 2.9, 70],
  [10, 1, 26.1, 0.0, 33.1, 37.5, 21.5, 65],
  [10, 2, 10.0, 0.0, 45.2, null, 29.0, 62],
  [11, 1, 25.0, 0.0, 59.2, null, 29.0, 31],
  [11, 2, 55.0, 45.2, 68.9, null, 6.7, 15],
];
export const SEASON_SOURCE = "Army Corps dam profiles, 1989–2026";
const UPLAKE = [[0, 17.1], [3.4, 14.4], [5.4, 13.2], [10.4, 11.5]]; // [miles from dam, Aug floor ft]
export const DAM = { lat: 37.279167, lon: -86.246944 }; // Corps station NRR20001
export const PROFILE_FRESH_DAYS = 10;

export function seasonFor(dateStr) {
  const m = Number(dateStr.slice(5, 7)), day = Number(dateStr.slice(8, 10)), half = day <= 15 ? 1 : 2;
  const r = SEASON.find((s) => s[0] === m && s[1] === half);
  if (!r) return null; // Dec–Mar: lake mixed, Corps rarely samples
  return { floor_ft: r[2], low_ft: r[3], high_ft: r[4], thermocline_ft: r[5], crash_pct: r[6], profiles: r[7] };
}

/** Straight-line miles from the dam station (lat/lon in degrees). */
export function milesFromDam(lat, lon) {
  if (lat == null || lon == null) return null;
  return Math.hypot((lat - DAM.lat) * 69.0, (lon - DAM.lon) * 55.0);
}
/** Scale a dam-site floor to a spot up the lake (the Aug pattern: about a third shallower 10 mi up). */
export function uplakeFloorFt(damFloorFt, miles) {
  if (damFloorFt == null || miles == null || miles <= 0) return damFloorFt;
  const mi = Math.min(miles, UPLAKE[UPLAKE.length - 1][0]);
  let i = 1; while (i < UPLAKE.length - 1 && UPLAKE[i][0] < mi) i++;
  const [m0, f0] = UPLAKE[i - 1], [m1, f1] = UPLAKE[i];
  const ratio = (f0 + ((mi - m0) / (m1 - m0)) * (f1 - f0)) / UPLAKE[0][1];
  return Math.round(damFloorFt * ratio * 10) / 10;
}

const ROW = /<tr>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<td>([\s\S]*?)<\/td>\s*<\/tr>/gi;
/** The latest full "Dam Site" profile on the USACE report → {observed_at, rows: [{depth_ft, temp_f, do_mg_l}]} or null. */
export function parseDamProfile(html, station = "Dam Site") {
  const by = new Map();
  for (const m of html.matchAll(ROW)) {
    const [, st, when, depth, tempC, doMg] = m;
    if (st.trim() !== station) continue;
    const w = /^(\d{4})(\d{2})(\d{2}), (\d{2})(\d{2})$/.exec(when.trim()); if (!w) continue;
    const day = `${w[1]}-${w[2]}-${w[3]}`, z = parseFloat(depth), t = parseFloat(tempC), d = parseFloat(doMg);
    if ([z, d].some(Number.isNaN)) continue;
    if (!by.has(day)) by.set(day, { observed_at: `${day}T${w[4]}:${w[5]}:00`, rows: [] });
    by.get(day).rows.push({ depth_ft: z, temp_f: Number.isNaN(t) ? null : Math.round((t * 9 / 5 + 32) * 10) / 10, do_mg_l: d });
  }
  const days = [...by.keys()].sort(); if (!days.length) return null;
  const p = by.get(days[days.length - 1]); p.rows.sort((a, b) => a.depth_ft - b.depth_ft);
  return p.rows.length >= 3 ? p : null;
}

/** Shallowest depth (interpolated) where DO drops under the threshold: 0 if the surface is already low,
 *  null if it never does (oxygen all the way down). */
export function floorFromProfile(rows, threshold = OXYGEN_OK_MG_L) {
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].do_mg_l < threshold) {
      if (i === 0) return 0;
      const a = rows[i - 1], b = rows[i];
      return Math.round((a.depth_ft + ((a.do_mg_l - threshold) / (a.do_mg_l - b.do_mg_l)) * (b.depth_ft - a.depth_ft)) * 10) / 10;
    }
  }
  return null;
}

const daysBetween = (a, b) => Math.round((Date.parse(b.slice(0, 10)) - Date.parse(a.slice(0, 10))) / 864e5);
const ft = (x) => `${Math.round(x)} ft`;

/** What to tell an angler about oxygen today: a fresh Corps profile if there is one, else the typical year.
 *  → {floor_ft|null, kind: "ok"|"floor"|"low", source: "profile"|"typical"|null, observed_at, headline, detail, warning} */
export function oxygenOutlook(todayStr, profile = null) {
  const s = seasonFor(todayStr);
  const fresh = profile && daysBetween(profile.observed_at, todayStr) <= PROFILE_FRESH_DAYS ? profile : null;
  const fall = Number(todayStr.slice(5, 7)) >= 10 || (todayStr.slice(5, 7) === "09" && Number(todayStr.slice(8, 10)) > 15);
  let warning = null;
  if (s && s.crash_pct >= 15) warning = `Turnover season: in about ${Math.round(s.crash_pct)}% of past Corps checks this time of year the whole lake was low on oxygen, surface included. Expect scattered, sluggish fish until it recovers (usually by late November).`;
  if (fresh) {
    const f = floorFromProfile(fresh.rows), surf = fresh.rows[0].do_mg_l;
    const when = `Corps dam profile ${Number(fresh.observed_at.slice(5, 7))}/${fresh.observed_at.slice(8, 10)}`;
    if (f === 0) {
      const f3 = floorFromProfile(fresh.rows, 3.0);
      return { floor_ft: 0, kind: "low", source: "profile", observed_at: fresh.observed_at, headline: "Low top to bottom",
        detail: `${when}: surface ${surf.toFixed(1)} mg/L, under the 5 mg/L bass like${f3 ? ` (stays above 3 mg/L to about ${ft(f3)})` : ""}. The lake is turning over.`,
        warning: warning || "The lake is turning over: oxygen is low even at the surface. Fish the top 10–15 ft, slow down, and look for wind-blown banks and creek mouths with fresher water." };
    }
    if (f == null) return { floor_ft: null, kind: "ok", source: "profile", observed_at: fresh.observed_at, headline: "OK to bottom",
      detail: `${when}: 5+ mg/L all the way down (${ft(fresh.rows[fresh.rows.length - 1].depth_ft)}). Depth isn't limited by oxygen right now.`, warning: fall ? warning : null };
    return { floor_ft: f, kind: "floor", source: "profile", observed_at: fresh.observed_at, headline: `~${ft(f)}`,
      detail: `${when}: oxygen drops under 5 mg/L at about ${ft(f)} near the dam. Up the lake it's shallower (about a third less 10 miles up). Fish deeper than that are rarely active bass.`,
      warning: fall ? warning : null };
  }
  if (!s) return { floor_ft: null, kind: "ok", source: null, observed_at: null, headline: "Not limited",
    detail: "Winter and early spring: the lake is mixed and oxygen isn't limiting depth. (The Corps rarely samples Dec–Mar.)", warning: null };
  if (s.crash_pct >= 15) return { floor_ft: null, kind: "unsettled", source: "typical", observed_at: null, headline: "Unsettled",
    detail: `Typical for this time of year (${SEASON_SOURCE}): turnover makes oxygen swing from year to year, from fine all the way down to low at the surface. No fresh Corps profile in the last ${PROFILE_FRESH_DAYS} days.`, warning };
  const deep = s.floor_ft >= 45;
  return { floor_ft: deep ? null : s.floor_ft, kind: deep ? "ok" : "floor", source: "typical", observed_at: null,
    headline: deep ? "Not limited" : `~${ft(s.floor_ft)}`,
    detail: deep ? `Typical for this time of year (${SEASON_SOURCE}): oxygen holds deep — median floor ${ft(s.floor_ft)} at the dam.`
      : `Typical for this time of year (${SEASON_SOURCE}): oxygen runs out at about ${ft(s.floor_ft)} near the dam (most years ${ft(s.low_ft)}–${ft(s.high_ft)}), shallower up the lake. No fresh Corps profile in the last ${PROFILE_FRESH_DAYS} days.`,
    warning };
}

// ---------------------------------------------------------------- lure advice (John 11-20: "switch the lure advice over")
/** The depth limit to plan lures around at a spot on a date: {limit_ft|null, kind, line (rationale text)|null}.
 *  "floor" = 5 mg/L floor scaled for how far up the lake the spot is; "low" (turnover, surface already < 5) = where it
 *  drops under 3 mg/L in the fresh profile; "ok"/"unsettled" = no limit (unsettled still explains why). */
export function lureOxygenLimit(dateStr, profile = null, spot = null) {
  const o = oxygenOutlook(dateStr, profile);
  const miles = spot ? milesFromDam(Number(spot.lat), Number(spot.lon)) : null;
  const where = miles != null && miles >= 1 ? ` at this spot (~${Math.round(miles)} mi up from the dam)` : " near the dam";
  const src = o.source === "profile" ? "the latest Corps profile" : `Corps records for this time of year`;
  if (o.kind === "floor" && o.floor_ft != null) {
    const lim = Math.round(uplakeFloorFt(o.floor_ft, Number.isFinite(miles) ? miles : 0));
    return { limit_ft: lim, kind: "floor", line: `Oxygen runs out around ${lim} ft${where}, per ${src} — baits are checked against that: keep them working above it, on the top and edge of the break, not below.` };
  }
  if (o.kind === "low") {
    const f3 = profile ? floorFromProfile(profile.rows, 3.0) : null;
    return { limit_ft: f3 ? Math.round(f3) : null, kind: "low", line: `Turnover: oxygen is low top to bottom right now (per ${src})${f3 ? `, and drops off fast below about ${Math.round(f3)} ft` : ""}. Expect sluggish, scattered fish — slow down and favor the upper water column.` };
  }
  if (o.kind === "unsettled") return { limit_ft: null, kind: "unsettled", line: "Turnover season: oxygen at depth swings from year to year right now — if fish seem shut down, try shallower and slower." };
  return { limit_ft: null, kind: o.kind, line: null };
}

/** One lure block's oxygen note for a depth limit, or null. `range` = the profile's depth_range_ft. */
export function oxygenNote(range, limit) {
  if (limit == null || !range) return null;
  const [lo, hi] = range;
  if (hi === 0) return null; // topwater
  if (lo >= limit) return `⚠️ Runs ${lo}–${hi} ft, at or below today's oxygen floor (~${limit} ft) here — few active bass down there. Use it only on the top of the break, or pick a shallower bait.`;
  if (hi > limit) return `Keep it above ~${limit} ft — below that, oxygen is too low for active bass today.`;
  return null;
}
const blockBelow = (range, limit) => limit != null && range && range[1] !== 0 && range[0] >= limit;

/** rec from recommend() → same shape with oxygen notes on each block (block.oxygen), baits that run entirely below the
 *  limit moved to the end of the second choices, a rationale line, and a caveat if the marked fish are below it. */
export function applyOxygen(rec, ox, profiles, fishDepth = null) {
  if (!rec || !ox || (!ox.line && ox.limit_ft == null)) return rec;
  const lim = ox.limit_ft, ann = (b) => ({ ...b, oxygen: oxygenNote(profiles[b.key]?.depth_range_ft, lim) });
  let first = rec.first_choice.map(ann), second = rec.second_choice.map(ann);
  const below = (b) => blockBelow(profiles[b.key]?.depth_range_ft, lim);
  const moved = [...first.filter(below), ...second.filter(below)];
  first = first.filter((b) => !below(b)); second = [...second.filter((b) => !below(b)), ...moved];
  if (!first.length && second.length) first = [second.shift()];
  const rationale = [...(ox.line ? [ox.line] : []), ...rec.rationale];
  if (lim != null && fishDepth != null && fishDepth > lim + 2) rationale.splice(1, 0, `Heads up: you're marking fish around ${Math.round(fishDepth)} ft, below today's oxygen floor (~${lim} ft) — likely baitfish, another species, or bass passing through. Target the fish suspended near ${lim} ft or shallower.`);
  return { ...rec, first_choice: first, second_choice: second, rationale };
}
/** Same notes on picks (picks.js may build blocks the plan didn't have). */
export function annotatePicks(picks, ox, profiles) {
  if (!picks || !ox || ox.limit_ft == null) return picks;
  return { ...picks, picks: picks.picks.map((p) => ({ ...p, block: { ...p.block, oxygen: p.block.oxygen ?? oxygenNote(profiles[p.key]?.depth_range_ft, ox.limit_ft) } })) };
}
