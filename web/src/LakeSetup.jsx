// "Lake setup" options for lure picks (old app's sidebar): water visibility → clarity, location/structure, water
// temperature, fish depth, forage. Kept on this phone between visits.
import { useState } from "react";
import { resolveWaterClarity, visibilityBand, STAIN_COLOR_OPTIONS } from "./lib/onwater.js";
import { FORAGE_OPTIONS, STRUCTURE_TYPES } from "./lib/lures.js";

export const OTHER_LOCATION = "__other";
export const LOCATION_TYPE_TO_STRUCTURE_TYPE = {
  "Main-lake point": "Main-lake point", "Secondary / pocket point": "Main-lake point", "Flat": "Flat", "Creek channel / ledge": "Creek channel / ledge",
  "Rock face / bluff": "Riprap / dam face", "Riprap": "Riprap / dam face", "Boat dock": "Boat dock", "Bridge piling": "Bridge piling",
  "Cove / pocket (shallow cover)": "Cove / pocket (shallow cover)", "Standing timber": "Standing timber", "Roadbed / old ford": "Flat", "Other": "Main-lake point",
};
const KEY = "fm.setup";
const DEFAULTS = { secchi: 2.5, stain: STAIN_COLOR_OPTIONS[0], stirred: false, location: OTHER_LOCATION, structure: STRUCTURE_TYPES[0], waterTemp: null, fishDepth: 8, forage: [] };

export function useLakeSetup() {
  const [setup, setState] = useState(() => { try { return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY)) || {}) }; } catch { return DEFAULTS; } });
  const set = (patch) => setState((s) => { const n = { ...s, ...patch }; try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  return [setup, set];
}

/** Resolve the setup into recommend() inputs. defaultTemp = today's estimated water temp. */
export function resolveSetup(setup, spots, defaultTemp) {
  const band = visibilityBand(setup.secchi).label;
  const clarity = resolveWaterClarity(setup.secchi, band === "Stained" ? setup.stain : null, setup.stirred);
  const spot = setup.location !== OTHER_LOCATION ? (spots || []).find((s) => s.spot_id === setup.location) : null;
  const structure = spot ? (LOCATION_TYPE_TO_STRUCTURE_TYPE[spot.location_type] || STRUCTURE_TYPES[0]) : setup.structure;
  return { clarity, band, structure, spot, waterTemp: setup.waterTemp ?? defaultTemp, fishDepth: setup.fishDepth, forage: setup.forage };
}

/** Text box with a number keypad that selects its contents on tap (iPhone won't do that for type="number"). */
export function NumberBox({ label, value, onChange, step = 0.5, min, max, placeholder }) {
  const [text, setText] = useState(value == null ? "" : String(value));
  const [lastValue, setLastValue] = useState(value);
  if (value !== lastValue) { setLastValue(value); setText(value == null ? "" : String(value)); }
  const commit = (t) => {
    if (t.trim() === "") { onChange(null); return; }
    let v = Number(t); if (!Number.isFinite(v)) { setText(value == null ? "" : String(value)); return; }
    if (min != null) v = Math.max(min, v); if (max != null) v = Math.min(max, v);
    v = Math.round(v / step) * step; v = Number(v.toFixed(2)); setText(String(v)); onChange(v);
  };
  return (
    <label className="field">{label}
      <input type="text" inputMode="decimal" value={text} placeholder={placeholder} onFocus={(e) => e.target.select()}
        onChange={(e) => setText(e.target.value)} onBlur={(e) => commit(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }} />
    </label>
  );
}

export function LakeSetupForm({ setup, set, spots, defaultTemp }) {
  const r = resolveSetup(setup, spots, defaultTemp);
  const vis = visibilityBand(setup.secchi);
  return (
    <div className="setup">
      <NumberBox label="Water visibility / Secchi depth (ft)" value={setup.secchi} min={0} max={20} onChange={(v) => set({ secchi: v ?? 2.5 })} />
      <p className="muted small">Visibility band: <b>{vis.label}</b> ({vis.detail}) How far down you can see a light-colored lure.</p>
      {vis.label === "Stained" && (
        <label className="field">Stain color (Nolin normally runs greenish-brown, leaning brown)
          <select value={setup.stain} onChange={(e) => set({ stain: e.target.value })}>{STAIN_COLOR_OPTIONS.map((o) => <option key={o}>{o}</option>)}</select>
        </label>
      )}
      <label className="check"><input type="checkbox" checked={setup.stirred} onChange={(e) => set({ stirred: e.target.checked })} /> Stirred up / muddy right now (recent wind or rain)</label>
      <p className="muted small">Water clarity used: <b>{r.clarity}</b></p>
      <label className="field">Location
        <select value={setup.location} onChange={(e) => set({ location: e.target.value })}>
          {(spots || []).map((s) => <option key={s.spot_id} value={s.spot_id}>{s.name}</option>)}
          <option value={OTHER_LOCATION}>Other (pick structure manually)</option>
        </select>
      </label>
      {setup.location === OTHER_LOCATION || !r.spot ? (
        <label className="field">Structure type
          <select value={setup.structure} onChange={(e) => set({ structure: e.target.value })}>{STRUCTURE_TYPES.map((o) => <option key={o}>{o}</option>)}</select>
        </label>
      ) : <p className="muted small">Structure: <b>{r.structure}</b> (from this spot's saved type)</p>}
      <div className="two">
        <NumberBox label="Water temp (°F)" value={setup.waterTemp} min={32} max={100} placeholder={`${defaultTemp ?? ""} (est.)`} onChange={(v) => set({ waterTemp: v })} />
        <NumberBox label="Fish depth (ft)" value={setup.fishDepth} step={1} min={0} max={100} onChange={(v) => set({ fishDepth: v ?? 8 })} />
      </div>
      <p className="muted small">Nolin has no live water-temperature feed — leave it blank to use today's estimate ({defaultTemp ?? "—"}°F), or enter your own reading. Fish depth = where fish show on your electronics.</p>
      <div className="field">Forage available / being eaten
        <div className="chips">
          {FORAGE_OPTIONS.map((f) => { const on = setup.forage.includes(f); return (
            <button key={f} type="button" className={`chip ${on ? "on" : ""}`} aria-pressed={on}
              onClick={() => set({ forage: on ? setup.forage.filter((x) => x !== f) : [...setup.forage, f] })}>{f}</button>); })}
        </div>
      </div>
      <p className="muted small">Gizzard shad and bluegill are Nolin's documented forage base; add others you're actually seeing.</p>
    </div>
  );
}

export function setupSummary(r) {
  return [r.clarity, r.spot ? r.spot.name : r.structure, `${r.waterTemp}°F`, `fish ${r.fishDepth} ft`, r.forage.length ? r.forage.join(", ") : "no forage set"].join(" · ");
}
