// Tackle box helpers: how each lure has done for you (from the trip log), Cabela's links and the saved picks for
// gaps. Cabela's can't be searched live from the app (their site blocks servers and other websites — tested 11-10),
// so "Find on Cabela's" opens their own search in a new tab and gap suggestions come from the old app's curated list.
import { parseConditions } from "./calibration.js";
import { lureHours } from "./history.js";
import { itemLabel, LURE_PROFILES } from "./lures.js";
import PICKS from "./data/cabelas_picks.json" with { type: "json" };
import { BAIT_STYLE_KEYS, categoryName, isBaitStyle } from "./baits.js";

export const cabelasSearchUrl = (q) => `https://www.cabelas.com/SearchDisplay#q=${encodeURIComponent((q || "").trim())}`;
export const savedPicks = (category) => PICKS[category] || [];
export const typeName = (k) => categoryName(k) || "No type set";

/** {label: {fish, hours, sessions, last}} for every lure label in the trip log (all anglers, or one owner). */
export function usageByLabel(trips, owner = null) {
  const out = {};
  for (const r of trips || []) {
    if (owner && (r.owner || "").toLowerCase() !== owner.toLowerCase()) continue;
    const label = (r.lure_used || "").trim(); if (!label) continue;
    const u = (out[label] ||= { fish: 0, hours: 0, sessions: new Set(), last: null });
    u.fish += parseInt(r.fish_caught, 10) || 0; u.hours += lureHours(r); u.sessions.add(r.session_id || r.trip_id);
    if (!u.last || r.trip_date > u.last) u.last = r.trip_date;
  }
  for (const u of Object.values(out)) u.sessions = u.sessions.size;
  return out;
}
export const usageFor = (usage, item) => usage[itemLabel(item)] || null;

/** Lure-type groups for the list: [{key, name, items}] in the app's type order, "No type set" last. */
export function groupByType(items) {
  const order = [...BAIT_STYLE_KEYS, ...Object.keys(LURE_PROFILES)], g = {};
  for (const it of items) (g[it.category && (LURE_PROFILES[it.category] || isBaitStyle(it.category)) ? it.category : ""] ||= []).push(it);
  return [...order.filter((k) => g[k]), ...(g[""] ? [""] : [])].map((k) => ({ key: k, name: typeName(k), items: g[k] }));
}

/** New item from the add form (old LureItem shape: brand, description, category, quantity, …). */
export function newItem(fields, id) {
  const now = new Date().toISOString().slice(0, 19);
  return { item_id: id, added_at: now, updated_at: now, brand: (fields.brand || "").trim(), description: (fields.description || "").trim(),
    category: fields.category || "", sku: fields.sku || "", price: fields.price ?? "", quantity: String(fields.quantity ?? 1), package_qty: fields.package_qty ?? "",
    image_url: fields.image_url || "", image_filename: "", image_path: fields.image_path || "", thumb_path: fields.thumb_path || "", source: fields.source || "Manual" };
}

/** Description from a scan: "Model - Color, Size" (the old app's "name - color" convention). */
export function describeScan(s) {
  return [s.product_name, [s.color, s.size].filter(Boolean).join(", ")].filter(Boolean).join(" - ");
}
