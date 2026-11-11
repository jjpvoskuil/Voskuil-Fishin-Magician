// Lake Map (old pages/2_Lake_Map.py, redesigned with John 11-10): satellite by default, your GPS dot, saved spots
// colored by how they've produced (filter by time of day / time of year / just you), fish attractors (KDFWR), who's
// fishing now, today's best spots, and fast pin-and-name: "Save where I am" or press-and-hold anywhere.
// Spots are shared by all anglers (fm_spots). Depth contours + structure layer come next (lidar, see CLAUDE.md).
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { NumberBox } from "./LakeSetup.jsx";
import { Sheet } from "./ui.jsx";
import { newId } from "./lib/db.js";
import { formatWeightLbOz } from "./lib/leaderboard.js";
import { segmentTimeRanges, SEGMENTS } from "./lib/scoring.js";
import * as S from "./lib/session.js";
import { HEAT_LEGEND, heatColor, SEASONS, spotStats } from "./lib/spotstats.js";
import { lakeNowNaive, lakeToday } from "./lib/weather.js";
import ATTRACTORS from "./lib/data/attractors.json" with { type: "json" };

export const LOCATION_TYPES = ["Main-lake point", "Secondary / pocket point", "Flat", "Creek channel / ledge", "Rock face / bluff", "Riprap", "Boat dock",
  "Bridge piling", "Cove / pocket (shallow cover)", "Standing timber", "Roadbed / old ford", "Other"];
export const BOTTOM_OPTIONS = ["Rocky", "Gravel", "Sand", "Clay / hardpan", "Mud / silt", "Standing timber", "Laydowns / brush", "Stumps", "Boulders", "Riprap"];
const GRADES = ["High (steep break)", "Medium", "Low (gradual taper)"];
const ATTRACTOR_COLORS = { Brush: "#a0522d", "Christmas Trees": "#2e8b57", "Pallet Stack": "#cd853f", Plastic: "#e34a33", "Spider Hump": "#9370db", "Reef Ball": "#aaaaaa", Rock: "#cccccc" };
const LAKE_CENTER = [37.33, -86.17];
const FKEY = "fm.mapFilters";
const F0 = { segments: [], season: "now", mine: false, attractors: true, satellite: true, depth: false, tries: true };
const readF = () => { try { return { ...F0, ...JSON.parse(localStorage.getItem(FKEY)) }; } catch { return F0; } };
const md = (d) => (d ? new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) : "");
const BASES = {
  satellite: () => L.layerGroup([
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, maxNativeZoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" }),
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19, maxNativeZoom: 18, opacity: 0.8 })]),
  map: () => L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }),
};

// depth contours (tools/build_contours.py → web/public/depth/contours.json): bottom ELEVATION lines; depth = level − e
let contoursPromise = null;
const loadContours = () => (contoursPromise ||= fetch(`${import.meta.env.BASE_URL}depth/contours.json`).then((r) => { if (!r.ok) throw new Error("no contours yet"); return r.json(); })
  .catch((e) => { contoursPromise = null; throw e; }));
let suggPromise = null;
const loadSuggestions = () => (suggPromise ||= fetch(`${import.meta.env.BASE_URL}depth/suggestions.json`).then((r) => { if (!r.ok) throw new Error("none"); return r.json(); })
  .catch((e) => { suggPromise = null; throw e; }));
export const TRY_KINDS = { point: ["Point", "Main-lake point", "#ffd54f"], break: ["Steep break / bluff", "Rock face / bluff", "#ff8a65"],
  swing: ["Channel swing", "Creek channel / ledge", "#ba68c8"], flat: ["Flat by deep water", "Flat", "#81c784"] };
const metersApart = (a, b) => { const k = Math.cos((a.lat * Math.PI) / 180); return Math.hypot((a.lat - b.lat) * 111320, (a.lon - b.lon) * 111320 * k); };
const depthColor = (d) => (d < 6 ? "#9be7ff" : d < 12 ? "#4fc3f7" : d < 20 ? "#1e88e5" : d < 30 ? "#1565c0" : "#0d2f8a");

export default function MapScreen({ active, db, me, demo, onMenu, trips, spots, reloadSpots, save, toast, onFishHere, onWatch, weather, lake }) {
  const [f, setFState] = useState(readF);
  const setF = (patch) => setFState((x) => { const n = { ...x, ...patch }; try { localStorage.setItem(FKEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  const [gps, setGps] = useState(null);         // {lat, lon, acc}
  const [sel, setSel] = useState(null);         // spot_id
  const [newPin, setNewPin] = useState(null);   // {lat, lon, how}
  const [editing, setEditing] = useState(null); // spot being edited
  const [panel, setPanel] = useState(null);     // "filters" | null
  const box = useRef(null), map = useRef(null), layers = useRef({});
  const today = lakeToday();
  const list = spots || [];
  const stats = useMemo(() => spotStats(trips, { segments: f.segments, season: f.season, owner: f.mine ? me.email : null }, today), [trips, f.segments, f.season, f.mine, me, today]);
  const live = useMemo(() => (trips ? S.openSessions(trips).filter((o) => o.owner !== me.email && o.rows[0].trip_date === today) : []), [trips, me, today]);
  const nowSeg = S.guessSegment(lakeNowNaive(), segmentTimeRanges(weather?.value, today));

  // ---- map setup (once)
  useEffect(() => {
    if (!box.current || map.current) return;
    const m = L.map(box.current, { zoomControl: false, attributionControl: true, tapHold: true, preferCanvas: true }).setView(LAKE_CENTER, 13);
    L.control.zoom({ position: "bottomright" }).addTo(m);
    m.on("contextmenu", (e) => setNewPin({ lat: e.latlng.lat, lon: e.latlng.lng, how: "pressed" })); // press-and-hold / right-click
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);
  useEffect(() => { if (active && map.current) setTimeout(() => map.current.invalidateSize(), 50); }, [active]);

  // ---- base layer
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.base?.remove();
    layers.current.base = BASES[f.satellite ? "satellite" : "map"]().addTo(m);
    layers.current.base.bringToBack?.();
  }, [f.satellite]);

  // ---- fish attractors
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.attr?.remove(); layers.current.attr = null;
    if (!f.attractors) return;
    const g = L.layerGroup();
    for (const a of ATTRACTORS) L.circleMarker([a.lat, a.lon], { radius: 4, weight: 1, color: "#000", fillColor: ATTRACTOR_COLORS[a.type] || "#888", fillOpacity: 0.9 })
      .bindTooltip(`Fish attractor: ${a.type} (${a.id})`).addTo(g);
    layers.current.attr = g.addTo(m);
  }, [f.attractors]);

  // ---- depth contours, following today's lake level
  const level = lake?.value?.[lake.value.length - 1]?.elevation_ft ?? null;
  const [contours, setContours] = useState(null), [zoom, setZoom] = useState(13);
  useEffect(() => { const m = map.current; if (!m) return; const on = () => setZoom(m.getZoom()); m.on("zoomend", on); return () => m.off("zoomend", on); }, []);
  useEffect(() => { if (f.depth && !contours) loadContours().then(setContours).catch(() => toast("Depth contours aren't available yet")); }, [f.depth]);
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.depth?.remove(); layers.current.depth = null;
    if (!f.depth || !contours || level == null) return;
    const every = zoom >= 15 ? 2 : zoom >= 14 ? 4 : 10;  // fewer lines when zoomed out
    const g = L.layerGroup();
    for (const ln of contours.lines) {
      const d = level - ln.e; if (d < 1) continue;
      if (Math.round(d) % every > 1 && every > 2) continue;
      L.polyline(ln.c.map(([lo, la]) => [la, lo]), { color: depthColor(d), weight: d % 10 < 2 ? 2.2 : 1.3, opacity: ln.est ? 0.75 : 0.95, dashArray: ln.est ? "5 6" : null, interactive: true })
        .bindTooltip(`${Math.round(d)} ft deep${ln.est ? " — estimated" : " — measured (lidar)"}`, { sticky: true }).addTo(g);
    }
    layers.current.depth = g.addTo(m);
    layers.current.spots?.bringToFront?.();
  }, [f.depth, contours, level, zoom]);

  // ---- spots to try (structure from the lidar: points, breaks, channel swings, flats by deep water)
  const [tries, setTries] = useState(null), [trySel, setTrySel] = useState(null);
  useEffect(() => { if (f.tries && !tries) loadSuggestions().then((d) => setTries(d.spots)).catch(() => {}); }, [f.tries]);
  const shownTries = useMemo(() => (tries || []).filter((t) => !list.some((s) => metersApart({ lat: +s.lat, lon: +s.lon }, t) < 120)), [tries, list]);
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.tries?.remove(); layers.current.tries = null;
    if (!f.tries || !shownTries.length) return;
    const g = L.layerGroup();
    for (const t of shownTries) L.marker([t.lat, t.lon], { icon: L.divIcon({ className: "try-pin", html: `<span style="background:${TRY_KINDS[t.kind][2]}">★</span>`, iconSize: [26, 26], iconAnchor: [13, 13] }) })
      .on("click", () => setTrySel(t)).addTo(g);
    layers.current.tries = g.addTo(m);
  }, [f.tries, shownTries]);

  // ---- saved spots, colored by heat
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.spots?.remove();
    const g = L.layerGroup();
    for (const s of list) {
      const st = stats.spots[s.spot_id], r = 9 + Math.min(7, Math.sqrt(st?.sessions || 0) * 1.5);
      const mk = L.circleMarker([+s.lat, +s.lon], { radius: r, weight: s.spot_id === sel ? 4 : 2, color: "#fff", fillColor: heatColor(st), fillOpacity: 0.95 });
      mk.bindTooltip(s.name, { permanent: true, direction: "right", offset: [r, 0], className: "spot-label" });
      mk.on("click", (e) => { L.DomEvent.stopPropagation(e); setSel(s.spot_id); });
      mk.addTo(g);
    }
    layers.current.spots = g.addTo(m);
  }, [list, stats, sel]);

  // ---- anglers on the water now
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.live?.remove();
    const g = L.layerGroup();
    for (const o of live) {
      const c = S.currentConditions(o), sp = list.find((x) => x.spot_id === c.spot_id); if (!sp) continue;
      const l = S.liveSummary(o, lakeNowNaive());
      L.marker([+sp.lat, +sp.lon], { icon: L.divIcon({ className: "live-pin", html: `<span>🎣 ${l.angler} · ${l.total}</span>`, iconSize: null }) })
        .on("click", () => onWatch(o.key)).addTo(g);
    }
    layers.current.live = g.addTo(m);
  }, [live, list]);

  // ---- GPS dot (only while the map is open)
  useEffect(() => {
    if (!active || !navigator.geolocation) return;
    const id = navigator.geolocation.watchPosition((p) => setGps({ lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy }), () => {},
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
    return () => navigator.geolocation.clearWatch(id);
  }, [active]);
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.gps?.remove(); if (!gps) return;
    layers.current.gps = L.layerGroup([L.circle([gps.lat, gps.lon], { radius: gps.acc, weight: 0, fillColor: "#2a7fff", fillOpacity: 0.12 }),
      L.circleMarker([gps.lat, gps.lon], { radius: 7, weight: 3, color: "#fff", fillColor: "#2a7fff", fillOpacity: 1 })]).addTo(m);
  }, [gps]);

  // ---- pending pin
  useEffect(() => {
    const m = map.current; if (!m) return;
    layers.current.pin?.remove(); if (!newPin) return;
    layers.current.pin = L.marker([newPin.lat, newPin.lon]).addTo(m);
  }, [newPin]);

  const saveHere = () => {
    if (gps) { setNewPin({ lat: gps.lat, lon: gps.lon, how: "gps" }); map.current?.setView([gps.lat, gps.lon], Math.max(map.current.getZoom(), 16)); return; }
    if (!navigator.geolocation) return toast("This phone isn't sharing its location — press and hold on the map instead");
    toast("Finding you…");
    navigator.geolocation.getCurrentPosition((p) => { const g = { lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy }; setGps(g); setNewPin({ ...g, how: "gps" });
      map.current?.setView([g.lat, g.lon], 16); }, () => toast("Couldn't get your location — press and hold on the map instead"), { enableHighAccuracy: true, timeout: 15000 });
  };
  const persist = async (spot, okMsg) => { if (await save((x) => x.saveSpot(spot), { ok: okMsg })) { reloadSpots(); return true; } return false; };
  const selSpot = list.find((s) => s.spot_id === sel) || null;
  const ranked = list.map((s) => ({ s, st: stats.spots[s.spot_id] })).filter((x) => x.st && x.st.hours >= 1).sort((a, b) => b.st.rate - a.st.rate);
  const filtersOn = (f.segments.length ? 1 : 0) + (f.season !== "any" ? 1 : 0) + (f.mine ? 1 : 0);

  return (
    <div className="screen map-screen" hidden={!active} id="screen-map">
      <Head kicker={`${list.length} saved spots · ${SEASONS[f.season]}${f.segments.length ? ` · ${f.segments.join(", ")}` : ""}`} title="Lake Map" onMenu={onMenu} demo={demo} />
      <div className="map-wrap">
        <div ref={box} className="map-box" />
        <div className="map-ctl">
          <button className="iconbtn" aria-label={f.satellite ? "Show plain map" : "Show satellite"} onClick={() => setF({ satellite: !f.satellite })}>{f.satellite ? "🗺️" : "🛰️"}</button>
          <button className={`iconbtn ${f.attractors ? "on" : ""}`} aria-label="Fish attractors on or off" onClick={() => setF({ attractors: !f.attractors })}>🪵</button>
          <button className={`iconbtn ${f.tries ? "on" : ""}`} aria-label="Spots to try on or off" onClick={() => setF({ tries: !f.tries })}>⭐</button>
          <button className={`iconbtn ${f.depth ? "on" : ""}`} aria-label="Depth contours on or off" onClick={() => setF({ depth: !f.depth })}>〰️</button>
          <button className="iconbtn" aria-label="Center on me" onClick={() => (gps ? map.current?.setView([gps.lat, gps.lon], Math.max(map.current.getZoom(), 15)) : saveHere())}>◎</button>
        </div>
        <div className="map-dock">
          <button className="btn primary big" onClick={saveHere}>📍 Save where I am</button>
          <button className="btn big" onClick={() => setPanel("filters")}>🔥 Hot spots{filtersOn ? ` (${filtersOn})` : ""}</button>
        </div>
        <div className="map-hint">{f.depth && level != null ? `Depths at today's level ${level.toFixed(1)} ft · solid = measured, dashed = estimated` : "Press and hold anywhere to pin a spot"}</div>
      </div>

      <NameSheet pin={newPin} onClose={() => setNewPin(null)} onSave={async (name, type) => {
        const now = new Date().toISOString().slice(0, 19);
        const spot = { spot_id: newId(), added_at: now, updated_at: now, name, lat: newPin.lat, lon: newPin.lon, location_type: type || "Other", bottom_structure: "",
          main_depth_ft: null, transition_depth_ft: null, transition_grade: "Medium", notes: "", added_by: me.name };
        if (await persist(spot, `Saved “${name}”`)) { setNewPin(null); setSel(spot.spot_id); }
      }} />

      <Sheet open={!!trySel} title={trySel ? `Worth a try: ${TRY_KINDS[trySel.kind][0]}` : ""} onClose={() => setTrySel(null)}>
        {trySel && <div className="setup">
          <p style={{ margin: 0 }}>{trySel.why}</p>
          {level != null && <p className="muted small" style={{ margin: 0 }}>About <b>{Math.max(0, Math.round(level - trySel.emax))}–{Math.max(0, Math.round(level - trySel.emin))} ft</b> deep at today's level ({level.toFixed(1)} ft){trySel.est ? " — partly estimated depth" : " — measured by lidar"}.</p>}
          <p className="muted small" style={{ margin: 0 }}>Picked from the lake's shape and the lidar bottom, not from catches — it's a suggestion to explore.</p>
          <button className="btn primary wide big" onClick={() => { setNewPin({ lat: trySel.lat, lon: trySel.lon, how: "try", type: TRY_KINDS[trySel.kind][1] }); setTrySel(null); }}>📍 Save as my spot</button>
          <a className="btn wide" href={`https://maps.apple.com/?daddr=${trySel.lat},${trySel.lon}`} target="_blank" rel="noopener noreferrer">Directions ↗</a>
        </div>}
      </Sheet>

      <Sheet open={!!selSpot && !editing} title={selSpot?.name || ""} onClose={() => setSel(null)}>
        {selSpot && <SpotPanel s={selSpot} st={stats.spots[selSpot.spot_id]} base={stats.base} f={f} onFish={() => onFishHere(selSpot.spot_id)} onEdit={() => setEditing(selSpot)} />}
      </Sheet>
      <EditSheet spot={editing} onClose={() => setEditing(null)} onSave={async (sp) => { if (await persist({ ...sp, updated_at: new Date().toISOString().slice(0, 19) }, "Saved")) setEditing(null); }}
        onDelete={async (sp) => { if (await save((x) => x.deleteSpot(sp.spot_id), { ok: `Deleted “${sp.name}”` })) { setEditing(null); setSel(null); reloadSpots(); } }} />

      <Sheet open={panel === "filters"} title="Hot spots" onClose={() => setPanel(null)}>
        <div className="setup">
          <div className="field">Time of day<div className="chips">
            <button className={`chip ${!f.segments.length ? "on" : ""}`} onClick={() => setF({ segments: [] })}>Any</button>
            {SEGMENTS.map((g) => { const on = f.segments.includes(g); return <button key={g} className={`chip ${on ? "on" : ""}`} onClick={() => setF({ segments: on ? f.segments.filter((x) => x !== g) : [...f.segments, g] })}>{g}{g === nowSeg ? " (now)" : ""}</button>; })}
          </div></div>
          <div className="field">Time of year<div className="chips">{Object.entries(SEASONS).map(([k, l]) => <button key={k} className={`chip ${f.season === k ? "on" : ""}`} onClick={() => setF({ season: k })}>{l}</button>)}</div></div>
          <div className="seg">{[[false, "Everyone's catches"], [true, "Just me"]].map(([v, l]) => <button key={l} className={f.mine === v ? "on" : ""} onClick={() => setF({ mine: v })}>{l}</button>)}</div>
          <button className="link" onClick={() => setF({ segments: [nowSeg], season: "now" })}>Right now: {nowSeg}, this time of year ›</button>
          <div className="legend">{HEAT_LEGEND.map(([c, l]) => <span key={l}><i style={{ background: c }} />{l}</span>)}</div>
          <div className="lr-h">Best spots for this filter</div>
          {ranked.length ? ranked.slice(0, 8).map(({ s, st }, i) => (
            <button key={s.spot_id} className="rank-row" onClick={() => { setPanel(null); setSel(s.spot_id); map.current?.setView([+s.lat, +s.lon], 16); }}>
              <i style={{ background: heatColor(st) }} /><span className="grow"><b>{i + 1}. {s.name}</b><span className="muted small block">{st.fish} fish in {Math.round(st.hours)} h · {st.sessions} sessions{st.lures[0] ? ` · best: ${st.lures[0].name}` : ""}</span></span>
              <b className="num">{st.rate.toFixed(1)}/hr</b></button>))
            : <p className="muted small">No logged fishing matches this filter yet — try "Any time".</p>}
          <p className="muted small">Fish per hour from the trip log, pulled toward the lake average ({stats.base.toFixed(1)}/hr) so thin data doesn't look hotter than it is.</p>
        </div>
      </Sheet>
    </div>
  );
}

function NameSheet({ pin, onClose, onSave }) {
  const [name, setName] = useState(""), [type, setType] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (pin) { setName(""); setType(pin.type || ""); setBusy(false); } }, [pin]);
  if (!pin) return null;
  return (
    <Sheet open title="Name this spot" onClose={onClose}>
      <form className="setup" onSubmit={async (e) => { e.preventDefault(); if (!name.trim()) return; setBusy(true); await onSave(name.trim(), type); setBusy(false); }}>
        <p className="muted small" style={{ margin: 0 }}>{pin.how === "gps" ? "📍 Where you are now" : pin.how === "try" ? "⭐ The suggested spot" : "📍 Where you pressed"} · {pin.lat.toFixed(5)}, {pin.lon.toFixed(5)}</p>
        <label className="field">Name<input type="text" value={name} autoFocus enterKeyHint="done" placeholder="e.g. Stripe Island Point" onChange={(e) => setName(e.target.value)} /></label>
        <div className="field">Type (optional)<div className="chips">{LOCATION_TYPES.map((t) => <button type="button" key={t} className={`chip ${type === t ? "on" : ""}`} onClick={() => setType(type === t ? "" : t)}>{t}</button>)}</div></div>
        <button className="btn primary wide big" disabled={!name.trim() || busy}>{busy ? "Saving…" : "Save spot"}</button>
        <p className="muted small" style={{ margin: 0 }}>Depths, bottom and notes can be added later from the spot.</p>
      </form>
    </Sheet>
  );
}

function SpotPanel({ s, st, base, f, onFish, onEdit }) {
  const bottom = (s.bottom_structure || "").split("|").filter(Boolean);
  return (
    <div className="setup">
      <p className="muted small" style={{ margin: 0 }}>{[s.location_type, bottom.join(", "), s.main_depth_ft && `main ${s.main_depth_ft} ft`, s.transition_depth_ft && `break to ${s.transition_depth_ft} ft (${s.transition_grade || ""})`].filter(Boolean).join(" · ") || "No details yet."}</p>
      {s.notes && <p className="small" style={{ margin: 0 }}>📝 {s.notes}</p>}
      <div className="three">
        <div className="award"><span className="v num">{st ? st.fish : 0}</span><span className="muted small">fish</span></div>
        <div className="award"><span className="v num">{st && st.hours >= 1 ? st.rate.toFixed(1) : "—"}</span><span className="muted small">fish / hr</span></div>
        <div className="award"><span className="v num">{st ? st.sessions : 0}</span><span className="muted small">sessions</span></div>
      </div>
      <p className="muted small" style={{ margin: 0 }}>For: {SEASONS[f.season].toLowerCase()}{f.segments.length ? `, ${f.segments.join("/")}` : ", any time of day"}{f.mine ? ", just you" : ", everyone"} · lake average {base.toFixed(1)}/hr{st?.last ? ` · last fish ${md(st.last)}` : ""}</p>
      {st?.lures.length > 0 && <div className="small"><b>Best lures here:</b> {st.lures.map((l) => `${l.name} (${l.fish} fish)`).join(" · ")}</div>}
      {st?.bestSegment && <div className="small"><b>Best time of day here:</b> {st.bestSegment}</div>}
      <button className="btn primary wide big" onClick={onFish}>🎣 Fish here now</button>
      <div className="two"><button className="btn" onClick={onEdit}>Edit details</button>
        <a className="btn" href={`https://maps.apple.com/?daddr=${s.lat},${s.lon}`} target="_blank" rel="noopener noreferrer">Directions ↗</a></div>
    </div>
  );
}

function EditSheet({ spot, onClose, onSave, onDelete }) {
  const [d, setD] = useState(null), [confirm, setConfirm] = useState(false);
  useEffect(() => { setD(spot ? { ...spot } : null); setConfirm(false); }, [spot]);
  if (!spot || !d) return null;
  const bottom = (d.bottom_structure || "").split("|").filter(Boolean);
  return <>
    <Sheet open={!confirm} title={`Edit ${spot.name}`} onClose={onClose}>
      <div className="setup">
        <label className="field">Name<input type="text" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
        <label className="field">Type<select value={d.location_type || "Other"} onChange={(e) => setD({ ...d, location_type: e.target.value })}>{LOCATION_TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
        <div className="field">Bottom<div className="chips">{BOTTOM_OPTIONS.map((b) => { const on = bottom.includes(b); return (
          <button type="button" key={b} className={`chip ${on ? "on" : ""}`} onClick={() => setD({ ...d, bottom_structure: (on ? bottom.filter((x) => x !== b) : [...bottom, b]).join("|") })}>{b}</button>); })}</div></div>
        <div className="two">
          <NumberBox label="Main area depth (ft)" value={d.main_depth_ft == null || d.main_depth_ft === "" ? null : Number(d.main_depth_ft)} min={0} max={200} placeholder="—" onChange={(v) => setD({ ...d, main_depth_ft: v })} />
          <NumberBox label="Drop-off depth (ft)" value={d.transition_depth_ft == null || d.transition_depth_ft === "" ? null : Number(d.transition_depth_ft)} min={0} max={200} placeholder="—" onChange={(v) => setD({ ...d, transition_depth_ft: v })} />
        </div>
        <label className="field">How fast it drops<select value={d.transition_grade || "Medium"} onChange={(e) => setD({ ...d, transition_grade: e.target.value })}>{GRADES.map((g) => <option key={g}>{g}</option>)}</select></label>
        <label className="field">Notes<textarea rows={3} value={d.notes || ""} onChange={(e) => setD({ ...d, notes: e.target.value })} /></label>
        <button className="btn primary wide big" disabled={!d.name.trim()} onClick={() => onSave({ ...d, name: d.name.trim() })}>Save</button>
        <button className="btn danger wide" onClick={() => setConfirm(true)}>Delete this spot</button>
      </div>
    </Sheet>
    <Sheet open={confirm} title="Delete this spot?" onClose={() => setConfirm(false)}>
      <div className="setup"><p>“{spot.name}” will be removed from the map for everyone. Trips logged there keep their records.</p>
        <button className="btn wide danger-solid" onClick={() => onDelete(spot)}>Delete</button><button className="btn wide" onClick={() => setConfirm(false)}>Keep it</button></div>
    </Sheet>
  </>;
}
