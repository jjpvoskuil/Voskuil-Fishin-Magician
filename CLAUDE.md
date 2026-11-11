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
  day, dark 30 min before sunset → 30 min after sunrise (`lib/theme.js`). Header has a sun/moon button (John, 11-10:
  no menu) that flips until the next automatic switch; More → Screen has Automatic / Light / Dark; Sign out is on More.
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
4. Spot Session + Trip History (both done 11-10). Lure picks v2 done 11-10. More per-angler personalization as screens come over (John 11-10). 5. Tackle Box (photos in private bucket `fm-lures`, scan via Edge Function holding
ANTHROPIC_API_KEY; Cabela's lookup may be blocked without browser-fingerprint impersonation — test early).
6. Lake Map (phase A done 11-10; phase B contours + spots to try done 11-11). Data import (11-11, John: do it now): `tools/make_import.py OUTDIR` (always reads origin/data — main has STALE data/ copies) → fishin_magician_import.sql (upserts by id; tested twice on local PG: 377 trips 212 John/164 Matthew/1 Alex, 17 spots, 95 lures) + lure photo zip (13 photos → 26 jpgs for Storage fm-lures/lures/). Never commit the output; send to John. Re-run at cutover. 7. Leaderboard, Reports (Excel in
browser), Punch list. 8. make_import.py (+ upload the 13 own lure photos from data/lure_images to the fm-lures bucket),
backups (private repo, twice weekly), make_restore.py, cutover.
- Cutover also: delete the `data` branch, remove private `data/` files from `main` and purge them from history (needs
  John's OK for the force-push), revoke the Streamlit GITHUB_TOKEN, delete the Streamlit Cloud app.
- Later (John, 11-10): show him other home-screen icon options once everything else is done.
- Lake Map (John, 11-10, reviewed): satellite by default + switch to plain map, GPS dot. Main use = naming and pinning
  spots, so make that fast ("Save where I am" + press-and-hold, name first, details optional). Spot pins colored by
  catch; tap → spot panel (details, history, best lures/time, Fish here now, Edit). "Hotness" overlay filterable by
  time of day and time of year. Keep fish attractors layer (KDFWR). Others fishing now on the map. Explore contours
  again (failed before) and a layer suggesting structurally promising areas (points, steep breaks, channel bends).
  Unanswered (assumed yes): rank spots for today.
  Contours (John 11-10): must follow the lake level — store bottom ELEVATION, depth = live USGS pool level − bottom.
  Lidar (checked 11-10): KyFromAbove Phase 2 DEM (STAC https://spved5ihrl.execute-api.us-west-2.amazonaws.com/,
  collection dem-phase2, 2-ft COG tiles in EPSG:3089 US ft, public S3 s3://kyfromabove) was flown Dec 2022–Apr 2023
  with Nolin at ~495.8 ft (flat water value) → real bottom above 496 (summer-pool depths 0–19 ft). Phase 1 (2014) at
  510 ft. Below 496: John has no Quickdraw export (no SD card) → ESTIMATE (dashed, labeled): extend edge slopes inward,
  deepen along old channels (data/nolin_channel.json), cap by John's rule: most areas ≤35 ft at summer pool (≥480),
  channel near dam / a few holes 55–60 ft (~455–460). Sandbox can't reach S3: process in a GitHub Action.
- No-grass cleanup DONE 11-11 (John: Nolin is rocky, almost no vegetation): "over grass" wording in core/lures.py →
  rock/wood/timber/flats (re-exported lures.data.json + lure fixtures); `NOT_SUGGESTED_ON_NOLIN = {hollow_body_frog}`
  (Python + JS) keeps the frog out of tackle-box gaps / Cabela's gap picks — the type stays valid for tagging/logging.
- Map spot pins: no permanent name labels (John 11-11, clutter); only the tapped spot shows its name.
- Contour depth numbers (John 11-11): small labels on the drawn lines, on screen only, ~1 per 280 px, ≥75 px apart,
  max 45, round tens first; recomputed on moveend (`.depth-lbl`).
- Season fix (John, 11-10, both apps): fall (day > 250) is checked before the spring rules: 58-65 °F = Fall Turnover
  (no bonus), 50-58 °F = new **Late Fall** (+0.6 `season_late_fall_bonus`, own lure plan: jerkbait / mid crank /
  swimbait, then football jig / blade / lipless — labeled as a general pattern, not Nolin-documented); 60-75 °F
  June–early Sept = Post-Spawn/Summer (was Fall Feed Up). Old bug: Nov 50-60 °F was Pre Spawn (+1.3).

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
- Also ported: `lake.js` (USGS level, USACE report parsing + DO saturation). Still to port: rest of activity_log, forecast_freeze (table `fm_score_freeze` exists; Forecast screen applies it).

## Screens built
- Today (`TodayScreen.jsx`, 11-10). Shared live data is loaded once in App (`lib/live.js`: weather + USGS cached in
  localStorage 30 min; USACE via Edge Function `fm-usace-wq` = `web/supabase/functions/fm-usace-wq/index.ts`, a plain
  HTML proxy deployed from the Supabase dashboard (John pastes index.ts → Edge Functions → fm-usace-wq → Deploy; the USACE server omits
  its intermediate cert, so the function ships DigiCert's public intermediate via Deno.createHttpClient + a browser-like
  User-Agent, with 3 tries — same fix in core/lake_water_quality.py via core/certs/); readings logged add-only to `fm_water_quality`; trips from
  `fm_trips`). Sheets render through a portal on <body> (each `.screen` is its own fixed layer).
- 7-Day Forecast (`ForecastScreen.jsx`, 11-10): week strip, day facts, segments (tap for why, ended ones frozen via
  `lib/freeze.js` → `fm_score_freeze`), lure picks per segment (`LureRec.jsx`) driven by Lake setup (`LakeSetup.jsx`,
  kept in localStorage `fm.setup`; blank water temp = today's estimate, like the old default). Cabela's suggestions in
  lure blocks come back with the Tackle Box screen. Tackle box = `fm_lures`, spots = `fm_spots` (shared, any approved).
- Spot Session (`SessionScreen.jsx` + `SessionParts.jsx`, logic in `lib/session.js`, 11-10): you = the signed-in angler
  (no "who's fishing" picker; owner = email, conditions.angler = name). Setup (GPS picks the nearest saved spot ≤300 m,
  conditions one-liner + Edit with per-field `field_sources` you/forecast/estimate/shared:<angler>/default, suggested
  lures with + Add, "Same lures as last time", draft kept in localStorage `fm.sessionDraft`) → Live (+ Fish two taps,
  10 s Undo, Change = retire, Add a lure, Moved/conditions: in-place within 10 min else close+reopen rows, End, Cancel =
  delete) → Watch (others' open sessions, 20 s refresh). Every change saves as a trip row through `lib/outbox.js`
  (localStorage `fm.outbox`, retries). Soft plastics have a "Rigged as" picker (`SOFT_PLASTIC_RIGS`, incl. Ned Rig `ned_rig` added 11-10) — the rig is the
  lure_category the picks learn from. Walk-through: `python3 web/tools/session_flow.py OUTDIR` (demo seeds an open
  session for the demo angler, so it exercises Live, cancels, then Setup).
- Lure picks v2 (`lib/picks.js` + `picks.test.js`, John 11-10, NEW APP ONLY — core/lures.py unchanged): recommend()
  still supplies the Nolin seasonal pattern; buildPicks() ranks by similarity-weighted personal history: each lure
  stretch weighted by water temp (σ10 °F), time of year (σ35 days, any year), recency (half-life 540 d), clarity,
  time of day, structure, same spot ×2, wind band, and (Just me mode) other anglers ×0.35; stretches count ≥0.5 h
  (some were logged with seconds-long times); rates shrunk toward your weighted average with 2 "similar hours".
  Tiers: Proven (eff ≥2 h, >1.2× average), Steady (≥5 sessions, catches fish in ≥60–75% of similar sessions — the
  drop shot), Seasonal (pattern first choices), Worth a try (in the pattern, <2.5 similar h); "not producing" =
  ≥2.5 similar h and rarely any fish. Used in Forecast (`LureRec picks`) and Session quick-add (`QuickPicks`).
  Checked on the real log locally (Nov morning 55 °F: ChatterBait + jerkbait Proven, drop shot Steady).
- Boat & electronics (John 11-10): More → "Main boat in use / Boat stored" (`lib/prefs.js useElectronics`, localStorage
  `fm.electronics`, per phone). Stored = sessions/Moved use the estimated water temp (not editable) and no fish depth;
  rows get `conditions.electronics: false`. Boat went into storage 2026-10-20: the 5 data-branch trips from then were
  marked `electronics:false, water_temp_unreliable:true (+fish_depth_unreliable)`; picks ignore unreliable temps.
  (Oct 1-19 temps of 70-74 °F were real readings with the boat in use.)
- Picks mode (John 11-10): default = everyone's catches equally, same spot ×2; "Just me" (`usePicksMode`,
  `fm.picksMode`) weights other anglers ×0.35. Switch shown above picks in Forecast and Session.
- Fishing together (John 11-10): in Session setup, another angler's open session today offers "Fishing with X?" → use
  their spot + all conditions (sources `shared:<angler>`), my rows get `conditions.group_id` = their group (anchor =
  first session's id). Every start/move/conditions change stamps `conditions_set_at`; in Live each member polls every
  30 s and follows the newest change in the group (`S.groupMembers/newestInGroup/relocateRows`; same timestamp or
  identical conditions = no-op, so no ping-pong). "Fish apart" sets group_id `solo:<own id>` (each phone unlinks itself).
- Watching (John 11-10): Today shows an "On the water now" card per other angler's open session (refresh 60 s);
  tap → Session's Watch view (`S.liveSummary`: fish, biggest, fish/hr, conditions, lures, catches). Your own live
  session shows a one-line summary of others not in your group. App `watchReq` routes Today → Session.
- Trip History (`HistoryScreen.jsx`, logic `lib/history.js` + `history.test.js`, 11-10): More → Trip History (hash
  `#more/history`; More pages open via App `page` state, READY set in MoreScreen). Filters apply live and are remembered
  (localStorage `fm.historyFilters`): Everyone / Just me, date chips (default 30 days), more filters (angler, time of
  day, location, lure type, specific lure). Sessions grouped by session_id and split into legs (location + conditions
  snapshot). Tap → view; Edit/Delete only for your own sessions (admins: any) — date, per-leg spot/segment/structure/
  conditions (changed fields get field_sources "you"), per-lure name/type-rig/color/technique/trailer/notes, fish
  edit/remove/add (FishSheet `initial` keeps exact weights unless changed); predicted score never re-run. Angler isn't
  editable (owner = who logged it). One shared outbox (App `useOutbox`) for Session + History.
  Walk-through: `python3 web/tools/history_flow.py OUTDIR`.
- Tackle Box (`TackleScreen.jsx`, `lib/tackle.js`, `lib/photo.js` from Vixen Vault, 11-10): More → Tackle Box
  (`#more/tackle`). Groups by lure type (collapsed when >4 types; search opens them), photo thumbs (own photo via
  signed URL, else the Cabela's image_url, which loads fine cross-site), −/+ quantity (0 = out, kept), per-item usage
  from the trip log (Everyone / Just me), duplicate warning (same brand, one name contains the other). Scan a lure =
  photo shrunk on the phone (1600 px + 400 px thumb) → Edge Function `fm-lure-scan` (Claude vision, key in Supabase
  secret ANTHROPIC_API_KEY, optional ANTHROPIC_MODEL, default claude-sonnet-5-5 — which REJECTS forced tool_choice, so use "auto" like Vixen Vault; approved anglers only; generated by
  `node web/tools/build_scan_function.mjs` from lures.data.json — re-run after adding a lure type) → you confirm.
  Photos: private bucket `fm-lures` (`lures/<item_id>-<rnd>.jpg` + `_thumb.jpg`; policies in schema.sql, tested in
  `test/test_storage.sql` with a storage stub). Cabela's live search is impossible (11-10: their token endpoint blocks
  other websites via CORS and servers with 403 Access Denied, even Deno with browser headers), so: "Find on Cabela's"
  opens `cabelas.com/SearchDisplay#q=…` in a new tab, gap suggestions + not-owned lure blocks use the old curated list
  (`tools/export_cabelas_picks.py` → `lib/data/cabelas_picks.json`, public catalog info). No need to copy the 80
  Cabela's images into the bucket at cutover (they load directly); only the 13 own photos in data/lure_images need
  uploading by make_import.
- Lake Map (`MapScreen.jsx`, `lib/spotstats.js`, 11-10, phase A): Leaflet, Esri World Imagery satellite by default
  (+ Esri place labels), 🗺️/🛰️ switch to OpenStreetMap, 🪵 fish attractors (KDFWR, `lib/data/attractors.json`, public),
  ◎ center on me, GPS dot (watchPosition only while the map is open). Spot pins = circle markers colored by "heat"
  (spot fish/hr shrunk 2 h toward the lake average ÷ that average; gray = <1 h data), sized by sessions, name labels.
  🔥 Hot spots sheet: time-of-day chips, time of year (any / this time of year ±30 d / seasons), Everyone/Just me,
  "Right now" shortcut, legend, ranked best spots. Filters kept in localStorage `fm.mapFilters`. Pinning: "📍 Save
  where I am" (GPS) or press-and-hold (Leaflet contextmenu, tapHold) → NameSheet (name + optional type chip) → spot
  saved and its panel opens. Spot panel: details, fish / fish/hr / sessions for the filter, best lures, best time of
  day, Fish here now (writes `fm.sessionDraft` spot_id + switches to Session), Edit details (type, bottom chips, depths,
  grade, notes, delete), Directions (Apple Maps). Others fishing now = green pins → Watch. Walk-through:
  `python3 web/tools/map_flow.py OUTDIR` (tiles are blocked in the sandbox).
- Lake Map phase B (11-11): `tools/build_contours.py` run by `.github/workflows/build-contours.yml` (workflow_dispatch;
  it pushes contours.json + suggestions.json to side branch `depth-build` because the sandbox can't download artifacts;
  Claude copies them into `web/public/depth/` with `git fetch --force origin depth-build:refs/remotes/origin/depth-build`).
  100 lidar tiles read at 8 ft via COG overviews; lake = ground ≤516 ft connected to the dam (5,128 acres in the bbox);
  flat water per tile = the lidar water line (495.8–499.4 ft); estimate below it = edge slope (normalized-convolution
  smoothed, ~300 ft) × distance, leveling to floor 480 ft (455 ft along the old channel corridor), Gaussian smoothed;
  deepest ≈ 58 ft at summer pool. Lines: 2-ft elevation steps 456–514, est = below the lidar water line, tiny loops
  dropped (~2.2 MB). Map: 〰️ toggles depth; lines below today's USGS level only, depth = level − e, every 10/4/2 ft by
  zoom, colored by depth, dashed = estimated, tap for "N ft deep — measured/estimated". ⭐ spots to try
  (suggestions.json, 70: points / steep breaks / channel swings / flats by deep water, spaced ≥250 m, hidden within
  120 m of a saved spot): tap → why + depth range at today's level + Save as my spot (type preset) + Directions.
- Drop shot fix (11-10, John): the auto-tagger put "straight worm" → wacky before drop shot, so both Roboworm FAT
  Straight Worms were tagged wacky_rig_senko and every drop-shot session was logged as wacky. Tagger fixed (drop shot
  first, + "roboworm"); the `data` branch was corrected (43 trip rows + 2 tackle-box items → drop_shot; nothing in the
  log was a real wacky rig). Drop shot = 71 fish / 27 sessions — what earlier stats called "Senko".
- Leaderboard (`LeaderboardScreen.jsx`, 11-11): port of core/stringer.py = `lib/stringer.js` (parity `stringer.test.js` vs
  `fixtures/stringer.fixtures.json.gz` from `TZ=UTC python3 web/tools/make_stringer_fixtures.py`, which forces pandas'
  sorts to kind="stable" — default quicksort leaves ties in no fixed order). Ring of season stats (swipe / ‹ › / dots),
  six ranked tabs, catches-by-day bars, species mix. New: period This year / Last 30 days / All time + Everyone / Just me
  (localStorage `fm.leaderboard`). Biggest Fish shows species as the title (the Python repeats the weight).
  Custom boards (John 11-11, `CustomBoard.jsx` + `lib/boards.js` + `boards.test.js`, new app only): Measure (fish, lbs,
  biggest, longest, avg weight, fish/hr, outings) × Ranked by (angler, lure, lure type, color, spot, month, time of
  day, species, year, outing, each fish, none) × filters (species, lure types, lure/color text, spots, anglers, time
  of day, months, water temp, date range). "Ask for a board": Edge Function `fm-board-ask`
  (web/supabase/functions/fm-board-ask/index.ts, same ANTHROPIC_API_KEY secret) gets the question + the log's real
  species/lure types/spots/anglers and returns ONLY settings via tool set_board ("bass" = black bass, not white bass);
  `cleanSpec` whitelists them; numbers always computed on the phone. Fish/hr counts fishless hours; ≥0.5 h per stint.
  Saved boards → table `fm_saved` (kind board|report, private to owner; RLS `test/test_saved.sql`, 10 checks) → ★ tabs.
  Reports must get the same pattern (John 11-11): stock reports + typed custom report + save (kind 'report').
  Shared filter widgets `Multi` / `Pick` now live in ui.jsx.
- Reports (`ReportsScreen.jsx`, 11-11): engine `lib/reports.js` = port of core/reports.py (parity `reports.test.js` vs
  `fixtures/reports.fixtures.json.gz` from `TZ=UTC python3 web/tools/make_report_fixtures.py`, sorts forced stable;
  250 factor×metric cases + moon/pressure predictions). Settings layer `lib/reportspec.js` (STOCK list, cleanReportSpec,
  runReport: who/me by owner, new-app lure-type + spot filters, period This year / 90 / 30 days / All time or the
  spec's own from–to). Screen: stock tabs, ★ saved (fm_saved kind "report"), ＋ Custom (Ask = fm-board-ask with
  mode "report" → tool set_report; or pick Show × By + filters), horizontal bars (n < 4 faded), ⤓ Excel via
  `write-excel-file/browser` (sheets Report + Trips; iPhone share sheet when available), 🔮 Predict a day (next 7
  days: moon history lookup always, pressure lookup only inside the forecast window). Reports group by the spot
  NAME stored on each trip (as the old app did), not the current spot list.
- Punch list (`PunchScreen.jsx` + `PunchSheet.jsx` + `lib/punch.js` + `punch.test.js`, 11-11): table `fm_punch`
  (task_no int pk, owner, data) + `fm_punch_counter` via security-definer `fm_next_task_no()` (approved only; never
  reuses a number; RLS `test/test_punch.sql`, 14 checks): everyone approved reads/adds, admins edit/delete any, others
  their own. ✎ button in every screen Head (Shell `NoteCtx`, App `openNote`) opens PunchSheet with the screen + what was
  showing captured (`captureContext`: title, kicker, hash, theme, build, viewport); "✨ Tidy with Claude" = fm-board-ask
  mode "punch" (tool set_item: title/details/kind/priority/page; original words kept as `original`). "📋 Copy for
  Claude" = `exportText` (open items by status/priority, context line, author/date; optional recently closed).
  Import: make_import.py writes `punch_list_import.sql` (97 items from data/dev_tasks.csv, old page names mapped,
  counter continues at 99). Plan: backups also write the punch list to the private backup repo so Claude can read it.
- NEXT after this app (John 11-11): **Deercast shot recovery puts probable deer spots in the lake** — give its recovery
  model real water: Nolin's shoreline from the KyFromAbove lidar water line (as tools/build_contours.py finds it) or
  OSM water polygons; exclude/penalize water cells in Deercast `deercast/recovery.py` + `web/src/lib/recovery.js` (parity).
- App icon (John 11-11, picked "D2 + VO medallion"): Voskuil Outdoors family look shared with Deercast — dark forest
  field #1f2b22, patch band (teal #3d9a88 here, orange #e07b24 on Deercast) with small stars, cream "VO" medallion at
  6 o'clock, leaping largemouth (Deercast: its deer, ring removed). Generator `web/tools/make_icons.py OUTDIR
  --style medal` (SVG → Chrome → PNG 512/192/180/64; writes both apps' icons — copy deercast-medal-* into Deercast).
- Screenshots: `python3 web/tools/screens.py OUTDIR Today[,More…] [--click "Button name"]` (mocks Open-Meteo/USGS
  from the engine fixtures; needs the vite preview running).

## Keyboard rule (John, 11-10)
Every text box must stay visible above the iPhone keyboard. `ui.jsx useKeyboardSafeInputs()` (mounted in App) sets
`--kb` from visualViewport (sheets sit above it; screens get that much extra bottom room) and scrolls the focused box
into the middle of the still-visible area. When a screen gains inputs, add them to `web/tools/keyboard_check.py`
CASES and run it (fakes a 380 px iOS keyboard; the simulated iPhone 13 viewport is 390×664) — it must print
"ALL FIELDS VISIBLE ABOVE THE KEYBOARD". Still confirm on John's phone.

## Phone lessons (from Deercast)
Number boxes = text inputs with numeric keypad that select on tap (not type="number"). Screens scroll inside their own
container — scroll that to top. iPhone pauses GPS on lock/background (wake lock, restart watchPosition, 20 s watchdog,
save on hide). New versions (11-11): Pages lets phones cache the page ~10 min, so `lib/update.js` fetches
`version.json` (emitted by vite.config.js with the build stamp) on open / return to screen (≤1/min) and shows
"New version ready · Update" (reload with a fresh `?v=`). No close-and-reopen needed any more.
