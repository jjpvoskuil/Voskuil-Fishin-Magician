// Reports → Oxygen & catch (John 11-20): our outings vs the Army Corps oxygen profiles. Engine: lib/o2catch.js.
// Fills in by itself: new Corps profiles arrive in fm_water_quality twice a day (deercast-data water-quality job).
import { useEffect, useMemo, useRef, useState } from "react";
import { o2Catch } from "./lib/o2catch.js";
import { windowFor } from "./lib/reportspec.js";
import { formatDateShort } from "./lib/stringer.js";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const wkLabel = (d) => `${MON[+d.slice(5, 7) - 1]} ${+d.slice(8, 10)}`;

function Bars({ rows, note }) {
  const max = Math.max(0, ...rows.map((b) => b.rate || 0));
  return <div className="rp-bars">{rows.map((b) => (
    <div key={b.key} className={`rp-bar ${b.outings && b.outings < 4 ? "thin" : ""}`}>
      <span className="rp-lbl">{b.label}</span>
      <span className="rp-track"><span style={{ width: `${max > 0 && b.rate ? Math.max(2, (b.rate / max) * 100) : 0}%` }} /></span>
      <span className="rp-val"><b className="num">{b.rate != null ? `${b.rate.toFixed(2)}/hr` : "–"}</b><span className="muted small block">{b.outings} outing{b.outings === 1 ? "" : "s"}{b.fish ? ` · ${b.fish} fish` : ""}</span></span>
    </div>))}{note && <p className="muted small" style={{ margin: "4px 0 0" }}>{note}</p>}</div>;
}

/** Week by week: fish/hr bar, with the oxygen floor at our spots (or "turnover") written under each week. */
function Weeks({ weeks }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.scrollLeft = ref.current.scrollWidth; }, [weeks.length]);
  const vmax = Math.max(1, ...weeks.map((w) => w.rate || 0)), step = 46, P = 8, H = 170, top = 18, bot = 40, W = Math.max(330, P * 2 + weeks.length * step);
  const Y = (v) => H - bot - (v / vmax) * (H - top - bot);
  return <div className="ot-wrap" ref={ref}>
    <svg className="sc-plot ot" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Fish per hour each week, with the oxygen floor at our spots">
      <line x1={P} x2={W - P} y1={Y(0)} y2={Y(0)} className="ax" />
      {weeks.map((w, i) => { const x = P + i * step + step / 2, v = w.rate;
        return <g key={w.week}>
          {v != null && <rect x={x - 13} y={Y(v)} width="26" height={Math.max(1, Y(0) - Y(v))} rx="3" className={`ot-bar${w.phase === "stratified" ? "" : " o2-turn"}`} opacity={w.outings < 3 ? 0.45 : 1}><title>{`Week of ${wkLabel(w.week)}: ${w.fish} fish in ${w.hours.toFixed(1)} h (${w.outings} outings)`}</title></rect>}
          {v != null && <text x={x} y={Y(v) - 4} className="tk" textAnchor="middle">{v.toFixed(1)}</text>}
          <text x={x} y={H - bot + 14} className="tk" textAnchor="middle">{wkLabel(w.week)}</text>
          <text x={x} y={H - bot + 27} className="tk sc-s" textAnchor="middle">{w.phase === "stratified" && w.floor != null ? `${Math.round(w.floor)} ft` : w.phase === "turnover" ? "turn" : "mixed"}</text>
        </g>; })}
    </svg></div>;
}

export default function O2Check({ db, trips, f, me, setScreen }) {
  const [spots, setSpots] = useState(null), [log, setLog] = useState(null);
  useEffect(() => { db.listSpots().then(setSpots).catch(() => setSpots([])); db.listWaterQuality().then(setLog).catch(() => setLog([])); }, [db]);
  const win = windowFor({}, f.period), owner = f.who === "me" ? me.email : null;
  const r = useMemo(() => (spots && log ? o2Catch(trips, { spots, waterLog: log, from: win.from, to: win.to, owner }) : null), [trips, spots, log, win.from, win.to, owner]);
  if (!r) return <section className="card"><div className="card-b"><p className="muted">Loading the Corps profiles…</p></div></section>;
  const strat = r.byPhase.find((x) => x.key === "stratified"), turn = r.byPhase.find((x) => x.key === "turnover");
  const hi = r.byPosition.filter((x) => x.key === "well" || x.key === "above"), at = r.byPosition.filter((x) => x.key === "at" || x.key === "below");
  const sum = (g) => { const h = g.reduce((s, x) => s + x.hours, 0), fi = g.reduce((s, x) => s + x.fish, 0); return { n: g.reduce((s, x) => s + x.outings, 0), rate: h >= 0.5 ? fi / h : null }; };
  const A = sum(hi), B = sum(at), last = r.profiles[r.profiles.length - 1];
  return <section className="card">
    <div className="card-h"><span className="t">Oxygen &amp; catch</span><span className="muted small">{r.matched} of {r.outings} outings matched</span></div>
    <div className="card-b setup" style={{ paddingTop: 10 }}>
      {f.period !== "all" && <p className="note-bar">Showing {f.period === "year" ? "this year" : `the last ${f.period} days`}. <button className="link" onClick={() => setScreen({ period: "all" })}>Show all our history ›</button></p>}
      {!r.matched ? <p className="empty">No outings near a Corps oxygen profile in this period yet. The Corps checks the lake about every two weeks, April–November.</p> : <>
        {A.rate != null && B.rate != null && <p style={{ margin: 0 }}><b>Fish marked more than 2 ft above the oxygen floor: {A.rate.toFixed(1)} fish/hr. At or below it: {B.rate.toFixed(1)}.</b>
          <span className="muted small"> ({A.n} vs {B.n} summer outings; all matched outings {formatDateShort(r.span[0], true)} – {formatDateShort(r.span[1], true)})</span></p>}
        <div className="lr-h">Where you marked fish vs the oxygen floor</div>
        <Bars rows={r.byPosition} note={`Summer only (lake layered). Floor = where the Corps measured oxygen dropping under 5 mg/L, shallower the further your spot is up the lake. Typical marked depth: ${r.medianMarkedVsFloor == null ? "–" : `${Math.abs(r.medianMarkedVsFloor).toFixed(1)} ft ${r.medianMarkedVsFloor < 0 ? "above" : "below"}`} the floor.`} />
        <div className="lr-h">Week by week</div>
        <Weeks weeks={r.weeks} />
        <p className="muted small" style={{ margin: 0 }}>Fish per angler-hour each week; under it, the oxygen floor at your spots that week, or "turn" for turnover. Faded = fewer than 3 outings that week. Swipe sideways for earlier weeks.</p>
        <div className="lr-h">How deep the floor was</div>
        <Bars rows={r.byFloor} note="Summer outings only, by the oxygen floor at the spot fished. A deeper floor = more room for bass." />
        <div className="lr-h">Lake phase</div>
        <Bars rows={r.byPhase} note={strat?.rate != null && turn?.rate != null ? `Turnover ran ${Math.round((1 - turn.rate / strat.rate) * 100)}% below summer.` : null} />
        <p className="muted small" style={{ margin: 0 }}>Conditions for each outing come from the Army Corps dam-site profiles ({r.profiles.length} so far, latest {last ? formatDateShort(last.date, true) : "–"}), blended between the checks before and after during summer layering, else the nearest check within 10 days. Hours = each session's first lure in to last lure out. Marked depth = the fish depth you logged (not when the boat was stored). Faded bars rest on fewer than 4 outings. One season so far — patterns firm up as more years come in.</p>
      </>}
    </div>
  </section>;
}
