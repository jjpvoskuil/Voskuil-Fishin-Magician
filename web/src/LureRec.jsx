// Lure plan display: top picks from your tackle box, tackle-box gaps, and the reasoning — the same content as the
// old app's render_lure_recommendation / render_lure_block. Cabela's suggestions come back with the Tackle Box screen.
import { curateRecommendation } from "./lib/lures.js";
import { pyFixed } from "./lib/py.js";

const lureImage = (it) => it.image_src || it.image_url || null; // own photos (image_src) arrive with the Tackle Box move

export function LureBlock({ block }) {
  return (
    <article className="lure">
      <h4>{block.name}</h4>
      {block.why.length > 0 && <p className="muted small">💡 Why: {block.why.join(" ")}</p>}
      {block.note && <p className="lure-note">{block.note}</p>}
      {block.owned_items.length > 0 ? (
        <div className="owned">
          <b className="ok">✅ In your tackle box:</b>
          {block.owned_items.map((it, i) => (
            <div key={it.item_id || i} className="owned-i">
              {lureImage(it) && <img src={lureImage(it)} alt="" loading="lazy" referrerPolicy="no-referrer" />}
              <span><b>#{i + 1}</b> {it.brand} – {it.description} <span className="muted">(qty {it.quantity})</span>
                {it._item_fish_per_hour ? <span className="ok"> — 📈 {pyFixed(it._item_fish_per_hour, 1)} fish/hr (your history)</span> : null}</span>
            </div>
          ))}
        </div>
      ) : block.owned_off_color_items.length > 0 ? (
        <p className="lure-note">🎣 Already in your tackle box, just not today's suggested color: {block.owned_off_color_items.slice(0, 2).map((it) => `${it.brand} – ${it.description}`).join("; ")}</p>
      ) : (
        <p className="muted small">🛒 Not in your inventory yet — worth picking one up for this presentation.</p>
      )}
      <dl className="lure-facts">
        <dt>Colors</dt><dd>{block.colors.join(", ")}</dd>
        {block.trailer && <><dt>Trailer</dt><dd>{block.trailer.type} — {block.trailer.colors.join(", ")}</dd></>}
        <dt>Depth</dt><dd>{block.depth}</dd>
        <dt>How</dt><dd>{block.presentation}</dd>
      </dl>
      <p className="small vids">📺 {block.videos.map((v, i) => <span key={v.url}>{i > 0 && " · "}<a href={v.url} target="_blank" rel="noopener noreferrer">{v.title}</a></span>)}</p>
    </article>
  );
}

export default function LureRec({ rec, inventory }) {
  const c = curateRecommendation(rec, inventory);
  return (
    <div className="lurerec">
      {c.recommended.length > 0 ? <>
        <div className="lr-h">🎣 Top picks from your tackle box</div>
        {c.recommended.map((b) => <LureBlock key={b.key} block={b} />)}
      </> : <p className="note-bar">Nothing in your tackle box is a strong fit for this exact situation yet — see the tackle box gaps below for what would rank well.</p>}
      {c.gaps.length > 0 && (
        <details className="gaps">
          <summary>🧰 Tackle box gaps worth a look ({c.gaps.length})</summary>
          <p className="muted small">Not in your tackle box today, but ranked among the best-fit lures for this exact situation — real alternatives worth considering, not a generic shopping list.</p>
          {c.gaps.map((b) => <LureBlock key={b.key} block={b} />)}
        </details>
      )}
      {rec.rationale.length > 0 && <p className="muted small rationale">{rec.rationale.join(" · ")}</p>}
    </div>
  );
}
