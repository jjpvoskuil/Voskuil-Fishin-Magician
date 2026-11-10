// Automatic light/dark: Soft (dark) from 30 min before sunset until 30 min after sunrise, Light in between.
// A manual choice overrides it until the next automatic switch ("until"), or for good ("always").
import { getTimes } from "suncalc";

export const MARGIN_MIN = 30;
const M = 60e3;

/** {theme: 'light' | 'dark', next: Date of the next automatic switch} for a place and time. */
export function autoTheme(lat, lon, now = new Date()) {
  const today = getTimes(now, lat, lon);
  const lightStart = new Date(today.sunrise.getTime() + MARGIN_MIN * M);
  const darkStart = new Date(today.sunset.getTime() - MARGIN_MIN * M);
  if (now >= lightStart && now < darkStart) return { theme: "light", next: darkStart, lightStart, darkStart };
  if (now < lightStart) return { theme: "dark", next: lightStart, lightStart, darkStart };
  const tomorrow = getTimes(new Date(now.getTime() + 24 * 3600e3), lat, lon);
  return { theme: "dark", next: new Date(tomorrow.sunrise.getTime() + MARGIN_MIN * M), lightStart, darkStart };
}

/** Resolve the theme to show. pref = {mode: 'auto'|'light'|'dark', until: ms|null}. */
export function resolveTheme(pref, lat, lon, now = new Date()) {
  const auto = autoTheme(lat, lon, now);
  if (pref && pref.mode !== "auto" && (!pref.until || now.getTime() < pref.until)) return { ...auto, theme: pref.mode, manual: true };
  return { ...auto, manual: false };
}
