// Soft-plastic bait styles (punch-list #103, Matthew 2026-11-14).
//
// The tackle box stores WHAT a soft plastic is (worm, creature, fluke, paddle tail, TRD); a session stores HOW it was
// fished (Texas rig, drop shot, Ned rig, ...). Trip rows keep the rig as conditions.lure_category — the engine lure key
// the picks, reports and leaderboards learn from — plus the style as conditions.bait_style.
//
// Older tackle-box items still carry a rig key (texas_rig_worm, drop_shot, ...): styleOf() maps those to a style, so
// they behave like the new ones until someone re-types them.
import DATA from "./data/lures.data.json" with { type: "json" };
const { LURE_PROFILES } = DATA; // straight from the data (lures.js imports this module)

export const BAIT_STYLES = {
  sp_worm: { name: "Soft Plastic (Worm)", defaultRig: "texas" },
  sp_creature: { name: "Soft Plastic (Creature Bait)", defaultRig: "texas" },
  sp_fluke: { name: "Soft Plastic (Fluke)", defaultRig: "weightless" },
  sp_paddle_tail: { name: "Soft Plastic (Paddle Tail)", defaultRig: "swimbait_head" },
  sp_trd: { name: "Soft Plastic (TRD / Ned)", defaultRig: "ned" },
};
export const BAIT_STYLE_KEYS = Object.keys(BAIT_STYLES);
export const isBaitStyle = (k) => !!k && k in BAIT_STYLES;

/** Rigs, in the order they're offered. `key(style)` = the engine lure key a trip row records. */
export const RIGS = [
  { id: "texas", name: "Texas rig", key: (s) => (s === "sp_creature" ? "texas_rig_creature" : "texas_rig_worm") },
  { id: "drop_shot", name: "Drop shot", key: () => "drop_shot" },
  { id: "ned", name: "Ned rig", key: () => "ned_rig" },
  { id: "shaky_head", name: "Shaky head", key: () => "finesse_shaky_head" },
  { id: "wacky", name: "Wacky rig", key: () => "wacky_rig_senko" },
  { id: "carolina", name: "Carolina rig", key: () => "carolina_rig" },
  { id: "weightless", name: "Weightless", key: () => "weightless_soft_plastic" },
  { id: "swimbait_head", name: "Swimbait jighead", key: () => "soft_swimbait" },
  { id: "underspin", name: "Underspin", key: () => "underspin" },
];
const RIG_BY_ID = Object.fromEntries(RIGS.map((r) => [r.id, r]));

/** Engine keys that are soft-plastic rigs (what the old tackle box used as types). */
const RIG_KEY_STYLE = {
  texas_rig_worm: "sp_worm", drop_shot: "sp_worm", finesse_shaky_head: "sp_worm", wacky_rig_senko: "sp_worm",
  carolina_rig: "sp_worm", texas_rig_creature: "sp_creature", weightless_soft_plastic: "sp_fluke",
  soft_swimbait: "sp_paddle_tail", ned_rig: "sp_trd",
};
export const SOFT_PLASTIC_RIG_KEYS = Object.keys(RIG_KEY_STYLE);
export const isSoftPlasticRigKey = (k) => !!k && k in RIG_KEY_STYLE;

/** The bait style of a tackle-box category (new style key, or an old rig key), else null. */
export const styleOf = (category) => (isBaitStyle(category) ? category : RIG_KEY_STYLE[category] || null);

/** Which rig an engine key is (for showing a trip's current rig), else null. */
export function rigIdOf(key) {
  for (const r of RIGS) if (r.key("sp_worm") === key || r.key("sp_creature") === key) return r.id;
  return null;
}
export const rigKey = (rigId, style) => RIG_BY_ID[rigId]?.key(style) || null;
export const rigName = (rigId) => RIG_BY_ID[rigId]?.name || rigId;

// The tagger's keyword rules (same as lures.js guessCategoryFromText; kept here to avoid an import cycle).
function guessFromName(item) {
  const t = `${item?.brand || ""} ${item?.description || ""}`.toLowerCase();
  for (const [cat, phrases] of DATA.CATEGORY_KEYWORD_RULES) if (phrases.some((p) => t.includes(p))) return cat;
  return null;
}

/** Rig to preselect for a tackle-box item: how it was rigged last time it was fished, else what the old type said,
 *  else the style's usual rig. */
export function defaultRigFor(item, trips) {
  const id = item?.item_id;
  if (id && trips?.length) {
    let best = null;
    for (const t of trips) {
      let c = t.conditions; if (typeof c === "string") { try { c = JSON.parse(c); } catch { c = null; } }
      if (!c || c.item_id !== id || !c.lure_category) continue;
      const when = `${t.trip_date || ""}T${c.lure_start_time || ""}`;
      if (!best || when > best.when) best = { when, key: c.lure_category };
    }
    const r = best && rigIdOf(best.key); if (r) return r;
  }
  const old = rigIdOf(item?.category); if (old) return old;
  const named = rigIdOf(guessFromName(item)); if (named) return named;   // "Roboworm" → drop shot, "Senko" → wacky
  return BAIT_STYLES[styleOf(item?.category)]?.defaultRig || "texas";
}

/** Engine keys a bait style can be fished as, for "do I own something for this pick?" (tackle-box gaps, owned items
 *  in a lure block). Kept to the common pairings so a worm doesn't claim every rig there is. */
export const STYLE_SERVES = {
  sp_worm: ["texas_rig_worm", "drop_shot", "finesse_shaky_head", "wacky_rig_senko", "carolina_rig"],
  sp_creature: ["texas_rig_creature", "carolina_rig"],
  sp_fluke: ["weightless_soft_plastic"],
  sp_paddle_tail: ["soft_swimbait", "underspin"],
  sp_trd: ["ned_rig"],
};

/** Engine keys a tackle-box item counts toward (a hard bait = its own key). */
export function servesKeys(category) {
  if (isBaitStyle(category)) return STYLE_SERVES[category];
  return category && category in LURE_PROFILES ? [category] : [];
}

/** Display name for any tackle-box or trip category. */
export const categoryName = (k) => (isBaitStyle(k) ? BAIT_STYLES[k].name : k && LURE_PROFILES[k] ? LURE_PROFILES[k].name : null);

/** Type choices for a tackle-box item: hard baits + bait styles; old rig keys are offered only when the item
 *  already has one (so its current value still shows). */
export function inventoryTypeOptions(current) {
  const hard = Object.entries(LURE_PROFILES).filter(([k]) => !isSoftPlasticRigKey(k)).map(([k, p]) => [k, p.name]);
  const soft = BAIT_STYLE_KEYS.map((k) => [k, BAIT_STYLES[k].name]);
  const keep = current && isSoftPlasticRigKey(current) ? [[current, `${LURE_PROFILES[current].name} (old type)`]] : [];
  return [...soft, ...hard, ...keep].sort((a, b) => a[1].localeCompare(b[1]));
}

/** A tagger guess (engine key) as a tackle-box type: soft-plastic rigs become their bait style. */
export const toInventoryCategory = (k) => (isSoftPlasticRigKey(k) ? RIG_KEY_STYLE[k] : k || "");
