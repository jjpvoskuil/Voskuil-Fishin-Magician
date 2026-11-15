// Reports → Forecast vs catch (#99 Matthew 11-14; John 11-15: the day's forecast score vs fish/hr over ALL our history).
// Score source: "Re-scored" = every day fished scored again with today's engine from archived weather (lib/rescore.js;
// default = the untuned engine, a fair test; "tuned" = today's weights, which learned from these same catches) or
// "Saved" = the score stored on the trip rows when they were logged (older engine versions; older days have none).
// Views: Over time (fish/hr bars + score line, day by day) and Score vs catch (scatter + bands + correlation).
import { useEffect, useMemo, useRef, useState } from "react";
import { calibrateWeights } from "./lib/calibration.js";
import { rescoreDays } from "./lib/rescore.js";
import { describeR, fishedDates, scoreCheck } from "./lib/scorecheck.js";
import { windowFor } from "./lib/reportspec.js";
import { formatDateShort } from "./lib/stringer.js";

const KEY = "fm.scoreCheck";
const DEF = { show: "rate", source: "re", tuned: false, view: "time" };
const read = () => { try { return { ...DEF, ...JSON.parse(localStorage.getItem(KEY)) }; } catch { return DEF; } };
const lakeToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function Seg({ value, options, onChange }) {
  return <div className="seg">{options.map(([k, l]) => <button key={String(k)} className={value === k ? "on" : ""} onClick={() => onChange(k)}>{l}</button>)}</div>;
}

/** Day-by-day: bars = fish/hr (or fish), line = score 0–10. Scrolls sideways when there are many days. */
function OverTime({ days, show }) {
  const ref = useRef(null);
  const val = (d) => (show === "rate" ? d.rate : d.fish);
  const vmax = Math.max(1, ...days.map((d) => val(d) ?? 0));
  const step = 12, P = 30, R = 26, H = 190, top = 12, bot = 34, W = Math.max(330, P + R + days.length * step);
  const X = (i) => P + i * step + step / 2, Yv = (v) => H - bot - (v / vmax) * (H - top - bot), Ys = (s) => H - bot - (Math.max(0, Math.min(10, s)) / 10) * (H - top - bot);
  useEffect(() => { if (ref.current) ref.current.scrollLeft = ref.current.scrollWidth; }, [days.length]);
  let prevM = "";
  const line = days.map((d, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Ys(d.score).toFixed(1)}`).join(" ");
  return <div className="ot-wrap" ref={ref}>
    <svg className="sc-plot ot" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Each day fished in order: catch as bars, forecast score as a line">
      {[0, 0.5, 1].map((t) => <line key={t} x1={P} x2={W - R} y1={Yv(vmax * t)} y2={Yv(vmax * t)} className="ax" opacity={t ? 0.5 : 1} />)}
      <text x={P - 4} y={Yv(vmax) + 4} className="tk" textAnchor="end">{show === "rate" ? vmax.toFixed(1) : Math.round(vmax)}</text>
      <text x={P - 4} y={Yv(0) + 3} className="tk" textAnchor="end">0</text>
      <text x={W - R + 4} y={Ys(10) + 4} className="tk sc-s">10</text><text x={W - R + 4} y={Ys(5) + 4} className="tk sc-s">5</text><text x={W - R + 4} y={Ys(0) + 3} className="tk sc-s">0</text>
      {days.map((d, i) => { const v = val(d); return v == null
        ? <rect key={d.date} x={X(i) - 3.5} y={Yv(0) - 2} width="7" height="2" className="ot-none"><title>{`${d.date}: ${d.fish} fish, no hours logged`}</title></rect>
        : <rect key={d.date} x={X(i) - 3.5} y={Yv(v)} width="7" height={Math.max(1, Yv(0) - Yv(v))} rx="1.5" className="ot-bar">
            <title>{`${d.date}: score ${d.score.toFixed(1)} · ${d.fish} fish${d.rate != null ? ` · ${d.rate.toFixed(2)}/hr` : ""}`}</title></rect>; })}
      <path d={line} className="ot-line" />
      {days.map((d, i) => <circle key={d.date} cx={X(i)} cy={Ys(d.score)} r="2.6" className="ot-dot" />)}
      {days.map((d, i) => { const m = d.date.slice(0, 7); if (m === prevM) return null; const yr = !prevM || prevM.slice(0, 4) !== m.slice(0, 4); prevM = m;
        return <g key={m}><line x1={X(i) - step / 2} x2={X(i) - step / 2} y1={H - bot} y2={H - bot + 5} className="ax" />
          <text x={X(i) - step / 2 + 2} y={H - bot + 15} className="tk">{MON[+m.slice(5) - 1]}</text>
          {yr && <text x={X(i) - step / 2 + 2} y={H - bot + 27} className="tk" fontWeight="700">{m.slice(0, 4)}</text>}</g>; })}
    </svg>
  </div>;
}

function Scatter({ days, show }) {
  const pts = days.map((d) => ({ x: d.score, y: show === "rate" ? d.rate : d.fish, d })).filter((p) => p.y != null);
  const ymax = Math.max(1, ...pts.map((p) => p.y)), W = 320, H = 150, P = 26;
  const X = (x) => P + (Math.max(0, Math.min(10, x)) / 10) * (W - P - 8), Y = (y) => H - 18 - (y / ymax) * (H - 30);
  return <svg className="sc-plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Each day fished: forecast score across, catch up">
    <line x1={P} y1={H - 18} x2={W - 8} y2={H - 18} className="ax" /><line x1={P} y1={8} x2={P} y2={H - 18} className="ax" />
    {[0, 2, 4, 6, 8, 10].map((t) => <text key={t} x={X(t)} y={H - 4} className="tk" textAnchor="middle">{t}</text>)}
    <text x={P - 4} y={Y(ymax) + 4} className="tk" textAnchor="end">{show === "rate" ? ymax.toFixed(1) : Math.round(ymax)}</text>
    <text x={P - 4} y={H - 18} className="tk" textAnchor="end">0</text>
    {pts.map((p) => <circle key={p.d.date} cx={X(p.x)} cy={Y(p.y)} r="4.5" className="dot"><title>{`${p.d.date}: score ${p.x.toFixed(1)}, ${p.d.fish} fish${p.d.rate != null ? `, ${p.d.rate.toFixed(2)}/hr` : ""}`}</title></circle>)}
  </svg>;
}

export default function ScoreCheck({ trips, f, me, setScreen }) {
  const [o, setO] = useState(read);
  const set = (p) => setO((x) => { const n = { ...x, ...p }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  const win = windowFor({}, f.period), owner = f.who === "me" ? me.email : null;
  const dates = useMemo(() => fishedDates(trips, { from: win.from, to: win.to, owner }), [trips, win.from, win.to, owner]);
  const weights = useMemo(() => calibrateWeights(trips || []), [trips]);
  const [re, setRe] = useState({ state: "idle" });   // {state: idle|loading|done, scores, missing, failed}
  const key = dates.join(",");
  useEffect(() => {
    if (o.source !== "re" || !dates.length) return;
    let live = true; setRe((r) => ({ ...r, state: "loading" }));
    rescoreDays(dates, weights, { today: lakeToday() }).then((out) => live && setRe({ state: "done", ...out }))
      .catch((e) => live && setRe({ state: "done", scores: {}, missing: dates, failed: 1, error: e.message }));
    return () => { live = false; };
  }, [o.source, key, weights]);
  const dayScore = useMemo(() => (o.source === "re" && re.scores ? Object.fromEntries(Object.entries(re.scores).map(([d, s]) => [d, o.tuned ? s.tuned : s.base])) : null), [o.source, o.tuned, re.scores]);
  const out = useMemo(() => (o.source === "re" && !dayScore ? null : scoreCheck(trips, { from: win.from, to: win.to, owner, dayScore })), [trips, win.from, win.to, owner, dayScore, o.source]);

  const r = out && (o.show === "rate" ? out.rRate : out.rFish);
  const rows = out ? out.bands.map((b) => ({ key: b.key, label: b.label, n: o.show === "rate" ? (b.rate == null ? 0 : b.days) : b.days, value: o.show === "rate" ? b.rate ?? 0 : b.fishPerDay })) : [];
  const max = Math.max(0, ...rows.map((x) => x.value));
  const span = out?.days.length ? `${formatDateShort(out.days[0].date, true)} – ${formatDateShort(out.days[out.days.length - 1].date, true)}` : "";
  return <section className="card">
    <div className="card-h"><span className="t">Forecast score vs fish caught</span><span className="muted small">{out ? `${out.days.length} of ${dates.length} days fished` : `${dates.length} days fished`}</span></div>
    <div className="card-b setup" style={{ paddingTop: 10 }}>
      {f.period !== "all" && <p className="note-bar">Showing {f.period === "year" ? "this year" : `the last ${f.period} days`}. <button className="link" onClick={() => setScreen({ period: "all" })}>Show all our history ›</button></p>}
      <Seg value={o.view} options={[["time", "Over time"], ["scatter", "Score vs catch"]]} onChange={(v) => set({ view: v })} />
      <Seg value={o.show} options={[["rate", "Fish per hour"], ["day", "Fish per day"]]} onChange={(v) => set({ show: v })} />
      <div className="field">Score<Seg value={o.source === "saved" ? "saved" : o.tuned ? "tuned" : "re"} options={[["re", "Today's engine"], ["tuned", "Tuned"], ["saved", "Saved when logged"]]}
        onChange={(v) => set(v === "saved" ? { source: "saved" } : { source: "re", tuned: v === "tuned" })} /></div>
      {o.source === "re" && re.state === "loading" && <p className="muted">Getting the weather for {dates.length} days fished and scoring them…</p>}
      {o.source === "re" && re.state === "done" && (() => {
        const today = lakeToday(), fresh = (re.missing || []).filter((d) => d >= today).length, old = (re.missing || []).length - fresh;
        const txt = re.failed > 0 ? `Couldn't reach the weather archive for part of the history (${re.missing.length} day${re.missing.length === 1 ? "" : "s"} left out) — try again later.`
          : [old > 0 && `${old} day${old === 1 ? "" : "s"} had no archived weather and ${old === 1 ? "is" : "are"} left out.`, fresh > 0 && "Today's fishing joins the chart tomorrow, once the weather archive has today."].filter(Boolean).join(" ");
        return txt ? <p className="note-bar">{txt}</p> : null; })()}
      {!dates.length ? <p className="empty">No days fished in this period.</p> : !out ? null : !out.days.length ? <p className="empty">No days with a forecast score in this period yet.</p> : <>
        <p style={{ margin: 0 }}><b>{describeR(r)}</b>{r != null && <span className="muted small"> (correlation {r >= 0 ? "+" : ""}{r.toFixed(2)} over {o.show === "rate" ? out.rateDays : out.days.length} days; ±1 = perfect, 0 = none)</span>}</p>
        {o.view === "time" ? <>
          <OverTime days={out.days} show={o.show} />
          <p className="muted small" style={{ margin: 0 }}><span className="key-bar" /> {o.show === "rate" ? "fish per angler-hour" : "fish that day"} (left scale) · <span className="key-line" /> forecast score (right, 0–10). Each step is one day fished, {span}; gaps between trips are skipped. Swipe sideways for earlier days.{o.show === "rate" ? " A flat mark = fish logged without times." : ""}</p>
        </> : <>
          <Scatter days={out.days} show={o.show} />
          <p className="muted small" style={{ margin: 0 }}>Each dot is a day fished: the forecast score across, {o.show === "rate" ? "fish per angler-hour" : "fish caught that day"} up.</p>
        </>}
        <div className="lr-h">By forecast score</div>
        <div className="rp-bars">{rows.map((b) => (
          <div key={b.key} className={`rp-bar ${b.n && b.n < 4 ? "thin" : ""}`}>
            <span className="rp-lbl">{b.label}</span>
            <span className="rp-track"><span style={{ width: `${max > 0 && b.n ? Math.max(2, (b.value / max) * 100) : 0}%` }} /></span>
            <span className="rp-val"><b className="num">{b.n ? (o.show === "rate" ? `${b.value.toFixed(2)}/hr` : b.value.toFixed(1)) : "–"}</b><span className="muted small block">{b.n} day{b.n === 1 ? "" : "s"}</span></span>
          </div>))}</div>
        <p className="muted small" style={{ margin: 0 }}>{o.source === "re"
          ? `Day score = today's scoring engine run on the archived forecast for each day fished (Open-Meteo historical forecasts; before 2022 the weather record, without rain chance). ${o.tuned ? "Tuned weights learned from these same catches, so their fit here is flattered." : "Untuned = the engine's default weights, a fair test that doesn't learn from these catches."}`
          : "Score = the forecast saved when each lure went in the water (that time of day), averaged over the day's sessions — made by whatever engine version ran then; days logged without one are left out."} Hours = each session's first lure in to last lure out. Faded bars rest on fewer than 4 days.</p>
      </>}
    </div>
  </section>;
}
