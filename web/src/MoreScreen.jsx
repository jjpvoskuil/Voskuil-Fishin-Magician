// More: the other pages (History, Leaderboard, Reports, Tackle Box, Punch list), the angler list (admins edit it),
// and the build stamp. Pages that aren't rebuilt yet say so.
import { useEffect, useState } from "react";
import Icon from "./Icon.jsx";
import { BUILD, Head } from "./Shell.jsx";

const PAGES = [["history", "Trip History", "history"], ["leaderboard", "Leaderboard", "trophy"], ["reports", "Reports", "chart"],
  ["tackle", "Tackle Box", "tackle"], ["punch", "Punch list", "tools"]];

export default function MoreScreen({ active, db, me, demo, onMenu, save, toast }) {
  const [users, setUsers] = useState(null);
  const [form, setForm] = useState(null); // {email, name, role, isNew}
  const admin = me?.role === "admin";
  const load = async () => { try { setUsers(await db.listUsers()); } catch (e) { toast(`Couldn't load anglers — ${e.message}`); } };
  useEffect(() => { if (active && users === null) load(); }, [active]);

  const submit = async (e) => {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) return toast("Enter a Google email address");
    if (!form.name.trim()) return toast("Enter a name");
    if (await save((d) => d.saveUser(form), { ok: "Saved" })) { setForm(null); load(); }
  };
  const remove = async (u) => {
    if (u.email === me.email) return toast("You can't remove yourself");
    if (!confirm(`Remove ${u.name}? They won't be able to open the app.`)) return;
    if (await save((d) => d.deleteUser(u.email), { ok: "Removed" })) load();
  };

  return (
    <div className="screen" hidden={!active} id="screen-more">
      <Head kicker="Fishin Magician" title="More" onMenu={onMenu} demo={demo} />
      <div className="body">
        <section className="card">
          {PAGES.map(([id, label, ic]) => (
            <button key={id} className="row" onClick={() => toast(`${label} is being rebuilt — use the old app for now`)}>
              <Icon name={ic} /><span className="grow">{label}</span><span className="muted small">soon</span>
            </button>
          ))}
        </section>

        <section className="card">
          <div className="card-h"><span className="t"><Icon name="user" />Anglers</span>
            {admin && !form && <button className="pill" onClick={() => setForm({ email: "", name: "", role: "member", isNew: true })}>Add</button>}</div>
          {users === null && <div className="empty">Loading…</div>}
          {users?.map((u) => (
            <div key={u.email} className="row">
              <span className="grow">{u.name} {u.role === "admin" && <span className="muted small">· admin</span>}
                <div className="muted small" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{u.email}</div></span>
              {admin && <button className="iconbtn" aria-label={`Edit ${u.name}`} onClick={() => setForm({ ...u, isNew: false })}><Icon name="chev" size={18} /></button>}
            </div>
          ))}
          {form && (
            <form className="card-b" onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10, borderTop: "1px solid var(--line-soft)" }}>
              <label className="field">Google email<input type="email" inputMode="email" autoCapitalize="none" value={form.email} disabled={!form.isNew}
                onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
              <label className="field">Name (shown on trips and the leaderboard)<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
              <div className="seg">{[["member", "Angler"], ["admin", "Admin"]].map(([r, l]) => (
                <button type="button" key={r} className={form.role === r ? "on" : ""} onClick={() => setForm({ ...form, role: r })}>{l}</button>))}</div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn primary" style={{ flex: 1 }}>Save</button>
                <button type="button" className="btn" onClick={() => setForm(null)}>Cancel</button>
                {!form.isNew && <button type="button" className="btn" aria-label="Remove" onClick={() => { const u = form; setForm(null); remove(u); }}><Icon name="trash" size={18} /></button>}
              </div>
            </form>
          )}
          {!admin && <div className="note muted small" style={{ padding: "10px 14px" }}>Only admins can add or remove anglers.</div>}
        </section>

        <p className="muted small" style={{ textAlign: "center", margin: "4px 0" }}>App updated {BUILD}</p>
      </div>
    </div>
  );
}
