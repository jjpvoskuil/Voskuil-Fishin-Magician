// Lure picker filters (John 11-11): broad lure-type families and color families, so "a crankbait" or "something
// chartreuse" narrows the tackle box in one tap. An item can be in several color families ("chartreuse sexy shad").
export const TYPE_FAMILIES = [
  ["Crankbaits", ["squarebill_crankbait", "medium_diving_crankbait", "deep_diving_crankbait", "lipless_crankbait"]],
  ["Jerkbaits", ["suspending_jerkbait"]],
  ["Bladed & spinners", ["chatterbait", "spinnerbait", "buzzbait", "blade_bait"]],
  ["Jigs", ["football_jig", "swim_jig"]],
  ["Topwater", ["walking_topwater", "popper", "buzzbait", "hollow_body_frog"]],
  ["Finesse", ["drop_shot", "ned_rig", "finesse_shaky_head", "wacky_rig_senko"]],
  ["Soft plastics", ["texas_rig_creature", "texas_rig_worm", "carolina_rig", "weightless_soft_plastic", "soft_swimbait", "drop_shot", "ned_rig", "finesse_shaky_head", "wacky_rig_senko"]],
  ["Swimbaits", ["soft_swimbait", "swim_jig"]],
  ["Spoons", ["spoon"]],
];
export const COLOR_FAMILIES = [
  ["Shad & white", /shad|white|bone|pearl|ghost|threadfin|shiner|baitfish|gizzard|herring|smoke|albino|sexy/i],
  ["Chartreuse", /chartreuse|chart\b|firetiger|fire tiger|citrus|lime|sexy shad|hot mustard|mustard/i],
  ["Green pumpkin & natural", /green pumpkin|pumpkin|watermelon|melon|natural|bluegill|perch|olive|summer craw|sprayed grass|goby/i],
  ["Craw, red & orange", /craw|red|orange|copper|rust|pb&j|peanut|delta|brown/i],
  ["Black & blue", /black|blue|junebug|june bug|purple|plum|moontalker|midnight/i],
  ["Chrome & metallic", /chrome|silver|gold|flash|metal|nickel|holo/i],
];
/** The color part of a description: after " - ", before the first comma ("Shadow Rap - Ghost Shad" → "Ghost Shad"). */
export const colorOf = (it) => { const d = String(it.description || ""), i = d.indexOf(" - "); return (i >= 0 ? d.slice(i + 3) : d).split(",")[0].trim(); };
export const inTypeFamily = (it, fam) => !fam || (TYPE_FAMILIES.find(([n]) => n === fam)?.[1] || []).includes(it.category);
export const inColorFamily = (it, fam) => !fam || !!COLOR_FAMILIES.find(([n]) => n === fam)?.[1].test(`${colorOf(it)} ${it.description || ""}`);
/** Only the families that have something in this list (so no dead chips). */
export const typeFamiliesIn = (items) => TYPE_FAMILIES.map(([n]) => n).filter((n) => items.some((it) => inTypeFamily(it, n)));
export const colorFamiliesIn = (items) => COLOR_FAMILIES.map(([n]) => n).filter((n) => items.some((it) => inColorFamily(it, n)));
