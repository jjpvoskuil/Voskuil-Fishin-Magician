// Small per-phone settings, kept in localStorage and shared live between screens:
//  - gear: is the main boat (with electronics) in use? Off in the fall when it's stored (John 11-10): water temp then
//    always comes from the estimate and there's no fish-depth reading.
//  - picksMode: lure picks from everyone's catches (default, best for the spot) or weighted to your own.
import { useEffect, useState } from "react";

const read = (k, d) => { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; } catch { return d; } };
function usePref(key, def) {
  const [v, setV] = useState(() => read(key, def));
  useEffect(() => {
    const on = (e) => { if (!e.key || e.key === key) setV(read(key, def)); };
    window.addEventListener("storage", on); window.addEventListener("fm-pref", on);
    return () => { window.removeEventListener("storage", on); window.removeEventListener("fm-pref", on); };
  }, [key]);
  const set = (x) => { try { localStorage.setItem(key, JSON.stringify(x)); } catch { /* ignore */ } setV(x); window.dispatchEvent(new CustomEvent("fm-pref")); };
  return [v, set];
}
export const useElectronics = () => usePref("fm.electronics", true);
export const usePicksMode = () => usePref("fm.picksMode", "everyone");
