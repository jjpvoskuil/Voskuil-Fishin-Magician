// ✎ Quick punch-list note from any screen (John 11-11): the screen you were on and what was showing are recorded
// automatically; dictate with the keyboard mic, then "Tidy with Claude" (fm-board-ask, mode "punch") writes it up
// as a clear item you check before saving. The original words are kept with it.
import { useState } from "react";
import { Sheet } from "./ui.jsx";
import { BUILD } from "./Shell.jsx";
import { contextLine, KINDS, PAGES, pageFor, PRIORITIES } from "./lib/punch.js";

/** What was on screen when ✎ was tapped. */
export function captureContext(screen, kicker) {
  return { screen, kicker: kicker || "", where: location.hash || "#today", theme: document.documentElement.dataset.theme || "", build: BUILD,
    device: `${window.innerWidth}×${window.innerHeight}`, at: new Date().toISOString().slice(0, 19) };
}

export default function PunchSheet({ open, ctx, db, me, toast, onClose, onSaved }) {
  const blank = () => ({ text: "", title: "", details: "", kind: "Change", priority: "Medium", page: pageFor(ctx?.screen), tidied: false });
  const [d, setD] = useState(blank), [busy, setBusy] = useState(""), [note, setNote] = useState("");
  const [lastCtx, setLastCtx] = useState(null);
  if (ctx !== lastCtx) { setLastCtx(ctx); setD(blank()); setNote(""); }
  const set = (p) => setD((x) => ({ ...x, ...p }));
  const tidy = async () => {
    if (d.text.trim().length < 3) { toast("Say or type the note first"); return; }
    setBusy("tidy"); setNote("");
    try {
      const a = await db.askBoard(d.text.trim(), { page: d.page, pages: PAGES, context: contextLine(ctx) }, "", "punch");
      set({ title: String(a.title || "").slice(0, 120), details: String(a.details || ""), kind: KINDS.includes(a.kind) ? a.kind : d.kind,
        priority: PRIORITIES.includes(a.priority) ? a.priority : d.priority, page: PAGES.includes(a.page) ? a.page : d.page, tidied: true });
      setNote(a.note || "");
    } catch (e) { toast(e.message); } finally { setBusy(""); }
  };
  const save = async () => {
    const raw = d.text.trim();
    if (!raw && !d.title.trim()) { toast("Nothing to save yet"); return; }
    setBusy("save");
    try {
      const task_no = await db.nextTaskNo(), now = new Date().toISOString().slice(0, 19);
      const item = { task_no, owner: me.email, author: me.name || me.email, status: "Open", priority: d.priority, kind: d.kind, page: d.page,
        title: (d.tidied ? d.title : "").trim() || raw.split(/\n/)[0].slice(0, 120), description: d.tidied ? d.details.trim() : raw,
        original: d.tidied ? raw : undefined, context: ctx || undefined, created_at: now, updated_at: now };
      await db.savePunch(item);
      toast(`Added #${task_no} to the punch list`); onSaved?.(item); onClose();
    } catch (e) { toast(`Couldn't save — ${e.message}`); } finally { setBusy(""); }
  };
  return (
    <Sheet open={open} title="Add to the punch list" onClose={onClose}>
      <div className="setup">
        {ctx && <p className="muted small" style={{ margin: 0 }}>From {ctx.screen}{ctx.kicker ? ` · ${ctx.kicker}` : ""} — the screen and build are saved with it.</p>}
        <label className="field">What should change?
          <textarea rows="4" value={d.text} placeholder="Tap the 🎤 on the keyboard and just talk — e.g. 'the plus fish button is too small with gloves on'"
            onChange={(e) => set({ text: e.target.value, tidied: false })} /></label>
        <button className="btn" disabled={!!busy} onClick={tidy}>{busy === "tidy" ? "Tidying…" : "✨ Tidy with Claude"}</button>
        {d.tidied && <>
          <label className="field">Title<input type="text" value={d.title} onChange={(e) => set({ title: e.target.value })} /></label>
          <label className="field">Details<textarea rows="4" value={d.details} onChange={(e) => set({ details: e.target.value })} /></label>
        </>}
        {note && <p className="note-bar">{note}</p>}
        <div className="two">
          <label className="field">Kind<select value={d.kind} onChange={(e) => set({ kind: e.target.value })}>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
          <label className="field">Priority<select value={d.priority} onChange={(e) => set({ priority: e.target.value })}>{PRIORITIES.map((k) => <option key={k}>{k}</option>)}</select></label>
        </div>
        <label className="field">Screen<select value={d.page} onChange={(e) => set({ page: e.target.value })}>{PAGES.map((k) => <option key={k}>{k}</option>)}</select></label>
        <button className="btn primary" disabled={!!busy} onClick={save}>{busy === "save" ? "Saving…" : "Add to punch list"}</button>
      </div>
    </Sheet>
  );
}
