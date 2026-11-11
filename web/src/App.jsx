import { useCallback, useEffect, useMemo, useState } from "react";
import { supabase, configured } from "./supabase.js";
import { LAKE } from "./config.js";
import { Head, NotYet, TabBar, TABS } from "./Shell.jsx";
import MoreScreen from "./MoreScreen.jsx";
import SessionScreen from "./SessionScreen.jsx";
import HistoryScreen from "./HistoryScreen.jsx";
import { useOutbox } from "./lib/outbox.js";
import TodayScreen from "./TodayScreen.jsx";
import ForecastScreen from "./ForecastScreen.jsx";
import { useLakeSetup } from "./LakeSetup.jsx";
import { useLakeLevel, useList, useTrips, useWaterQuality, useWeather } from "./lib/live.js";
import { demoSeed, DEMO_EMAIL } from "./demo.js";
import { demoDb, supabaseDb } from "./lib/db.js";
import { resolveTheme } from "./lib/theme.js";
import { useKeyboardSafeInputs } from "./ui.jsx";

const THEME_PREF = "fm.theme";
const TAB_IDS = TABS.map((t) => t[0]);
const BASE = import.meta.env.BASE_URL;

/** Light/dark: automatic by sunrise/sunset at the lake, with a manual override. */
function useTheme() {
  const [pref, setPrefState] = useState(() => { try { return JSON.parse(localStorage.getItem(THEME_PREF)) || { mode: "auto" }; } catch { return { mode: "auto" }; } });
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 60e3); return () => clearInterval(t); }, []);
  const info = resolveTheme(pref, LAKE.lat, LAKE.lon, now);
  if (document.documentElement.dataset.theme !== info.theme) document.documentElement.dataset.theme = info.theme; // now, so the sun/moon button renders right
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
  const [tab, setTabState] = useState(() => { const h = location.hash.slice(1).split("/")[0]; return TAB_IDS.includes(h) ? h : "today"; });
  const [watchReq, setWatchReq] = useState(null); // Today's "on the water now" card → Session's watch view
  const [page, setPageState] = useState(() => location.hash.slice(1).split("/")[1] || null); // a page under More (e.g. history)
  const [toast, setToast] = useState("");
  const theme = useTheme();
  useKeyboardSafeInputs();
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(""), 2600); return () => clearTimeout(t); }, [toast]);

  const setPage = (p) => { setPageState(p); history.replaceState(null, "", `#more${p ? `/${p}` : ""}`); };
  const onTab = (id) => {
    if (id === tab) document.getElementById(`screen-${id}`)?.scrollTo({ top: 0, behavior: "smooth" }); // re-tap = back to top
    if (id === tab && id === "more" && page) { setPage(null); return; } // re-tap More = back to the list
    setTabState(id); history.replaceState(null, "", `#${id}${id === "more" && page ? `/${page}` : ""}`);
  };

  useEffect(() => {
    if (demo) { setSession({ user: { email: DEMO_EMAIL } }); return; }
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, [demo]);

  const db = useMemo(() => (session ? (demo ? demoDb(demoSeed, session.user.email) : supabaseDb(supabase, session.user.email)) : null), [session?.user?.email, demo]);
  useEffect(() => { if (!db) return; db.whoami().then(setMe, (e) => setError(e.message)); }, [db]);
  const approvedDb = me ? db : null; // shared data loads only once we know this person is on the list
  const weather = useWeather(), lake = useLakeLevel(), water = useWaterQuality(approvedDb), { trips, reload: reloadTrips } = useTrips(approvedDb);
  const outbox = useOutbox(approvedDb); // one save queue for Session and History
  const lures = useList(approvedDb, "listLures"), spots = useList(approvedDb, "listSpots");
  const [setup, setSetup] = useLakeSetup();

  /** Run a save, report failure as a toast. Returns true on success. */
  const save = useCallback(async (fn, { ok } = {}) => {
    try { await fn(db); if (ok) setToast(ok); return true; } catch (e) { setToast(`Couldn't save — ${e.message}`); return false; }
  }, [db]);

  const signIn = () => supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin + BASE } });
  const signOut = () => { if (demo) { db.reset?.(); location.reload(); } else supabase.auth.signOut(); };

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

  const onMenu = () => theme.flip(); // the header's sun/moon button
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
      <TodayScreen {...common} active={tab === "today"} weather={weather} lake={lake} water={water} trips={trips} reloadTrips={reloadTrips}
        onWatch={(key) => { setWatchReq({ key, at: Date.now() }); onTab("session"); }} />
      <ForecastScreen {...common} active={tab === "forecast"} weather={weather} trips={trips} lures={lures.items} spots={spots.items} setup={setup} setSetup={setSetup} />
      <SessionScreen {...common} active={tab === "session"} weather={weather} trips={trips} reloadTrips={reloadTrips} lures={lures.items} spots={spots.items} outbox={outbox} watchReq={watchReq} />
      {stub("map", "Lake Map", "The lake map")}
      <MoreScreen {...common} active={tab === "more" && !page} onSignOut={signOut} onOpen={setPage} />
      <HistoryScreen {...common} active={tab === "more" && page === "history"} trips={trips} spots={spots.items} outbox={outbox} reloadTrips={reloadTrips} onBack={() => setPage(null)} />
      <TabBar tab={tab} onTab={onTab} />
      {toast && <div className="toast" role="status">{toast}</div>}
    </>
  );
}
