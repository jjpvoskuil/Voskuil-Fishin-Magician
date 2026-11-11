// Punch list (old pages/7_Development.py; Deercast's DevPage as the pattern): numbered items everyone can see and add
// to (✎ on any screen, or Add here); admins edit/close/delete any, others their own. "Copy for Claude" builds the
// note a new session works from. Logic in lib/punch.js; table fm_punch (numbers via fm_next_task_no, never reused).
import { useEffect, useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { Sheet } from "./ui.jsx";
import { canEdit, contextLine, exportText, KINDS, PAGES, PRIORITIES, sortItems, STATUSES, titleOf } from "./lib/punch.js";

const KEY = "fm.punchShow";
const readShow = () => { try { return JSON.parse(localStorage.getItem(KEY)) || ["Open", "In progress"]; } catch { return ["Open", "In progress"]; } };
const day = (s) => (s ? new Date(`${String(s).slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "");

export default function PunchScreen({ active, db, me, onBack, onMenu, demo, toast, onAdd, version }) {
  const [items, setItems] = useState(null), [show, setShowState] = useState(readShow), [q, setQ] = useState(""), [edit, setEdit] = useState(null);
  const [copyOpen, setCopyOpen] = useState(false), [withDone, setWithDone] = useState(false);
  const setShow = (v) => { setShowState(v); try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* ignore */ } };
  const load = () => db.listPunch().then(setItems).catch((e) => { toast(e.message); setItems([]); });
  useEffect(() => { if (active && db) load(); }, [active, db, version]);
  const view = useMemo(() => sortItems((items || []).filter((p) => show.includes(p.status) && (!q.trim() || `#${p.task_no} ${titleOf(p)} ${p.description} ${p.page} ${p.author}`.toLowerCase().includes(q.trim().toLowerCase())))), [items, show, q]);
  const text = useMemo(() => exportText(items || [], { includeDone: withDone }), [items, withDone]);
  const save = async (p) => {
    const now = new Date().toISOString().slice(0, 19), closed = p.status === "Done" || p.status === "Won't do";
    try { await db.savePunch({ ...p, updated_at: now, completed_at: closed ? p.completed_at || now : null }); toast(`Saved #${p.task_no}`); setEdit(null); load(); }
    catch (e) { toast(`Couldn't save — ${e.message}`); }
  };
  const quick = async (p, status) => save({ ...p, status });
  const remove = async (p) => { try { await db.deletePunch(p.task_no); toast(`Deleted #${p.task_no}`); setEdit(null); load(); } catch (e) { toast(e.message); } };
  const copy = async () => { try { await navigator.clipboard.writeText(text); toast("Copied — paste it into a Claude session"); } catch { toast("Couldn't copy — press and hold the text to copy it"); } };

  if (!active) return null;
  const counts = Object.fromEntries(STATUSES.map((s) => [s, (items || []).filter((p) => p.status === s).length]));
  return (
    <div className="screen" id="screen-punch">
      <Head kicker={`More · ${counts.Open || 0} open${counts["In progress"] ? `, ${counts["In progress"]} in progress` : ""}`} title="Punch list" onMenu={onMenu} demo={demo}>
        <button className="iconbtn" aria-label="Back to More" onClick={onBack}><Icon name="back" size={20} /></button>
      </Head>
      <div className="body">
        <div className="two">
          <button className="btn primary big" onClick={() => onAdd("Punch list")}>＋ Add an item</button>
          <button className="btn big" onClick={() => setCopyOpen(true)}>📋 Copy for Claude</button>
        </div>
        <p className="muted small" style={{ margin: "0 4px" }}>Tip: the ✎ at the top of every screen adds a note about that screen, with what was showing.</p>
        <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
          <label className="field">Search<input type="search" value={q} placeholder="number, words, screen or who" onChange={(e) => setQ(e.target.value)} /></label>
          <div className="chips">{STATUSES.map((s) => { const on = show.includes(s); return <button key={s} className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => setShow(on ? show.filter((x) => x !== s) : [...show, s])}>{s} · {counts[s] || 0}</button>; })}</div>
        </div></section>
        {items === null ? <p className="muted">Loading…</p> : <section className="card">
          {!view.length && <p className="empty">Nothing here{q ? " matching that" : ""}.</p>}
          {view.map((p) => (
            <button key={p.task_no} className="pl-row" onClick={() => setEdit({ ...p })}>
              <span className={`pl-no ${p.priority === "High" ? "hi" : ""}`}>#{p.task_no}</span>
              <span className="grow"><b>{titleOf(p)}</b>
                <span className="muted small block">{p.status} · {p.priority || "Medium"}{p.kind ? ` · ${p.kind}` : ""} · {p.page || "General"} · {p.author || "?"} · {day(p.created_at)}</span></span>
              <Icon name="chev" size={18} />
            </button>))}
        </section>}
      </div>

      <Sheet open={!!edit} title={edit ? `#${edit.task_no}` : ""} onClose={() => setEdit(null)}>
        {edit && (() => { const mine = canEdit(edit, me); return <div className="setup">
          {mine ? <>
            <label className="field">Title<input type="text" value={edit.title || ""} placeholder={titleOf(edit)} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></label>
            <label className="field">Details<textarea rows="5" value={edit.description || ""} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></label>
            <div className="two">
              <label className="field">Status<select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })}>{STATUSES.map((k) => <option key={k}>{k}</option>)}</select></label>
              <label className="field">Priority<select value={edit.priority || "Medium"} onChange={(e) => setEdit({ ...edit, priority: e.target.value })}>{PRIORITIES.map((k) => <option key={k}>{k}</option>)}</select></label>
            </div>
            <div className="two">
              <label className="field">Kind<select value={edit.kind || ""} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}><option value="">—</option>{KINDS.map((k) => <option key={k}>{k}</option>)}</select></label>
              <label className="field">Screen<select value={edit.page || ""} onChange={(e) => setEdit({ ...edit, page: e.target.value })}>{[...new Set([edit.page, ...PAGES].filter(Boolean))].map((k) => <option key={k}>{k}</option>)}</select></label>
            </div>
          </> : <>
            <p style={{ margin: 0 }}><b>{titleOf(edit)}</b></p>
            {edit.description && edit.description !== titleOf(edit) && <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{edit.description}</p>}
            <p className="muted small" style={{ margin: 0 }}>{edit.status} · {edit.priority} · {edit.page}. Only {edit.author || "whoever added it"} or an admin can change it.</p>
          </>}
          {edit.original && <details className="gaps"><summary>As first said</summary><p style={{ whiteSpace: "pre-wrap", margin: "6px 0 0" }}>{edit.original}</p></details>}
          {edit.context && <p className="muted small" style={{ margin: 0 }}>Noted on {contextLine(edit.context)}</p>}
          <p className="muted small" style={{ margin: 0 }}>Added by {edit.author || "?"} {day(edit.created_at)}{edit.completed_at ? ` · closed ${day(edit.completed_at)}` : ""}{edit.from_old_app ? " · from the old app" : ""}</p>
          {mine && <>
            <button className="btn primary" onClick={() => save(edit)}>Save</button>
            <div className="two">
              {edit.status !== "Done" ? <button className="btn" onClick={() => quick(edit, "Done")}>✓ Mark done</button> : <button className="btn" onClick={() => quick(edit, "Open")}>Reopen</button>}
              <button className="btn" onClick={() => remove(edit)}>Delete</button>
            </div>
          </>}
        </div>; })()}
      </Sheet>

      <Sheet open={copyOpen} title="Copy for Claude" onClose={() => setCopyOpen(false)}>
        <div className="setup">
          <p className="muted small" style={{ margin: 0 }}>Paste this at the start of a Claude session (or just say "work #101 and #104").</p>
          <div className="seg">{[[false, "Open items"], [true, "+ recently closed"]].map(([v, l]) => <button key={l} className={withDone === v ? "on" : ""} onClick={() => setWithDone(v)}>{l}</button>)}</div>
          <pre className="pl-export">{text}</pre>
          <button className="btn primary" onClick={copy}>Copy</button>
        </div>
      </Sheet>
    </div>
  );
}
