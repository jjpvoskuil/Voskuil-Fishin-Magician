// Tackle Box (old pages/5_Lure_Inventory.py): your lures by type with photos and how each has done, Scan a lure
// (photo → Claude reads brand/model/color/type → you confirm), add by hand, edit, quantity, and gap suggestions.
// The tackle box is shared by all anglers (fm_lures). Cabela's can't be searched live (they block it — tested 11-10):
// "Find on Cabela's" opens their search in a new tab; gap picks come from the old app's saved list.
import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { Head } from "./Shell.jsx";
import { Sheet } from "./ui.jsx";
import { newId } from "./lib/db.js";
import { guessCategoryFromText as guessEngineKey, itemLabel, LURE_PROFILES, NOT_SUGGESTED_ON_NOLIN } from "./lib/lures.js";
import { inventoryTypeOptions, servesKeys, toInventoryCategory } from "./lib/baits.js";
// The tackle box types soft plastics by bait style (#103), so a tagger guess like "texas_rig_worm" becomes "worm".
const guessCategoryFromText = (...t) => toInventoryCategory(guessEngineKey(...t));
import { blobB64, preparePhoto } from "./lib/photo.js";
import { cabelasSearchUrl, describeScan, groupByType, newItem, savedPicks, typeName, usageByLabel, usageFor } from "./lib/tackle.js";

const md = (d) => (d ? new Date(`${d}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) : "");
const usageText = (u) => (u ? `${u.fish} fish · ${u.hours >= 1 ? `${Math.round(u.hours)} h` : `${Math.round(u.hours * 60)} min`} fished${u.last ? ` · last ${md(u.last)}` : ""}` : "Not logged yet");

export default function TackleScreen({ active, db, me, trips, lures, reloadLures, onBack, onMenu, demo, toast, save }) {
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(false);
  const [edit, setEdit] = useState(null);   // {item?, draft, photo?, scan?, scanning?, error?}
  const [urls, setUrls] = useState({});
  const fileRef = useRef(null);
  const items = lures || [];
  const usage = useMemo(() => usageByLabel(trips, mine ? me.email : null), [trips, mine, me]);
  const thumbs = useMemo(() => items.map((i) => i.thumb_path).filter(Boolean), [items]);
  useEffect(() => { if (active && thumbs.length && db?.photoUrls) db.photoUrls(thumbs).then(setUrls).catch(() => {}); }, [active, thumbs.join("|")]);

  const shown = items.filter((i) => !q.trim() || `${i.brand} ${i.description} ${typeName(i.category)}`.toLowerCase().includes(q.trim().toLowerCase()));
  const groups = groupByType(shown);
  const owned = new Set(items.filter((i) => Number(i.quantity) > 0).flatMap((i) => servesKeys(i.category)));
  const gaps = Object.keys(LURE_PROFILES).filter((k) => !owned.has(k) && !NOT_SUGGESTED_ON_NOLIN.has(k) && savedPicks(k).length);
  const totalQty = items.reduce((a, i) => a + (Number(i.quantity) || 0), 0);

  // ---- scan / add
  const pickPhoto = async (file, forItem = null) => {
    if (!file) return;
    let photo;
    try { photo = await preparePhoto(file); } catch (e) { toast(e.message); return; }
    const preview = URL.createObjectURL(photo.thumb);
    const base = forItem ? { item: forItem, draft: { ...forItem } } : { item: null, draft: { brand: "", description: "", category: "", quantity: 1 } };
    setEdit({ ...base, photo, preview, scanning: true });
    try {
      const s = await db.scanLure(await blobB64(photo.full));
      setEdit((e) => e && { ...e, scanning: false, scan: s, draft: !s.visible ? e.draft : { ...e.draft,
        brand: e.draft.brand || s.brand, description: e.draft.description || describeScan(s),
        category: e.draft.category || toInventoryCategory(s.lure_type) || guessCategoryFromText(s.brand, s.product_name, s.search_query) } });
    } catch (err) { setEdit((e) => e && { ...e, scanning: false, error: err.message }); }
  };
  const saveItem = async () => {
    const e = edit, d = e.draft;
    if (!`${d.brand}${d.description}`.trim()) return toast("Add a brand or a name");
    const id = e.item?.item_id || newId();
    let paths = {};
    if (e.photo) { try { paths = await db.uploadLurePhoto(id, e.photo); } catch (err) { return toast(`Couldn't save the photo — ${err.message}`); } }
    const rec = e.item ? { ...e.item, ...d, quantity: String(d.quantity ?? 1), updated_at: new Date().toISOString().slice(0, 19), ...paths }
      : newItem({ ...d, ...paths, source: e.scan ? "Scanned" : "Manual" }, id);
    const old = e.item && e.photo ? [e.item.image_path, e.item.thumb_path] : [];
    if (await save((x) => x.saveLure(rec), { ok: e.item ? "Saved" : `Added ${itemLabel(rec)}` })) {
      if (old.some(Boolean)) db.removePhotos(old).catch(() => {});
      setEdit(null); reloadLures();
    }
  };
  const setQty = async (it, n) => { if (await save((x) => x.saveLure({ ...it, quantity: String(Math.max(0, n)), updated_at: new Date().toISOString().slice(0, 19) }))) reloadLures(); };
  const remove = async (it) => {
    if (await save((x) => x.deleteLure(it.item_id), { ok: `Removed ${itemLabel(it)}` })) { db.removePhotos([it.image_path, it.thumb_path]).catch(() => {}); setEdit(null); reloadLures(); }
  };

  if (!active) return null;
  return (
    <div className="screen" id="screen-tackle">
      <Head kicker={`More · ${items.length} lures, ${totalQty} in stock`} title="Tackle Box" onMenu={onMenu} demo={demo}>
        <button className="iconbtn" aria-label="Back to More" onClick={onBack}><Icon name="back" size={20} /></button>
      </Head>
      <div className="body">
        <div className="two">
          <button className="btn primary big" onClick={() => fileRef.current?.click()}>📷 Scan a lure</button>
          <button className="btn big" onClick={() => setEdit({ item: null, draft: { brand: "", description: "", category: "", quantity: 1 } })}>＋ Add by hand</button>
        </div>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; pickPhoto(f); }} />
        <p className="muted small" style={{ margin: "0 4px" }}>Scan: photograph the lure or its package — Claude reads the brand, model, color and type; you check it before it's saved.</p>

        <section className="card"><div className="card-b setup" style={{ paddingTop: 12 }}>
          <label className="field">Search your tackle<input type="search" value={q} placeholder="brand, name, color or type" onChange={(e) => setQ(e.target.value)} /></label>
          <div className="seg">{[[false, "Everyone's catches"], [true, "Just me"]].map(([v, l]) => <button key={l} className={mine === v ? "on" : ""} onClick={() => setMine(v)}>{l}</button>)}</div>
        </div></section>

        {lures === null ? <p className="muted">Loading your tackle box…</p> : !items.length ? <p className="note-bar">Nothing here yet — scan a lure or add one by hand.</p> : null}
        {groups.map((g) => (
          <details key={g.key || "none"} className="card tgroup" open={!!q.trim() || groups.length <= 4}>
            <summary className="card-h"><span className="t">{g.name}</span><span className="pill">{g.items.length}</span></summary>
            {g.items.map((it) => { const u = usageFor(usage, it), img = urls[it.thumb_path] || it.image_url, out = Number(it.quantity) <= 0; return (
              <div key={it.item_id} className={`titem ${out ? "out" : ""}`}>
                <button className="titem-main" onClick={() => setEdit({ item: it, draft: { brand: it.brand, description: it.description, category: it.category, quantity: Number(it.quantity) || 0 } })}>
                  {img ? <img src={img} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="tph"><Icon name="tackle" /></span>}
                  <span className="grow"><b>{it.brand}</b> {it.description}<span className="muted small block">{out ? "Out — none left · " : ""}{usageText(u)}</span></span>
                </button>
                <span className="qty">
                  <button aria-label={`One less ${itemLabel(it)}`} onClick={() => setQty(it, (Number(it.quantity) || 0) - 1)}>−</button>
                  <b className="num">{Number(it.quantity) || 0}</b>
                  <button aria-label={`One more ${itemLabel(it)}`} onClick={() => setQty(it, (Number(it.quantity) || 0) + 1)}>+</button>
                </span>
              </div>); })}
          </details>))}

        {gaps.length > 0 && <details className="card tgroup">
          <summary className="card-h"><span className="t">🎯 Fill your tackle gaps ({gaps.length} types)</span></summary>
          <div className="card-b">
            <p className="muted small" style={{ margin: 0 }}>Lure types you don't have in stock, with two Cabela's picks each (saved list — prices may have changed).</p>
            {gaps.map((k) => <div key={k} className="gap"><b>{typeName(k)}</b>
              {savedPicks(k).map((p) => <a key={p.sku} className="gap-i" href={cabelasSearchUrl(`${p.brand} ${p.description}`)} target="_blank" rel="noopener noreferrer">
                <img src={p.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" /><span className="grow small">{p.description}{p.price ? ` · $${p.price.toFixed(2)}` : ""}</span><span className="link">Cabela's ›</span></a>)}
            </div>)}
          </div>
        </details>}
      </div>

      <ItemSheet edit={edit} setEdit={setEdit} urls={urls} usage={usage} onSave={saveItem} onRemove={remove} onPhoto={(f) => pickPhoto(f, edit?.item)} items={items} />
    </div>
  );
}

function ItemSheet({ edit, setEdit, urls, usage, onSave, onRemove, onPhoto, items }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const photoRef = useRef(null);
  useEffect(() => { setConfirm(false); setBusy(false); }, [edit?.item?.item_id, !!edit]);
  if (!edit) return null;
  const { item, draft: d, scan, scanning, error, preview } = edit;
  const set = (patch) => setEdit({ ...edit, draft: { ...d, ...patch } });
  const img = preview || urls[item?.thumb_path] || item?.image_url;
  // same brand and one name contains the other ("KVD 1.5 - Sexy Shad" vs "KVD 1.5 - Sexy Shad, 1/2 oz")
  const norm = (x) => (x || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const dup = !item && d.description && items.find((i) => norm(i.brand) === norm(d.brand) && norm(i.description) && (norm(i.description).includes(norm(d.description)) || norm(d.description).includes(norm(i.description))));
  const u = item ? usageFor(usage, item) : null;
  return <>
    <Sheet open={!confirm} title={item ? itemLabel(item) : scan || scanning ? "Scanned lure" : "Add a lure"} onClose={() => setEdit(null)}>
      <div className="setup">
        <div className="tphoto">{img ? <img src={img} alt="" referrerPolicy="no-referrer" /> : <span className="tph big"><Icon name="tackle" /></span>}
          <button className="btn" onClick={() => photoRef.current?.click()}>{img ? "Change photo" : "Add a photo"}</button>
          <input ref={photoRef} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; onPhoto(f); }} /></div>
        {scanning && <p className="note-bar">🔎 Reading the photo…</p>}
        {scan && !scan.visible && <p className="warn">Couldn't make out a lure in that photo — try again closer, or fill it in by hand.</p>}
        {scan?.visible && <p className="muted small">Filled in from the photo — check it before saving.{scan.notes ? ` ${scan.notes}` : ""}</p>}
        {error && <p className="warn">{error} You can still fill it in by hand.</p>}
        {dup && <p className="note-bar">Looks like you already have this: {dup.description} (qty {dup.quantity}). <button className="link" onClick={() => setEdit({ item: dup, draft: { ...dup, quantity: (Number(dup.quantity) || 0) + 1 } })}>Add one more to that instead ›</button></p>}
        <label className="field">Brand<input type="text" value={d.brand || ""} onChange={(e) => set({ brand: e.target.value })} /></label>
        <label className="field">Name, color, size<input type="text" value={d.description || ""} onChange={(e) => set({ description: e.target.value })} /></label>
        <div className="two">
          <label className="field">Type<select value={d.category || ""} onChange={(e) => set({ category: e.target.value })}>
            <option value="">— pick a type —</option>{inventoryTypeOptions(d.category).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
          <div className="field">How many<span className="qty big"><button type="button" onClick={() => set({ quantity: Math.max(0, (Number(d.quantity) || 0) - 1) })}>−</button>
            <b className="num">{Number(d.quantity) || 0}</b><button type="button" onClick={() => set({ quantity: (Number(d.quantity) || 0) + 1 })}>+</button></span></div>
        </div>
        {!d.category && (d.brand || d.description) && guessCategoryFromText(d.brand, d.description) && <button className="link" onClick={() => set({ category: guessCategoryFromText(d.brand, d.description) })}>
          Looks like a {typeName(guessCategoryFromText(d.brand, d.description))} — use that ›</button>}
        {u && <p className="muted small">📈 {usageText(u)} across {u.sessions} session{u.sessions === 1 ? "" : "s"}.</p>}
        <button className="btn primary wide big" disabled={busy || scanning} onClick={async () => { setBusy(true); await onSave(); setBusy(false); }}>{busy ? "Saving…" : item ? "Save changes" : "Add to tackle box"}</button>
        {(d.brand || d.description) && <a className="btn wide" href={cabelasSearchUrl(scan?.search_query || `${d.brand} ${d.description}`)} target="_blank" rel="noopener noreferrer">Find on Cabela's ↗</a>}
        {item && <button className="btn danger wide" onClick={() => setConfirm(true)}>Remove from tackle box</button>}
      </div>
    </Sheet>
    <Sheet open={confirm} title="Remove this lure?" onClose={() => setConfirm(false)}>
      <div className="setup"><p>{item && itemLabel(item)} will be removed from the tackle box (past trips keep their records). If you just ran out, set the count to 0 instead.</p>
        <button className="btn wide danger-solid" onClick={() => onRemove(item)}>Remove</button><button className="btn wide" onClick={() => setConfirm(false)}>Keep it</button></div>
    </Sheet>
  </>;
}
