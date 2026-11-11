// Spot Session building blocks: conditions summary/form, tackle-box lure picker with the trailer question,
// and the log-a-fish panel. Every value you touch is tagged "you" in conditions.field_sources.
import { useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { NumberBox } from "./LakeSetup.jsx";
import { Sheet } from "./ui.jsx";
import { FORAGE_OPTIONS } from "./lib/lures.js";
import { LIGHT_CONDITIONS, LIGHT_CONDITION_INFO, PRECIPITATION_OPTIONS, STAIN_COLOR_OPTIONS, WIND_BANDS, WIND_BAND_LABELS, WIND_DIRECTIONS,
  visibilityBand, waterTempBand } from "./lib/onwater.js";
import { FISH_ACTIVITY_OPTIONS, FISH_SPECIES_OPTIONS, FORAGE_ACTIVITY_OPTIONS, HIT_TYPE_OPTIONS, LENGTH_OPTIONS, RETRIEVE_SPEED_OPTIONS,
  RETRIEVE_STYLE_OPTIONS, WEIGHT_LB_OPTIONS, WEIGHT_OZ_OPTIONS, canTakeTrailer, itemLabel, lengthInForDropdown, weightLbForDropdown } from "./lib/session.js";
import { LURE_CATEGORY_OPTIONS, isTrailerEligible } from "./lib/lures.js";
import * as S from "./lib/session.js";

const SHORT = { "Inactive / shut down": "Shut down", "Sluggish": "Sluggish", "Moderate": "Moderate", "Active": "Active", "Very active": "Very active",
  "None seen": "None", "Sparse / scattered": "Sparse", "Active / schooling": "Schooling", "Frenzied (busting bait)": "Busting" };
const SOURCE_LABEL = (s) => (s === "you" ? "" : s === "forecast" ? "forecast" : s === "estimate" ? "estimate" : s?.startsWith("shared:") ? `from ${s.slice(7)}` : "default");

export function conditionsSummary(c) {
  return [`${c.water_temp_f}°F`, `${c.secchi_ft} ft ${c.stirred_up ? "muddy" : visibilityBand(c.secchi_ft).label === "Stained" ? (c.stain_color || "").replace(" stained", "").toLowerCase() : visibilityBand(c.secchi_ft).label.toLowerCase()}`,
    `${c.wind_band.toLowerCase()} ${c.wind_direction}`, c.light_condition.toLowerCase(), c.precipitation === "None" ? "no rain" : c.precipitation.toLowerCase(),
    `fish ${(SHORT[c.fish_activity] || c.fish_activity).toLowerCase()}`].join(" · ");
}

function Steps({ label, options, value, onChange }) {
  return (
    <div className="field">{label}
      <div className="steps" role="radiogroup" aria-label={label}>
        {options.map((o) => <button type="button" key={o} role="radio" aria-checked={value === o} className={value === o ? "on" : ""} onClick={() => onChange(o)}>{SHORT[o] || o}</button>)}
      </div>
    </div>
  );
}
const Select = ({ label, value, options, onChange, src }) => (
  <label className="field"><span>{label}{src && <span className="src"> · {src}</span>}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)}>{options.map((o) => <option key={o}>{o}</option>)}</select>
  </label>
);

/** The full conditions form. cond = {values, sources}; onChange(field, value) marks the field as yours. */
export function ConditionsForm({ cond, onChange }) {
  const v = cond.values, src = (f) => SOURCE_LABEL(cond.sources[f]);
  const vis = visibilityBand(v.secchi_ft), band = waterTempBand(v.water_temp_f);
  return (
    <div className="setup">
      <div className="two">
        <NumberBox label={`Water temp (°F)${src("water_temp_f") ? ` · ${src("water_temp_f")}` : ""}`} value={v.water_temp_f} min={32} max={100} onChange={(x) => onChange("water_temp_f", x ?? 60)} />
        <NumberBox label={`Visibility (ft)${src("secchi_ft") ? ` · ${src("secchi_ft")}` : ""}`} value={v.secchi_ft} min={0} max={20} onChange={(x) => onChange("secchi_ft", x ?? 2.5)} />
      </div>
      <p className="muted small"><b>{band.label}</b> — {band.detail} <b>{vis.label}</b> — {vis.detail}</p>
      {vis.label === "Stained" && <div className="chips" role="radiogroup" aria-label="Stain color">
        {STAIN_COLOR_OPTIONS.map((o) => <button type="button" key={o} className={`chip ${v.stain_color === o ? "on" : ""}`} aria-pressed={v.stain_color === o} onClick={() => onChange("stain_color", o)}>{o}</button>)}
      </div>}
      <label className="check"><input type="checkbox" checked={v.stirred_up} onChange={(e) => onChange("stirred_up", e.target.checked)} /> Stirred up / muddy right now (recent wind or rain)</label>
      <div className="two">
        <Select label="Wind" value={v.wind_band} options={WIND_BAND_LABELS} onChange={(x) => onChange("wind_band", x)} src={src("wind_band")} />
        <Select label="Direction" value={v.wind_direction} options={WIND_DIRECTIONS} onChange={(x) => onChange("wind_direction", x)} src={src("wind_direction")} />
      </div>
      <p className="muted small">{WIND_BANDS.find((b) => b[2] === v.wind_band)?.[3]} {LIGHT_CONDITION_INFO[v.light_condition]?.range}</p>
      <div className="two">
        <Select label="Sky" value={v.light_condition} options={LIGHT_CONDITIONS} onChange={(x) => onChange("light_condition", x)} src={src("light_condition")} />
        <Select label="Rain" value={v.precipitation} options={PRECIPITATION_OPTIONS} onChange={(x) => onChange("precipitation", x)} src={src("precipitation")} />
      </div>
      <div className="field">Forage seen (optional)
        <div className="chips">{FORAGE_OPTIONS.map((f) => { const on = (v.forage_seen || []).includes(f); return (
          <button type="button" key={f} className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => onChange("forage_seen", on ? v.forage_seen.filter((x) => x !== f) : [...(v.forage_seen || []), f])}>{f}</button>); })}</div>
      </div>
      <Steps label="Fish activity" options={FISH_ACTIVITY_OPTIONS} value={v.fish_activity} onChange={(x) => onChange("fish_activity", x)} />
      <Steps label="Forage activity" options={FORAGE_ACTIVITY_OPTIONS} value={v.forage_activity} onChange={(x) => onChange("forage_activity", x)} />
      <NumberBox label="Depth fish are showing on electronics (ft, optional)" value={v.fish_depth_ft} step={1} min={0} max={100} placeholder="—" onChange={(x) => onChange("fish_depth_ft", x)} />
    </div>
  );
}

/** Search the tackle box and pick lures; asks about a trailer for lures that take one. */
export function LurePicker({ open, onClose, inventory, onPick, already }) {
  const [q, setQ] = useState("");
  const [trailerFor, setTrailerFor] = useState(null);
  const list = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (inventory || []).filter((i) => Number(i.quantity) > 0 || i.quantity === "" || i.quantity == null)
      .filter((i) => !t || `${i.brand} ${i.description} ${i.category}`.toLowerCase().includes(t))
      .sort((a, b) => itemLabel(a).localeCompare(itemLabel(b)));
  }, [inventory, q]);
  const pick = (it) => { const stub = { label: itemLabel(it), category: it.category || null, item_id: it.item_id };
    if (canTakeTrailer(it)) setTrailerFor(stub); else onPick(stub); };
  return <>
    <Sheet open={open && !trailerFor} title="Add from your tackle box" onClose={onClose}>
      <label className="field" style={{ paddingTop: 10 }}>Search<input type="text" value={q} placeholder="brand, name, color or type" onChange={(e) => setQ(e.target.value)} /></label>
      <div className="pick-list">
        {list.map((it) => { const added = already?.has(it.item_id); return (
          <button key={it.item_id} className="row" disabled={added} onClick={() => pick(it)}>
            <span className="grow">{itemLabel(it)}<div className="muted small">{it.category ? it.category.replace(/_/g, " ") : "no type"} · qty {it.quantity || "?"}</div></span>
            <span className={added ? "muted small" : "pill"}>{added ? "added" : "+ Add"}</span>
          </button>); })}
        {!list.length && <p className="muted">Nothing matches.</p>}
        <button className="row" onClick={() => { const label = q.trim(); if (label) pick({ item_id: null, brand: "", description: label, category: null }); }} disabled={!q.trim()}>
          <span className="grow">Not in the tackle box? Add "{q.trim() || "…"}" as typed</span><Icon name="plus" size={18} /></button>
      </div>
      <button className="btn primary wide" style={{ marginTop: 10 }} onClick={onClose}>Done</button>
    </Sheet>
    <TrailerSheet stub={trailerFor} inventory={inventory} onClose={() => setTrailerFor(null)} onDone={(s) => { setTrailerFor(null); onPick(s); }} />
  </>;
}

export function TrailerSheet({ stub, inventory, onClose, onDone }) {
  const [use, setUse] = useState(false);
  const [pickId, setPickId] = useState("");
  const [typed, setTyped] = useState("");
  const trailers = (inventory || []).filter(isTrailerEligible);
  if (!stub) return null;
  const finish = () => {
    let trailer = null;
    if (use) {
      const it = trailers.find((t) => t.item_id === pickId);
      trailer = it ? { item_id: it.item_id, label: itemLabel(it), category: it.category, color: it.description || "" } : typed.trim() ? { item_id: null, label: typed.trim(), category: null, color: null } : null;
    }
    setUse(false); setPickId(""); setTyped("");
    onDone({ ...stub, trailer });
  };
  return (
    <Sheet open title="Add a trailer?" onClose={onClose}>
      <div className="setup">
        <b>{stub.label}</b>
        <label className="check"><input type="checkbox" checked={use} onChange={(e) => setUse(e.target.checked)} /> Used a trailer with this lure</label>
        {use && <label className="field">Trailer
          <select value={pickId} onChange={(e) => setPickId(e.target.value)}><option value="">Type it in…</option>{trailers.map((t) => <option key={t.item_id} value={t.item_id}>{itemLabel(t)}</option>)}</select></label>}
        {use && !pickId && <label className="field">Trailer name<input type="text" value={typed} onChange={(e) => setTyped(e.target.value)} /></label>}
        <button className="btn primary wide" onClick={finish}>Add lure</button>
      </div>
    </Sheet>
  );
}

const LAST = "fm.lastFish";
/** Log a fish: species preselected (your last one), everything else optional; remembers retrieve. */
/** Dropdown values for a stored weight/length (edit mode). */
const lbOz = (w) => { if (!w) return ["", ""]; if (w >= 10.5) return ["10+", ""]; let lb = Math.floor(w), oz = Math.round((w - lb) * 16); if (oz === 16) { lb += 1; oz = 0; } return [String(lb), String(oz)]; };
const lenSel = (l) => (!l ? "" : l < 12 ? "<12" : l > 26 ? "26+" : String(Math.round(l)));

export function FishSheet({ lure, onClose, onSave, initial }) {
  return lure ? <FishForm key={initial ? JSON.stringify(initial) : "new"} lure={lure} onClose={onClose} onSave={onSave} initial={initial} /> : null;
}
function FishForm({ lure, onClose, onSave, initial }) {
  const last = (() => { try { return JSON.parse(localStorage.getItem(LAST)) || {}; } catch { return {}; } })();
  const known = initial && FISH_SPECIES_OPTIONS.includes(initial.species);
  const [species, setSpecies] = useState(initial ? (known ? initial.species : "Other (type in species)") : last.species || "Largemouth Bass");
  const [other, setOther] = useState(initial && !known ? initial.species || "" : "");
  const [w0, l0] = [lbOz(initial?.weight_lb), lenSel(initial?.length_in)];
  const [lb, setLb] = useState(w0[0]), [oz, setOz] = useState(w0[1]), [len, setLen] = useState(l0);
  const [hits, setHits] = useState(initial?.hit_types || []);
  const [style, setStyle] = useState(initial ? initial.retrieve_style || "" : last.style || ""), [speed, setSpeed] = useState(initial ? initial.retrieve_speed || "" : last.speed || "Medium");
  const save = () => {
    const weighed = lb !== "" || oz !== "";
    if (!initial) try { localStorage.setItem(LAST, JSON.stringify({ species, style, speed })); } catch { /* ignore */ }
    // in edit mode an untouched weight/length keeps its exact stored value (dropdowns are whole oz / whole inches)
    const weightLb = initial && lb === w0[0] && oz === w0[1] ? initial.weight_lb ?? null : weighed ? weightLbForDropdown(lb === "" ? 0 : lb, oz === "" ? 0 : oz) : null;
    const lengthIn = initial && len === l0 ? initial.length_in ?? null : len === "" ? null : lengthInForDropdown(len === "<12" || len === "26+" ? len : Number(len));
    onSave({ species, speciesOther: other, weightLb, lengthIn, hitTypes: hits, retrieveStyle: style || null, retrieveSpeed: speed || null });
  };
  return (
    <Sheet open title={`${initial ? "Edit fish" : "Log a fish"} · ${lure.lure_used}`} onClose={onClose}>
      <div className="setup">
        <button className="btn primary wide big" onClick={save}>{initial ? "Save changes" : "Save fish"}</button>
        <div className="field">Species
          <div className="chips">{FISH_SPECIES_OPTIONS.map((s) => <button type="button" key={s} className={`chip ${species === s ? "on" : ""}`} aria-pressed={species === s} onClick={() => setSpecies(s)}>{s.replace(" (type in species)", "…")}</button>)}</div>
        </div>
        {species === "Other (type in species)" && <label className="field">Species (type it in)<input type="text" value={other} onChange={(e) => setOther(e.target.value)} /></label>}
        <div className="three">
          <label className="field">Weight lb<select value={lb} onChange={(e) => setLb(e.target.value)}><option value="">—</option>{WEIGHT_LB_OPTIONS.map((o) => <option key={o} value={o}>{o} lb</option>)}</select></label>
          <label className="field">oz<select value={oz} onChange={(e) => setOz(e.target.value)}><option value="">—</option>{WEIGHT_OZ_OPTIONS.map((o) => <option key={o} value={o}>{o} oz</option>)}</select></label>
          <label className="field">Length<select value={len} onChange={(e) => setLen(e.target.value)}><option value="">—</option>{LENGTH_OPTIONS.map((o) => <option key={o} value={o}>{o === "<12" ? "Under 12 in" : o === "26+" ? "26+ in" : `${o} in`}</option>)}</select></label>
        </div>
        <div className="field">Type of hit (any that apply)
          <div className="chips">{HIT_TYPE_OPTIONS.map((h) => { const on = hits.includes(h); return <button type="button" key={h} className={`chip ${on ? "on" : ""}`} aria-pressed={on} onClick={() => setHits(on ? hits.filter((x) => x !== h) : [...hits, h])}>{h}</button>; })}</div>
        </div>
        <label className="field">Retrieve<select value={style} onChange={(e) => setStyle(e.target.value)}><option value="">—</option>{RETRIEVE_STYLE_OPTIONS.map((o) => <option key={o}>{o}</option>)}</select></label>
        <div className="field">Speed<div className="seg">{RETRIEVE_SPEED_OPTIONS.map((o) => <button type="button" key={o} className={speed === o ? "on" : ""} onClick={() => setSpeed(o)}>{o}</button>)}</div></div>
        <p className="muted small">Only the species is needed — weight, length and the rest are optional.</p>
      </div>
    </Sheet>
  );
}

/** "Rigged as" picker for soft plastics (drop shot, wacky, shaky head, Texas, Carolina, weightless). */
export function RigSelect({ category, onChange }) {
  if (!S.isSoftPlastic(category)) return null;
  return <label className="rig">Rigged as
    <select value={category} onChange={(e) => onChange(e.target.value)}>
      {S.SOFT_PLASTIC_RIGS.map((k) => <option key={k} value={k}>{RIG_NAMES[k] || k}</option>)}
    </select></label>;
}
const RIG_NAMES = Object.fromEntries(LURE_CATEGORY_OPTIONS);
