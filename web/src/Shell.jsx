// Pieces every screen shares: the screen header, the menu (appearance, account, build stamp) and the bottom tab bar.
import Icon from "./Icon.jsx";

export const TABS = [["today", "Today", "home"], ["forecast", "Forecast", "calendar"], ["session", "Session", "session"], ["map", "Map", "map"], ["more", "More", "more"]];
export const BUILD = typeof __BUILD__ === "undefined" ? "dev" : __BUILD__;
const fmtTime = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

/** Screen header: small uppercase line, big title, menu button. */
export function Head({ kicker, title, onMenu, demo, children }) {
  return (
    <header className="head">
      <div>
        <div className="kicker">{kicker}{demo && <> <span className="demo">DEMO</span></>}</div>
        <h1>{title}</h1>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {children}
        <button className="iconbtn" onClick={onMenu} aria-label="Menu"><Icon name="menu" size={20} /></button>
      </div>
    </header>
  );
}

export function Menu({ open, onClose, theme, me, onSignOut }) {
  if (!open) return null;
  return (
    <div className="menu" onClick={onClose}>
      <div className="menu-card" onClick={(e) => e.stopPropagation()}>
        <div className="menu-h">Appearance</div>
        <div className="seg">
          {[["auto", "Automatic"], ["light", "Light"], ["dark", "Dark"]].map(([m, l]) => (
            <button key={m} className={theme.mode === m ? "on" : ""} onClick={() => theme.choose(m)}>{l}</button>
          ))}
        </div>
        <div className="note">
          {theme.mode === "auto" && `Dark from ${fmtTime(theme.darkStart)} to ${fmtTime(theme.lightStart)} (30 min around sunset and sunrise).`}
          {theme.mode === "temp" && `${theme.theme === "dark" ? "Dark" : "Light"} until ${fmtTime(theme.next)}, then automatic.`}
          {(theme.mode === "light" || theme.mode === "dark") && "Stays this way until you pick Automatic."}
        </div>
        <div className="menu-h">Signed in</div>
        <div className="row" style={{ borderBottom: 0 }}><Icon name="user" /><span className="grow">{me?.name}<div className="muted small">{me?.email}</div></span></div>
        <button className="row" onClick={onSignOut} style={{ borderBottom: 0 }}><span className="grow">Sign out</span></button>
        <div className="note">App updated {BUILD}</div>
      </div>
    </div>
  );
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
