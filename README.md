# Voskuil Fishin' Magician 🎣

A 7-day largemouth bass fishing forecast app for **Nolin River Lake, KY**, built with Streamlit.

## What it does

- **1-10 daily activity score** for largemouth bass, built from barometric pressure trend,
  moon phase, solunar major/minor windows, cloud cover, wind, and season/water-temp estimate.
- **Time-of-day breakdown** (Dawn / Morning / Midday / Afternoon / Dusk / Night) with the
  best window(s) to fish each day.
- **Lure, color, and technique recommendations** for each time segment, tailored to season,
  water clarity, and structure type.
- **Zoomable contour map** of Nolin Lake with modeled depth contour lines - click
  *anywhere* on the lake (not just preset spots) to get a location-specific
  recommendation for any day/time in the forecast window.
- **Per-lure recommendation blocks** - each recommended lure (first choice, then a
  second-choice section) gets its own self-contained block: specific colors for that
  lure, trailer type/color if one applies, depth to run, presentation style, and a
  couple of how-to videos - all in one place.
- **Lake Setup Options sidebar** - optionally enter a real surface-temp reading and/or
  the depth you're marking fish at on your electronics (e.g. a Garmin Livescope/sonar
  unit). When provided, these override the app's estimates: a temp reading can shift
  the seasonal pattern used for lure selection, and a fish-depth reading re-ranks and
  annotates every lure block by how well its typical running depth matches what you're
  actually seeing. Both carry over across pages for the session.
- **Trip logging** - record what actually happened (lures, catches) so the model can
  calibrate its weights against your own results over time.

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
  cross-section tapering to shore. It's clearly labeled as modeled in the app, and it's
  designed to improve: real depth readings you log from a trip can blend into the model
  over time, the same way the forecast weights calibrate from logged trips.
- Instructional videos (`core/videos.py`): a curated table of real, verified YouTube
  links per lure/technique. A couple of techniques without a confidently-verified direct
  link fall back to a live YouTube search link instead of a guessed URL.
- Summer/normal pool elevation used for the map context: 515 ft, ~5,795 surface acres
  (confirmed against USACE data), vs. ~2,890 acres at winter pool.

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
