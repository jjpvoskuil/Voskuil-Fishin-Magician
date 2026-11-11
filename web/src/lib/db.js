// One data API for every screen. Two backends with the same methods:
//   supabaseDb — the real data, in the shared Deercast Supabase project's fm_* tables; who may read/write what is
//                enforced by row-level security (supabase/schema.sql), never by this file
//   demoDb     — made-up data kept in this browser only (?demo in the URL, and testing)
// More tables (trips, lures, spots, punch list…) are added here as each screen is rebuilt.

export const newId = () => Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, "0")).join("");
export const nowIso = () => new Date().toISOString();
export const lower = (e) => (e || "").trim().toLowerCase();

// ---------------------------------------------------------------- Supabase
const URL_SECONDS = 6 * 3600;
const rnd = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, "0")).join("");

export function supabaseDb(sb, email) {
  const me = lower(email);
  const bucket = () => sb.storage.from("fm-lures");
  const urlCache = new Map(); // path -> {url, until}
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
    // shared tackle box + lake spots (every approved angler can edit)
    listLures: async () => ok(await sb.from("fm_lures").select("id,data").order("id")).map((r) => ({ ...r.data, item_id: r.id })),
    saveLure: async (l) => ok(await sb.from("fm_lures").upsert({ id: l.item_id, data: l })),
    deleteLure: async (id) => ok(await sb.from("fm_lures").delete().eq("id", id)),
    listSpots: async () => ok(await sb.from("fm_spots").select("id,data").order("id")).map((r) => ({ ...r.data, spot_id: r.id })),
    saveSpot: async (sp) => ok(await sb.from("fm_spots").upsert({ id: sp.spot_id, data: sp })),
    deleteSpot: async (id) => ok(await sb.from("fm_spots").delete().eq("id", id)),
    // tackle-box photos (private bucket fm-lures)
    /** Upload {full, thumb} JPEGs for a lure → {image_path, thumb_path}. */
    async uploadLurePhoto(itemId, { full, thumb }) {
      const stem = `lures/${itemId}-${rnd()}`;
      ok(await bucket().upload(`${stem}.jpg`, full, { contentType: "image/jpeg" }));
      ok(await bucket().upload(`${stem}_thumb.jpg`, thumb, { contentType: "image/jpeg" }));
      return { image_path: `${stem}.jpg`, thumb_path: `${stem}_thumb.jpg` };
    },
    removePhotos: async (paths) => { const p = paths.filter(Boolean); if (p.length) ok(await bucket().remove(p)); },
    /** Temporary private links for photos: {path: url}, cached until shortly before they expire. */
    async photoUrls(paths) {
      const want = [...new Set(paths.filter(Boolean))], now = Date.now();
      const missing = want.filter((p) => !(urlCache.get(p)?.until > now));
      for (let i = 0; i < missing.length; i += 100) {
        const res = ok(await bucket().createSignedUrls(missing.slice(i, i + 100), URL_SECONDS));
        for (const r of res) if (r.signedUrl) urlCache.set(r.path, { url: r.signedUrl, until: now + (URL_SECONDS - 600) * 1000 });
      }
      return Object.fromEntries(want.filter((p) => urlCache.has(p)).map((p) => [p, urlCache.get(p).url]));
    },
    /** Claude reads a lure photo (fm-lure-scan Edge Function) → {visible, brand, product_name, color, size, lure_type, search_query, notes} */
    async scanLure(image_b64, media_type = "image/jpeg") {
      const { data, error } = await sb.functions.invoke("fm-lure-scan", { body: { image_b64, media_type } });
      if (error) {
        let msg = error.message;
        try { const j = await error.context.json(); if (j?.error) msg = j.error; } catch { /* keep the generic message */ }
        if (/Failed to send|not found|404/i.test(msg)) msg = "The lure scanner isn't set up yet (Edge Function fm-lure-scan).";
        throw new Error(msg);
      }
      if (data?.error) throw new Error(data.error);
      return data;
    },
    /** Army Corps report page HTML, through the fm-usace-wq Edge Function */
    usaceHtml: async () => { const { data, error } = await sb.functions.invoke("fm-usace-wq"); if (error) throw new Error(error.message); if (data?.error) throw new Error(data.error); return data.html; },
  };
}

/** fm_trips row → the trip object every screen and the engine use (old trip_log.csv shape) */
export const tripRow = (r) => ({ ...r.data, trip_id: r.id, owner: r.owner, trip_date: r.trip_date, session_id: r.session_id ?? r.data?.session_id ?? "" });
export const tripRecord = (t, me) => { const { owner, ...data } = t; return { id: t.trip_id, owner: lower(owner || me), trip_date: t.trip_date, session_id: t.session_id || null, data }; };

// ---------------------------------------------------------------- demo (browser-only)
const DEMO_KEY = "fm.demo.v3";
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
    listLures: async () => clone(st.lures || []),
    saveLure: async (l) => up((st.lures ||= []), clone(l), "item_id"),
    deleteLure: async (id) => del(st.lures || [], (l) => l.item_id === id),
    // photos: the thumbnail is kept in this browser as a data URL (full size isn't needed for the demo)
    async uploadLurePhoto(itemId, { thumb }) {
      const url = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(thumb); });
      const path = `lures/${itemId}-${rnd()}_thumb.jpg`; (st.photos ||= {})[path] = url; save();
      return { image_path: path, thumb_path: path };
    },
    removePhotos: async (paths) => { for (const p of paths) if (st.photos) delete st.photos[p]; save(); },
    photoUrls: async (paths) => Object.fromEntries(paths.filter((p) => st.photos?.[p]).map((p) => [p, st.photos[p]])),
    scanLure: async () => { await new Promise((r) => setTimeout(r, 700));
      return { visible: true, brand: "Strike King", product_name: "KVD Squarebill 1.5", color: "Sexy Shad", size: "1/2 oz", lure_type: "squarebill_crankbait",
        search_query: "Strike King KVD Squarebill 1.5", notes: "Demo answer — the real scanner reads your photo." }; },
    listSpots: async () => clone(st.spots || []),
    saveSpot: async (sp) => up((st.spots ||= []), clone(sp), "spot_id"),
    deleteSpot: async (id) => del(st.spots || [], (sp) => sp.spot_id === id),
    reset: () => { localStorage.removeItem(DEMO_KEY); },
  };
}
