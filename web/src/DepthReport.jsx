// Reports → Fish depth (John 11-20): where fish were marked, and how that went, by depth band, month, water temp and
// lake phase, with the oxygen floor at the spots fished. Engine: lib/fishdepth.js — the same history sets the depth
// the lure advice aims for when no fish depth is entered.
import { useMemo } from "react";
import { expectedDepth, fishDepth } from "./lib/fishdepth.js";
import { windowFor } from "./lib/reportspec.js";
import { lakeToday } from "./lib/weather.js";
import { useLakeCtx, useTodayLake } from "./WhereReport.jsx";

function Table({ rows, first }) {
  return <div className="scroll"><table className="tbl"><thead><tr><th>{first}</th><th>Outings</th><th>Marked</th><th>Best depth</th><th>O₂ floor</th></tr></thead>
    <tbody>{rows.map((m) => <tr key={m.key}><td>{m.label}</td><td className="num">{m.outings}</td><td className="num">{m.median != null ? `${m.median} ft` : "–"}</td>
      <td>{m.best ? `${m.best.label} (${m.best.rate.toFixed(1)}/hr)` : <span className="muted">too few</span>}</td><td className="num">{m.floor != null ? `~${Math.round(m.floor)} ft` : "–"}</td></tr>)}</tbody></table></div>;
}

export default function DepthReport({ trips, spots, waterLog, weather, f, me, setScreen }) {
  const ctx = useLakeCtx(waterLog), now = useTodayLake(ctx, weather);
  const win = windowFor({}, f.period), owner = f.who === "me" ? me.email : null;
  const r = useMemo(() => (ctx && spots ? fishDepth(trips, ctx, { from: win.from, to: win.to, owner, spots }) : null), [ctx, spots, trips, win.from, win.to, owner]);
  const exp = useMemo(() => (ctx && now ? expectedDepth(trips, ctx, { date: lakeToday(), tempF: now.temp, phase: now.phase }, { owner }) : null), [ctx, now, trips, owner]);
  if (!r) return <section className="card"><div className="card-b"><p className="muted">Loading…</p></div></section>;
  const max = Math.max(0, ...r.byBand.map((b) => b.rate || 0));
  const eights = (trips || []).filter((t) => { try { const c = typeof t.conditions === "string" ? JSON.parse(t.conditions) : t.conditions; return Number(c?.fish_depth_ft) === 8; } catch { return false; } }).length;
  return <section className="card">
    <div className="card-h"><span className="t">Fish depth</span><span className="muted small">{r.marked} outings with a marked depth</span></div>
    <div className="card-b setup" style={{ paddingTop: 10 }}>
      {f.period !== "all" && <p className="note-bar">Showing {f.period === "year" ? "this year" : `the last ${f.period} days`}. <button className="link" onClick={() => setScreen({ period: "all" })}>Show all our history ›</button></p>}
      {!r.marked ? <p className="empty">No outings with a marked fish depth in this period.</p> : <>
        <p style={{ margin: 0 }}><b>{exp ? `For a lake like today's: fish marked around ${exp.depth_ft} ft on good outings` : "Not enough similar outings yet to say where fish sit in a lake like today's"}</b>
          {exp && <span className="muted small"> ({exp.n} similar outings). The lure plans aim here when no fish depth is entered.</span>}</p>
        <div className="lr-h">Catch rate by marked depth</div>
        <div className="rp-bars">{r.byBand.map((b) => (
          <div key={b.key} className={`rp-bar ${b.outings && b.outings < 4 ? "thin" : ""}`}>
            <span className="rp-lbl">{b.label}</span>
            <span className="rp-track"><span style={{ width: `${max > 0 && b.rate ? Math.max(2, (b.rate / max) * 100) : 0}%` }} /></span>
            <span className="rp-val"><b className="num">{b.rate != null ? `${b.rate.toFixed(2)}/hr` : "–"}</b><span className="muted small block">{b.outings} outing{b.outings === 1 ? "" : "s"}</span></span>
          </div>))}</div>
        <div className="lr-h">By month</div><Table rows={r.byMonth} first="Month" />
        <div className="lr-h">By water temperature</div><Table rows={r.byTemp} first="Water" />
        <div className="lr-h">By lake phase</div><Table rows={r.byPhase} first="Lake" />
        <p className="muted small" style={{ margin: 0 }}>Marked = the typical fish depth you logged (median). Best depth = the 3-ft band with the most fish per hour, among bands with 3+ outings. O₂ floor = where the Army Corps found oxygen dropping under 5 mg/L, scaled to the spots you fished (summer layering only). Readings with the boat stored are left out.{eights > 20 ? ` Note: ${eights} logged rows say exactly 8 ft — 8 ft was the form's starting value, so some of those are real readings and some are the default left in place (the old app didn't record which). Untouched defaults are ignored from now on.` : ""}</p>
      </>}
    </div>
  </section>;
}
