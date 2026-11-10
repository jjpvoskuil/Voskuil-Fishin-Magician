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
  };
}

// ---------------------------------------------------------------- demo (browser-only)
const DEMO_KEY = "fm.demo.v1";
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
    reset: () => { localStorage.removeItem(DEMO_KEY); },
  };
}
