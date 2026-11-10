import { useCallback, useEffect, useMemo, useState } from "react";
import { supabase, configured } from "./supabase.js";
import { LAKE } from "./config.js";
import { Head, Menu, NotYet, TabBar, TABS } from "./Shell.jsx";
import MoreScreen from "./MoreScreen.jsx";
import { demoSeed, DEMO_EMAIL } from "./demo.js";
import { demoDb, supabaseDb } from "./lib/db.js";
import { resolveTheme } from "./lib/theme.js";

const THEME_PREF = "fm.theme";
const TAB_IDS = TABS.map((t) => t[0]);
const BASE = import.meta.env.BASE_URL;

/** Light/dark: automatic by sunrise/sunset at the lake, with a manual override. */
function useTheme() {
  const [pref, setPrefState] = useState(() => { try { return JSON.parse(localStorage.getItem(THEME_PREF)) || { mode: "auto" }; } catch { return { mode: "auto" }; } });
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 60e3); return () => clearInterval(t); }, []);
  const info = resolveTheme(pref, LAKE.lat, LAKE.lon, now);
  useEffect(() => {
    document.documentElement.dataset.theme = info.theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", info.theme === "dark" ? "#0F1512" : "#F3F5F0");
  }, [info.theme]);
  const setPref = (p) => { setPrefState(p); try { localStorage.setItem(THEME_PREF, JSON.stringify(p)); } catch { /* ignore */ } };
  return {
    ...info, mode: info.manual ? (pref.until ? "temp" : pref.mode) : "auto",
    flip: () => setPref({ mode: info.theme === "dark" ? "light" : "dark", until: info.next.getTime() }),
    choose: (mode) => setPref(mode === "auto" ? { mode: "auto" } : { mode, until: null }),
  };
}

function Splash({ children }) {
  return <div className="splash"><img src={`${BASE}icon-192.png`} width="96" height="96" alt="" /><h1>Fishin Magician</h1>{children}</div>;
}

export default function App() {
  const demo = !configured || new URLSearchParams(location.search).has("demo"); // ?demo = made-up data only
  const [session, setSession] = useState(undefined); // undefined = still checking
  const [me, setMe] = useState(undefined);            // fm_users row; null = not on the allow-list
  const [error, setError] = useState("");
  const [tab, setTabState] = useState(() => { const h = location.hash.slice(1); return TAB_IDS.includes(h) ? h : "today"; });
  const [menu, setMenu] = useState(false);
  const [toast, setToast] = useState("");
  const theme = useTheme();
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(""), 2600); return () => clearTimeout(t); }, [toast]);

  const onTab = (id) => {
    if (id === tab) document.getElementById(`screen-${id}`)?.scrollTo({ top: 0, behavior: "smooth" }); // re-tap = back to top
    setTabState(id); history.replaceState(null, "", `#${id}`);
  };

  useEffect(() => {
    if (demo) { setSession({ user: { email: DEMO_EMAIL } }); return; }
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, [demo]);

  const db = useMemo(() => (session ? (demo ? demoDb(demoSeed, session.user.email) : supabaseDb(supabase, session.user.email)) : null), [session?.user?.email, demo]);
  useEffect(() => { if (!db) return; db.whoami().then(setMe, (e) => setError(e.message)); }, [db]);

  /** Run a save, report failure as a toast. Returns true on success. */
  const save = useCallback(async (fn, { ok } = {}) => {
    try { await fn(db); if (ok) setToast(ok); return true; } catch (e) { setToast(`Couldn't save — ${e.message}`); return false; }
  }, [db]);

  const signIn = () => supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin + BASE } });
  const signOut = () => { setMenu(false); if (demo) { db.reset?.(); location.reload(); } else supabase.auth.signOut(); };

  if (error) return <Splash><p className="err">Couldn't load: {error}</p><button className="btn" onClick={() => location.reload()}>Try again</button></Splash>;
  if (session === undefined) return <Splash><p className="muted">Loading…</p></Splash>;
  if (!session) return (
    <Splash>
      <p className="muted">Private app — sign in to continue.</p>
      <button className="btn primary" onClick={signIn}>Sign in with Google</button>
    </Splash>
  );
  if (me === undefined) return <Splash><p className="muted">Loading…</p></Splash>;
  if (me === null) return (
    <Splash>
      <p><b>{session.user.email}</b> isn't set up for Fishin Magician.</p>
      <p className="muted">Ask John or Matt to add you.</p>
      <button className="btn" onClick={signOut}>Sign out</button>
    </Splash>
  );

  const onMenu = () => setMenu(true);
  const common = { db, me, demo, theme, save, toast: setToast, onMenu };
  const today = new Date().toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: LAKE.tz });
  const stub = (id, title, what) => (
    <div className="screen" hidden={tab !== id} id={`screen-${id}`} key={id}>
      <Head kicker={`${today} · Nolin Lake`} title={title} onMenu={onMenu} demo={demo} />
      <div className="body"><NotYet what={what} /></div>
    </div>
  );
  return (
    <>
      {stub("today", "Today", "The Today screen")}
      {stub("forecast", "7-Day Forecast", "The 7-day forecast")}
      {stub("session", "Spot Session", "Spot Session")}
      {stub("map", "Lake Map", "The lake map")}
      <MoreScreen {...common} active={tab === "more"} />
      <TabBar tab={tab} onTab={onTab} />
      <Menu open={menu} onClose={() => setMenu(false)} theme={theme} me={me} onSignOut={signOut} />
      {toast && <div className="toast" role="status">{toast}</div>}
    </>
  );
}
