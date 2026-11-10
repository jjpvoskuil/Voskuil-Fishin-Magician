# Fishin Magician — notes for Claude

John has no coding background: Claude writes all code and pushes straight to `main`; John does setup clicks, one screen
at a time, and confirms each. He wants direct, accurate answers. Keep this file current and append a dated entry to
`docs/SESSION_LOG.md` at the end of every session.

## What's happening (Nov 2026): moving off Streamlit
The Streamlit app (`app.py`, `home.py`, `pages/`, `core/`, `SESSION_NOTES.md`) is being rebuilt as a phone-first web
app in `web/`, the same way Deercast was (repo jjpvoskuil/Deercast is the finished reference). The Python stays as the
**reference**: every computation is ported to `web/src/lib/` as JavaScript with parity tests (`node --test`) against
fixtures generated from the Python. Until cutover, the live data is still on the Streamlit app's `data` branch.

- **https://jjpvoskuil.github.io/Voskuil-Fishin-Magician/** — React (Vite) in `web/`, published to **GitHub Pages** by
  `.github/workflows/pages.yml` on every push touching `web/` (build uses `BASE=/Voskuil-Fishin-Magician/`; use
  `import.meta.env.BASE_URL` / `%BASE_URL%` for any local asset path; manifest paths are relative). Never Netlify.
  Check a deploy: `gh run list --workflow pages.yml`. Build time shows in the menu and under More.
- **Supabase: the Deercast project** (`https://gzxobsvhzscouehlrxeg.supabase.co`), shared on purpose (free plan = 2
  projects; John may merge the apps later). This app uses ONLY `fm_*` tables and `fm_*` functions, its own allow-list
  `fm_users`, its own RLS; never touch Deercast's tables. Own auth storageKey `fm-auth`. Google sign-in screen branding
  is the shared Google client (Deercast's Google Cloud project), renamed "Voskuil Outdoors"; its home page and privacy
  links point at web/public/outdoors.html and privacy.html here (they cover both apps — keep them current).
- Anglers: John (jjpvoskuil@gmail.com, admin), Matthew (mattvoskuil@gmail.com, admin), Alex (akvoskuil94@gmail.com).
- Theme: "Lakeside Pro" (direction A, picked 11-10) — all colors/fonts/spacing in `web/src/styles.css` tokens; light by
  day, dark 30 min before sunset → 30 min after sunrise (`lib/theme.js`), manual override in the menu.
- Data layer: `web/src/lib/db.js` — `supabaseDb` and a browser-only `demoDb` (made-up data, `?demo`). The sandbox can't
  reach Supabase: build/test against demo. Check screens with Playwright (iPhone 13, light + dark;
  `/usr/bin/google-chrome`; run `vite preview` WITH `BASE=/Voskuil-Fishin-Magician/`).
- Schema: `web/supabase/schema.sql`, re-runnable. Test RLS first on local Postgres 16:
  `source web/supabase/test/local_pg.sh` then run Deercast's schema + ours + `test/test_*.sql` (outsider, signed out,
  member, admin; Deercast-only user must see nothing). Upserts must also pass the SELECT policy.
- Tabs: Today · Forecast · Session · Map · More (History, Leaderboard, Reports, Tackle Box, Punch list under More).

## Plan (order agreed 11-10)
1. Foundation (done 11-10: scaffold, theme, sign-in + fm_users, Pages workflow). 2. Port the engine (scoring, lures,
calibration, astro, thermocline, weather/lake-level parsing) with parity fixtures. 3. Today + 7-Day Forecast.
4. Spot Session + Trip History. 5. Tackle Box (photos in private bucket `fm-lures`, scan via Edge Function holding
ANTHROPIC_API_KEY; Cabela's lookup may be blocked without browser-fingerprint impersonation — test early).
6. Lake Map (Leaflet satellite; bathymetry precomputed in Python, shipped static). 7. Leaderboard, Reports (Excel in
browser), Punch list. 8. make_import.py (+ one-time GitHub Action copying the 80 Cabela's lure images into the bucket),
backups (private repo, twice weekly), make_restore.py, cutover.
- Cutover also: delete the `data` branch, remove private `data/` files from `main` and purge them from history (needs
  John's OK for the force-push), revoke the Streamlit GITHUB_TOKEN, delete the Streamlit Cloud app.
- Later (John, 11-10): show him other home-screen icon options once everything else is done.
- Known oddity to raise, not silently fix: the Python scores "Season: Pre Spawn" in November (season looks keyed off
  water temp). Port as-is for parity.

## Engine port notes
- Ported so far (11-10): `lib/py.js` (Python-exact rounding/sum/time helpers), `astro.js`, `weather.js`, `onwater.js`
  (+ thermocline), `scoring.js`, `calibration.js`. Parity: `npm test` runs `engine.test.js` against
  `lib/fixtures/engine.fixtures.json` from `TZ=UTC python3 web/tools/make_engine_fixtures.py` (synthetic data only;
  regenerate after any Python change). Also verified on the real trip log locally (not committed).
- Exactness traps: naive datetimes = µs numbers; Python round()/f"{:.0f}" round exact ties to even (`pyRound`,
  `pyFixed`); Python 3.12+ `sum()` of floats is compensated (`pySum`); Python `%` is floor-mod (`pmod`); timedelta
  division/multiplication rounds µs half-even. Fixtures MUST be made with TZ=UTC (astro treats naive times as server
  local = UTC on Streamlit Cloud). Water-temp and wind band gaps FIXED 11-10 in both Python and JS (John asked); wind table/proxies unchanged.
- Also ported (11-10): `lures.js` (recommend/curate + lure_history + videos; data tables exported from the Python by
  `tools/export_lure_data.py` → `lib/data/lures.data.json` — re-run after editing core/lures.py or core/videos.py),
  `leaderboard.js` (daily_leaderboard + format_weight_lb_oz). Parity: `lures.test.js` vs
  `fixtures/lures.fixtures.json.gz` (`TZ=UTC python3 web/tools/make_lure_fixtures.py`); fixtures are gzipped.
- Still to port: stringer (Leaderboard page), reports, rest of activity_log, lake_level / lake_water_quality parsing
  (USACE needs an Edge Function — no CORS), forecast_freeze.

## Phone lessons (from Deercast)
Number boxes = text inputs with numeric keypad that select on tap (not type="number"). Screens scroll inside their own
container — scroll that to top. iPhone pauses GPS on lock/background (wake lock, restart watchPosition, 20 s watchdog,
save on hide). Users must fully close and reopen the home-screen app to get a new version.
