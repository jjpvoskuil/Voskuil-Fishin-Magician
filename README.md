# Voskuil Fishin' Magician 🎣

A 7-day largemouth bass fishing forecast app for **Nolin River Lake, KY**, built with Streamlit.

Picking this project back up in a new Claude chat? Use [`NEW_SESSION_PROMPT.md`](NEW_SESSION_PROMPT.md)
to kick things off, and see [`SESSION_NOTES.md`](SESSION_NOTES.md) for the full development history,
key decisions, and known open items.

## What it does

- **1-10 daily activity score** for largemouth bass, built from barometric pressure trend,
  moon phase, solunar major/minor windows, cloud cover, wind, and season/water-temp estimate.
- **Time-of-day breakdown** (Dawn / Morning / Midday / Afternoon / Dusk / Night) with the
  best window(s) to fish each day.
- **Lure, color, and technique recommendations** for each time segment, tailored to season,
  water color/clarity, structure type, and (when you provide it) the depth you're marking
  fish at.
- **Zoomable lake map** of Nolin Lake, clipped to the real digitized shoreline - click
  *anywhere* on the lake (not just preset spots) to get a location-specific
  recommendation for any day/time in the forecast window. No numeric depth contour
  lines are drawn (two attempts at modeling them from public data didn't hold up well
  enough to trust). Instead, the primary layers are: real **pre-dam bottom cover**
  (`data/nolin_cover.csv`) - every cell of the lake bottom classified as wooded (likely
  standing timber), cleared (likely open bottom), or the original stream channel, read
  directly off the same 1953/54 USGS topo sheets used elsewhere in this project - and
  **346 real fish attractors** (`data/nolin_fish_attractors.csv`) GPS-placed by
  Kentucky Fish & Wildlife (brush piles, Christmas trees, pallet stacks, plastic
  structures, rock piles, reef balls) - the most authoritative point data in the app,
  since it's a state agency's own placement records, not anything derived or modeled.
  Other toggleable layers show where the (still-present, but de-emphasized) depth
  model's anchor values come from: channel-model anchor points colored by source
  (green = surveyed USGS benchmark, orange = read off historic topo contour lines,
  gray = extrapolated), the small set of real digitized depth points from pre-dam USGS
  topo sheets (blue dots, western coves), and the real shoreline outline itself (off
  by default).
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
  and Bluegill/Sunfish are pre-checked as documented Nolin forage; Threadfin Shad,
  Crawfish, Shiners/Minnows, and Stonerollers are optional add-ons). Nudges lure
  color/pattern choice toward what the bass are actually keyed on, and makes sure at
  least one forage-matched lure shows up in the recommendation.
- **Trip logging** - record what actually happened (lures, catches, water conditions,
  forage seen) so the model can calibrate its weights against your own results over time.
- **Lure inventory** - your tackle box, tracked: brand, full description, a category
  (matching it to one of the forecast engine's lure types), a photo, the last price
  paid, and how many you have on hand. Seeded from a Cabela's order history import; add
  more any time by typing them in or by uploading/taking a photo. See "Lure inventory"
  below for details.
- **Inventory-aware lure suggestions** - the 7-Day Forecast and Lake Map pages check
  every recommended lure against your tackle inventory: lures you already own are
  flagged (✅ "In your tackle box", with the specific brand/description/quantity) and
  sorted to the top of each choice tier, while ones you don't have yet stay in the list
  underneath as pick-up suggestions (🛒). Nothing is added or hidden based on ownership -
  the season/structure/pressure/forage logic still decides what's recommended; ownership
  only decides what's flagged and what floats to the top.

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

  The channel's depth values are grounded in real elevation data where possible: Nolin
  Lake was impounded in 1963, and USGS's Historical Topographic Map Collection (public
  domain, free via TopoView/The National Map) has 7.5' quad sheets surveyed just before
  the dam - e.g. Dickeys Mills, KY 1954 (the cell later re-surveyed and renamed Nolin
  Lake/Nolin Reservoir once the lake existed) and Bee Spring, KY 1953 - showing the
  original ground contours for what's now lake bed, at a 20 ft contour interval, plus a
  surveyed benchmark (446 ft) right at the dam. Reading those against the 1966 post-dam
  sheets (which print the 515' summer pool shoreline directly) gives real depth values
  at the dam and through the open valley just upstream of it; points further up the
  channel, where the model's smoothed centerline diverges from the actual historic
  river meander, are extrapolated along the general gradient rather than read directly.
  `core/historic_bathymetry.py` / `data/historic_bathymetry.csv` also carries a small
  set of real digitized depth points for two coves at the western edge of the lake
  (from the same Bee Spring sheet) that blend in the same way described below. Full
  automated contour-line digitization across the whole lake was attempted and
  abandoned - gaps in the historical scans (text labels, roads crossing contour lines)
  make flood-fill region tracing unreliable past a small, clean area - see
  SESSION_NOTES.md for what was tried.

  Where the water actually is comes from a separate, real source rather than the
  channel model's own shape: `data/nolin_shoreline.geojson` (`core/shoreline.py`) is
  the real lake shoreline, digitized from the water fill on the same 1966 post-dam USGS
  sheets. The channel centerline is only ~8-10 hand-placed points joined by straight
  lines, so it doesn't reliably follow Nolin Lake's actual winding shape.

  Despite that shoreline fix, two attempts at deriving smooth numeric depth contours
  from this public data didn't produce results worth trusting - there's no actual
  bathymetric survey for Nolin Lake, and public sources can't support depth isolines
  at the fidelity anglers need. The map no longer draws them. What the same source
  data (the pre-dam 1953/54 USGS sheets) *can* support reliably is bottom-cover
  classification, which only needs the color/symbol on the scan rather than precise
  elevation: `core/cover.py` / `data/nolin_cover.csv` classifies every ~55m cell of the
  real lake footprint as wooded (likely standing timber), cleared (likely open
  bottom), or the original stream channel, and this is now the map's primary layer.
  The depth model (`core/bathymetry.py`) still exists and still backs the "Modeled
  depth" number and structure-type auto-suggestion on the Lake Map page - both are
  explicitly labeled as a rough guess, not a chart.

  It's also designed to improve with your own real soundings: if you record Garmin
  Quickdraw Contours, export them with [qdc-converter](https://github.com/interlark/qdc-converter)
  (`.qdc`/`.qcc` -> CSV of lon/lat/depth) and drop the CSV into `data/quickdraw/` (see
  that folder's README for the exact steps) - any number of files is fine, so you can
  add more as you explore more of the lake. `core/survey_points.py` loads and
  deduplicates every CSV there, and `core/bathymetry.py` blends the real readings into
  the modeled grid: real data wins (inverse-distance weighted) within ~50m of where you
  actually recorded it, fading smoothly back to the model beyond that, and can extend
  the map into coves/arms the hand-modeled channel doesn't cover at all. The Lake Map
  page's info box shows how many real and historic points are currently blended in.
  Since it's your own recorded sonar data (not a scraped commercial chart), there's no
  copyright issue using it directly - it plugs into the same real basemap (streets/
  shoreline) the map already renders on, so it lines up automatically.
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
  lake's bass fishery; threadfin shad, crawfish, shiners/minnows, and stonerollers are
  near-universal secondary/alternate forage in Kentucky hill-land reservoirs (craw-pattern
  jig/worm colors are standard advice for this lake type) offered as optional add-ons,
  since they aren't specifically documented for Nolin the way gizzard shad/bluegill are.

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

## Lure inventory

The **Lure Inventory** page (`pages/5_Lure_Inventory.py`) is a tackle-box tracker that
also feeds the forecast/recommendation engine (`core/lures.py`) - the two stay loosely
coupled through a single `category` field rather than sharing internals. For each lure
it shows brand, full product description, a category, a photo, the last price paid, and
current quantity on hand. Two ways items get in:

- **Order-history / cart import** - the initial set was seeded from a Cabela's order
  (order #W283763341), and two further batches were pulled from the items sitting in
  the Cabela's cart on 2026-08-07 (source: "Cabela's cart (2026-08-07)") - not yet
  purchased at the time they were added, so treat those rows as a wishlist/on-order
  snapshot rather than confirmed on-hand stock until reconciled against an actual
  order. All import batches include the vendor's own product photo for each item,
  linked directly from Bass Pro/Cabela's own CDN rather than copied into the repo -
  this app only needs to *display* the vendor's product photography, not keep a stored
  copy of it. Two SKUs (1784868, 3243224) appear in both the original order and the
  first cart batch; they're kept as separate rows rather than merged, consistent with
  how repeat items within a single order are already handled.
- **Manual entry** - add a lure any time with brand, description, price, quantity, and
  category, and optionally attach a photo you upload or take right there with your
  camera. These photos are yours, so they're stored under `data/lure_images/` and
  committed to the repo like any other user data.

**Category** is what links a tackle item to the forecast engine's lure suggestions - it's
one of the same lure types `core/lures.py` recommends (Football Jig, Squarebill
Crankbait, Wacky-Rigged Senko, and so on), picked from a dropdown when you add or edit an
item. The 40 items imported from Cabela's were auto-tagged with a best-guess category
based on the product name; spot-check them (search/filter by category on this page) and
correct anything that looks off - a wrong category just means that item won't get
matched to the right forecast suggestion, not a real error. Items left "Not categorized /
other" simply don't participate in the ownership matching described below.

Quantity, price, and category can be edited (or the item deleted) from each card. Like
trip logs, inventory changes are committed and pushed back to GitHub when a
`GITHUB_TOKEN` is configured, so they survive Streamlit Cloud restarts.

### How inventory feeds the forecast

`core.lures.recommend()` takes an optional `inventory` argument (the same rows this page
reads/writes) and, for each lure it would otherwise recommend, checks whether any
in-hand item (quantity > 0) shares that lure's category. If so, the block is flagged
✅ **"In your tackle box"** with the specific brand/description/quantity, and that block
is stable-sorted to the front of its choice tier (first choice or second choice) - so the
best options you actually own surface first. Lures you don't have are left in place
tagged 🛒 as still-worth-trying suggestions. This only reorders and annotates; it never
adds, removes, or changes *which* lures a given day/segment/structure/forage combination
recommends - that's still entirely the season/structure/pressure/forage logic described
above.

One addition specifically for this: a **Medium-Diving Crankbait** lure type (6-12 ft,
e.g. Strike King 3XD, Rapala DT-8) was added to `core/lures.py` alongside the existing
Squarebill/Lipless/Deep-Diving crankbait types, since several inventory items are exactly
that depth class and neither existing crankbait profile fit them accurately. It's not
part of any season's default picks, but when your sonar reading (Lake Setup Options
sidebar) falls in its 6-12 ft zone, it swaps in for whichever shallower/deeper crankbait
the season pattern would otherwise have suggested - a depth-accuracy improvement on its
own, and also what lets an owned medium-diving crank actually get surfaced.

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
  5_Lure_Inventory.py    Tackle inventory (brand/description/category/photo/price/qty)
core/
  astro.py               Moon phase + solunar rise/transit/set
  weather.py              Open-Meteo integration + water-temp estimate
  scoring.py              1-10 activity scoring engine
  lures.py                Lure/color/technique rule engine + tackle-inventory ownership matching
  spots.py                Lake map data + figure builder
  storage.py              Trip log read/write + git commit-back (generic - reused by
                           lure_inventory.py too)
  calibration.py          Weight calibration from logged trips
  lure_inventory.py       Tackle inventory read/write + photo storage (category field
                           links each item to a core.lures lure type)
  bathymetry.py            Modeled depth grid + historic-topo + real-data blending
  historic_bathymetry.py   Loads depth points read from pre-dam USGS historical topo maps
  survey_points.py         Loads the angler's own Quickdraw CSV exports
  shoreline.py              Real digitized lake shoreline + point-in-polygon clip mask
  cover.py                  Pre-dam bottom-cover classification (wooded/cleared/channel)
  fish_attractors.py        Loads real KY Fish & Wildlife fish attractor GPS data
data/
  nolin_spots.json        Named lake spots (edit to add your own waypoints)
  nolin_channel.json      Modeled river-channel centerline anchoring the bathymetry
  historic_bathymetry.csv Depth points read from pre-dam USGS historical topo maps
  nolin_cover.csv         Pre-dam bottom-cover cells, read from the same USGS topo sheets
  nolin_fish_attractors.csv Real fish attractors placed by KY Fish & Wildlife (KDFWR)
  nolin_shoreline.geojson Real lake shoreline, digitized from 1966 post-dam USGS topo sheets
  trip_log.csv            Logged trips (grows over time)
  lure_inventory.csv      Tackle inventory (grows over time; category column links
                           each item to a core.lures lure type)
  lure_images/            User-uploaded/captured lure photos
tests/                    pytest unit tests for astro/scoring/lures/inventory
```

## Disclaimers

Forecast scores are a fishing-planning aid based on general bass-behavior heuristics,
not a guarantee. Water temperature is estimated, not measured. Map locations are
approximate. Always check current weather/lightning conditions before heading out.
