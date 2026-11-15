// My Stats (punch #105, Matthew 11-15): your whole log broken down — by lure, lure type, color, spot, structure, time
// of day, month, water temp, wind, year. Tap any row for its full stats (same drop-down as the Leaderboard, #104).
// Logic in lib/groupstats.js. Period / who / breakdown / sort are remembered on the phone (localStorage fm.myStats).
import { useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import StatDetail from "./StatDetail.jsx";
import { breakdown, DIMENSIONS, records, summarize } from "./lib/groupstats.js";

const KEY = "fm.myStats";
const PERIODS = [["year", "This year"], ["90", "Last 90 days"], ["all", "All time"]];
const SORTS = [["fish", "Fish"], ["fph", "Fish / hr"], ["success", "Success"], ["lbs", "Weight"]];
const DEF = { period: "all", who: "me", dim: "lure", sort: "fish" };
const read = () => { try { return { ...DEF, ...JSON.parse(localStorage.getItem(KEY)) }; } catch { return DEF; } };
const lakeToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
const minusDays = (d, n) => new Date(Date.parse(`${d}T12:00:00Z`) - n * 864e5).toISOString().slice(0, 10);
const SMALL = 3; // fewer uses than this = "small sample"
const sortVal = { fish: (s) => s.fish, fph: (s) => s.fishPerHour ?? -1, success: (s) => s.successRate ?? -1, lbs: (s) => s.lbs };

export default function MyStatsScreen({ active, me, trips, spots, onBack, onMenu, demo }) {
  const [f, setFState] = useState(read);
  const setF = (p) => setFState((x) => { const n = { ...x, ...p }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  const [open, setOpen] = useState(null);
  const names = useMemo(() => Object.fromEntries((spots || []).map((s) => [s.spot_id, s.name])), [spots]);
  const recs = useMemo(() => {
    const today = lakeToday(), from = f.period === "year" ? `${today.slice(0, 4)}-01-01` : f.period === "90" ? minusDays(today, 89) : "";
    const rows = (trips || []).filter((r) => (!from || String(r.trip_date) >= from) && (f.who === "all" || (r.owner || "").toLowerCase() === (me?.email || "").toLowerCase()));
    return records(rows, names);
  }, [trips, f.period, f.who, me, names]);
  const all = useMemo(() => summarize(recs), [recs]);
  const days = useMemo(() => new Set(recs.map((x) => x.date).filter(Boolean)).size, [recs]);
  const list = useMemo(() => {
    const l = breakdown(recs, f.dim), ordered = ["month", "temp", "year"].includes(f.dim);
    return ordered && f.sort === "fish" ? l : [...l].sort((a, b) => sortVal[f.sort](b.stats) - sortVal[f.sort](a.stats) || b.stats.fish - a.stats.fish);
  }, [recs, f.dim, f.sort]);
  const dimLabel = DIMENSIONS.find(([k]) => k === f.dim)?.[1] || "";

  if (!active) return null;
  const who = f.who === "me" ? (me?.name || "You") : "Everyone";
  return (
    <div className="screen" id="screen-mystats">
      <Head kicker={`More · ${who}`} title="My Stats" onMenu={onMenu} demo={demo}>
        <button className="iconbtn" aria-label="Back to More" onClick={onBack}><Icon name="back" size={20} /></button>
      </Head>
      <div className="body">
        <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
          <div className="seg">{PERIODS.map(([k, l]) => <button key={k} className={f.period === k ? "on" : ""} onClick={() => { setF({ period: k }); setOpen(null); }}>{l}</button>)}</div>
          <div className="seg">{[["me", "Just me"], ["all", "Everyone"]].map(([k, l]) => <button key={k} className={f.who === k ? "on" : ""} onClick={() => { setF({ who: k }); setOpen(null); }}>{l}</button>)}</div>
        </div></section>

        {!recs.length ? <p className="note-bar">No trips logged {f.who === "me" ? "by you " : ""}in this period yet.</p> : <>
          <section className="card">
            <div className="card-h"><span className="t">Overall</span><span className="muted small">{all.uses} outing{all.uses === 1 ? "" : "s"} · {days} day{days === 1 ? "" : "s"}</span></div>
            <StatDetail stats={all} />
          </section>

          <section className="card">
            <div className="card-h"><span className="t">Break down by</span></div>
            <div className="card-b" style={{ paddingBottom: 6 }}>
              <div className="chips">{DIMENSIONS.map(([k, l]) => <button key={k} className={`chip ${f.dim === k ? "on" : ""}`} onClick={() => { setF({ dim: k }); setOpen(null); }}>{l}</button>)}</div>
              <div className="ms-sort"><span className="muted small">Sort</span>
                <div className="seg">{SORTS.map(([k, l]) => <button key={k} className={f.sort === k ? "on" : ""} onClick={() => { setF({ sort: k }); setOpen(null); }}>{l}</button>)}</div></div>
            </div>
          </section>

          <section className="card">
            <div className="card-h"><span className="t">By {dimLabel.toLowerCase()}</span><span className="muted small">tap one for its stats</span></div>
            {!list.length ? <p className="empty">Nothing logged for {dimLabel.toLowerCase()} in this period.</p> : list.map((g, n) => {
              const s = g.stats, on = open === g.key, pct = s.successRate == null ? null : `${Math.round(s.successRate * 100)}% with fish`;
              const num = f.sort === "fph" ? (s.fishPerHour == null ? "–" : `${s.fishPerHour.toFixed(2)} / hr`) : f.sort === "success" ? (pct ? `${Math.round(s.successRate * 100)}%` : "–")
                : f.sort === "lbs" ? (s.lbs > 0 ? `${s.lbs.toFixed(1)} lb` : "–") : `${s.fish} fish`;
              return <div key={g.key} className={`lb-item ${on ? "on" : ""}`}>
                <button className="lb-row lb-tap" aria-expanded={on} onClick={() => setOpen(on ? null : g.key)}>
                  <span className={`lb-rank ${n === 0 ? "r1" : ""}`}>{n + 1}</span>
                  <span className="grow"><b>{g.label}</b><span className="muted small block">{[f.sort !== "fish" && `${s.fish} fish`, `${s.uses} use${s.uses === 1 ? "" : "s"}`, f.sort !== "success" && pct, f.sort !== "fph" && s.fishPerHour != null && `${s.fishPerHour.toFixed(2)}/hr`].filter(Boolean).join(" · ")}</span></span>
                  <span className="lb-num"><b className="num">{num}</b>{s.uses < SMALL && <span className="pill">small sample</span>}</span>
                  <span className="lb-chev" aria-hidden="true">›</span>
                </button>
                {on && <StatDetail stats={s} />}
              </div>;
            })}
          </section>
          <p className="muted small" style={{ margin: "0 4px" }}>A "use" is one outing it was fished in; success rate is the share of those outings with at least one fish. Fish / hr counts fishless time; stints under 30 min count as 30 min. Water temps from the boat-stored period (estimates) are left out of the water-temp breakdown.</p>
        </>}
      </div>
    </div>
  );
}
