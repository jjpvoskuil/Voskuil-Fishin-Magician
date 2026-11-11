// "Saved as you go": every trip change is kept on the phone first (localStorage), then sent to the database; if the
// signal drops it retries every 15 s and when the phone comes back online. Latest version of each trip wins.
import { useCallback, useEffect, useRef, useState } from "react";

const KEY = "fm.outbox";
const read = () => { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; } };
const write = (q) => { try { localStorage.setItem(KEY, JSON.stringify(q)); } catch { /* storage blocked */ } };

/** Queue an op: {op: "save", trip} or {op: "delete", id}. Replaces any queued op for the same trip. */
export function enqueue(op) {
  const id = op.op === "save" ? op.trip.trip_id : op.id;
  const q = read().filter((x) => (x.op === "save" ? x.trip.trip_id : x.id) !== id);
  q.push({ ...op, queued_at: Date.now() });
  write(q);
}
export const pendingOps = () => read();

/** Send everything queued; stops at the first failure (keeps order). Returns number still pending. */
export async function flush(db) {
  let q = read();
  while (q.length) {
    const op = q[0];
    try { if (op.op === "save") await db.saveTrip(op.trip); else await db.deleteTrip(op.id); }
    catch (e) { return { pending: q.length, error: e.message || String(e) }; }
    q = read().slice(1); // re-read: another op may have been queued meanwhile
    write(q);
  }
  return { pending: 0, error: "" };
}

/** {pending, error, save(trip), remove(id), flushNow()} — flushes on change, every 15 s, and when back online. */
export function useOutbox(db) {
  const [state, setState] = useState({ pending: read().length, error: "" });
  const busy = useRef(false);
  const flushNow = useCallback(async () => {
    if (!db || busy.current) return;
    busy.current = true;
    try { setState(await flush(db)); } finally { busy.current = false; }
  }, [db]);
  useEffect(() => {
    flushNow();
    const t = setInterval(() => { if (read().length) flushNow(); }, 15e3);
    window.addEventListener("online", flushNow);
    const onShow = () => { if (document.visibilityState === "visible") flushNow(); };
    document.addEventListener("visibilitychange", onShow);
    return () => { clearInterval(t); window.removeEventListener("online", flushNow); document.removeEventListener("visibilitychange", onShow); };
  }, [flushNow]);
  return {
    ...state,
    save: (trip) => { enqueue({ op: "save", trip }); setState((s) => ({ ...s, pending: read().length })); flushNow(); },
    remove: (id) => { enqueue({ op: "delete", id }); setState((s) => ({ ...s, pending: read().length })); flushNow(); },
    flushNow,
  };
}
