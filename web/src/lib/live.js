// Live data for the screens: weather (Open-Meteo), lake level (USGS), Army Corps water quality (via Edge Function),
// and the trip log. Each keeps its last good answer in this browser, so a weak signal at the lake still shows the
// latest data (with its age) instead of nothing.
import { useCallback, useEffect, useState } from "react";
import { fetchForecast } from "./weather.js";
import { fetchLakeLevels, parseSurfaceWaterQuality } from "./lake.js";

const read = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } };
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage full or blocked: fine */ } };

/** Re-run `load` on mount, when the app comes back to the screen, and every `everyMs`. */
function useRefreshing(load, everyMs) {
  useEffect(() => {
    load();
    const t = setInterval(load, everyMs);
    const onShow = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onShow);
    window.addEventListener("pageshow", onShow);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", onShow); window.removeEventListener("pageshow", onShow); };
  }, [load, everyMs]);
}

/** Cached fetch: answer from cache if younger than maxAgeMs, else fetch; on failure keep the cached value + error. */
function useCached(key, fetcher, maxAgeMs) {
  const [state, setState] = useState(() => { const c = read(key); return { value: c?.value ?? null, at: c?.at ?? null, error: "", loading: !c }; });
  const load = useCallback(async (force = false) => {
    const c = read(key);
    if (!force && c && Date.now() - c.at < maxAgeMs) { setState({ value: c.value, at: c.at, error: "", loading: false }); return; }
    setState((s) => ({ ...s, loading: true }));
    try { const value = await fetcher(); const at = Date.now(); write(key, { value, at }); setState({ value, at, error: "", loading: false }); }
    catch (e) { setState((s) => ({ ...s, error: e.message || String(e), loading: false })); }
  }, [key, fetcher, maxAgeMs]);
  useRefreshing(load, maxAgeMs);
  return { ...state, reload: () => load(true) };
}

const getWeather = () => fetchForecast(7);
const getLake = () => fetchLakeLevels(1);
/** {value: bundle, at, error, loading, reload} — refreshed every 30 min */
export const useWeather = () => useCached("fm.wx", getWeather, 30 * 60e3);
/** {value: [{elevation_ft, observed_at, site_name}], …} — refreshed every 30 min */
export const useLakeLevel = () => useCached("fm.lake", getLake, 30 * 60e3);

/** Latest Army Corps surface reading: live from the report (logged once, shared with everyone), else the last one logged. */
export function useWaterQuality(db) {
  const [state, setState] = useState({ reading: null, live: false, error: "", loading: true });
  const load = useCallback(async () => {
    if (!db) return;
    let live = null, err = "";
    try { live = parseSurfaceWaterQuality(await db.usaceHtml()); } catch (e) { err = e.message || String(e); }
    if (live) {
      try { await db.addWaterQuality(live); } catch { /* logging is best-effort */ }
      setState({ reading: live, live: true, error: "", loading: false }); return;
    }
    try { const log = await db.listWaterQuality(); setState({ reading: log.length ? log[log.length - 1] : null, live: false, error: err, loading: false }); }
    catch (e) { setState({ reading: null, live: false, error: err || e.message, loading: false }); }
  }, [db]);
  useRefreshing(load, 6 * 3600e3);
  return state;
}

/** The whole trip log (everyone's), reloaded when the app comes back to the screen. */
export function useTrips(db) {
  const [state, setState] = useState({ trips: null, error: "" });
  const load = useCallback(async () => { if (!db) return; try { setState({ trips: await db.listTrips(), error: "" }); } catch (e) { setState((s) => ({ ...s, error: e.message })); } }, [db]);
  useRefreshing(load, 5 * 60e3);
  return { ...state, reload: load };
}
