// Today: the day's score and why, best window + all six segments, lake right now (USGS level, USACE oxygen),
// and today's / this week's fishing activity. Port of the Streamlit home.py.
import { useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { Breakdown, ScoreRing, Sheet, ago, fmtTime, signed, verdict } from "./ui.jsx";
import { calibrateWeights } from "./lib/calibration.js";
import { NORMAL_SUMMER_POOL_FT } from "./lib/lake.js";
import { buildDailyActivity, buildWeeklyActivity, dailyAwards, formatWeightLbOz, leaderboardTableRows, weekBounds } from "./lib/leaderboard.js";
import { scoreDay } from "./lib/scoring.js";
import { lakeNowNaive, lakeToday } from "./lib/weather.js";

const mdy = (d) => `${Number(d.slice(5, 7))}/${d.slice(8, 10)}`;

export default function TodayScreen({ active, demo, onMenu, weather, lake, water, trips }) {
  const today = lakeToday();
  const [sheet, setSheet] = useState(null); // {title, breakdown, score}
  const [period, setPeriod] = useState("today");

  const weights = useMemo(() => (trips ? calibrateWeights(trips) : null), [trips]);
  const { day, dayError } = useMemo(() => {
    if (!weather.value || !weights) return { day: null, dayError: "" };
    try { return { day: scoreDay(weather.value, today, weights), dayError: "" }; } catch (e) { return { day: null, dayError: e.message }; }
  }, [weather.value, weights, today]);

  const now = lakeNowNaive();
  const best = day ? day.segments.reduce((b, s) => (s.score > b.score ? s : b), day.segments[0]) : null;
  const helping = day ? day.overall_breakdown.filter(([l, d]) => l !== "Base" && d > 0).sort((a, b) => b[1] - a[1]).slice(0, 2).map((x) => x[0].toLowerCase()) : [];
  const hurting = day ? day.overall_breakdown.filter(([, d]) => d < 0).sort((a, b) => a[1] - b[1]).slice(0, 2).map((x) => x[0].toLowerCase()) : [];
  const level = lake.value?.[lake.value.length - 1];
  const levelTime = level ? new Date(level.observed_at) : null;

  const stats = trips ? (period === "today" ? buildDailyActivity(trips, today) : buildWeeklyActivity(trips, today)) : null;
  const [wkStart, wkEnd] = weekBounds(today);

  return (
    <div className="screen" hidden={!active} id="screen-today">
      <Head kicker={`${new Date(`${today}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" })} · Nolin Lake`} title="Today" onMenu={onMenu} demo={demo} />
      <div className="body">
        {weather.error && !weather.value && <div className="card"><div className="empty">Couldn't fetch live weather right now ({weather.error}).<br />This can happen if Open-Meteo is briefly unreachable — try again in a minute.<br /><button className="btn" style={{ marginTop: 12 }} onClick={weather.reload}>Try again</button></div></div>}
        {weather.error && weather.value && <p className="note-bar">No connection to the weather service — showing the forecast from {ago(weather.at)}.</p>}
        {dayError && <div className="card"><div className="empty">Today's forecast isn't available yet: {dayError}</div></div>}
        {!day && !dayError && !(weather.error && !weather.value) && <div className="card"><div className="empty">Loading today's forecast…</div></div>}

        {day && <>
          <section className="card">
            <div className="card-h"><span className="t"><Icon name="trend" />Today at a glance</span></div>
            <div className="card-b glance">
              <ScoreRing score={day.overall_score} />
              <div className="glance-t">
                <b>{verdict(day.overall_score)}</b>
                {(helping.length > 0 || hurting.length > 0) && <span className="muted small">
                  {helping.length > 0 && <>Helping: {helping.join(", ")}. </>}{hurting.length > 0 && <>Hurting: {hurting.join(", ")}.</>}</span>}
                <button className="link" onClick={() => setSheet({ title: "Today's activity score", breakdown: day.overall_breakdown, score: day.overall_score })}>Why this score</button>
              </div>
            </div>
            <div className="stats">
              <div className="stat"><span className="v">{day.water_temp_f}°F</span><span className="k">Water (est.)</span></div>
              <div className="stat"><span className="v">{Math.round(day.moon.illumination_pct)}%</span><span className="k">{day.moon.name}</span></div>
              <div className="stat"><span className="v">{signed(day.pressure_trend_24h)}</span><span className="k">hPa, 24 h</span></div>
              <div className="stat"><span className="v">{Math.round(day.weather_summary.avg_wind_mph)} mph</span><span className="k">Wind (avg)</span></div>
            </div>
          </section>

          <section className="card">
            <div className="card-h"><span className="t"><Icon name="clock" />Best window</span><span className="pill">{best.name} · {best.score.toFixed(1)}</span></div>
            <div className="card-b">
              <div style={{ fontWeight: 700, marginBottom: 10 }}>{fmtTime(best.start)} – {fmtTime(best.end)}</div>
              <div className="segs">
                {day.segments.map((s) => {
                  const isNow = now >= s.start && now < s.end;
                  return (
                    <button key={s.name} className="seg-row" onClick={() => setSheet({ title: `${s.name} · ${fmtTime(s.start)}–${fmtTime(s.end)}`, breakdown: s.breakdown, score: s.score })}
                      aria-label={`${s.name} score ${s.score}, show why`}>
                      <span className="seg-n">{s.name}{isNow && <span className="now">now</span>}</span>
                      <span className="bar"><span style={{ width: `${s.score * 10}%` }} className={s === best ? "best" : ""} /></span>
                      <span className="num seg-s">{s.score.toFixed(1)}</span>
                    </button>
                  );
                })}
              </div>
              {day.warnings.map((w) => <p key={w} className="warn">{w}</p>)}
              <p className="muted small" style={{ margin: "10px 0 0" }}>
                {trips?.length ? `Tap a time of day to see why. Scores are tuned by ${trips.length} logged trip${trips.length === 1 ? "" : "s"}.` : "Tap a time of day to see why. No trips logged yet — using default weights."}
              </p>
            </div>
          </section>
        </>}

        <section className="card">
          <div className="card-h"><span className="t"><Icon name="wave" />Lake right now</span></div>
          <div className="stats" style={{ borderTop: 0 }}>
            <div className="stat"><span className="v">{level ? `${level.elevation_ft} ft` : "—"}</span><span className="k">{level ? `${signed(level.elevation_ft - NORMAL_SUMMER_POOL_FT)} vs pool` : "Lake level"}</span></div>
            <div className="stat"><span className="v">{water.reading ? `${water.reading.do_mg_l} mg/l` : "—"}</span><span className="k">Oxygen</span></div>
            <div className="stat"><span className="v">{water.reading ? `${Math.round(water.reading.do_saturation_pct)}%` : "—"}</span><span className="k">O₂ saturation</span></div>
          </div>
          <div className="card-b muted small" style={{ borderTop: "1px solid var(--line-soft)", lineHeight: 1.45 }}>
            {level ? `Level from USGS ${levelTime.toLocaleString("en-US", { month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago" })}. ` : lake.error ? "Couldn't reach USGS for the lake level just now. " : ""}
            {water.reading ? <>Oxygen from the Army Corps Dam Site survey {mdy(water.reading.observed_at.slice(0, 10))} (surface water {water.reading.water_temp_f}°F) — a periodic manual survey, not a daily feed.{!water.live && " The Army Corps site couldn't be reached, so this is the last reading logged."}</>
              : water.loading ? "Checking the Army Corps survey…" : water.error ? `Couldn't get the Army Corps oxygen reading: ${water.error}` : "No Army Corps oxygen reading yet."}
          </div>
        </section>

        <section className="card">
          <div className="card-h"><span className="t"><Icon name="trophy" />Fishing activity</span></div>
          <div className="card-b">
            <div className="seg" style={{ marginBottom: 12 }}>
              <button className={period === "today" ? "on" : ""} onClick={() => setPeriod("today")}>Today</button>
              <button className={period === "week" ? "on" : ""} onClick={() => setPeriod("week")}>This week</button>
            </div>
            {!stats ? <p className="muted">Loading…</p> : !stats.length ? <p className="muted">Nobody's logged a Spot Session yet {period === "today" ? "today" : "this week"} — be the first one out there!</p> : <Activity stats={stats} />}
            <p className="muted small" style={{ margin: "10px 0 0" }}>
              {period === "today" ? "Resets at midnight lake time." : `Week of ${mdy(wkStart)} – ${mdy(wkEnd)} (Sun–Sat).`} All-time rankings are on the Leaderboard (under More).
            </p>
          </div>
        </section>

        <p className="muted small" style={{ textAlign: "center", lineHeight: 1.5, margin: "4px 8px" }}>
          Nolin River Lake normal pool: {NORMAL_SUMMER_POOL_FT} ft elevation, ~5,795 surface acres. Lake map locations are planning approximations — verify with your own GPS/chartplotter on the water.
        </p>
      </div>
      <Sheet open={!!sheet} title={sheet?.title} onClose={() => setSheet(null)}>{sheet && <Breakdown breakdown={sheet.breakdown} score={sheet.score} />}</Sheet>
    </div>
  );
}

function Activity({ stats }) {
  const a = dailyAwards(stats), rows = leaderboardTableRows(stats);
  const awards = [
    ["Berkley — Biggest Fish", a.biggest_fish ? `${a.biggest_fish.angler} · ${formatWeightLbOz(a.biggest_fish.weight_lb)}` : "None yet", a.biggest_fish?.species],
    ["String King — Top Angler", a.top_angler_weight ? `${a.top_angler_weight.angler} · ${formatWeightLbOz(a.top_angler_weight.total_weight_lb) || "no weights"}` : "None yet", "Most total weight"],
    ["Z-Man — Bag Limit Buster", a.top_bag_count ? `${a.top_bag_count.angler} · ${a.top_bag_count.fish_count} fish` : "None yet", "Most fish"],
  ];
  return <>
    <div className="roster">
      {stats.map((s) => <span key={s.angler} className="roster-i"><span className={`dot ${s.active ? "on" : ""}`} aria-label={s.active ? "fishing now" : ""} />{s.angler} <span className="muted">· {s.fish_count} fish</span></span>)}
    </div>
    <div className="awards">
      {awards.map(([t, v, sub]) => <div className="award" key={t}><span className="k">{t}</span><span className="v">{v}</span>{sub && <span className="muted small">{sub}</span>}</div>)}
    </div>
    {rows.length > 0 && <div className="tbl-wrap"><table className="tbl">
      <thead><tr><th>Angler</th><th>Species</th><th className="r">Fish</th><th className="r">Largest</th><th className="r">Total</th></tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className={r.Angler === "Subtotal" || r.Angler.startsWith("All anglers") ? "sub" : ""}>
        <td>{r.Angler}</td><td>{r.Species}</td><td className="r num">{r["# Fish"]}</td><td className="r">{r.Largest}</td><td className="r">{r.Total}</td></tr>)}</tbody>
    </table></div>}
    <p className="muted small" style={{ margin: "8px 0 0" }}><span className="dot on" /> = has a Spot Session open right now.</p>
  </>;
}
