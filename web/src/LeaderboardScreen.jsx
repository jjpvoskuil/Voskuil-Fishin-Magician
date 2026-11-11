// Leaderboard = "The Stringer" (old pages/8_Leaderboard.py): a ring of season stats you swipe through, six ranked
// tabs (Biggest Fish, Top Anglers, Hot Lures, Top Spots, Longest Fish, Top Sessions), daily catch bars and the
// species mix. Logic in lib/stringer.js (parity-tested port of core/stringer.py). New here: a period choice
// (This year / Last 30 days / All time) and Everyone / Just me, both remembered on the phone.
import { useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { buildFrames, CATEGORIES, dailyActivitySeries, formatDateShort, heroStates, seasonLabel, speciesMix } from "./lib/stringer.js";

const KEY = "fm.leaderboard";
const PERIODS = [["year", "This year"], ["30", "Last 30 days"], ["all", "All time"]];
const read = () => { try { return { period: "year", who: "all", tab: "biggest", ...JSON.parse(localStorage.getItem(KEY)) }; } catch { return { period: "year", who: "all", tab: "biggest" }; } };
const lakeToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
const minusDays = (d, n) => new Date(Date.parse(`${d}T12:00:00Z`) - n * 864e5).toISOString().slice(0, 10);

function Ring({ value, total, size = 132 }) {
  const pct = total > 0 ? Math.max(0, Math.min(100, (value / total) * 100)) : 0;
  return (
    <div className="ring" style={{ width: size, height: size, background: `conic-gradient(var(--accent) 0 ${pct}%, var(--accent-track) ${pct}% 100%)` }}
      role="img" aria-label={`${value} of ${total}`}>
      <div className="ring-in" style={{ width: size - 20, height: size - 20 }}>
        <span className="num" style={{ fontSize: 34, lineHeight: 1 }}>{Math.round(pct)}<small style={{ fontSize: 16 }}>%</small></span>
        <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>{value} of {total}</span>
      </div>
    </div>
  );
}

function Bars({ days }) {
  const max = Math.max(0, ...days.map(([, c]) => c));
  if (!max) return <p className="muted small" style={{ margin: 0 }}>No catches logged in this period.</p>;
  const W = 400, H = 110, slot = W / days.length, w = Math.max(slot - 1.2, 0.6);
  let peak = 0; days.forEach(([, c], i) => { if (c > days[peak][1]) peak = i; });
  return <>
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 110, display: "block" }} role="img"
      aria-label={`Fish per day; best day ${formatDateShort(days[peak][0])} with ${days[peak][1]}`}>
      {days.map(([d, c], i) => { const h = c ? Math.max((c / max) * (H - 4), 1.5) : 0.8; return (
        <rect key={d} x={i * slot} y={H - h} width={w} height={h} rx="0.6" fill={i === peak ? "var(--accent)" : "var(--muted)"} opacity={i === peak ? 1 : 0.45} />); })}
    </svg>
    <div className="lb-axis muted small"><span>{formatDateShort(days[0][0])}</span><span>Best day: {formatDateShort(days[peak][0])} · {days[peak][1]} fish</span><span>{formatDateShort(days[days.length - 1][0])}</span></div>
  </>;
}

export default function LeaderboardScreen({ active, me, trips, spots, onBack, onMenu, demo }) {
  const [f, setFState] = useState(read);
  const setF = (p) => setFState((x) => { const n = { ...x, ...p }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  const [ring, setRing] = useState(0);
  const touch = useRef(null);

  const names = useMemo(() => Object.fromEntries((spots || []).map((s) => [s.spot_id, s.name])), [spots]);
  const rows = useMemo(() => {
    const today = lakeToday(), from = f.period === "year" ? `${today.slice(0, 4)}-01-01` : f.period === "30" ? minusDays(today, 29) : "";
    return (trips || []).filter((r) => (!from || String(r.trip_date) >= from) && (f.who === "all" || r.owner === me.email));
  }, [trips, f.period, f.who, me]);
  const { fish, trips: tr } = useMemo(() => buildFrames(rows, names), [rows, names]);
  const states = useMemo(() => heroStates(fish, tr, true), [fish, tr]);
  const cat = CATEGORIES.find(([k]) => k === f.tab) || CATEGORIES[0];
  const list = useMemo(() => cat[3](fish, tr), [cat, fish, tr]);
  const days = useMemo(() => { const d = tr.map((t) => t.date).filter(Boolean).sort(); return d.length ? dailyActivitySeries(fish, d[0], d[d.length - 1]) : []; }, [fish, tr]);
  const mix = useMemo(() => speciesMix(fish), [fish]);

  if (!active) return null;
  const i = states.length ? ((ring % states.length) + states.length) % states.length : 0, s = states[i];
  const step = (d) => setRing(i + d);
  const label = seasonLabel(tr, true);
  return (
    <div className="screen" id="screen-leaderboard">
      <Head kicker={`More · ${label || PERIODS.find(([k]) => k === f.period)[1]}`} title="Leaderboard" onMenu={onMenu} demo={demo}>
        <button className="iconbtn" aria-label="Back to More" onClick={onBack}><Icon name="back" size={20} /></button>
      </Head>
      <div className="body">
        <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
          <div className="seg">{PERIODS.map(([k, l]) => <button key={k} className={f.period === k ? "on" : ""} onClick={() => { setF({ period: k }); setRing(0); }}>{l}</button>)}</div>
          <div className="seg">{[["all", "Everyone"], ["me", "Just me"]].map(([k, l]) => <button key={k} className={f.who === k ? "on" : ""} onClick={() => { setF({ who: k }); setRing(0); }}>{l}</button>)}</div>
        </div></section>

        {trips === null ? <p className="muted">Loading the trip log…</p> : !tr.length ? <p className="note-bar">No trips in this period yet{f.who === "me" ? " for you" : ""}.</p> : <>
          {s && <section className="card lb-hero" onTouchStart={(e) => { touch.current = e.touches[0].clientX; }}
            onTouchEnd={(e) => { const dx = e.changedTouches[0].clientX - (touch.current ?? e.changedTouches[0].clientX); if (Math.abs(dx) > 45) step(dx < 0 ? 1 : -1); touch.current = null; }}>
            <div className="lb-hero-h">
              <button className="iconbtn" aria-label="Previous stat" onClick={() => step(-1)} disabled={states.length < 2}>‹</button>
              <h2>{s.title}</h2>
              <button className="iconbtn" aria-label="Next stat" onClick={() => step(1)} disabled={states.length < 2}>›</button>
            </div>
            <div className="lb-hero-b">
              <Ring value={s.value} total={s.total} />
              <div className="grow">
                <div className="muted small b">{s.legend}</div>
                <p style={{ margin: "4px 0 10px" }}>{s.desc}</p>
                <div className="muted small b">{s.sec_label}</div>
                <div className="num" style={{ fontSize: 22 }}>{s.sec_value}</div>
              </div>
            </div>
            {states.length > 1 && <div className="lb-dots">{states.map((_, k) => <button key={k} className={k === i ? "on" : ""} aria-label={`Show stat ${k + 1}`} onClick={() => setRing(k)} />)}</div>}
          </section>}

          <div className="lb-tabs" role="tablist">{CATEGORIES.map(([k, l]) => <button key={k} role="tab" aria-selected={f.tab === k} className={f.tab === k ? "on" : ""} onClick={() => setF({ tab: k })}>{l}</button>)}</div>
          <section className="card">
            <div className="card-h"><span className="t">{cat[1]}</span><span className="muted small">{cat[2]}</span></div>
            {!list.length ? <p className="empty">Nothing for this one yet.</p> : list.map((r0, n) => {
              // Biggest Fish repeats the weight as its title — show the species there instead
              const parts = r0.secondary.split(" · "), r = r0.primary === r0.num && parts.length > 1 ? { ...r0, primary: parts[0], secondary: parts.slice(1).join(" · ") } : r0;
              return (
              <div key={n} className="lb-row">
                <span className={`lb-rank ${n === 0 ? "r1" : ""}`}>{n + 1}</span>
                <span className="grow"><b>{r.primary}</b><span className="muted small block">{r.secondary}</span></span>
                <span className="lb-num"><b className="num">{r.num}</b>{r.tag && <span className="pill">{r.tag}</span>}</span>
              </div>); })}
          </section>

          <section className="card">
            <div className="card-h"><span className="t">Catches by day</span></div>
            <div className="card-b"><Bars days={days} /></div>
          </section>
          {mix.length > 0 && <section className="card">
            <div className="card-h"><span className="t">Species mix</span></div>
            <div className="card-b">{mix.map(([name, c]) => (
              <div key={name} className="lb-sp"><span className="lb-sp-n">{name}</span>
                <span className="lb-sp-bar"><span style={{ width: `${(c / mix[0][1]) * 100}%` }} className={c === mix[0][1] ? "top" : ""} /></span>
                <b className="num">{c}</b></div>))}</div>
          </section>}
        </>}
      </div>
    </div>
  );
}
