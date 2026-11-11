// A custom leaderboard (John 11-11): ask in words (Claude picks the settings via fm-board-ask) or pick them by hand;
// the numbers are always computed here from the trip log (lib/boards.js). Save keeps it in fm_saved (yours only)
// and adds it to the Leaderboard's tabs.
import { useEffect, useMemo, useState } from "react";
import { Multi, Pick } from "./ui.jsx";
import { newId } from "./lib/db.js";
import { cleanSpec, describeSpec, GROUPS, MEASURES, MONTHS, runBoard, SEGMENTS } from "./lib/boards.js";

const lakeToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
const tempText = (v) => (v == null ? "" : String(v));
const EXAMPLES = ["Most lbs of bass on a jerkbait", "Biggest fish at each spot this fall", "My fish per hour by time of day", "Best lure in water under 55°"];

/** Number box that only applies its value when you leave it (so typing 5 on the way to 55 doesn't jump). */
function TempBox({ label, value, onChange }) {
  const [t, setT] = useState(tempText(value));
  useEffect(() => setT(tempText(value)), [value]);
  return <label className="field">{label}<input type="text" inputMode="decimal" value={t} placeholder="any" onFocus={(e) => e.target.select()}
    onChange={(e) => setT(e.target.value)} onBlur={() => onChange(t.trim() === "" ? null : t)} /></label>;
}

export function BoardRows({ list }) {
  if (!list.length) return <p className="empty">Nothing matches these settings yet.</p>;
  return list.map((r, n) => (
    <div key={n} className="lb-row">
      <span className={`lb-rank ${n === 0 ? "r1" : ""}`}>{n + 1}</span>
      <span className="grow"><b>{r.primary}</b><span className="muted small block">{r.secondary}</span></span>
      <span className="lb-num"><b className="num">{r.num}</b>{r.tag && <span className="pill">{r.tag}</span>}</span>
    </div>));
}

export default function CustomBoard({ db, me, board, rowsPeriod, rowsWho, names, choices, setPeriodWho, onSaved, onDeleted, toast }) {
  const [spec, setSpec] = useState(() => cleanSpec(board?.spec || { measure: "lbs", by: "angler" }, choices));
  const [q, setQ] = useState(""), [asking, setAsking] = useState(false), [note, setNote] = useState(board ? "" : "");
  const [open, setOpen] = useState(false), [title, setTitle] = useState(board?.title || "");
  useEffect(() => { setSpec(cleanSpec(board?.spec || { measure: "lbs", by: "angler" }, choices)); setTitle(board?.title || ""); setNote(""); }, [board?.id]);
  const set = (p) => setSpec((s) => cleanSpec({ ...s, ...p }, choices));
  const rows = spec.from || spec.to ? rowsWho : rowsPeriod;
  const result = useMemo(() => runBoard(rows, spec, names), [rows, spec, names]);
  const typeNames = Object.fromEntries(choices.lure_types), typeKeys = Object.fromEntries(choices.lure_types.map(([k, n]) => [n, k]));
  const nFilters = ["species", "lure_types", "spots", "anglers", "segments", "months"].reduce((a, k) => a + (spec[k].length ? 1 : 0), 0)
    + (spec.temp_min != null || spec.temp_max != null ? 1 : 0) + (spec.lure_text ? 1 : 0) + (spec.color_text ? 1 : 0) + (spec.from || spec.to ? 1 : 0);

  const ask = async (text = q) => {
    if (text.trim().length < 3) { toast("Type a question first"); return; }
    setAsking(true); setNote("");
    try {
      const a = await db.askBoard(text.trim(), choices, lakeToday());
      const s = cleanSpec(a, choices);
      setSpec(s); setTitle(String(a.title || text).slice(0, 80)); setNote(a.note || "");
      if (s.period || s.who) setPeriodWho({ ...(s.period && { period: s.period }), ...(s.who && { who: s.who }) });
    } catch (e) { toast(e.message); } finally { setAsking(false); }
  };
  const save = async () => {
    const t = (title || describeSpec(spec)).slice(0, 80), item = { id: board?.id || newId(), owner: me.email, title: t, spec };
    try { await db.saveSaved("board", item); toast(board ? "Board updated" : `Saved "${t}" — it's in the tabs now`); onSaved(item); } catch (e) { toast(e.message); }
  };
  const remove = async () => { try { await db.deleteSaved(board.id); toast("Board deleted"); onDeleted(); } catch (e) { toast(e.message); } };

  return <>
    <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
      <label className="field">Ask for a board
        <input type="text" value={q} enterKeyHint="go" placeholder="e.g. most lbs of bass on a jerkbait" onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); ask(); } }} />
      </label>
      <button className="btn primary" disabled={asking} onClick={() => ask()}>{asking ? "Reading your question…" : "Ask"}</button>
      {!board && !q && <div className="chips">{EXAMPLES.map((x) => <button key={x} className="chip" onClick={() => { setQ(x); ask(x); }}>{x}</button>)}</div>}
      {note && <p className="note-bar">{note}</p>}
    </div></section>

    <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
      <div className="two">
        <label className="field">Measure<select value={spec.measure} onChange={(e) => set({ measure: e.target.value })}>{MEASURES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Ranked by<select value={spec.by} onChange={(e) => set({ by: e.target.value })}>
          {GROUPS.filter(([k]) => k !== "fish" || ["biggest", "longest"].includes(spec.measure)).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      </div>
      <button className="link" onClick={() => setOpen(!open)} style={{ alignSelf: "flex-start" }}>{open ? "Hide filters" : `Filters${nFilters ? ` (${nFilters} on)` : ""}`} ›</button>
      {open && <>
        <Pick label="Species" options={choices.species} value={spec.species} onChange={(v) => set({ species: v })} />
        <Pick label="Lure type" options={choices.lure_types.map(([, n]) => n)} value={spec.lure_types.map((k) => typeNames[k] || k)} onChange={(v) => set({ lure_types: v.map((n) => typeKeys[n] || n) })} />
        <label className="field">Lure name contains<input type="text" value={spec.lure_text} placeholder="e.g. Shadow Rap" onChange={(e) => set({ lure_text: e.target.value })} /></label>
        <label className="field">Color contains<input type="text" value={spec.color_text} placeholder="e.g. shad" onChange={(e) => set({ color_text: e.target.value })} /></label>
        <Pick label="Spot" options={choices.spots} value={spec.spots} onChange={(v) => set({ spots: v })} />
        <Pick label="Angler" options={choices.anglers} value={spec.anglers} onChange={(v) => set({ anglers: v })} />
        <Multi label="Time of day" options={SEGMENTS} value={spec.segments} onChange={(v) => set({ segments: v })} />
        <Multi label="Months" options={MONTHS} value={spec.months.map((m) => MONTHS[m - 1])} onChange={(v) => set({ months: v.map((x) => MONTHS.indexOf(x) + 1) })} />
        <div className="two">
          <TempBox label="Water from (°F)" value={spec.temp_min} onChange={(v) => set({ temp_min: v })} />
          <TempBox label="Water to (°F)" value={spec.temp_max} onChange={(v) => set({ temp_max: v })} />
        </div>
        {(spec.from || spec.to) && <p className="note-bar">Dates {spec.from || "start"} to {spec.to || "now"} (this replaces the period above) <button className="link" onClick={() => set({ from: "", to: "" })}>Clear</button></p>}
        {nFilters > 0 && <button className="link" style={{ alignSelf: "flex-start" }} onClick={() => set({ species: [], lure_types: [], spots: [], anglers: [], segments: [], months: [], temp_min: null, temp_max: null, lure_text: "", color_text: "", from: "", to: "" })}>Clear all filters</button>}
      </>}
    </div></section>

    <section className="card">
      <div className="card-h"><span className="t">{title || "Custom board"}</span></div>
      <p className="muted small" style={{ margin: 0, padding: "8px 14px 0" }}>{describeSpec(spec)}</p>
      <BoardRows list={result.rows} />
    </section>

    <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
      <label className="field">Board name<input type="text" value={title} placeholder={describeSpec(spec).slice(0, 60)} onChange={(e) => setTitle(e.target.value)} /></label>
      <div className={board ? "two" : "setup"}>
        <button className="btn primary" onClick={save}>{board ? "Save changes" : "☆ Save this board"}</button>
        {board && <button className="btn" onClick={remove}>Delete</button>}
      </div>
    </div></section>
  </>;
}
