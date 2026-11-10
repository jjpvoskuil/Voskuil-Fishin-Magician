// One data API for every screen. Two backends with the same methods:
//   supabaseDb — the real data, in the shared Deercast Supabase project's fm_* tables; who may read/write what is
//                enforced by row-level security (supabase/schema.sql), never by this file
//   demoDb     — made-up data kept in this browser only (?demo in the URL, and testing)
// More tables (trips, lures, spots, punch list…) are added here as each screen is rebuilt.

export const newId = () => Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, "0")).join("");
export const nowIso = () => new Date().toISOString();
export const lower = (e) => (e || "").trim().toLowerCase();

// ---------------------------------------------------------------- Supabase
export function supabaseDb(sb, email) {
  const me = lower(email);
  const ok = (r) => { if (r.error) throw new Error(r.error.message); return r.data; };
  return {
    kind: "supabase", email: me,
    /** this user's fm_users row, or null if not on the allow-list */
    async whoami() { const u = ok(await sb.from("fm_users").select("*").eq("email", me)); return u[0] || null; },
    listUsers: async () => ok(await sb.from("fm_users").select("*").order("name")),
    saveUser: async (u) => ok(await sb.from("fm_users").upsert({ email: lower(u.email), name: (u.name || "").trim(), role: u.role || "member" })),
    deleteUser: async (e) => ok(await sb.from("fm_users").delete().eq("email", lower(e))),
    // trips: everyone approved reads all; you write your own (admins: anyone's)
    listTrips: async () => {
      const out = []; const page = 1000;
      for (let from = 0; ; from += page) {
        const r = ok(await sb.from("fm_trips").select("id,owner,trip_date,session_id,data").order("trip_date").order("id").range(from, from + page - 1));
        out.push(...r.map(tripRow)); if (r.length < page) break;
      }
      return out;
    },
    saveTrip: async (t) => ok(await sb.from("fm_trips").upsert(tripRecord(t, me))),
    deleteTrip: async (id) => ok(await sb.from("fm_trips").delete().eq("id", id)),
    // lake water-quality readings (add-only) and frozen forecast scores (add-only)
    listWaterQuality: async () => ok(await sb.from("fm_water_quality").select("observed_at,data").order("observed_at")).map((r) => ({ observed_at: r.observed_at, ...r.data })),
    addWaterQuality: async (w) => { const { observed_at, ...data } = w; return ok(await sb.from("fm_water_quality").upsert({ observed_at, data }, { ignoreDuplicates: true })); },
    listFreezes: async (date) => ok(await sb.from("fm_score_freeze").select("the_date,segment_name,data").eq("the_date", date)).map((r) => ({ the_date: r.the_date, segment_name: r.segment_name, ...r.data })),
    addFreezes: async (rows) => (rows.length ? ok(await sb.from("fm_score_freeze").upsert(rows.map(({ the_date, segment_name, ...data }) => ({ the_date, segment_name, data })), { ignoreDuplicates: true })) : null),
    /** Army Corps report page HTML, through the fm-usace-wq Edge Function */
    usaceHtml: async () => { const { data, error } = await sb.functions.invoke("fm-usace-wq"); if (error) throw new Error(error.message); if (data?.error) throw new Error(data.error); return data.html; },
  };
}

/** fm_trips row → the trip object every screen and the engine use (old trip_log.csv shape) */
export const tripRow = (r) => ({ ...r.data, trip_id: r.id, owner: r.owner, trip_date: r.trip_date, session_id: r.session_id ?? r.data?.session_id ?? "" });
export const tripRecord = (t, me) => { const { owner, ...data } = t; return { id: t.trip_id, owner: lower(owner || me), trip_date: t.trip_date, session_id: t.session_id || null, data }; };

// ---------------------------------------------------------------- demo (browser-only)
const DEMO_KEY = "fm.demo.v2";
export function demoDb(seed, email = "demo@example.com") {
  let st;
  try { st = JSON.parse(localStorage.getItem(DEMO_KEY)); } catch { st = null; }
  if (!st) st = seed();
  const save = () => { try { localStorage.setItem(DEMO_KEY, JSON.stringify(st)); } catch { /* ignore */ } };
  const me = lower(email);
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const up = (arr, rec, key = "id") => { const i = arr.findIndex((x) => x[key] === rec[key]); if (i >= 0) arr[i] = rec; else arr.push(rec); save(); };
  const del = (arr, pred) => { for (let i = arr.length - 1; i >= 0; i--) if (pred(arr[i])) arr.splice(i, 1); save(); };
  const isAdmin = () => st.users.find((u) => u.email === me)?.role === "admin";
  const needAdmin = () => { if (!isAdmin()) throw new Error("only admins can change the list"); };
  return {
    kind: "demo", email: me,
    whoami: async () => clone(st.users.find((u) => u.email === me) || null),
    listUsers: async () => clone([...st.users].sort((a, b) => a.name.localeCompare(b.name))),
    saveUser: async (u) => { needAdmin(); up(st.users, { email: lower(u.email), name: (u.name || "").trim(), role: u.role || "member" }, "email"); },
    deleteUser: async (e) => { needAdmin(); del(st.users, (u) => u.email === lower(e)); },
    listTrips: async () => clone(st.trips || []),
    saveTrip: async (t) => up((st.trips ||= []), { ...clone(t), owner: lower(t.owner || me) }, "trip_id"),
    deleteTrip: async (id) => del(st.trips || [], (t) => t.trip_id === id),
    listWaterQuality: async () => clone(st.water_quality || []),
    addWaterQuality: async (w) => { st.water_quality ||= []; if (!st.water_quality.some((x) => x.observed_at === w.observed_at)) { st.water_quality.push(clone(w)); save(); } },
    listFreezes: async (date) => clone((st.freezes || []).filter((f) => f.the_date === date)),
    addFreezes: async (rows) => { st.freezes ||= []; for (const r of rows) if (!st.freezes.some((f) => f.the_date === r.the_date && f.segment_name === r.segment_name)) st.freezes.push(clone(r)); save(); },
    usaceHtml: async () => st.usace_html || "",
    reset: () => { localStorage.removeItem(DEMO_KEY); },
  };
}
