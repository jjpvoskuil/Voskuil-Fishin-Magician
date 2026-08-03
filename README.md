# Voskuil Fishin' Magician 🎣

A 7-day largemouth bass fishing forecast app for **Nolin River Lake, KY**, built with Streamlit.

## What it does

- **1-10 daily activity score** for largemouth bass, built from barometric pressure trend,
  moon phase, solunar major/minor windows, cloud cover, wind, and season/water-temp estimate.
- **Time-of-day breakdown** (Dawn / Morning / Midday / Afternoon / Dusk / Night) with the
  best window(s) to fish each day.
- **Lure, color, and technique recommendations** for each time segment, tailored to season,
  water color/clarity, structure type, and (when you provide it) the depth you're marking
  fish at.
- **Zoomable contour map** of Nolin Lake with modeled depth contour lines - click
  *anywhere* on the lake (not just preset spots) to get a location-specific
  recommendation for any day/time in the forecast window.
- **Per-lure recommendation blocks** - each recommended lure (first choice, then a
  second-choice section) gets its own self-contained block: specific colors for that
  lure, trailer type/color if one applies, depth to run, presentation style, and a
  couple of how-to videos - all in one place. Depth guidance accounts for the fact that
  bass are upward-biased sight feeders (narrow binocular vision cone above/in front of
  the snout, blind below/behind, upward-hinging jaw) - reaction/"column" lures (crankbaits,
  jerkbaits, spinnerbaits, etc.) get a target running depth 1-2 ft *above* the depth
  you're marking fish at, while bottom-contact baits (jigs, Carolina rigs, etc.) get
  count-down-to-depth guidance instead.
- **Lake Setup Options sidebar** - two required, direct inputs since Nolin has no live
  feed for either: your water surface temp reading, and the depth you're marking fish
  at on your electronics (e.g. a Garmin Livescope/sonar unit). These always drive the
  seasonal pattern used for lure selection and the depth-to-run/countdown guidance on
  every lure block, and carry over across pages for the session.
- **Water color model** - Nolin normally runs a greenish-brown stain (leaning brown).
  Pick your usual base stain color (Clear / Green stained / Brown stained) plus a
  separate "stirred up / muddy" checkbox for after wind or heavy rain - the two combine
  into one effective water-clarity reading that drives lure color choice, independent
  of the base color you picked.
- **Thermocline depth input** - a required, direct sidebar input (like water temp and
  fish depth), pre-filled with a seasonal estimate (none in winter/early spring, forming
  through May-June, ~13-17 ft at peak summer, breaking down through September) but always
  editable with your own electronics/temp-probe reading. Flags a caveat on the lure
  recommendation if the depth you're marking fish at is below it (usually too
  oxygen-depleted to hold active bass). See "Data sources" below for how the estimate
  is built.
- **Forage selector** - pick which baitfish/prey are actually available (Gizzard Shad
  and Bluegill/Sunfish are pre-checked as documented Nolin forage; Crawfish and
  Shiners/Minnows are optional add-ons). Nudges lure color/pattern choice toward what
  the bass are actually keyed on, and makes sure at least one forage-matched lure
  shows up in the recommendation.
- **Trip logging** - record what actually happened (lures, catches, water conditions,
  forage seen) so the model can calibrate its weights against your own results over time.

## How the model works (and its limits)

This is a transparent, rule-based heuristic - not a black box and not a proprietary
fishing-app data feed. It's designed to be reasoned about, and to improve as you log
real trips. See `core/scoring.py` for the documented weights and `core/lures.py` for the
lure/color/technique rule table.

**Data sources:**
- Weather (temperature, pressure, cloud cover, wind, precipitation): [Open-Meteo](https://open-meteo.com/) - free, no API key.
- Moon phase & solunar rise/transit/set times: computed locally with a compact
  low-precision lunar-position algorithm (`core/astro.py`) - no external service or
  ephemeris download needed.
- Water temperature: **estimated**, not measured (Nolin Lake has no live buoy feed) -
  blended from recent air temperature and a seasonal baseline curve. Always shown as an
  estimate in the UI.
- Lake spot coordinates (`data/nolin_spots.json`): anchored to verified public sources
  (USACE gauge location, Kentucky State Parks/GNIS coordinate, U.S. Census TIGER address
  geocoding) with a few nearby fishing-relevant sub-spots offset from those anchors.
  **These are planning approximations, not survey-grade positions.** If you have exact
  waypoints from your own chartplotter/Navionics, edit that file to improve accuracy -
  it's the single source of truth the map and lure engine read from.
- Depth contours (`data/nolin_channel.json`, `core/bathymetry.py`): there is no free,
  downloadable full-lake bathymetric survey for Nolin Lake (checked USACE eHydro -
  navigation channels only - and USGS, which only has a partial 2016 water-quality
  study). Commercial charts exist but their data is proprietary and can't be scraped or
  embedded here. Instead, depth is **modeled** from a hand-defined river-channel
  centerline anchored at the same verified points as the spot list, with a Gaussian
  cross-section tapering to shore. It's clearly labeled as modeled in the app.

  It's also designed to improve with your own real soundings: if you record Garmin
  Quickdraw Contours, export them with [qdc-converter](https://github.com/interlark/qdc-converter)
  (`.qdc`/`.qcc` -> CSV of lon/lat/depth) and drop the CSV into `data/quickdraw/` (see
  that folder's README for the exact steps) - any number of files is fine, so you can
  add more as you explore more of the lake. `core/survey_points.py` loads and
  deduplicates every CSV there, and `core/bathymetry.py` blends the real readings into
  the modeled grid: real data wins (inverse-distance weighted) within ~50m of where you
  actually recorded it, fading smoothly back to the model beyond that, and can extend
  the map into coves/arms the hand-modeled channel doesn't cover at all. The Lake Map
  page's info box shows how many real points are currently blended in. Since it's your
  own recorded sonar data (not a scraped commercial chart), there's no copyright issue
  using it directly - it plugs into the same real basemap (streets/shoreline) the map
  already renders on, so it lines up automatically.
- Instructional videos (`core/videos.py`): a curated table of real, verified YouTube
  links per lure/technique. A couple of techniques without a confidently-verified direct
  link fall back to a live YouTube search link instead of a guessed URL.
- Summer/normal pool elevation used for the map context: 515 ft, ~5,795 surface acres
  (confirmed against USACE data), vs. ~2,890 acres at winter pool.
- Thermocline depth (`core/thermocline.py`): the sidebar input is a required, direct
  reading, but its default value is **modeled**, not measured - Nolin has no public
  real-time dissolved-oxygen/temperature profile buoy we can call for free (the USACE
  Louisville District's lake-profile tool has live readings per lake, but it's a
  manual web page, not an API). The default is anchored to a real, lake-specific data
  point: KDFWR (Kentucky Afield Outdoors, Lee McLellan, July 2019) reported Nolin's
  thermocline at about 15 ft in mid/late summer, grouped with Green River, Barren
  River, and Rough River as similar mid-depth, relatively clear hill-land reservoirs.
  Combined with general reservoir-stratification timing (none in winter/early spring,
  forming in May, established through summer, breaking down each fall) to seed a
  month-by-month default - override it any time with your own reading.
- Forage base (`core/lures.py`'s `FORAGE_OPTIONS`): gizzard shad and bluegill are
  explicitly documented as Nolin forage in Kentucky Afield Outdoors coverage of the
  lake's bass fishery; crawfish and shiners/minnows are near-universal secondary forage
  in Kentucky hill-land reservoirs (craw-pattern jig/worm colors are standard advice
  for this lake type) offered as optional add-ons.

## Trip logging & calibration

Logged trips are stored in `data/trip_log.csv`, inside the repo itself - no external
database required. When a `GITHUB_TOKEN` secret is configured (see below), each new log
entry is also committed and pushed back to this repo, so it survives Streamlit Cloud app
restarts/redeploys. Without a token, entries still work but only persist for that
session.

`core/calibration.py` compares catch outcomes between trips where a given factor (e.g.
"falling pressure") was present vs. absent, and nudges that factor's weight - capped at
+/-35% of its default - once you've logged at least 4 trips on each side. See the **Trip
History** page in the app for calibration status.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying on Streamlit Community Cloud

1. Push this repo to GitHub (already done if you're reading this from the repo).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, and click "New app".
3. Point it at `jjpvoskuil/Voskuil-Fishin-Magician`, branch `main`, main file `app.py`.
4. In the app's **Settings -> Secrets**, paste the contents of `secrets.toml.example`
   with your own fine-grained GitHub PAT (Contents: Read and write, scoped to just this
   repo) so trip logs can be committed back automatically.
5. Deploy. Streamlit Cloud auto-redeploys whenever you push new commits to `main`.

## Project layout

```
app.py                  Landing page - today at a glance
pages/
  1_7_Day_Forecast.py   Full week, drill into any day
  2_Lake_Map.py          Click-to-recommend map
  3_Log_a_Trip.py        Trip logging form
  4_Trip_History.py      Logged trips + calibration status
core/
  astro.py               Moon phase + solunar rise/transit/set
  weather.py              Open-Meteo integration + water-temp estimate
  scoring.py              1-10 activity scoring engine
  lures.py                Lure/color/technique rule engine
  spots.py                Lake map data + figure builder
  storage.py              Trip log read/write + git commit-back
  calibration.py          Weight calibration from logged trips
data/
  nolin_spots.json        Named lake spots (edit to add your own waypoints)
  trip_log.csv            Logged trips (grows over time)
tests/                    pytest unit tests for astro/scoring/lures
```

## Disclaimers

Forecast scores are a fishing-planning aid based on general bass-behavior heuristics,
not a guarantee. Water temperature is estimated, not measured. Map locations are
approximate. Always check current weather/lightning conditions before heading out.
