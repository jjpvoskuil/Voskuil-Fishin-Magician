// Pieces every screen shares: the screen header, the menu (appearance, account, build stamp) and the bottom tab bar.
import Icon from "./Icon.jsx";

export const TABS = [["today", "Today", "home"], ["forecast", "Forecast", "calendar"], ["session", "Session", "session"], ["map", "Map", "map"], ["more", "More", "more"]];
export const BUILD = typeof __BUILD__ === "undefined" ? "dev" : __BUILD__;
const fmtTime = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

/** Screen header: small uppercase line, big title, light/dark button (onMenu = flip the theme). */
export function Head({ kicker, title, onMenu, demo, children }) {
  return (
    <header className="head">
      <div>
        <div className="kicker">{kicker}{demo && <> <span className="demo">DEMO</span></>}</div>
        <h1>{title}</h1>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {children}
        <ThemeButton onFlip={onMenu} />
      </div>
    </header>
  );
}

/** Sun/moon button: shows what a tap switches TO. Reads the current theme from <html data-theme>. */
function ThemeButton({ onFlip }) {
  const dark = typeof document !== "undefined" && document.documentElement.dataset.theme === "dark";
  return (
    <button className="iconbtn theme" onClick={onFlip} aria-label={dark ? "Switch to light screen" : "Switch to dark screen"} title={dark ? "Light screen" : "Dark screen"}>
      <Icon name={dark ? "sun" : "moon"} size={20} />
    </button>
  );
}

/** Appearance choice (More page): Automatic follows sunrise/sunset; the header button overrides until the next switch. */
export function Appearance({ theme }) {
  return <>
    <div className="seg">
      {[["auto", "Automatic"], ["light", "Light"], ["dark", "Dark"]].map(([m, l]) => (
        <button key={m} className={theme.mode === m ? "on" : ""} onClick={() => theme.choose(m)}>{l}</button>
      ))}
    </div>
    <p className="muted small" style={{ margin: "8px 0 0", lineHeight: 1.45 }}>
      {theme.mode === "auto" && `Dark from ${fmtTime(theme.darkStart)} to ${fmtTime(theme.lightStart)} (30 min around sunset and sunrise). The sun/moon button at the top switches right away.`}
      {theme.mode === "temp" && `${theme.theme === "dark" ? "Dark" : "Light"} until ${fmtTime(theme.next)} (set with the sun/moon button), then automatic again.`}
      {(theme.mode === "light" || theme.mode === "dark") && "Stays this way until you pick Automatic."}
    </p>
  </>;
}

export function TabBar({ tab, onTab }) {
  return (
    <nav className="tabbar">
      {TABS.map(([id, label, ic]) => (
        <button key={id} className={tab === id ? "on" : ""} aria-current={tab === id ? "page" : undefined} onClick={() => onTab(id)}>
          <Icon name={ic} /><span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

/** Placeholder card for a screen that hasn't been rebuilt yet. */
export function NotYet({ what }) {
  return <div className="card"><div className="empty">{what} is being rebuilt.<br />Until then, keep using the old app for this.</div></div>;
}
