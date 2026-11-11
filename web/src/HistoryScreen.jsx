// Trip History (old pages/4_Trip_History.py): filter sessions, open one to see everything, edit or delete your own
// (admins: anyone's). Filters apply as you tap (no "See Trips" button) and are remembered on this phone.
import { useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { NumberBox } from "./LakeSetup.jsx";
import { ConditionsForm, FishSheet, conditionsSummary } from "./SessionParts.jsx";
import { Sheet } from "./ui.jsx";
import { parseConditions } from "./lib/calibration.js";
import { buildSessions, fishTotals, lureTypeLabel, matches, summarize, applyLegEdit, LEG_CONDITION_KEYS } from "./lib/history.js";
import { formatWeightLbOz } from "./lib/leaderboard.js";
import { LURE_CATEGORY_OPTIONS, STRUCTURE_TYPES } from "./lib/lures.js";
import { addDays } from "./lib/py.js";
import { SEGMENTS } from "./lib/scoring.js";
import * as S from "./lib/session.js";
import { lakeToday } from "./lib/weather.js";

const FKEY = "fm.historyFilters";
const NO_FILTERS = { range: "30", from: "", to: "", who: "all", anglers: [], segments: [], locations: [], lureTypes: [], lures: [] };
const readF = () => { try { return { ...NO_FILTERS, ...JSON.parse(localStorage.getItem(FKEY)) }; } catch { return NO_FILTERS; } };
const RANGES = [["today", "Today"], ["7", "7 days"], ["30", "30 days"], ["year", "This year"], ["all", "All"], ["custom", "Pick dates"]];
const t12 = (t) => { if (!t) return "?"; const [h, m] = t.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
const dayLabel = (d) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: d.slice(0, 4) === lakeToday().slice(0, 4) ? undefined : "numeric" }) : "Unknown date");
const fishText = (f) => [f.count > 1 ? `${f.count} × ${f.species}` : f.species || "Unknown species", f.caught_at && t12(f.caught_at), f.weight_lb && (f.count > 1 ? `~${formatWeightLbOz(f.weight_lb)} each` : formatWeightLbOz(f.weight_lb)),
  f.length_in && `${f.length_in} in`, f.depth_ft && `${f.depth_ft} ft deep`, (f.hit_types || []).join(", ") || null, [f.retrieve_speed, f.retrieve_style].filter(Boolean).join(" / ") || null].filter(Boolean).join(" · ");
const shortLure = (r) => (r.lure_used || "Unspecified").split(" - ").slice(0, 2).join(" ");

function dateBounds(f) {
  const today = lakeToday();
  if (f.range === "today") return [today, today];
  if (f.range === "7") return [addDays(today, -6), today];
  if (f.range === "30") return [addDays(today, -29), today];
  if (f.range === "year") return [`${today.slice(0, 4)}-01-01`, today];
  if (f.range === "custom") return [f.from || null, f.to || null];
  return [null, null];
}

export default function HistoryScreen({ active, db, me, trips, spots, outbox, reloadTrips, onBack, onMenu, demo, toast }) {
  const [f, setFState] = useState(readF);
  const setF = (patch) => setFState((x) => { const n = { ...x, ...patch }; try { localStorage.setItem(FKEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  const [more, setMore] = useState(false);
  const [openKey, setOpenKey] = useState(null);
  const [limit, setLimit] = useState(40);
  const spotName = useMemo(() => { const m = new Map((spots || []).map((s) => [s.spot_id, s.name])); return (id) => m.get(id) || null; }, [spots]);
  const sessions = useMemo(() => buildSessions(trips || [], spotName), [trips, spotName]);
  const [from, to] = dateBounds(f);
  const shown = useMemo(() => sessions.filter((s) => matches(s, { from, to, mine: f.who === "me" ? me.email : null, anglers: f.who === "all" ? f.anglers : [],
    segments: f.segments, locations: f.locations, lureTypes: f.lureTypes, lures: f.lures })), [sessions, f, from, to, me]);
  const sum = summarize(shown);
  const opts = useMemo(() => ({
    anglers: [...new Set(sessions.map((s) => s.angler).filter(Boolean))].sort(),
    locations: [...new Set(sessions.flatMap((s) => s.locations))].sort(),
    lureTypes: [...new Set(sessions.flatMap((s) => [...s.lure_types]))].sort(),
    lures: [...new Set(sessions.flatMap((s) => [...s.lures]))].sort(),
  }), [sessions]);
  const extra = (f.who === "all" ? f.anglers.length : 0) + f.segments.length + f.locations.length + f.lureTypes.length + f.lures.length;
  const open = openKey ? sessions.find((s) => s.key === openKey) : null;
  const canEdit = (s) => me.role === "admin" || s.rows.every((r) => (r.owner || "").toLowerCase() === me.email.toLowerCase());

  if (!active) return null;
  return (
    <div className="screen" id="screen-history">
      <Head kicker="More" title="Trip History" onMenu={onMenu} demo={demo}>
        <button className="iconbtn" aria-label="Back to More" onClick={onBack}><Icon name="back" size={20} /></button>
      </Head>
      <div className="body">
        <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
          <div className="seg">{[["all", "Everyone"], ["me", "Just me"]].map(([k, l]) => <button key={k} className={f.who === k ? "on" : ""} onClick={() => setF({ who: k })}>{l}</button>)}</div>
          <div className="chips">{RANGES.map(([k, l]) => <button key={k} className={`chip ${f.range === k ? "on" : ""}`} aria-pressed={f.range === k} onClick={() => setF({ range: k })}>{l}</button>)}</div>
          {f.range === "custom" && <div className="two">
            <label className="field">From<input type="date" value={f.from} max={lakeToday()} onChange={(e) => setF({ from: e.target.value })} /></label>
            <label className="field">To<input type="date" value={f.to} max={lakeToday()} onChange={(e) => setF({ to: e.target.value })} /></label></div>}
          <button className="link" onClick={() => setMore(!more)}>{more ? "Fewer filters" : `More filters${extra ? ` (${extra} on)` : ""}`} ›</button>
          {more && <>
            {f.who === "all" && opts.anglers.length > 1 && <Multi label="Angler" options={opts.anglers} value={f.anglers} onChange={(v) => setF({ anglers: v })} />}
            <Multi label="Time of day" options={SEGMENTS} value={f.segments} onChange={(v) => setF({ segments: v })} />
            <Pick label="Location" options={opts.locations} value={f.locations} onChange={(v) => setF({ locations: v })} />
            <Pick label="Lure type" options={opts.lureTypes} value={f.lureTypes} onChange={(v) => setF({ lureTypes: v })} />
            <Pick label="Specific lure" options={opts.lures} value={f.lures} onChange={(v) => setF({ lures: v })} />
            {extra > 0 && <button className="btn" onClick={() => setF({ anglers: [], segments: [], locations: [], lureTypes: [], lures: [] })}>Clear these filters</button>}
          </>}
        </div></section>

        {trips === null ? <p className="muted">Loading trips…</p> : <>
          <p className="muted small" style={{ margin: "0 4px" }}><b>{sum.sessions}</b> of {sessions.length} sessions · <b>{sum.fish}</b> fish
            {sum.hours > 0 && <> · {sum.hours.toFixed(1)} h on lures · <b>{(sum.fish / sum.hours).toFixed(2)}</b> fish/hr</>}</p>
          {!shown.length && <p className="note-bar">No sessions match. Try a wider date range or clear the filters.</p>}
          {shown.slice(0, limit).map((s) => <SessionCard key={s.key} s={s} onOpen={() => setOpenKey(s.key)} />)}
          {shown.length > limit && <button className="btn wide" onClick={() => setLimit(limit + 40)}>Show more ({shown.length - limit} left)</button>}
        </>}
      </div>
      {open && <SessionSheet s={open} canEdit={canEdit(open)} spots={spots} onClose={() => setOpenKey(null)}
        onSave={(rows) => { for (const r of rows) outbox.save(r); toast("Saved"); setTimeout(reloadTrips, 1200); }}
        onDelete={() => { for (const r of open.rows) outbox.remove(r.trip_id); setOpenKey(null); toast("Session deleted"); setTimeout(reloadTrips, 1200); }} />}
    </div>
  );
}

function Multi({ label, options, value, onChange }) {
  return <div className="field">{label}<div className="chips">{options.map((o) => { const on = value.includes(o); return (
    <button type="button" key={o} className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}>{o}</button>); })}</div></div>;
}
/** Long option lists: a select to add, chips of what's picked (tap to remove). */
function Pick({ label, options, value, onChange }) {
  return <div className="field"><label className="field" style={{ gap: 4 }}>{label}
    <select value="" onChange={(e) => e.target.value && onChange([...value, e.target.value])}>
      <option value="">{value.length ? "Add another…" : "Any"}</option>{options.filter((o) => !value.includes(o)).map((o) => <option key={o} value={o}>{o}</option>)}</select></label>
    {value.length > 0 && <div className="chips">{value.map((v) => <button type="button" key={v} className="chip on" onClick={() => onChange(value.filter((x) => x !== v))}>{v} ✕</button>)}</div>}</div>;
}

function SessionCard({ s, onOpen }) {
  const span = s.legs.length ? [s.legs[0].time_span.split(" – ")[0], s.legs[s.legs.length - 1].time_span.split(" – ")[1]].filter(Boolean).join(" – ") : "";
  const perLure = s.rows.map((r) => `${shortLure(r)}${Number(r.fish_caught) ? ` · ${r.fish_caught}` : ""}`);
  return (
    <button className="card hist" onClick={onOpen}>
      <div className="card-b">
        <div className="hist-top"><span className="muted small">{dayLabel(s.date)}{span && ` · ${span}`}{s.open && " · live now"}</span>
          <span className="pill">{s.fish_total} fish</span></div>
        <b className="hist-loc">{s.locations.join(" → ")}</b>
        <div className="muted small">{[s.angler, s.segments.join(" → "), s.biggest ? `biggest ${formatWeightLbOz(s.biggest)}` : null].filter(Boolean).join(" · ")}</div>
        <div className="hist-lures small">{perLure.join("  ·  ")}</div>
      </div>
    </button>
  );
}

/* ------------------------------------------------------------------ one session: view, edit, delete */
function SessionSheet({ s, canEdit, spots, onClose, onSave, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const multi = s.legs.length > 1;
  return <>
    <Sheet open={!confirm} title={`${dayLabel(s.date)} · ${s.angler || "Unspecified"}`} onClose={onClose}>
      {editing ? <EditSession s={s} spots={spots} onCancel={() => setEditing(false)} onSave={(rows) => { onSave(rows); setEditing(false); }} />
        : <div className="setup">
          {multi && <p className="note-bar">{s.locations.length > 1 ? `📍 Moved during this session: ${s.locations.join(" → ")}` : `🔄 Conditions were updated ${s.legs.length - 1}× at ${s.locations[0]}`}</p>}
          {s.legs.map((leg, i) => <LegView key={i} leg={leg} n={multi ? `${i + 1} of ${s.legs.length}` : null} />)}
          {canEdit ? <div className="two"><button className="btn primary" onClick={() => setEditing(true)}>Edit</button>
            <button className="btn danger" onClick={() => setConfirm(true)}>Delete</button></div>
            : <p className="muted small">Only {s.angler || "the angler who logged it"} or an admin can change this session.</p>}
          {s.open && <p className="muted small">This session is still open in Spot Session.</p>}
        </div>}
    </Sheet>
    <Sheet open={confirm} title="Delete this session?" onClose={() => setConfirm(false)}>
      <div className="setup"><p>Everything in it ({s.rows.length} lure{s.rows.length > 1 ? "s" : ""}, {s.fish_total} fish) will be deleted. This can't be undone.</p>
        <button className="btn wide danger-solid" onClick={onDelete}>Delete session</button>
        <button className="btn wide" onClick={() => setConfirm(false)}>Keep it</button></div>
    </Sheet>
  </>;
}

function LegView({ leg, n }) {
  const c = parseConditions(leg.rows[0]);
  const cond = { ...S.CONDITION_FIELDS, ...Object.fromEntries(LEG_CONDITION_KEYS.filter((k) => c[k] != null).map((k) => [k, c[k]])) };
  return <div className="leg">
    <div className="lr-h">{n && `📍 ${n}: `}{leg.location}</div>
    <div className="muted small">{[leg.segment, leg.time_span, leg.structure_type, leg.rows[0].water_clarity && `${leg.rows[0].water_clarity} water`, leg.rows[0].predicted_score && `predicted ${leg.rows[0].predicted_score}`].filter(Boolean).join(" · ")}</div>
    <p className="setup-sum" style={{ margin: "6px 0" }}>{conditionsSummary(cond)}{c.forage_seen?.length ? ` · forage: ${c.forage_seen.join(", ")}` : ""}{c.fish_depth_ft ? ` · fish at ${c.fish_depth_ft} ft` : ""}</p>
    {leg.rows.map((r) => { const lc = parseConditions(r), fish = Array.isArray(lc.fish) && lc.source === "spot_session" ? lc.fish : null; return (
      <div key={r.trip_id} className="lure-v">
        <b>{r.lure_used || "Unspecified"}</b>
        <div className="muted small">{[lureTypeLabel(lc), lc.trailer_used && `+ ${lc.trailer_name || "trailer"}${lc.trailer_color ? ` (${lc.trailer_color})` : ""}`, r.technique_used,
          `${t12(lc.lure_start_time)} – ${lc.lure_end_time ? t12(lc.lure_end_time) : "still open"}`].filter(Boolean).join(" · ")}</div>
        {fish ? (fish.length ? fish.map((x, i) => <div key={i} className="fishline small">🐟 {fishText(x)}</div>) : <div className="muted small">No fish on this lure.</div>)
          : <div className="small">{r.fish_caught || 0} fish{r.biggest_fish_lb ? `, biggest ${formatWeightLbOz(Number(r.biggest_fish_lb))}` : ""}</div>}
        {r.notes && <div className="small">📝 {r.notes}</div>}
      </div>); })}
  </div>;
}

/* ------------------------------------------------------------------ edit */
function EditSession({ s, spots, onCancel, onSave }) {
  const [date, setDate] = useState(s.date || lakeToday());
  const [legs, setLegs] = useState(() => s.legs.map((leg) => {
    const c = parseConditions(leg.rows[0]);
    return { spot_id: leg.spot_id, spot_name: leg.rows[0].spot_name, segment: leg.segment || "Morning", structure_type: leg.structure_type || STRUCTURE_TYPES[0],
      cond: { ...S.CONDITION_FIELDS, ...Object.fromEntries(LEG_CONDITION_KEYS.filter((k) => c[k] !== undefined).map((k) => [k, c[k]])) }, sources: c.field_sources || {}, changed: [],
      lures: Object.fromEntries(leg.rows.map((r) => { const lc = parseConditions(r); return [r.trip_id, { lure_used: r.lure_used || "", color_used: r.color_used || "", technique_used: r.technique_used || "",
        notes: r.notes || "", lure_category: lc.lure_category || "", trailer_used: !!lc.trailer_used, trailer_name: lc.trailer_name || "", trailer_color: lc.trailer_color || "",
        fish: Array.isArray(lc.fish) && lc.source === "spot_session" ? lc.fish : undefined, fish_caught: Number(r.fish_caught) || 0, biggest_fish_lb: r.biggest_fish_lb ? Number(r.biggest_fish_lb) : null }]; })) };
  }));
  const [fishEdit, setFishEdit] = useState(null); // {li, tid, i (index | null = new), lure}
  const setLeg = (li, patch) => setLegs((ls) => ls.map((l, j) => (j === li ? { ...l, ...patch } : l)));
  const setLure = (li, tid, patch) => setLegs((ls) => ls.map((l, j) => (j === li ? { ...l, lures: { ...l.lures, [tid]: { ...l.lures[tid], ...patch } } } : l)));
  const spotList = [...(spots || [])].sort((a, b) => a.name.localeCompare(b.name));
  const save = () => {
    const rows = s.legs.flatMap((leg, li) => { const e = legs[li];
      const lures = Object.fromEntries(Object.entries(e.lures).map(([tid, l]) => { const { fish, fish_caught, biggest_fish_lb, ...rest } = l;
        return [tid, { ...rest, lure_category: l.lure_category || null, ...(fish ? { fish } : { fish_caught, biggest_fish_lb }) }]; }));
      return applyLegEdit(leg.rows, { segment: e.segment, spot_id: e.spot_id, spot_name: spotList.find((x) => x.spot_id === e.spot_id)?.name || e.spot_name, structure_type: e.structure_type,
        cond: e.cond, changed: e.changed, lures }, date); });
    onSave(rows);
  };
  return <div className="setup">
    <label className="field">Date<input type="date" value={date} max={lakeToday()} onChange={(e) => setDate(e.target.value || date)} /></label>
    {legs.map((e, li) => <div key={li} className="leg">
      {legs.length > 1 && <div className="lr-h">📍 Location {li + 1} of {legs.length}</div>}
      <label className="field">Location<select value={e.spot_id} onChange={(ev) => setLeg(li, { spot_id: ev.target.value })}>
        {!spotList.some((x) => x.spot_id === e.spot_id) && <option value={e.spot_id}>{e.spot_name || "Unknown"} (not in saved spots)</option>}
        {spotList.map((x) => <option key={x.spot_id} value={x.spot_id}>{x.name}</option>)}</select></label>
      <div className="two">
        <label className="field">Time of day<select value={e.segment} onChange={(ev) => setLeg(li, { segment: ev.target.value })}>{[...new Set([...SEGMENTS, e.segment])].map((x) => <option key={x}>{x}</option>)}</select></label>
        <label className="field">Structure<select value={e.structure_type} onChange={(ev) => setLeg(li, { structure_type: ev.target.value })}>{[...new Set([...STRUCTURE_TYPES, e.structure_type])].map((x) => <option key={x}>{x}</option>)}</select></label>
      </div>
      <details className="gaps"><summary>Conditions: {conditionsSummary(e.cond)}</summary>
        <ConditionsForm cond={{ values: e.cond, sources: e.sources }} onChange={(k, v) => setLeg(li, { cond: { ...e.cond, [k]: v }, sources: { ...e.sources, [k]: "you" }, changed: [...new Set([...e.changed, k])] })} />
      </details>
      <p className="muted small">The predicted score stays as it was recorded — editing corrects what you saw, it doesn't re-run the forecast.</p>
      {s.legs[li].rows.map((r) => { const l = e.lures[r.trip_id], pre = `lure-${r.trip_id}`; return (
        <div key={r.trip_id} className="lure-v">
          <label className="field">Lure<input type="text" id={pre} value={l.lure_used} onChange={(ev) => setLure(li, r.trip_id, { lure_used: ev.target.value })} /></label>
          <div className="two">
            <label className="field">Type / rig<select value={l.lure_category} onChange={(ev) => setLure(li, r.trip_id, { lure_category: ev.target.value })}>
              <option value="">Unspecified</option>{LURE_CATEGORY_OPTIONS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
            <label className="field">Color<input type="text" value={l.color_used} onChange={(ev) => setLure(li, r.trip_id, { color_used: ev.target.value })} /></label>
          </div>
          <label className="field">Technique<input type="text" value={l.technique_used} onChange={(ev) => setLure(li, r.trip_id, { technique_used: ev.target.value })} /></label>
          <label className="check"><input type="checkbox" checked={l.trailer_used} onChange={(ev) => setLure(li, r.trip_id, { trailer_used: ev.target.checked })} /> Used a trailer</label>
          {l.trailer_used && <div className="two">
            <label className="field">Trailer<input type="text" value={l.trailer_name} onChange={(ev) => setLure(li, r.trip_id, { trailer_name: ev.target.value })} /></label>
            <label className="field">Trailer color<input type="text" value={l.trailer_color} onChange={(ev) => setLure(li, r.trip_id, { trailer_color: ev.target.value })} /></label></div>}
          <label className="field">Notes<textarea rows={2} value={l.notes} onChange={(ev) => setLure(li, r.trip_id, { notes: ev.target.value })} /></label>
          {l.fish ? <div className="field">Fish ({fishTotals(l.fish).fish_caught})
            {l.fish.map((x, i) => <div key={i} className="fishline small"><span className="grow">🐟 {fishText(x)}</span>
              <button type="button" className="iconbtn" aria-label="Edit this fish" onClick={() => setFishEdit({ li, tid: r.trip_id, i, lure: { lure_used: l.lure_used } })}><Icon name="edit" size={14} /></button>
              <button type="button" className="iconbtn" aria-label="Remove this fish" onClick={() => setLure(li, r.trip_id, { fish: l.fish.filter((_, j) => j !== i) })}><Icon name="x" size={14} /></button></div>)}
            <button type="button" className="btn" onClick={() => setFishEdit({ li, tid: r.trip_id, i: null, lure: { lure_used: l.lure_used } })}>＋ Add a fish</button></div>
            : <div className="two">
              <NumberBox label="Fish caught" value={l.fish_caught} step={1} min={0} max={200} onChange={(v) => setLure(li, r.trip_id, { fish_caught: v ?? 0 })} />
              <NumberBox label="Biggest (lb)" value={l.biggest_fish_lb} step={0.0625} min={0} max={15} placeholder="—" onChange={(v) => setLure(li, r.trip_id, { biggest_fish_lb: v })} /></div>}
        </div>); })}
    </div>)}
    <div className="two"><button className="btn primary" onClick={save}>Save changes</button><button className="btn" onClick={onCancel}>Cancel</button></div>
    {fishEdit && <FishSheet lure={fishEdit.lure} initial={fishEdit.i == null ? undefined : legs[fishEdit.li].lures[fishEdit.tid].fish[fishEdit.i]} onClose={() => setFishEdit(null)}
      onSave={(v) => { const cur = legs[fishEdit.li].lures[fishEdit.tid].fish, old = fishEdit.i == null ? null : cur[fishEdit.i];
        const nf = { ...(old || { count: 1, caught_at: null }), species: v.species === "Other (type in species)" && v.speciesOther.trim() ? v.speciesOther.trim() : v.species,
          species_other: v.speciesOther || null, weight_lb: v.weightLb, length_in: v.lengthIn, hit_types: v.hitTypes, retrieve_style: v.retrieveStyle, retrieve_speed: v.retrieveSpeed };
        setLure(fishEdit.li, fishEdit.tid, { fish: fishEdit.i == null ? [...cur, nf] : cur.map((x, j) => (j === fishEdit.i ? nf : x)) }); setFishEdit(null); }} />}
  </div>;
}
