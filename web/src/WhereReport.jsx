// Reports → Where to fish (John 11-20): spots and spot types ranked by fish/hr in a lake condition — "Like today"
// (same lake phase, water within ±6 °F), a phase, and/or a water-temp band. Engine: lib/wheretofish.js.
import { useMemo, useState } from "react";
import { lakeContext, PHASE_LABEL, TEMP_BANDS, todayLake } from "./lib/lakectx.js";
import { likeLabel, whereToFish } from "./lib/wheretofish.js";
import { windowFor } from "./lib/reportspec.js";
import { estimateWaterTempF, lakeToday } from "./lib/weather.js";

const KEY = "fm.whereReport";
const read = () => { try { return { cond: "like", band: "", ...JSON.parse(localStorage.getItem(KEY)) }; } catch { return { cond: "like", band: "" }; } };

export function useLakeCtx(waterLog) { return useMemo(() => (waterLog ? lakeContext(waterLog) : null), [waterLog]); }
export function useTodayLake(ctx, weather) {
  const today = lakeToday();
  return useMemo(() => { if (!ctx) return null; let est = null; try { est = weather?.value ? estimateWaterTempF(weather.value, today) : null; } catch { est = null; } return todayLake(ctx, today, est); }, [ctx, weather?.value, today]);
}

function Bars({ rows, sub }) {
  const max = Math.max(0, ...rows.map((b) => b.rate || 0));
  return <div className="rp-bars">{rows.map((b) => (
    <div key={b.key} className={`rp-bar ${b.hours < 3 ? "thin" : ""}`}>
      <span className="rp-lbl">{b.name || b.key}{b.type && <span className="muted small block">{b.type}</span>}</span>
      <span className="rp-track"><span style={{ width: `${max > 0 ? Math.max(2, (b.rate / max) * 100) : 0}%` }} /></span>
      <span className="rp-val"><b className="num">{b.rate.toFixed(2)}/hr</b><span className="muted small block">{sub(b)}</span></span>
    </div>))}</div>;
}

export default function WhereReport({ trips, spots, waterLog, weather, f, me, setScreen }) {
  const [o, setO] = useState(read);
  const set = (p) => setO((x) => { const n = { ...x, ...p }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  const ctx = useLakeCtx(waterLog), now = useTodayLake(ctx, weather);
  const win = windowFor({}, f.period), owner = f.who === "me" ? me.email : null;
  const cond = o.cond === "like" ? { like: now } : { phase: o.cond === "any" ? null : o.cond, band: o.band || null };
  const r = useMemo(() => (ctx && spots && (o.cond !== "like" || now) ? whereToFish(trips, spots, ctx, { cond, from: win.from, to: win.to, owner }) : null),
    [ctx, spots, trips, o.cond, o.band, now, win.from, win.to, owner]);
  if (!r) return <section className="card"><div className="card-b"><p className="muted">Loading spots and lake conditions…</p></div></section>;
  const condText = o.cond === "like" ? `a lake like today's (${likeLabel(now).replace(" °F water", "\u00a0°F")})` : [o.cond === "any" ? "any lake condition" : PHASE_LABEL[o.cond].toLowerCase(), o.band].filter(Boolean).join(", ");
  const top = r.spots.find((s) => s.hours >= 3);
  const sub = (b) => `${b.outings} outing${b.outings === 1 ? "" : "s"} · ${b.hours.toFixed(1)} h · ${b.fish} fish`;
  return <section className="card">
    <div className="card-h"><span className="t">Where to fish</span><span className="muted small">{r.n} outings</span></div>
    <div className="card-b setup" style={{ paddingTop: 10 }}>
      {f.period !== "all" && <p className="note-bar">Showing {f.period === "year" ? "this year" : `the last ${f.period} days`}. <button className="link" onClick={() => setScreen({ period: "all" })}>Show all our history ›</button></p>}
      <div className="chips">{[["like", "Like today"], ["any", "Any"], ["stratified", PHASE_LABEL.stratified], ["turnover", PHASE_LABEL.turnover], ["mixed", PHASE_LABEL.mixed]].map(([k, l]) =>
        <button key={k} className={`chip ${o.cond === k ? "on" : ""}`} onClick={() => set({ cond: k })}>{l}</button>)}</div>
      {o.cond !== "like" && <div className="chips">{[["", "Any water temp"], ...TEMP_BANDS.map((b) => [b[2], b[2]])].map(([k, l]) =>
        <button key={k || "any"} className={`chip ${o.band === k ? "on" : ""}`} onClick={() => set({ band: k })}>{l}</button>)}</div>}
      {!r.n ? <p className="empty">No outings in {condText} yet{o.cond === "like" ? " — try Any, or a lake phase" : ""}.</p> : <>
        <p style={{ margin: 0 }}><b>{top ? `In ${condText}, best so far: ${top.name}, ${top.rate.toFixed(1)} fish/hr` : `Not enough hours at any one spot in ${condText} yet`}</b>
          <span className="muted small"> (average for these conditions {r.base.toFixed(1)}/hr)</span></p>
        <div className="lr-h">Spots</div>
        <Bars rows={r.spots} sub={sub} />
        <div className="lr-h">Kinds of spot</div>
        <Bars rows={r.types} sub={sub} />
        {r.untried.length > 0 && <p className="note-bar">Hardly tried in these conditions (under 3 outings): {r.untried.join(", ")}. The ⭐ spots to try on the Lake Map include these kinds of places.</p>}
        <p className="muted small" style={{ margin: 0 }}>Fish per angler-hour, pulled toward the average for these conditions until a spot has a few hours (so one lucky stint doesn't top the list). Lake phase comes from the Army Corps oxygen profiles; water temp = what you logged with the boat's electronics, else the Corps surface reading. "Like today" = the same lake phase and water within 6 °F of today's. The Lake Map's 🔥 Hot spots has the same "Like today's lake" filter.</p>
      </>}
    </div>
  </section>;
}
