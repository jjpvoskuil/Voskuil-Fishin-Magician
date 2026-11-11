// 7-Day Forecast: a strip of days, then the chosen day's conditions, best window, six segments (tap for why) and
// lure picks for each time of day. Ended windows' scores are frozen (fm_score_freeze). Port of pages/1_7_Day_Forecast.py.
import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import LureRec from "./LureRec.jsx";
import { buildPicks } from "./lib/picks.js";
import { useElectronics, usePicksMode } from "./lib/prefs.js";
import { LakeSetupForm, resolveSetup, setupSummary } from "./LakeSetup.jsx";
import { Breakdown, Sheet, ago, fmtTime, signed } from "./ui.jsx";
import { calibrateWeights } from "./lib/calibration.js";
import { applyFreeze } from "./lib/freeze.js";
import { recommend } from "./lib/lures.js";
import { effectiveSeasonAndTemp, scoreWeek } from "./lib/scoring.js";
import { titleWords } from "./lib/py.js";
import { lakeNowNaive, lakeToday } from "./lib/weather.js";

const dayLabel = (d, opts) => new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { timeZone: "UTC", ...opts });

export default function ForecastScreen({ active, demo, onMenu, db, me, weather, trips, lures, spots, setup, setSetup }) {
  const today = lakeToday();
  const [frozen, setFrozen] = useState(null);
  const [pick, setPick] = useState(today);
  const [segPick, setSegPick] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const saving = useRef(false);

  useEffect(() => { if (active && db) db.listFreezes(today).then(setFrozen, () => setFrozen([])); }, [active, db, today]);

  const weights = useMemo(() => (trips ? calibrateWeights(trips) : null), [trips]);
  const { week, newRows } = useMemo(() => {
    if (!weather.value || !weights || frozen == null) return { week: null, newRows: [] };
    const w = scoreWeek(weather.value, today, 7, weights), now = lakeNowNaive(), rows = [];
    for (const d of w) rows.push(...applyFreeze(d, frozen, now));
    return { week: w, newRows: rows };
  }, [weather.value, weights, frozen, today]);

  // save windows that just ended (shared with everyone; first one in wins)
  useEffect(() => {
    if (!newRows.length || saving.current || !db) return;
    saving.current = true;
    db.addFreezes(newRows).then(() => db.listFreezes(today)).then(setFrozen).catch(() => {}).finally(() => { saving.current = false; });
  }, [newRows, db, today]);

  const day = week?.find((d) => d.the_date === pick) || week?.[0];
  const best = day ? day.segments.reduce((b, s) => (s.score > b.score ? s : b), day.segments[0]) : null;
  const seg = day ? day.segments.find((s) => s.name === segPick) || best : null;
  const [electronics] = useElectronics(), [picksMode, setPicksMode] = usePicksMode();
  const r = resolveSetup(setup, spots, week?.[0]?.water_temp_f ?? null, electronics);
  const [effSeason, effTemp] = day ? effectiveSeasonAndTemp(day, r.waterTemp) : [null, null];

  const rec = useMemo(() => {
    if (!day || !seg || !lures || !trips) return null;
    return recommend({ season: effSeason, water_temp_f: effTemp, segment_name: seg.name, pressure_trend_24h: seg.pressure_trend_24h,
      structure_type: r.structure, water_clarity: r.clarity, fish_depth_ft: r.fishDepth, forage: r.forage,
      inventory: lures, trip_history: trips, wind_mph: day.weather_summary.avg_wind_mph });
  }, [day, seg, lures, trips, effSeason, effTemp, r.structure, r.clarity, r.fishDepth, r.forage]);

  const picks = useMemo(() => (rec ? buildPicks(rec, { trips, inventory: lures, today: lakeToday(), ctx: { water_temp_f: effTemp, water_clarity: r.clarity, segment_name: seg?.name,
    structure_type: r.structure, spot_id: r.spot?.spot_id || null, me: picksMode === "me" ? me?.email : null, fish_depth_ft: r.fishDepth } }) : null), [rec, trips, lures, effTemp, r.clarity, seg, r.structure, r.spot, me, r.fishDepth, picksMode]);
  const ws = day?.weather_summary;
  return (
    <div className="screen" hidden={!active} id="screen-forecast">
      <Head kicker="Next 7 days · Nolin Lake" title="Forecast" onMenu={onMenu} demo={demo} />
      <div className="body">
        {weather.error && !weather.value && <div className="card"><div className="empty">Couldn't fetch the forecast ({weather.error}).<br /><button className="btn" style={{ marginTop: 12 }} onClick={weather.reload}>Try again</button></div></div>}
        {weather.error && weather.value && <p className="note-bar">No connection to the weather service — showing the forecast from {ago(weather.at)}.</p>}
        {!week && !(weather.error && !weather.value) && <div className="card"><div className="empty">Loading the forecast…</div></div>}
        {week && week.length === 0 && <div className="card"><div className="empty">No forecast days are available right now — the weather data may not have refreshed yet. Try again in a moment.</div></div>}
        {week && week.length > 0 && week.length < 7 && <p className="note-bar">Only {week.length} of 7 days had weather data just now — showing what's available.</p>}

        {week && week.length > 0 && <>
          <div className="week" role="tablist" aria-label="Days">
            {week.map((d) => (
              <button key={d.the_date} role="tab" aria-selected={d === day} className={`wday ${d === day ? "on" : ""}`} onClick={() => { setPick(d.the_date); setSegPick(null); }}>
                <span className="wd">{d.the_date === today ? "Today" : dayLabel(d.the_date, { weekday: "short" })}</span>
                <span className="num ws">{d.overall_score.toFixed(1)}</span>
                <span className="wbar"><span style={{ width: `${d.overall_score * 10}%` }} /></span>
              </button>
            ))}
          </div>

          <section className="card">
            <div className="card-h"><span className="t"><Icon name="calendar" />{dayLabel(day.the_date, { weekday: "long", month: "long", day: "numeric" })}</span>
              <button className="pill" onClick={() => setSheet({ title: `${dayLabel(day.the_date, { weekday: "long" })} · overall`, breakdown: day.overall_breakdown, score: day.overall_score })}>{day.overall_score.toFixed(1)} · why</button></div>
            <div className="card-b facts">
              <div><span className="muted">Pattern</span><b>{titleWords(effSeason)}</b></div>
              <div><span className="muted">Moon</span><b>{day.moon.name} · {Math.round(day.moon.illumination_pct)}%</b></div>
              <div><span className="muted">Water temp</span><b>{effTemp}°F{setup.waterTemp == null ? " (est.)" : " (yours)"}</b></div>
              <div><span className="muted">Pressure 24 h</span><b>{signed(day.pressure_trend_24h)} hPa</b></div>
              <div><span className="muted">Sun</span><b>{fmtTime(day.sunrise)} – {fmtTime(day.sunset)}</b></div>
              <div><span className="muted">High / low</span><b>{ws.temp_hi_f ?? "—"}° / {ws.temp_lo_f ?? "—"}°F</b></div>
              <div><span className="muted">Clouds · wind</span><b>{Math.round(ws.avg_cloud_pct)}% · {Math.round(ws.avg_wind_mph)} mph</b></div>
              <div><span className="muted">Rain chance</span><b>{Math.round(ws.max_precip_prob_pct)}%</b></div>
            </div>
            {effSeason !== day.season && <p className="muted small" style={{ padding: "0 14px" }}>Your water temp puts this day in the {titleWords(effSeason)} pattern for lure selection (the weather-only estimate would be {titleWords(day.season)}).</p>}
            {day.warnings.map((w) => <p key={w} className="warn" style={{ margin: "0 14px 12px" }}>{w}</p>)}
          </section>

          <section className="card">
            <div className="card-h"><span className="t"><Icon name="clock" />Time of day</span><span className="pill">Best: {best.name}</span></div>
            <div className="card-b">
              <div className="segs">
                {day.segments.map((s) => {
                  const now = lakeNowNaive(), isNow = now >= s.start && now < s.end, ended = s.end <= now;
                  return (
                    <button key={s.name} className="seg-row" onClick={() => setSheet({ title: `${s.name} · ${fmtTime(s.start)}–${fmtTime(s.end)}${ended ? " (frozen)" : ""}`, breakdown: s.breakdown, score: s.score })} aria-label={`${s.name} score ${s.score}, show why`}>
                      <span className="seg-n">{s.name}{isNow && <span className="now">now</span>}{s.solunar_overlap && <span className="sol" title={`solunar ${s.solunar_overlap}`}>☾ {s.solunar_overlap}</span>}</span>
                      <span className="bar"><span style={{ width: `${s.score * 10}%` }} className={s === best ? "best" : ""} /></span>
                      <span className="num seg-s">{s.score.toFixed(1)}</span>
                    </button>
                  );
                })}
              </div>
              <p className="muted small" style={{ margin: "10px 0 0" }}>Tap a time of day for why. Times that have ended keep the score they had (frozen). {trips?.length ? `Calibrated using ${trips.length} logged trips.` : "Using default weights — log trips to calibrate."}</p>
            </div>
          </section>

          <section className="card">
            <div className="card-h"><span className="t"><Icon name="tackle" />Lure setup</span>
              <button className="pill" onClick={() => setSetupOpen(true)}>Lake setup</button></div>
            <div className="card-b">
              <button className="setup-sum" onClick={() => setSetupOpen(true)}>{setupSummary(r)} <span className="link">Change</span></button>
              <div className="segchips" role="tablist" aria-label="Time of day">
                {day.segments.map((s) => (
                  <button key={s.name} role="tab" aria-selected={s === seg} className={`chip ${s === seg ? "on" : ""}`} onClick={() => setSegPick(s.name)}>
                    {s.name} <span className="num">{s.score.toFixed(1)}</span></button>
                ))}
              </div>
              <p className="muted small" style={{ margin: "8px 0 10px" }}>{seg.name}: {fmtTime(seg.start)} – {fmtTime(seg.end)}</p>
              {!rec ? <p className="muted">Loading your tackle box…</p> : <LureRec rec={rec} inventory={lures} picks={picks} mode={picksMode} setMode={setPicksMode} />}
            </div>
          </section>
          <p className="muted small" style={{ textAlign: "center", margin: "0 8px" }}>Scores are 1 (least active) to 10 (most active), built from pressure trend, moon phase, solunar windows, cloud cover, wind, and season.</p>
        </>}
      </div>
      <Sheet open={!!sheet} title={sheet?.title} onClose={() => setSheet(null)}>{sheet && <Breakdown breakdown={sheet.breakdown} score={sheet.score} />}</Sheet>
      <Sheet open={setupOpen} title="Lake setup" onClose={() => setSetupOpen(false)}>
        <LakeSetupForm setup={setup} set={setSetup} spots={spots} defaultTemp={week?.[0]?.water_temp_f ?? null} electronics={electronics} />
        <button className="btn primary wide" style={{ marginTop: 14 }} onClick={() => setSetupOpen(false)}>Done</button>
      </Sheet>
    </div>
  );
}
