// Spot Session (old pages/6_Spot_Session.py): set up → start → log fish per lure → change/add lures → moved or
// conditions changed → end (or cancel). Others can watch a live session. You are the signed-in angler.
// Every change is saved as a trip row right away through the outbox (lib/outbox.js), so nothing is lost on a weak signal.
import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import LureRec from "./LureRec.jsx";
import { ConditionsForm, FishSheet, LurePicker, RigSelect, TrailerSheet, conditionsSummary } from "./SessionParts.jsx";
import { LOCATION_TYPE_TO_STRUCTURE_TYPE } from "./LakeSetup.jsx";
import { Breakdown, Sheet, fmtTime, verdict } from "./ui.jsx";
import { calibrateWeights, locationAdjustments, parseConditions } from "./lib/calibration.js";
import { curateRecommendation, recommend } from "./lib/lures.js";
import { formatWeightLbOz } from "./lib/leaderboard.js";
import { windMphForBand } from "./lib/onwater.js";
import { dateOf, parseIso, pyFixed } from "./lib/py.js";
import { segmentTimeRanges } from "./lib/scoring.js";
import * as S from "./lib/session.js";
import { lakeNowNaive, lakeToday } from "./lib/weather.js";

const DRAFT = "fm.sessionDraft";
const readDraft = () => { try { return JSON.parse(localStorage.getItem(DRAFT)) || {}; } catch { return {}; } };
const writeDraft = (d) => { try { localStorage.setItem(DRAFT, JSON.stringify(d)); } catch { /* ignore */ } };
const STRUCT = (spot) => LOCATION_TYPE_TO_STRUCTURE_TYPE[spot?.location_type] || "Main-lake point";
const t12 = (hms) => { if (!hms) return "?"; const [h, m] = hms.split(":").map(Number); return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`; };
const fishLine = (f) => [t12(f.caught_at), f.count > 1 ? `${f.count} × ${f.species}` : f.species, f.weight_lb ? formatWeightLbOz(f.weight_lb) : null,
  f.length_in ? `${f.length_in} in` : null, (f.hit_types || []).join(", ") || null, [f.retrieve_speed, f.retrieve_style].filter(Boolean).join(" / ") || null].filter(Boolean).join(" · ");
const spotMeta = (s) => [s.location_type, (s.bottom_structure || "").split("|").filter(Boolean).join(", "), s.main_depth_ft && `main area ${s.main_depth_ft} ft`,
  s.transition_depth_ft && `transition ${s.transition_depth_ft} ft (${s.transition_grade || ""})`].filter(Boolean).join(" · ");

export default function SessionScreen({ active, demo, onMenu, db, me, weather, trips, reloadTrips, lures, spots, toast, outbox }) {
  const [local, setLocal] = useState(null);          // my open session rows (edited here, saved through the outbox)
  const [watching, setWatching] = useState(null);    // session key of someone else's session
  const [sheet, setSheet] = useState(null);
  const [undo, setUndo] = useState(null);
  const bundle = weather.value;

  // my open session comes from the database (another device, or a reload) unless I have unsaved edits here
  const remoteMine = useMemo(() => (trips ? S.myOpenSession(trips, me) : null), [trips, me]);
  // Follow the database copy only when it changes (a reload) and nothing of mine is still waiting to save — never just
  // because the outbox emptied, or edits would flip back to the stale list until the next reload.
  const pendingRef = useRef(outbox.pending); pendingRef.current = outbox.pending;
  useEffect(() => { if (!pendingRef.current) setLocal(remoteMine ? remoteMine.rows : null); }, [remoteMine]);
  const wasPending = useRef(0);
  useEffect(() => { if (wasPending.current && !outbox.pending) reloadTrips(); wasPending.current = outbox.pending; }, [outbox.pending, reloadTrips]);
  const others = useMemo(() => (trips ? S.openSessions(trips).filter((s) => s.owner !== me.email && s.angler.toLowerCase() !== (me.name || "").toLowerCase()) : []), [trips, me]);
  useEffect(() => { if (!watching || !active) return; const t = setInterval(reloadTrips, 20e3); return () => clearInterval(t); }, [watching, active, reloadTrips]);

  const saveRows = (rows) => { for (const r of rows) outbox.save(r); };
  const weights = useMemo(() => (trips ? calibrateWeights(trips) : null), [trips]);
  const locAdj = useMemo(() => (trips ? locationAdjustments(trips) : {}), [trips]);

  if (!active) return <div className="screen" hidden id="screen-session" />;
  const watched = watching ? others.find((s) => s.key === watching) : null;
  const common = { bundle, weights, locAdj, lures, spots, trips, me, toast, setSheet };
  return (
    <div className="screen" id="screen-session">
      {watched ? <Watch s={watched} onStop={() => setWatching(null)} onMenu={onMenu} demo={demo} />
        : local && local.length ? <Live rows={local} setRows={(rows, changed) => { setLocal(rows); saveRows(changed); }} {...common}
          outbox={outbox} onMenu={onMenu} demo={demo} setUndo={setUndo}
          onEnded={(msg) => { setLocal(null); setUndo(null); toast(msg); setTimeout(reloadTrips, 1500); }}
          onCancel={(ids) => { for (const id of ids) outbox.remove(id); setLocal(null); setUndo(null); toast("Session canceled — nothing from it was saved"); setTimeout(reloadTrips, 1500); }} />
        : <Setup {...common} others={others} onWatch={setWatching} onMenu={onMenu} demo={demo}
          onStart={(rows) => { setLocal(rows); saveRows(rows); toast("Session started — tap + Fish when you land one"); }} db={db} />}
      <Sheet open={!!sheet} title={sheet?.title} onClose={() => setSheet(null)}>{sheet?.body}</Sheet>
      {undo && <div className="toast undo" role="status"><span>{undo.text}</span><button onClick={() => { undo.run(); setUndo(null); }}>Undo</button></div>}
      {outbox.pending > 0 && <div className="outbox" role="status">{outbox.pending} change{outbox.pending > 1 ? "s" : ""} waiting to save{outbox.error ? " — no connection, retrying" : "…"}
        <button className="link" onClick={outbox.flushNow}>Retry now</button></div>}
    </div>
  );
}

/* ------------------------------------------------------------------ before you start */
function Setup({ bundle, weights, locAdj, lures, spots, trips, me, toast, setSheet, others, onWatch, onStart, onMenu, demo, db }) {
  const today = lakeToday();
  const [draft, setDraftState] = useState(() => readDraft());
  const setDraft = (patch) => setDraftState((d) => { const n = { ...d, ...patch }; writeDraft(n); return n; });
  const [gps, setGps] = useState(null);
  const [editing, setEditing] = useState(false);
  const [picker, setPicker] = useState(false);
  const [trailerFor, setTrailerFor] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const sorted = useMemo(() => [...(spots || [])].sort((a, b) => a.name.localeCompare(b.name)), [spots]);
  const date = draft.date && draft.date <= today ? draft.date : today;
  const now = lakeNowNaive(), at = parseIso(`${date}T${dateOf(now) === date ? new Date(now / 1000).toISOString().slice(11, 19) : "12:00:00"}`);
  const segRanges = segmentTimeRanges(bundle, date);
  const segment = S.guessSegment(date === today ? now : at, segRanges);

  // pick the nearest saved spot by GPS once, unless you already chose one
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current || draft.spot_id || !sorted.length || !navigator.geolocation) return;
    asked.current = true;
    navigator.geolocation.getCurrentPosition((p) => {
      const n = S.nearestSpot(sorted, p.coords.latitude, p.coords.longitude);
      if (n) { setGps({ name: n.spot.name, m: Math.round(n.d) }); setDraft({ spot_id: n.spot.spot_id, spot_source: "gps" }); }
    }, () => {}, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  }, [sorted, draft.spot_id]);
  const spot = sorted.find((s) => s.spot_id === draft.spot_id) || null;

  const cond = useMemo(() => S.mergeConditions(S.weatherDefaults(bundle, date, date === today ? now : at), S.sharedWaterConditions(trips, date),
    { values: draft.cond || {}, sources: Object.fromEntries(Object.keys(draft.cond || {}).map((k) => [k, "you"])) }), [bundle, date, trips, draft.cond]);
  const scoring = useMemo(() => (spot ? S.computeScoring(cond.values, date, bundle, date === today ? now : at, segment, { spotId: spot.spot_id, locAdj, weights }) : null),
    [spot, cond, date, bundle, segment, locAdj, weights]);
  const rec = useMemo(() => (spot && scoring && lures && trips ? recommend({ season: scoring.season, water_temp_f: cond.values.water_temp_f, segment_name: segment,
    pressure_trend_24h: scoring.rt.pressure_trend_24h, structure_type: STRUCT(spot), water_clarity: scoring.water_clarity, fish_depth_ft: cond.values.fish_depth_ft || null,
    forage: cond.values.forage_seen, inventory: lures, trip_history: trips, spot_id: spot.spot_id, fish_activity: cond.values.fish_activity,
    forage_activity: cond.values.forage_activity, wind_mph: windMphForBand(cond.values.wind_band) }) : null), [spot, scoring, lures, trips, cond, segment]);
  const pending = draft.lures || [];
  const pendingIds = new Set(pending.map((l) => l.item_id).filter(Boolean));
  const addLure = (stub) => { if (stub.item_id && pendingIds.has(stub.item_id)) return; setDraft({ lures: [...pending, stub] }); toast(`Added ${stub.label}`); };
  const quickAdd = (item, category) => { const stub = { label: S.itemLabel(item), category, item_id: item.item_id }; if (S.canTakeTrailer({ category })) setTrailerFor(stub); else addLure(stub); };
  const lastLures = useMemo(() => S.lastSessionLures(trips, me, lures), [trips, me, lures]);
  const todaysHere = (trips || []).filter((t) => spot && t.spot_id === spot.spot_id && t.trip_date === date);

  const start = () => {
    const startAt = lakeNowNaive(), startDate = date, seg = date === today ? S.guessSegment(startAt, segmentTimeRanges(bundle, date)) : segment;
    const sc = S.computeScoring(cond.values, startDate, bundle, date === today ? startAt : at, seg, { spotId: spot.spot_id, locAdj, weights });
    const base = { ...S.baseConditions(cond.values, cond.sources, sc, new Date(startAt / 1000).toISOString().slice(11, 19), seg, me.name), spot_source: draft.spot_source || "picked",
      predicted_breakdown: sc.score.breakdown };
    const session = { id: S.newTripId(), date: startDate };
    const rows = pending.map((l) => S.lureRow({ base, lure: l, at: startAt, session, spot, structure: STRUCT(spot), clarity: sc.water_clarity, segment: seg, predicted: sc.score.score, owner: me.email }));
    writeDraft({ spot_id: draft.spot_id, cond: draft.cond }); // keep the spot + your readings for next time, clear the lures
    setDraftState(readDraft());
    onStart(rows);
  };

  return <>
    <Head kicker={`${spot ? spot.name : "Spot Session"} · ${segment}`} title="Session" onMenu={onMenu} demo={demo} />
    <div className="body" style={{ paddingBottom: "calc(96px + var(--kb))" }}>
      {others.length > 0 && <section className="card"><div className="card-b">
        {others.map((o) => <button key={o.key} className="row" style={{ padding: 0, borderBottom: 0 }} onClick={() => onWatch(o.key)}>
          <Icon name="session" /><span className="grow">👀 <b>{o.angler || "Someone"}</b> is fishing {o.rows[o.rows.length - 1].spot_name} now</span><span className="link">Watch</span></button>)}
      </div></section>}

      <section className="card">
        <div className="card-h"><span className="t"><Icon name="map" />Where &amp; when</span><span className="pill">You: {me.name}</span></div>
        <div className="card-b setup" style={{ paddingTop: 12 }}>
          {!sorted.length ? <NoSpots db={db} toast={toast} /> : <>
            <label className="field">Spot
              <select value={draft.spot_id || ""} onChange={(e) => setDraft({ spot_id: e.target.value, spot_source: "picked" })}>
                <option value="">— choose a saved spot —</option>{sorted.map((s) => <option key={s.spot_id} value={s.spot_id}>{s.name}</option>)}
              </select></label>
            {gps && draft.spot_source === "gps" && <p className="muted small">📍 Picked by GPS — you're about {gps.m} m from {gps.name}.</p>}
            {spot && <p className="muted small">{spotMeta(spot) || "No saved details for this spot yet."}</p>}
            <div className="two">
              <label className="field">Date<input type="date" value={date} max={today} onChange={(e) => setDraft({ date: e.target.value || today })} /></label>
              <div className="field">Time of day<div className="static">{segment}{segRanges?.[segment] && <span className="muted small"> {fmtTime(segRanges[segment][0])}–{fmtTime(segRanges[segment][1])}</span>}</div></div>
            </div>
            {date !== today && <p className="muted small">Logging a past session — pressure trend and solunar timing may fall back to their no-data defaults outside the forecast window.</p>}
            {todaysHere.length > 0 && <p className="muted small">📋 Already logged here on {date}: {todaysHere.map((t) => `${t.lure_used || "unknown lure"} (${t.fish_caught || 0} fish)`).join(", ")}</p>}
          </>}
        </div>
      </section>

      {spot && <>
        <section className="card">
          <div className="card-h"><span className="t"><Icon name="wave" />Conditions</span><button className="pill" onClick={() => setEditing(!editing)}>{editing ? "Done" : "Edit"}</button></div>
          <div className="card-b">
            {!editing ? <button className="setup-sum" onClick={() => setEditing(true)}>{conditionsSummary(cond.values)} <span className="link">Edit</span></button>
              : <ConditionsForm cond={cond} onChange={(f, v) => setDraft({ cond: { ...(draft.cond || {}), [f]: v } })} />}
            <p className="muted small" style={{ margin: "8px 0 0" }}>Filled from the forecast{Object.values(cond.sources).some((s) => s.startsWith("shared:")) ? " and today's readings from another angler" : ""} — anything you change is saved as yours.</p>
          </div>
        </section>

        {scoring && <section className="card">
          <div className="card-h"><span className="t"><Icon name="trend" />Predicted for {segment}</span>
            <button className="pill" onClick={() => setSheet({ title: `${segment} at ${spot.name}`, body: <Breakdown breakdown={scoring.score.breakdown} score={scoring.score.score} /> })}>{scoring.score.score.toFixed(1)} · why</button></div>
          <div className="card-b"><b>{verdict(scoring.score.score).replace(" day", "")}</b> <span className="muted small">· {scoring.water_clarity} water · {scoring.season.replace(/_/g, " ")}</span>
            {scoring.score.warnings.map((w) => <p key={w} className="warn">{w}</p>)}
            {!bundle && <p className="muted small">No forecast right now — pressure trend and solunar timing aren't in this score.</p>}</div>
        </section>}

        {rec && <section className="card">
          <div className="card-h"><span className="t"><Icon name="tackle" />Suggested — tap + to fish it</span></div>
          <div className="card-b">
            <QuickPicks rec={rec} lures={lures} added={pendingIds} onAdd={quickAdd} />
            <button className="link" onClick={() => setShowDetails(!showDetails)}>{showDetails ? "Hide" : "Colors, depth, how to fish them, gaps"} ›</button>
            {showDetails && <LureRec rec={rec} inventory={lures} />}
          </div>
        </section>}

        <section className="card">
          <div className="card-h"><span className="t"><Icon name="tackle" />Your lures for this session ({pending.length})</span>
            <button className="pill" onClick={() => setPicker(true)}>Tackle box</button></div>
          <div className="card-b">
            {pending.map((l, i) => <div key={i} className="pend">
              <div className="row" style={{ padding: "0 0", minHeight: 44, borderBottom: 0 }}>
                <span className="grow">{l.label}{l.trailer && <span className="muted"> + {l.trailer.label}</span>}</span>
                <button className="iconbtn" aria-label={`Remove ${l.label}`} onClick={() => setDraft({ lures: pending.filter((_, j) => j !== i) })}><Icon name="x" size={16} /></button></div>
              <RigSelect category={l.category} onChange={(c) => setDraft({ lures: pending.map((x, j) => (j === i ? { ...x, category: c } : x)) })} /></div>)}
            {!pending.length && <p className="muted small" style={{ margin: 0 }}>No lures yet — tap + on a suggestion, pick from the tackle box, or repeat last time.</p>}
            {lastLures.length > 0 && <button className="btn wide" style={{ marginTop: 10 }} onClick={() => setDraft({ lures: [...pending, ...lastLures.filter((l) => !pending.some((p) => p.label === l.label))] })}>
              ↺ Same lures as last time ({lastLures.length})</button>}
          </div>
        </section>
      </>}
    </div>
    {spot && <div className="dock"><button className="btn primary wide big" disabled={!pending.length} onClick={start}>▶ Start session{pending.length ? ` (${pending.length} lure${pending.length > 1 ? "s" : ""})` : ""}</button></div>}
    <LurePicker open={picker} onClose={() => setPicker(false)} inventory={lures} already={pendingIds} onPick={(s) => { addLure(s); }} />
    <TrailerSheet stub={trailerFor} inventory={lures} onClose={() => setTrailerFor(null)} onDone={(s) => { setTrailerFor(null); addLure(s); }} />
  </>;
}

/** One line per owned top pick with a "+ Add" button (old _render_recommendation_with_quick_add). */
function QuickPicks({ rec, lures, added, onAdd }) {
  const c = curateRecommendation(rec, lures);
  if (!c.recommended.length) return <p className="muted small">Nothing in your tackle box is a strong fit right now — see the gaps under details.</p>;
  return <div className="qp">{c.recommended.map((b) => (
    <div key={b.key} className="qp-b"><b>{b.name}</b>
      {b.owned_items.map((it) => { const on = added.has(it.item_id); return (
        <div key={it.item_id} className="qp-i"><span className="grow small">{it.brand} – {it.description}{it._item_fish_per_hour ? <span className="ok"> · {pyFixed(it._item_fish_per_hour, 1)} fish/hr for you</span> : null}</span>
          <button className={on ? "btn small-btn" : "btn primary small-btn"} disabled={on} onClick={() => onAdd(it, b.key)}>{on ? "✓ Added" : "+ Add"}</button></div>); })}
    </div>))}</div>;
}

function NoSpots({ db, toast }) {
  return <p className="muted small" style={{ margin: 0 }}>You don't have any saved spots yet. Saved spots come from the Lake Map, which is being rebuilt — until then, add spots in the old app.</p>;
}

/* ------------------------------------------------------------------ live session */
function Live({ rows, setRows, bundle, weights, locAdj, lures, spots, trips, me, toast, setSheet, outbox, onEnded, onCancel, onMenu, demo, setUndo }) {
  const [fishFor, setFishFor] = useState(null);
  const [picker, setPicker] = useState(false);
  const [moving, setMoving] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 30e3); return () => clearInterval(t); }, []);
  const base = S.sessionConditions(rows[rows.length - 1]);
  const open = rows.filter((r) => !r.conditions.lure_end_time), retired = rows.filter((r) => r.conditions.lure_end_time);
  const current = open[open.length - 1] || rows[rows.length - 1];
  const totalFish = rows.reduce((a, r) => a + Number(r.fish_caught || 0), 0);
  const startHms = S.sessionStartTime(rows) || "00:00:00";
  const mins = Math.max(0, Math.round((lakeNowNaive() - parseIso(`${rows[0].trip_date}T${startHms.slice(0, 8)}`)) / 60e6));
  const replace = (r) => rows.map((x) => (x.trip_id === r.trip_id ? r : x));
  const undoable = (text, before, changed) => { setUndo({ text, run: () => { setRows(before, changed.map((c) => before.find((b) => b.trip_id === c.trip_id)).filter(Boolean)); } });
    setTimeout(() => setUndo((u) => (u && u.text === text ? null : u)), 10e3); };

  const logFish = (row, f) => {
    const nr = S.withFish(row, [...row.conditions.fish, S.newFish({ ...f, at: lakeNowNaive() })]);
    const before = rows; setRows(replace(nr), [nr]); setFishFor(null);
    undoable(`🐟 Fish logged on ${row.lure_used.split(" - ")[0]}`, before, [nr]);
  };
  const removeFish = (row, i) => { const nr = S.withFish(row, row.conditions.fish.filter((_, j) => j !== i)); setRows(replace(nr), [nr]); };
  const change = (row) => { const nr = S.retireRow(row, lakeNowNaive()); const before = rows; setRows(replace(nr), [nr]); undoable(`Retired ${row.lure_used.split(" - ")[0]}`, before, [nr]); };
  const addLure = (stub) => {
    if (stub.item_id && open.some((r) => r.conditions.item_id === stub.item_id)) { toast("That lure is already in this session"); return; }
    const r = S.lureRow({ base, lure: stub, at: lakeNowNaive(), session: { id: current.session_id, date: current.trip_date }, spot: { spot_id: current.spot_id, name: current.spot_name },
      structure: current.structure_type, clarity: current.water_clarity, segment: current.segment, predicted: current.predicted_score, owner: me.email });
    setRows([...rows, r], [r]); setPicker(false); toast(`Added ${stub.label}`);
  };
  const end = () => { const now = lakeNowNaive(), ended = S.endRows(rows, now); setRows(ended, ended); onEnded(`✅ Session closed at ${current.spot_name} — ${totalFish} fish`); };

  return <>
    <Head kicker={`Live · started ${t12(startHms)} · ${Math.floor(mins / 60) ? `${Math.floor(mins / 60)} h ` : ""}${mins % 60} m`} title={current.spot_name} onMenu={onMenu} demo={demo} />
    <div className="body" style={{ paddingBottom: "calc(96px + var(--kb))" }}>
      <section className="card"><div className="card-b" style={{ flexDirection: "row", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span className="muted small">{current.segment} · {current.water_clarity} water · predicted <b className="num">{current.predicted_score}</b>{" "}
          {base.predicted_breakdown && <button className="link" onClick={() => setSheet({ title: "Predicted score", body: <Breakdown breakdown={base.predicted_breakdown} score={Number(current.predicted_score)} /> })}>why</button>}</span>
        <span className="pill">{totalFish} fish</span></div></section>
      <p className="muted small" style={{ margin: "0 4px" }}>Tap <b>+ Fish</b> every time you land one. <b>Change</b> retires a lure without ending the session.</p>
      {open.map((r) => (
        <section key={r.trip_id} className="card"><div className="card-b">
          <div><b style={{ fontSize: 16 }}>{r.lure_used}</b><div className="muted small">{r.conditions.trailer_name ? `+ ${r.conditions.trailer_name} · ` : ""}since {t12(r.conditions.lure_start_time)} · {r.fish_caught || 0} fish</div></div>
          <RigSelect category={r.conditions.lure_category} onChange={(c) => { const nr = S.withRig(r, c); setRows(replace(nr), [nr]); }} />
          <div className="fishbtns"><button className="btn primary big" onClick={() => setFishFor(r)}>+ Fish</button><button className="btn" onClick={() => change(r)}>Change</button></div>
          {r.conditions.fish.length > 0 && <div className="fishlist">{r.conditions.fish.map((f, i) => <div key={i} className="fishline"><span className="grow">{fishLine(f)}</span>
            <button className="iconbtn" aria-label="Remove this fish" onClick={() => setConfirm({ text: `Remove this fish (${fishLine(f)})?`, run: () => removeFish(r, i) })}><Icon name="x" size={14} /></button></div>)}</div>}
        </div></section>))}
      {!open.length && <p className="note-bar">All lures are retired — add a lure to keep fishing, or end the session.</p>}
      <div className="two"><button className="btn" onClick={() => setPicker(true)}>＋ Add a lure</button><button className="btn" onClick={() => setMoving(true)}>↻ Moved / conditions</button></div>
      {retired.length > 0 && <details className="gaps"><summary>Retired lures ({retired.length})</summary>
        {retired.map((r) => <p key={r.trip_id} className="muted small">{r.lure_used} @ {r.spot_name} · {r.fish_caught || 0} fish · {t12(r.conditions.lure_start_time)}–{t12(r.conditions.lure_end_time)}</p>)}</details>}
      <p className="muted small" style={{ margin: "0 4px" }}>Saved as you go — if your signal drops, it catches up when you're back in range.</p>
    </div>
    <div className="dock dock2"><button className="btn primary big" onClick={() => setConfirm({ text: `End this session? ${totalFish} fish will be saved.`, ok: "End session", run: end })}>■ End session</button>
      <button className="btn danger" onClick={() => setConfirm({ text: "Cancel this session? Everything logged in it (lures and fish) will be deleted. This can't be undone.", ok: "Delete session", danger: true, run: () => onCancel(rows.map((r) => r.trip_id)) })}>Cancel</button></div>
    <FishSheet lure={fishFor} onClose={() => setFishFor(null)} onSave={(f) => logFish(fishFor, f)} />
    <AddLureSheet open={picker} onClose={() => setPicker(false)} lures={lures} trips={trips} base={base} current={current} bundle={bundle} weights={weights} locAdj={locAdj} onAdd={addLure} openIds={new Set(open.map((r) => r.conditions.item_id).filter(Boolean))} />
    <MoveSheet open={moving} onClose={() => setMoving(false)} rows={rows} setRows={setRows} base={base} current={current} spots={spots} bundle={bundle} weights={weights} locAdj={locAdj} me={me} toast={toast} />
    <Sheet open={!!confirm} title="Are you sure?" onClose={() => setConfirm(null)}>
      {confirm && <div className="setup"><p>{confirm.text}</p>
        <button className={`btn wide ${confirm.danger ? "danger-solid" : "primary"}`} onClick={() => { confirm.run(); setConfirm(null); }}>{confirm.ok || "Yes"}</button>
        <button className="btn wide" onClick={() => setConfirm(null)}>Keep fishing</button></div>}
    </Sheet>
  </>;
}

function AddLureSheet({ open, onClose, lures, trips, base, current, bundle, weights, locAdj, onAdd, openIds }) {
  const [tackle, setTackle] = useState(false);
  const [trailerFor, setTrailerFor] = useState(null);
  const rec = useMemo(() => {
    if (!open || !lures || !trips) return null;
    const sc = S.computeScoring(base, current.trip_date, bundle, lakeNowNaive(), current.segment, { spotId: current.spot_id, locAdj, weights });
    return recommend({ season: sc.season, water_temp_f: base.water_temp_f ?? 85, segment_name: current.segment, pressure_trend_24h: sc.rt.pressure_trend_24h,
      structure_type: current.structure_type, water_clarity: current.water_clarity, fish_depth_ft: base.fish_depth_ft || null, forage: base.forage_seen,
      inventory: lures, trip_history: trips, spot_id: current.spot_id, fish_activity: base.fish_activity, forage_activity: base.forage_activity, wind_mph: windMphForBand(base.wind_band) });
  }, [open, lures, trips, base, current, bundle, weights, locAdj]);
  const pick = (item, category) => { const stub = { label: S.itemLabel(item), category, item_id: item.item_id }; if (S.canTakeTrailer({ category })) setTrailerFor(stub); else onAdd(stub); };
  return <>
    <Sheet open={open && !tackle && !trailerFor} title="Add a lure" onClose={onClose}>
      <div className="setup">
        <button className="btn wide" onClick={() => setTackle(true)}>Search the tackle box</button>
        <div className="lr-h">Suggested for right now</div>
        {rec ? <QuickPicks rec={rec} lures={lures} added={openIds} onAdd={pick} /> : <p className="muted">Loading…</p>}
      </div>
    </Sheet>
    <LurePicker open={open && tackle} onClose={() => setTackle(false)} inventory={lures} already={openIds} onPick={(s) => { setTackle(false); onAdd(s); }} />
    <TrailerSheet stub={trailerFor} inventory={lures} onClose={() => setTrailerFor(null)} onDone={(s) => { setTrailerFor(null); onAdd(s); }} />
  </>;
}

/** Moved to another spot or conditions changed (old _relocate_active_session). Small fixes in the first 10 minutes of
 *  the current lures update them in place; otherwise the current lures are closed and reopened under the new conditions,
 *  so every row's conditions stay true for the time it covers. */
function MoveSheet({ open, onClose, rows, setRows, base, current, spots, bundle, weights, locAdj, me, toast }) {
  const [spotId, setSpotId] = useState(current.spot_id);
  const [edits, setEdits] = useState({});
  useEffect(() => { if (open) { setSpotId(current.spot_id); setEdits({}); } }, [open]);
  if (!open) return null;
  const spot = (spots || []).find((s) => s.spot_id === spotId) || { spot_id: current.spot_id, name: current.spot_name, location_type: null };
  const cond = { values: { ...S.CONDITION_FIELDS, ...Object.fromEntries(Object.keys(S.CONDITION_FIELDS).map((k) => [k, base[k] ?? S.CONDITION_FIELDS[k]])), ...edits },
    sources: { ...(base.field_sources || {}), ...Object.fromEntries(Object.keys(edits).map((k) => [k, "you"])) } };
  const now = lakeNowNaive(), seg = S.guessSegment(now, segmentTimeRanges(bundle, current.trip_date));
  const sc = S.computeScoring(cond.values, current.trip_date, bundle, now, seg, { spotId: spot.spot_id, locAdj, weights });
  const apply = () => {
    const open = rows.filter((r) => !r.conditions.lure_end_time);
    const newBase = { ...S.baseConditions(cond.values, cond.sources, sc, base.start_time, seg, me.name), spot_source: spotId === current.spot_id ? base.spot_source : "picked", predicted_breakdown: sc.score.breakdown };
    const young = open.every((r) => (now - parseIso(`${r.trip_date}T${r.conditions.lure_start_time.slice(0, 8)}`)) < 10 * 60e6);
    let next = rows, changed = [];
    if (spotId === current.spot_id && young) {
      changed = open.map((r) => ({ ...r, segment: seg, water_clarity: sc.water_clarity, predicted_score: sc.score.score,
        conditions: { ...newBase, ...Object.fromEntries(Object.entries(r.conditions).filter(([k]) => ["lure_category", "trailer_used", "trailer_name", "trailer_color", "trailer_category", "item_id", "lure_start_time", "lure_end_time", "fish", "source"].includes(k))) } }));
      next = rows.map((r) => changed.find((c) => c.trip_id === r.trip_id) || r);
    } else {
      const closed = open.map((r) => S.retireRow(r, now));
      const reopened = open.map((r) => S.lureRow({ base: newBase, lure: { label: r.lure_used, category: r.conditions.lure_category, item_id: r.conditions.item_id,
        trailer: r.conditions.trailer_used ? { label: r.conditions.trailer_name, color: r.conditions.trailer_color, category: r.conditions.trailer_category } : null },
        at: now, session: { id: r.session_id, date: r.trip_date }, spot, structure: STRUCT(spot), clarity: sc.water_clarity, segment: seg, predicted: sc.score.score, owner: me.email }));
      changed = [...closed, ...reopened];
      next = [...rows.map((r) => closed.find((c) => c.trip_id === r.trip_id) || r), ...reopened];
    }
    setRows(next, changed); onClose(); toast(spotId === current.spot_id ? "Conditions updated" : `Moved to ${spot.name}`);
  };
  return (
    <Sheet open title="Moved or conditions changed?" onClose={onClose}>
      <div className="setup">
        <label className="field">Spot<select value={spotId} onChange={(e) => setSpotId(e.target.value)}>
          {[...(spots || [])].sort((a, b) => a.name.localeCompare(b.name)).map((s) => <option key={s.spot_id} value={s.spot_id}>{s.name}</option>)}
          {!(spots || []).some((s) => s.spot_id === current.spot_id) && <option value={current.spot_id}>{current.spot_name}</option>}</select></label>
        <ConditionsForm cond={cond} onChange={(f, v) => setEdits({ ...edits, [f]: v })} />
        <p className="muted small">New {seg} score here: <b className="num">{sc.score.score.toFixed(1)}</b> (was {current.predicted_score}).</p>
        <button className="btn primary wide" onClick={apply}>Update session</button>
      </div>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ watching someone */
function Watch({ s, onStop, onMenu, demo }) {
  const rows = s.rows, c0 = parseConditions(rows[0]), last = rows[rows.length - 1];
  const fish = rows.flatMap((r) => (parseConditions(r).fish || []).map((f) => ({ ...f, lure: r.lure_used })));
  const total = fish.reduce((a, f) => a + (f.count || 1), 0), biggest = Math.max(0, ...fish.map((f) => Number(f.weight_lb) || 0));
  const open = rows.filter((r) => !parseConditions(r).lure_end_time);
  return <>
    <Head kicker="Watching · updates every 20 s" title={s.angler || "Someone"} onMenu={onMenu} demo={demo} />
    <div className="body">
      <section className="card"><div className="card-b">
        <span className="muted small">📍 {last.spot_name} · started {t12(S.sessionStartTime(rows))} · {last.segment} · predicted <b className="num">{last.predicted_score}</b></span>
        <div className="two" style={{ marginTop: 10 }}>
          <div className="award"><span className="v num">{total}</span><span className="muted small">fish</span></div>
          <div className="award"><span className="v num">{biggest ? formatWeightLbOz(biggest) : "—"}</span><span className="muted small">biggest</span></div>
        </div></div></section>
      <section className="card"><div className="card-h"><span className="t">Fishing now</span></div><div className="card-b">
        {open.map((r) => { const f = parseConditions(r).fish || []; return <div key={r.trip_id} style={{ marginBottom: 8 }}><b>{r.lure_used}</b>
          <div className="muted small">since {t12(parseConditions(r).lure_start_time)} · {r.fish_caught || 0} fish{f.length ? ` · latest ${fishLine(f[f.length - 1])}` : ""}</div></div>; })}
      </div></section>
      <p className="muted small">Read-only — only {s.angler || "they"} can change this session.</p>
      <button className="btn wide" onClick={onStop}>Stop watching — start my own session</button>
    </div>
  </>;
}
