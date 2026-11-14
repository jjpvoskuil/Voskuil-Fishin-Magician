// Reports (old pages/9_Reports.py): any factor × any metric as a bar chart + table + Excel, stock reports, a typed
// custom report (fm-board-ask, mode "report" — Claude only picks the settings), saved reports (fm_saved, kind
// "report", yours only) and the two "predict a day" history lookups (moon the night before, forecast pressure trend).
// Engine = lib/reports.js (parity-tested port of core/reports.py); settings = lib/reportspec.js.
import { useEffect, useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { Multi, Pick } from "./ui.jsx";
import { newId } from "./lib/db.js";
import { choicesFrom } from "./lib/boards.js";
import { FACTORS, METRICS, predictByMoon, predictByPressure, SECCHI_BUCKET, SPECIES_METRICS, WATER_TEMP_BUCKET } from "./lib/reports.js";
import { cleanReportSpec, describeReport, fmtValue, metricName, runReport, STOCK, windowFor } from "./lib/reportspec.js";
import { describeR, scoreCheck } from "./lib/scorecheck.js";
import { SEGMENTS } from "./lib/scoring.js";

const KEY = "fm.reports";
const PERIODS = [["year", "This year"], ["90", "90 days"], ["30", "30 days"], ["all", "All time"]];
const read = () => { try { return { period: "year", who: "all", tab: "segment", ...JSON.parse(localStorage.getItem(KEY)) }; } catch { return { period: "year", who: "all", tab: "segment" }; } };
const lakeToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" });
const plus = (d, n) => new Date(Date.parse(`${d}T12:00:00Z`) + n * 864e5).toISOString().slice(0, 10);
const dayName = (d, i) => (i === 0 ? "Today" : i === 1 ? "Tomorrow" : new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }));
const EXAMPLES = ["Does water temperature matter?", "Best colors in stained water", "My fish per hour by moon phase", "Biggest fish by lure type this fall"];

function Bars({ rows, metric, nWord }) {
  const max = Math.max(0, ...rows.map((r) => (r.n ? r.value : 0)));
  if (!rows.some((r) => r.n)) return <p className="empty">No trips match these settings yet — try a longer period or fewer filters.</p>;
  return <div className="rp-bars">{rows.map((r) => (
    <div key={r.key} className={`rp-bar ${r.n && r.n < 4 ? "thin" : ""}`}>
      <span className="rp-lbl">{r.label}</span>
      <span className="rp-track"><span style={{ width: `${max > 0 && r.n ? Math.max(2, (r.value / max) * 100) : 0}%` }} /></span>
      <span className="rp-val"><b className="num">{fmtValue(metric, r.value, r.n)}</b><span className="muted small block">{r.n} {r.n === 1 && nWord === "trips" ? "trip" : nWord}</span></span>
    </div>))}
    <p className="muted small" style={{ margin: "6px 0 0" }}>Faded bars rest on fewer than 4 {nWord} — don't lean on them.</p>
  </div>;
}

async function exportExcel(title, spec, result) {
  const { default: writeExcelFile } = await import("write-excel-file/browser");
  const head = (xs) => xs.map((value) => ({ value, fontWeight: "bold" }));
  const rep = [head([FACTORS.find(([k]) => k === spec.factor)?.[1] || spec.factor, metricName(spec.metric), "Sample (n)"]),
    ...result.rows.map((r) => [String(r.key), r.n ? Number(r.value.toFixed(4)) : null, r.n])];
  const cols = ["date", "angler", "spot", "lure", "lure_category", "color", "technique", "segment", "light_condition", "wind_band", "water_temp_f",
    "water_clarity", "pressure_trend_24h", "moon_illumination_pct", "fish_caught", "trustworthy_hours"];
  const { from, to } = result.win;
  const trips = result.data.trips.filter((t) => (!from || (t.date && t.date >= from)) && (!to || (t.date && t.date <= to))
    && (!spec.anglers.length || spec.anglers.includes(t.angler)) && (!spec.segments.length || spec.segments.includes(t.segment)));
  const tr = [head(cols), ...trips.map((t) => cols.map((c) => (t[c] == null ? null : typeof t[c] === "number" ? Number(t[c].toFixed(4)) : String(t[c]))))];
  const name = `${(title || "Fishin Magician report").replace(/[^\w\- ]+/g, "").trim() || "report"}.xlsx`;
  const file = writeExcelFile([{ data: rep, sheet: "Report", stickyRowsCount: 1 }, { data: tr, sheet: "Trips", stickyRowsCount: 1 }]);
  const blob = await file.toBlob(), f = new File([blob], name, { type: blob.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  if (navigator.canShare?.({ files: [f] })) { try { await navigator.share({ files: [f], title: name }); return; } catch (e) { if (e?.name === "AbortError") return; } }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 30e3);
}

function Predict({ trips, spec, weather, me, who }) {
  const today = lakeToday(), [day, setDay] = useState(plus(today, 1));
  const metric = spec.metric === "trip_count" ? "fish_per_hour" : spec.metric;
  const res = useMemo(() => {
    const r = runReport(trips, { ...spec, factor: "segment" }, { screenPeriod: "all", screenWho: who, me });  // all-time history, same filters
    const opts = { species: spec.species || null, anglers: spec.anglers, segments: spec.segments };
    return { moon: predictByMoon(r.data, day, metric, opts), pressure: weather?.value ? predictByPressure(r.data, day, weather.value, metric, opts) : null };
  }, [trips, spec, day, weather?.value, metric, me, who]);
  const line = (p, what) => (p.predicted_value == null ? `No logged trips yet with ${what}.` : `${fmtValue(metric, p.predicted_value, p.n)} historically (${p.n} ${["fish_per_hour"].includes(metric) || (metric === "total_fish" && !spec.species) ? "trips" : "fish"})${p.low_sample ? " — thin, don't lean on it" : ""}`);
  return <section className="card">
    <div className="card-h"><span className="t">🔮 Predict a day</span><span className="muted small">{metricName(metric)}</span></div>
    <div className="card-b setup" style={{ paddingTop: 10 }}>
      <div className="chips">{Array.from({ length: 7 }, (_, i) => plus(today, i)).map((d, i) => <button key={d} className={`chip ${d === day ? "on" : ""}`} onClick={() => setDay(d)}>{dayName(d, i)}</button>)}</div>
      <p style={{ margin: 0 }}><b>Moon {Math.round(res.moon.moon_illumination_pct)}% the night before</b> ({res.moon.moon_illumination_bucket}): {line(res.moon, "that much moon")}</p>
      {res.pressure && (res.pressure.forecast_available
        ? <p style={{ margin: 0 }}><b>Pressure {res.pressure.pressure_trend_band.toLowerCase()}</b> ({res.pressure.pressure_trend_24h >= 0 ? "+" : ""}{res.pressure.pressure_trend_24h.toFixed(1)} hPa/24 h forecast): {line(res.pressure, "that pressure trend")}</p>
        : <p className="muted small" style={{ margin: 0 }}>That day is past the weather forecast's reach, so there's no pressure lookup.</p>)}
      <p className="muted small" style={{ margin: 0 }}>What happened on your logged trips under the same moon / pressure trend — a history lookup, not a promise.</p>
    </div>
  </section>;
}

function Builder({ db, me, report, choices, setScreen, onSaved, onDeleted, toast, trips, f, weather }) {
  const blank = { factor: "lure_category", metric: "fish_per_hour" };
  const [spec, setSpec] = useState(() => cleanReportSpec(report?.spec || blank, choices));
  const [q, setQ] = useState(""), [asking, setAsking] = useState(false), [note, setNote] = useState(""), [title, setTitle] = useState(report?.title || "");
  useEffect(() => { setSpec(cleanReportSpec(report?.spec || blank, choices)); setTitle(report?.title || ""); setNote(""); }, [report?.id]);
  const set = (p) => setSpec((s) => cleanReportSpec({ ...s, ...p }, choices));
  const typeNames = Object.fromEntries(choices.lure_types), typeKeys = Object.fromEntries(choices.lure_types.map(([k, n]) => [n, k]));
  const ask = async (text = q) => {
    if (text.trim().length < 3) { toast("Type what you'd like to see first"); return; }
    setAsking(true); setNote("");
    try {
      const a = await db.askBoard(text.trim(), choices, lakeToday(), "report"), s = cleanReportSpec(a, choices);
      setSpec(s); setTitle(String(a.title || text).slice(0, 80)); setNote(a.note || "");
      if (s.period || s.who) setScreen({ ...(s.period && { period: s.period }), ...(s.who && { who: s.who }) });
    } catch (e) { toast(e.message); } finally { setAsking(false); }
  };
  const save = async () => {
    const t = (title || describeReport(spec, typeNames)).slice(0, 80), item = { id: report?.id || newId(), owner: me.email, title: t, spec };
    try { await db.saveSaved("report", item); toast(report ? "Report updated" : `Saved "${t}" — it's in the tabs now`); onSaved(item); } catch (e) { toast(e.message); }
  };
  const remove = async () => { try { await db.deleteSaved(report.id); toast("Report deleted"); onDeleted(); } catch (e) { toast(e.message); } };
  return <>
    <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
      <label className="field">Ask for a report
        <input type="text" value={q} enterKeyHint="go" placeholder="e.g. does water temperature matter?" onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); ask(); } }} /></label>
      <button className="btn primary" disabled={asking} onClick={() => ask()}>{asking ? "Reading your request…" : "Ask"}</button>
      {!report && !q && <div className="chips">{EXAMPLES.map((x) => <button key={x} className="chip" onClick={() => { setQ(x); ask(x); }}>{x}</button>)}</div>}
      {note && <p className="note-bar">{note}</p>}
    </div></section>
    <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
      <div className="two">
        <label className="field">Show<select value={spec.metric} onChange={(e) => set({ metric: e.target.value })}>{METRICS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">By<select value={spec.factor} onChange={(e) => set({ factor: e.target.value })}>{FACTORS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      </div>
      {spec.factor === WATER_TEMP_BUCKET && <label className="field">Degrees per bar<select value={spec.tempWidth} onChange={(e) => set({ tempWidth: e.target.value })}>{[1, 2, 3, 5].map((w) => <option key={w} value={w}>{w} °F</option>)}</select></label>}
      {spec.factor === SECCHI_BUCKET && <label className="field">Feet per bar<select value={spec.secchiWidth} onChange={(e) => set({ secchiWidth: e.target.value })}>{[0.25, 0.5, 1, 2].map((w) => <option key={w} value={w}>{w} ft</option>)}</select></label>}
      {SPECIES_METRICS.has(spec.metric) && <label className="field">Species<select value={spec.species} onChange={(e) => set({ species: e.target.value })}><option value="">All species</option>{choices.species.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>}
      <Pick label="Lure type" options={choices.lure_types.map(([, n]) => n)} value={spec.lure_types.map((k) => typeNames[k] || k)} onChange={(v) => set({ lure_types: v.map((n) => typeKeys[n] || n) })} />
      <Pick label="Spot" options={choices.spots} value={spec.spots} onChange={(v) => set({ spots: v })} />
      <Pick label="Angler" options={choices.anglers} value={spec.anglers} onChange={(v) => set({ anglers: v })} />
      <Multi label="Time of day" options={SEGMENTS} value={spec.segments} onChange={(v) => set({ segments: v })} />
      {(spec.from || spec.to) && <p className="note-bar">Dates {spec.from || "start"} to {spec.to || "now"} (instead of the period above) <button className="link" onClick={() => set({ from: "", to: "" })}>Clear</button></p>}
    </div></section>
    <ReportCard trips={trips} spec={spec} title={title || "Custom report"} f={f} me={me} typeNames={typeNames} />
    <Predict trips={trips} spec={spec} weather={weather} me={me.email} who={f.who} />
    <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
      <label className="field">Report name<input type="text" value={title} placeholder={describeReport(spec, typeNames).slice(0, 60)} onChange={(e) => setTitle(e.target.value)} /></label>
      <div className={report ? "two" : "setup"}>
        <button className="btn primary" onClick={save}>{report ? "Save changes" : "☆ Save this report"}</button>
        {report && <button className="btn" onClick={remove}>Delete</button>}
      </div>
    </div></section>
  </>;
}

function ReportCard({ trips, spec, title, f, me, typeNames }) {
  const result = useMemo(() => runReport(trips, spec, { screenPeriod: f.period, screenWho: f.who, me: me.email }), [trips, spec, f.period, f.who, me]);
  const nWord = spec.metric === "fish_per_hour" || spec.metric === "trip_count" || (spec.metric === "total_fish" && !spec.species) ? "trips" : "fish";
  const [busy, setBusy] = useState(false);
  return <section className="card">
    <div className="card-h"><span className="t">{title}</span>
      <button className="link" disabled={busy} onClick={async () => { setBusy(true); try { await exportExcel(title, spec, result); } finally { setBusy(false); } }}>{busy ? "Making…" : "⤓ Excel"}</button></div>
    <p className="muted small" style={{ margin: 0, padding: "8px 14px 0" }}>{describeReport(spec, typeNames)} · {result.win.from ? `${result.win.from} to ${result.win.to}` : `all time to ${result.win.to}`}</p>
    <div className="card-b"><Bars rows={result.rows} metric={spec.metric} nWord={nWord} /></div>
  </section>;
}

/** #99 (Matthew 11-14): the forecast score vs what was caught, for the days fished. */
function ScoreCheck({ trips, f, me }) {
  const [show, setShow] = useState("rate");
  const win = windowFor({}, f.period);
  const out = useMemo(() => scoreCheck(trips, { from: win.from, to: win.to, owner: f.who === "me" ? me.email : null }), [trips, win.from, win.to, f.who, me]);
  const rows = out.bands.map((b) => ({ key: b.key, label: b.label, n: show === "rate" ? (b.rate == null ? 0 : b.days) : b.days,
    value: show === "rate" ? b.rate ?? 0 : b.fishPerDay }));
  const max = Math.max(0, ...rows.map((r) => r.value));
  const r = show === "rate" ? out.rRate : out.rFish;
  // scatter: x = score 0–10, y = fish/hr or fish that day
  const pts = out.days.map((d) => ({ x: d.score, y: show === "rate" ? d.rate : d.fish, d })).filter((p) => p.y != null);
  const ymax = Math.max(1, ...pts.map((p) => p.y)), W = 320, H = 150, P = 26;
  const X = (x) => P + (Math.max(0, Math.min(10, x)) / 10) * (W - P - 8), Y = (y) => H - 18 - (y / ymax) * (H - 30);
  return <section className="card">
    <div className="card-h"><span className="t">Forecast score vs fish caught</span><span className="muted small">{out.days.length} days fished</span></div>
    <div className="card-b setup" style={{ paddingTop: 10 }}>
      <div className="seg">{[["rate", "Fish per hour"], ["day", "Fish per day"]].map(([k, l]) => <button key={k} className={show === k ? "on" : ""} onClick={() => setShow(k)}>{l}</button>)}</div>
      {!out.days.length ? <p className="empty">No days with a forecast score in this period yet.</p> : <>
        <p style={{ margin: 0 }}><b>{describeR(r)}</b>{r != null && <span className="muted small"> (correlation {r >= 0 ? "+" : ""}{r.toFixed(2)} over {show === "rate" ? out.rateDays : out.days.length} days; ±1 = perfect, 0 = none)</span>}</p>
        <svg className="sc-plot" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Each day fished: forecast score across, catch up">
          <line x1={P} y1={H - 18} x2={W - 8} y2={H - 18} className="ax" /><line x1={P} y1={8} x2={P} y2={H - 18} className="ax" />
          {[0, 2, 4, 6, 8, 10].map((t) => <text key={t} x={X(t)} y={H - 4} className="tk" textAnchor="middle">{t}</text>)}
          <text x={P - 4} y={Y(ymax) + 4} className="tk" textAnchor="end">{show === "rate" ? ymax.toFixed(1) : Math.round(ymax)}</text>
          <text x={P - 4} y={H - 18} className="tk" textAnchor="end">0</text>
          {pts.map((p) => <circle key={p.d.date} cx={X(p.x)} cy={Y(p.y)} r="4.5" className="dot"><title>{`${p.d.date}: score ${p.x.toFixed(1)}, ${p.d.fish} fish${p.d.rate != null ? `, ${p.d.rate.toFixed(2)}/hr` : ""}`}</title></circle>)}
        </svg>
        <p className="muted small" style={{ margin: 0 }}>Each dot is a day fished: the forecast score across, {show === "rate" ? "fish per angler-hour" : "fish caught that day"} up.</p>
        <div className="lr-h">By forecast score</div>
        <div className="rp-bars">{rows.map((b) => (
          <div key={b.key} className={`rp-bar ${b.n && b.n < 4 ? "thin" : ""}`}>
            <span className="rp-lbl">{b.label}</span>
            <span className="rp-track"><span style={{ width: `${max > 0 && b.n ? Math.max(2, (b.value / max) * 100) : 0}%` }} /></span>
            <span className="rp-val"><b className="num">{b.n ? (show === "rate" ? `${b.value.toFixed(2)}/hr` : b.value.toFixed(1)) : "–"}</b><span className="muted small block">{b.n} day{b.n === 1 ? "" : "s"}</span></span>
          </div>))}</div>
        <p className="muted small" style={{ margin: 0 }}>Score = the forecast saved when each lure went in the water (the time-of-day score), averaged over the day's sessions. Hours = each session's first lure in to last lure out. The scoring itself has been tuned over the season (Sep rebalance, Nov season fix), so older days were scored by older versions. Faded bars rest on fewer than 4 days.</p>
      </>}
    </div>
  </section>;
}

export default function ReportsScreen({ active, db, me, trips, weather, onBack, onMenu, demo, toast }) {
  const [f, setFState] = useState(read);
  const setF = (p) => setFState((x) => { const n = { ...x, ...p }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  // reports group by the spot name saved on each trip (as the old app did)
  const choices = useMemo(() => choicesFrom(trips || [], {}), [trips]);
  const [saved, setSaved] = useState([]);
  useEffect(() => { if (active && db?.listSaved) db.listSaved("report").then(setSaved).catch(() => {}); }, [active, db]);
  if (!active) return null;
  const stock = STOCK.find((s) => s.id === f.tab);
  const report = f.tab.startsWith("saved:") ? saved.find((r) => `saved:${r.id}` === f.tab) || null : null;
  const spec = stock ? cleanReportSpec(stock, choices) : null;
  const typeNames = Object.fromEntries(choices.lure_types);
  return (
    <div className="screen" id="screen-reports">
      <Head kicker={`More · ${PERIODS.find(([k]) => k === f.period)[1]}`} title="Reports" onMenu={onMenu} demo={demo}>
        <button className="iconbtn" aria-label="Back to More" onClick={onBack}><Icon name="back" size={20} /></button>
      </Head>
      <div className="body">
        <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
          <div className="seg">{PERIODS.map(([k, l]) => <button key={k} className={f.period === k ? "on" : ""} onClick={() => setF({ period: k })}>{l}</button>)}</div>
          <div className="seg">{[["all", "Everyone"], ["me", "Just me"]].map(([k, l]) => <button key={k} className={f.who === k ? "on" : ""} onClick={() => setF({ who: k })}>{l}</button>)}</div>
        </div></section>
        <div className="lb-tabs" role="tablist">
          {STOCK.map((s) => <button key={s.id} role="tab" aria-selected={f.tab === s.id} className={f.tab === s.id ? "on" : ""} onClick={() => setF({ tab: s.id })}>{s.title}</button>)}
          <button role="tab" aria-selected={f.tab === "forecast"} className={f.tab === "forecast" ? "on" : ""} onClick={() => setF({ tab: "forecast" })}>Forecast vs catch</button>
          {saved.map((r) => <button key={r.id} role="tab" aria-selected={f.tab === `saved:${r.id}`} className={f.tab === `saved:${r.id}` ? "on" : ""} onClick={() => setF({ tab: `saved:${r.id}` })}>★ {r.title}</button>)}
          <button role="tab" aria-selected={f.tab === "custom"} className={f.tab === "custom" ? "on" : ""} onClick={() => setF({ tab: "custom" })}>＋ Custom</button>
        </div>
        {trips === null ? <p className="muted">Loading the trip log…</p> : <>
          {f.tab === "forecast" ? <ScoreCheck trips={trips} f={f} me={me} /> : stock ? <ReportCard trips={trips} spec={spec} title={stock.title} f={f} me={me} typeNames={typeNames} />
            : <Builder db={db} me={me} report={report} choices={choices} trips={trips} f={f} toast={toast} weather={weather} setScreen={(p) => setF(p)}
                onSaved={(item) => { setSaved((l) => [...l.filter((x) => x.id !== item.id), item]); setF({ tab: `saved:${item.id}` }); }}
                onDeleted={() => { setSaved((l) => l.filter((x) => x.id !== report.id)); setF({ tab: "custom" }); }} />}
          {stock && <Predict trips={trips} spec={spec} weather={weather} me={me.email} who={f.who} />}
        </>}
      </div>
    </div>
  );
}
