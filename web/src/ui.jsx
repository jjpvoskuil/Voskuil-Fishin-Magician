// Small shared UI pieces: bottom sheet, score breakdown, score ring, time/number formatting.
import { useEffect } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon.jsx";
import { parts, pyRound } from "./lib/py.js";

/** naive µs → "6:12 AM" */
export function fmtTime(us) {
  if (us == null) return "—";
  const { h, mi } = parts(us);
  return `${((h + 11) % 12) + 1}:${String(mi).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}
/** Python's f"{x:g}" for the numbers we show (no trailing zeros, up to 6 significant digits) */
export const fmtG = (x) => String(Number(Number(x).toPrecision(6)));
export const signed = (x, digits = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(digits)}`;
export const ago = (ms) => { const m = Math.round((Date.now() - ms) / 60e3); return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };

/** Bottom sheet over the screen. */
export function Sheet({ open, title, onClose, children }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  // rendered on <body>: each screen is its own fixed layer, so a sheet inside it would sit under the tab bar
  return createPortal(
    <div className="sheet-scrim" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-h"><b>{title}</b><button className="iconbtn" aria-label="Close" onClick={onClose}><Icon name="x" size={18} /></button></div>
        <div className="sheet-b">{children}</div>
      </div>
    </div>, document.body);
}

/** "How this score was derived" — the same rows and wording as the old app's ℹ️ popover. */
export function Breakdown({ breakdown, score }) {
  let raw = 0;
  for (const [, d] of breakdown) raw += d;
  return (
    <div className="bd">
      {breakdown.map(([label, d, detail], i) => (
        <div className="bd-row" key={i}>
          <span className={`bd-d num ${label === "Base" ? "" : d > 0 ? "up" : d < 0 ? "down" : ""}`}>{label === "Base" ? fmtG(d) : `${d >= 0 ? "+" : ""}${fmtG(d)}`}</span>
          <span className="bd-t"><b>{label}</b><span className="muted">{detail}</span></span>
        </div>
      ))}
      <div className="bd-total">
        <span>Score</span><span className="num">{score}/10</span>
      </div>
      {pyRound(raw, 1) !== score && <p className="muted small">Raw total {fmtG(raw)} is clamped to the 1-10 range.</p>}
    </div>
  );
}

/** Ring showing a 1–10 score. */
export function ScoreRing({ score, size = 92 }) {
  const pct = Math.max(0, Math.min(100, score * 10));
  return (
    <div className="ring" style={{ width: size, height: size, background: `conic-gradient(var(--accent) 0 ${pct}%, var(--accent-track) ${pct}% 100%)` }}
      role="img" aria-label={`Score ${score} out of 10`}>
      <div className="ring-in" style={{ width: size - 18, height: size - 18 }}>
        <span className="num" style={{ fontSize: size * 0.28, lineHeight: 1 }}>{score.toFixed(1)}</span>
        <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>of 10</span>
      </div>
    </div>
  );
}

export const verdict = (s) => (s >= 8 ? "Excellent day" : s >= 6.5 ? "Good day" : s >= 5 ? "Fair day" : s >= 3.5 ? "Tough day" : "Poor day");
