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
- Fixed (John asked): wind label gaps (3.5/9.5/16.5 mph showed "Heavy / Turbulent") in Python + JS; labels only, scores unchanged.
- Built the Today screen (score ring + why, best window + 6 segments with breakdowns, lake level, USACE oxygen, today/week awards + table). New tables fm_trips / fm_water_quality / fm_score_freeze with RLS (18 more checks pass). Edge Function fm-usace-wq written (John deploys it).
- USACE oxygen showed dashes: the Army Corps server omits its intermediate TLS certificate (and 403s python-requests' User-Agent), so the old Streamlit fetch had been failing since ~August too. Fixed in both the Edge Function and core/lake_water_quality.py; verified live from GitHub Actions (Oct 28 Dam Site: 0.56 mg/l DO, 6.4% sat).
- Built the 7-Day Forecast (week strip, day facts, segments with frozen past scores, per-segment lure picks, Lake setup). Added fm_lures + fm_spots tables (shared). Replaced the header menu with a sun/moon light/dark button (John's ask); appearance + sign-out moved to More.
- Keyboard safety (John's ask): inputs scroll into the visible area above the iPhone keyboard, sheets sit on top of it; tools/keyboard_check.py verifies all 7 current inputs (caught and fixed the More → Add angler boxes being covered).
- Season fix (John asked): November 50-60F was labeled Pre Spawn (+1.3) and June 72-75F Fall Feed Up. Fall now checked first: Fall Turnover 58-65F (no bonus), new Late Fall 50-58F (+0.6, own lure plan); June-early Sept 60-75F = Post-Spawn/Summer. In both apps; tests + fixtures updated.
- Built Spot Session with all six speed-ups (GPS spot, conditions one-liner with per-field source, quick-add suggestions, same lures as last time, two-tap fish + Undo, offline-safe saving). Uses the signed-in angler, no picker. Found and fixed three sync bugs in testing (edits reverting after save, canceled session reappearing, 12:00 AM start time).
- Drop shot: John spotted that drop-shot sessions were logged as wacky rig. Cause: the auto-tagger matched "straight worm" → wacky before drop shot, so both Roboworm FAT Straight Worms were mis-tagged on import. Fixed the tagger (Python + JS) and corrected the live data branch (43 trip rows, 2 tackle-box items). Added a "Rigged as" choice for soft plastics in Session.
- Ned Rig (John): new lure type `ned_rig` (profile, colors, verified video, tagger: "ned rig"/"finesse trd"/"ned head"; shaky head also matches "shakey head"), added to the Session "Rigged as" choices; the 3 Z-Man Finesse TRDs in the tackle box re-tagged ned_rig on the data branch (no trips used them).
