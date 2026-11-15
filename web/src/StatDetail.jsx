// The stat drop-down shown under a tapped row (punch #104 on the Leaderboard, #105 My Stats). Numbers from
// lib/groupstats.js; "use" = an outing it was fished in, success rate = share of those outings with a fish.
import { statTiles } from "./lib/groupstats.js";
import { formatDateShort } from "./lib/stringer.js";

export default function StatDetail({ stats, extra = null }) {
  if (!stats) return null;
  const span = stats.first ? (stats.first === stats.last ? formatDateShort(stats.first, true) : `${formatDateShort(stats.first, true)} – ${formatDateShort(stats.last, true)}`) : null;
  return (
    <div className="stat-detail">
      <div className="stat-tiles">{statTiles(stats).map(([k, v, n]) => (
        <div key={k}><span className="k">{k}</span><b className="num">{v}</b>{n && <span className="n">{n}</span>}</div>))}</div>
      {(span || extra) && <p className="muted small" style={{ margin: "8px 2px 0" }}>{[span && `Fished ${span}`, extra].filter(Boolean).join(" · ")}</p>}
    </div>
  );
}
