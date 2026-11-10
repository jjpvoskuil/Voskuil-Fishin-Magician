# Session log

## 2026-11-10 — Step 0 + foundation of the web app
- Studied the Streamlit app (9 pages, no sign-in, CSV data on the `data` branch, 13 own + 80 Cabela's lure images,
  secrets GITHUB_TOKEN + ANTHROPIC_API_KEY, feeds Open-Meteo/USGS/USACE/Cabela's). Reported to John.
- Decisions: keep repo public (data moves to Supabase; purge private data from git at cutover); put tables in the
  Deercast Supabase project (fm_* tables); Google branding renamed "Voskuil Outdoors"; design direction A "Lakeside Pro";
  automatic light/dark; anglers John + Matthew (admins), Alex.
- Built `web/` scaffold: theme tokens, Google sign-in against `fm_users`, tab bar, More page with angler admin, menu with
  appearance + build stamp, demo backend, Pages workflow, app icon. `schema.sql` (fm_users) RLS-tested on local PG 16
  alongside Deercast's schema (12 checks pass). Checked light/dark on simulated iPhone.
- Next: John enables Pages, runs schema, adds the redirect URL; then port the scoring engine.
- Later the same day: John finished setup (Pages on, schema in the Deercast project after a first run landed in Vixen
  Vault by mistake — cleaned up with drops of the fm_* objects; redirect URL; Google branding renamed Voskuil Outdoors,
  app already In production). Sign-in works on his phone. Added outdoors.html + privacy.html for the Google branding.
- Engine port started: astro, weather, onwater/thermocline, scoring, calibration — 8 parity test groups pass
  (moon, solunar, 500 segment-score combos, 8 synthetic forecast weeks, calibration); real trip log also matches.
- Fixed (John asked): water-temperature band gaps (62.1–62.9 and 76.1–76.9 °F fell to "Extreme Thermal Load" and lost their score bonus) — in core/onwater.py (old app gets it too) and lib/onwater.js.
- Ported lure recommendations (700 synthetic situations + 150 with John's real tackle box/trips match) and the daily/weekly leaderboard + awards.
