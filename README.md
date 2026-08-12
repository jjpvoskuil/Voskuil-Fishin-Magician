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
- **Zoomable lake map** of Nolin Lake showing two things, each toggleable on/off from
  a small layer selector in the map's corner: **346 real fish attractors**
  (`data/nolin_fish_attractors.csv`) GPS-placed by Kentucky Fish & Wildlife (brush
  piles, Christmas trees, pallet stacks, plastic structures, rock piles, reef balls) -
  the most authoritative point data in the app, since it's a state agency's own
  placement records, not anything derived or modeled - and your own **saved spots**
  (see below). Earlier versions of this map also drew a modeled pre-dam bottom-cover
  layer, channel-depth anchor points, historic-topo depth points, and the real
  shoreline outline, all behind a much busier layer selector and an explanatory
  dialog about where that data came from; all of that was removed in favor of this
  simpler map.
- **Personal spot catalog** - click anywhere on the Lake Map to drop a pin and record
  what you know about that exact spot: a name you choose, the type of location (main-
  lake point, flat, rock face/bluff, dock, creek channel/ledge, and more), what the
  bottom is actually made of (rocky, gravel, mud/silt, weeds, standing timber,
  brush/laydowns, stumps, and more - pick as many as apply), the depth of the main
  area, the depth of the transition/drop-off nearby, how sharp that transition is
  (high/medium/low grade), and free-form notes for anything else worth remembering.
  Click an existing pin (or jump to it from the dropdown) to view or edit it. Spots are
  stored in `data/lake_spots.csv` and, like the trip log and lure inventory, committed
  back to GitHub when a `GITHUB_TOKEN` is configured so they survive Streamlit Cloud
  restarts.
- **Spot Session page** - from any saved spot's detail panel on the Lake Map, click
  "🎯 Fish this spot now" to open a page dedicated to that pin - or open the Spot
  Session page directly and pick a saved spot from the dropdown there, no trip through
  the map required. Pick a session date (defaults to today; pick an earlier date to
  log a past session) right under the spot name, then enter what you're actually
  seeing on the water (water temp, visibility/Secchi depth + stain color if
  it's in the ambiguous mid-range or a "stirred up/muddy" checkbox to override either,
  wind as a plain-language band like "Light Ripple" rather than an mph guess, light
  condition, precipitation, a manually-entered session start time, and a time-of-day
  window shown with today's actual clock range, e.g. "Dawn (5:52 AM-7:52 AM)"), and it
  scores that moment - using the time you actually entered, not whatever time you
  happened to be filling out the page - and calls the same lure/color recommendation
  engine the 7-Day Forecast page uses, just fed by a live reading instead of a
  forecast. This score factors in your entered water temperature, water clarity, and
  whether you reported seeing forage, on top of pressure trend and moon phase (see
  "How the model works" below for exactly how); hover the small ⓘ next to the score
  to see the full factor-by-factor breakdown of how it was calculated. That score and
  the lure recommendation sit in their own collapsible "Suggestions for right now"
  section (open by default) - it only appears once you've submitted Conditions right
  now. Below it, a second collapsible section, "Add results" (closed by default),
  lets you log what actually happened - and this one doesn't need Conditions filled
  in at all, so you can jump straight to logging a catch without scoring the moment
  first if that's all you want to do (the trip is saved with a blank predicted score
  and "Unknown" water clarity in that case, everything else logs normally). Picking
  the lure (and
  trailer, if that lure type takes one) is a searchable, photo card grid instead of a
  plain dropdown - search your tackle box by brand or description, then click the
  card you want; a "Used a trailer" checkbox reveals the same card-grid picker for
  the trailer, with its own name/color fields. Underneath, a "Conditions during this
  lure use" group holds the time range you fished it, wind speed and direction, fish
  activity, forage activity, forage type seen, and notes for that window. Fish get
  logged as you catch them - click "➕ Add fish" each time and fill in species
  (Largemouth/Spotted/Striped, or type in your own), weight, length, depth caught,
  presentation/technique, and retrieval speed for that one fish; each save adds it to
  a running list (with a "Remove" if you need to undo one) so you're not committing
  to a fish count up front. It all writes into the same shared trip log the **Trip
  History** page reads from - Spot Session is now the only way to log a trip; see
  "How the model works" below for the condition bands behind this page's inputs.
- **Per-lure recommendation blocks** - each recommended lure (first choice, then a
  second-choice section) gets its own self-contained block: specific colors for that
  lure, trailer type/color if one applies, depth to run, presentation style, and a
  couple of how-to videos - all in one place. Depth guidance accounts for the fact that
  bass are upward-biased sight feeders (narrow binocular vision cone above/in front of
  the snout, blind below/behind, upward-hinging jaw) - reaction/"column" lures (crankbaits,
  jerkbaits, spinnerbaits, etc.) get a target running depth 1-2 ft *above* the depth
  you're marking fish at, while bottom-contact baits (jigs, Carolina rigs, etc.) get
  count-down-to-depth guidance instead.
- **Lake Setup Options sidebar** (7-Day Forecast page) - a compact, two-column layout
  so it fits without scrolling. Two required, direct inputs since Nolin has no live
  feed for either: your water surface temp reading, and the depth you're marking fish
  at on your electronics (e.g. a Garmin Livescope/sonar unit) - these always drive the
  seasonal pattern used for lure selection and the depth-to-run/countdown guidance on
  every lure block. A **Location** dropdown lists your own saved spots (from the Lake
  Map page) - pick one and its structure type is filled in automatically, the same way
  Spot Session resolves it; pick "Other" to set a structure type by hand instead.
- **Water color model** - Nolin normally runs a greenish-brown stain (leaning brown).
  Pick your usual base stain color (Clear / Green stained / Brown stained) plus a
  separate "stirred up / muddy" checkbox for after wind or heavy rain - the two combine
  into one effective water-clarity reading that drives lure color choice, independent
  of the base color you picked.
- **Forage selector** - pick which baitfish/prey are actually available (Gizzard Shad,
  Threadfin Shad, Bluegill/Sunfish, Crawfish, Shiners/Minnows, Stonerollers). Nothing is
  pre-checked - an empty selection means "not specified" rather than assuming a forage
  base you didn't actually confirm. Nudges lure color/pattern choice toward what the
  bass are actually keyed on, and makes sure at least one forage-matched lure shows up
  in the recommendation.
- **Trip logging** - the Spot Session page's log section records what actually happened
  (lures, catches, water conditions, forage seen) so the model can calibrate its
  weights against your own results over time.
- **Trip History** - every logged trip in one filterable table: filter by date/date
  range, time of day, location, lure type, water clarity, structure type, catches-only,
  or free-text search, plus a per-trip details view and the model's calibration status.
- **Lure inventory** - your tackle box, tracked: brand, full description, a category
  (matching it to one of the forecast engine's lure types), a photo, the last price
  paid, and how many you have on hand. Seeded from a Cabela's order history import; add
  more any time by typing them in or by uploading/taking a photo. See "Lure inventory"
  below for details.
- **Inventory-aware lure suggestions** - the 7-Day Forecast page checks
  every recommended lure against your tackle inventory: lures you already own are
  flagged (✅ "In your tackle box", with the specific brand/description/quantity **and
  a photo thumbnail** of the owned item(s), up to 4 per lure block) and sorted to the
  top of each choice tier, while ones you don't have yet stay in the list underneath as
  pick-up suggestions (🛒). Nothing is added or hidden based on ownership - the
  season/structure/pressure/forage logic still decides what's recommended; ownership
  only decides what's flagged and what floats to the top.
- **Color-match filtering on owned lures** - within a lure block, owned items are
  further checked against that block's suggested color for today's water clarity, and
  only the ones whose description shares color/pattern words with the suggestion
  (e.g. "shad" in both "Green shad" and "Tennessee Shad") are shown as ✅ "Color
  match." An owned item in the same lure category but a different color (e.g. a
  green-pumpkin crankbait next to a chartreuse suggestion) isn't shown for that
  block at all - if none of your on-hand items match today's suggested color, the
  block falls back to the normal 🛒 pick-up-suggestion treatment.

## How the model works (and its limits)

This is a transparent, rule-based heuristic - not a black box and not a proprietary
fishing-app data feed. It's designed to be reasoned about, and to improve as you log
real trips. See `core/scoring.py` for the documented weights and `core/lures.py` for the
lure/color/technique rule table. On the Spot Session page, hovering the ⓘ next to the
activity score shows exactly which factors fired and by how much - the same
transparency principle, made visible in the UI rather than just in the source.

The 1-10 activity score is built from pressure trend, moon phase, solunar major/minor
windows, cloud cover, wind, season/water-temp, and precipitation (see below for each) -
every one of these applies on both the 7-Day Forecast page and the Spot Session page,
since both draw from the same `core.scoring._segment_score()` formula. Two more
factors - a water-clarity bonus/penalty and a small bonus for confirmed forage nearby -
only apply on the Spot Session page, since they need a real on-the-water reading
(Secchi depth, seeing baitfish) that a forecast API has no way to supply. Light/steady
rain short of storm level gets a small bonus on both pages (a well-documented pattern -
reduced light penetration and surface disturbance make fish less wary), distinct from
the storm penalty that still applies to genuinely heavy rain/high storm probability on
both pages too.

**2026 evidence-based rebalance:** the weights above weren't tuned in a vacuum - after
noticing forecast scores skewing consistently high (averaging well above the "5 =
average day" the scale is meant to represent), each factor was checked against outside
research and reweighted to match how well-supported it actually is, rather than just
adding symmetric penalties everywhere for the sake of symmetry:
  - **Solunar major/minor windows and moon phase** (the same underlying "solunar
    theory") kept only a small, now genuinely two-sided weight - a 2023 peer-reviewed
    study (*SN Applied Sciences*) tested seven commercial solunar services against 361
    real freshwater fishing trips and found no significant relationship to catch rate
    at all. Moon phase now also penalizes the quarter moons, not just bonusing new/full.
  - **Barometric pressure trend** was trimmed from this model's single biggest lever to
    something more proportionate - a detailed critique (citing oceanographer Dr. David
    Ross) argues a realistic barometric swing is trivial next to the pressure change a
    fish causes itself by moving a few feet vertically, and a controlled 12-month
    single-lure experiment found no significant catch-rate difference by pressure
    alone. It's kept as a believable proxy for a front's real, better-evidenced side
    effects (cloud cover, wind, temperature), just not weighted as if it were the
    proven mechanism.
  - **Cloud cover** is now genuinely two-sided - clear/bright ("bluebird") skies score
    an explicit penalty instead of just missing out on the overcast bonus, matching the
    near-universal professional-angler pattern of a tough bite after a front clears out.
  - **Water temperature**'s metabolic-band bonus/penalty (Cold/Lethargic, Pre-Spawn,
    Peak Optimal, Extreme Thermal Load) now applies to the 7-Day Forecast page too,
    using its own daily temperature *estimate* - previously it only ran on Spot
    Session's exact reading. This is the one factor the same peer-reviewed study found
    to actually predict catch rate (roughly +1% per 10°F warmer).
  - **Wind** stayed two-sided (it already was) but was trimmed slightly further, since
    that same study found wind speed had no measurable effect on catch rate at all -
    the weakest evidence of any factor still in the model.

See `SESSION_NOTES.md`'s development log for the full source list and a before/after
distribution check (mean dropped from ~7.0 to ~5.7 across a large randomized sample of
plausible day/segment combinations, with the tails far more balanced).

**Data sources:**
- Weather (temperature, pressure, cloud cover, wind, precipitation): [Open-Meteo](https://open-meteo.com/) - free, no API key.
- Moon phase & solunar rise/transit/set times: computed locally with a compact
  low-precision lunar-position algorithm (`core/astro.py`) - no external service or
  ephemeris download needed.
- Water temperature: **estimated**, not measured (Nolin Lake has no live buoy feed) -
  blended from recent air temperature and a seasonal baseline curve. Always shown as an
  estimate in the UI.
- Lake spot coordinates (`data/nolin_spots.json`): a handful of general reference spots
  anchored to verified public sources (USACE gauge location, Kentucky State Parks/GNIS
  coordinate, U.S. Census TIGER address geocoding). **These are planning
  approximations, not survey-grade positions.** This is separate from your own
  **saved spots** on the Lake Map page (`data/lake_spots.csv`, see above) - those are
  exact pins you drop yourself, not this curated reference list. Not currently wired
  into any page (its last caller, the old Log a Trip page, has been removed in favor
  of logging from Spot Session) - left in place rather than deleted.
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
  at the fidelity anglers need. What the same source data (the pre-dam 1953/54 USGS
  sheets) *can* support reliably is bottom-cover classification, which only needs the
  color/symbol on the scan rather than precise elevation: `core/cover.py` /
  `data/nolin_cover.csv` classifies every ~55m cell of the real lake footprint as
  wooded (likely standing timber), cleared (likely open bottom), or the original
  stream channel.

  As of this modeled-depth/bottom-cover/channel-point/historic-point/shoreline layer
  set, none of it is currently rendered on the Lake Map page - per user feedback, that
  page was simplified down to just real fish attractors and your own saved spots (see
  above), since the modeled/derived layers added complexity without anything
  survey-grade to show for it. The modules and data (`core/bathymetry.py`,
  `core/cover.py`, `core/historic_bathymetry.py`, `core/shoreline.py`,
  `core/survey_points.py`) are still here, still tested, and still able to blend in
  your own real Garmin Quickdraw Contour soundings (export with
  [qdc-converter](https://github.com/interlark/qdc-converter), drop the CSV into
  `data/quickdraw/`) - they're just not wired into the map's UI right now. Re-adding a
  depth/cover layer to the map (behind an opt-in toggle, not the always-on checkboxes
  it used to have) would be a deliberate follow-up, not something this round did.
- Instructional videos (`core/videos.py`): a curated table of real, verified YouTube
  links per lure/technique. A couple of techniques without a confidently-verified direct
  link fall back to a live YouTube search link instead of a guessed URL.
- Summer/normal pool elevation used for the map context: 515 ft, ~5,795 surface acres
  (confirmed against USACE data), vs. ~2,890 acres at winter pool.
- Thermocline depth (`core/thermocline.py`): no longer wired into any page's UI (both
  the Spot Session and 7-Day Forecast sidebar inputs for it have since been removed) -
  see "Known limitations" in `SESSION_NOTES.md`. Its modeled default is anchored to a
  real, lake-specific data point: KDFWR (Kentucky Afield Outdoors, Lee McLellan, July
  2019) reported Nolin's thermocline at about 15 ft in mid/late summer, grouped with
  Green River, Barren River, and Rough River as similar mid-depth, relatively clear
  hill-land reservoirs, combined with general reservoir-stratification timing (none in
  winter/early spring, forming in May, established through summer, breaking down each
  fall) to seed a month-by-month default.
- Forage base (`core/lures.py`'s `FORAGE_OPTIONS`): gizzard shad and bluegill are
  explicitly documented as Nolin forage in Kentucky Afield Outdoors coverage of the
  lake's bass fishery; threadfin shad, crawfish, shiners/minnows, and stonerollers are
  near-universal secondary/alternate forage in Kentucky hill-land reservoirs (craw-pattern
  jig/worm colors are standard advice for this lake type) offered as optional add-ons,
  since they aren't specifically documented for Nolin the way gizzard shad/bluegill are.
- On-the-water condition bands (`core/onwater.py`), used by the Spot Session page: light
  conditions (lux-based - Night, Crepuscular/Dawn-Dusk, Overcast/Diffuse Day, Direct High
  Sun), wind (mph - Glassy, Light Ripple, Moderate Chop/Action Trigger, Heavy/Turbulent),
  water visibility (Secchi depth - Clear, Stained, Dirty/Muddy), and water temperature
  (metabolic state - Cold/Lethargic, Pre-Spawn Transition, Peak Optimal Prime, Summer
  Stratified, Extreme Thermal Load) - all supplied by the angler from general bass-biology
  reference bands, not derived from a Nolin-specific source.

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
  (order #W283763341), two further batches were pulled from the items sitting in the
  Cabela's cart on 2026-08-07 (source: "Cabela's cart (2026-08-07)") - not yet
  purchased at the time they were added, so treat those rows as a wishlist/on-order
  snapshot rather than confirmed on-hand stock until reconciled against an actual
  order - and on 2026-08-12 a shipped order (#W284504313) plus another cart snapshot
  were imported (a second order URL from that same day, #W284273868, turned out to be
  a canceled duplicate of #W284504313 with every line at qty 0, so nothing was pulled
  from it). All import batches include the vendor's own product photo for each item,
  linked directly from Bass Pro/Cabela's own CDN rather than copied into the repo -
  this app only needs to *display* the vendor's product photography, not keep a stored
  copy of it. Two SKUs (1784868, 3243224) appear in both the original order and the
  first cart batch; they're kept as separate rows rather than merged, consistent with
  how repeat items within a single order are already handled - that was already the
  case before the 2026-08-12 import. Starting with the 2026-08-12 import, though, a
  SKU that matches an *existing* inventory row no longer creates a duplicate row at
  all - its quantity is bumped instead (two items from that batch, SKU 2585737 and
  3227747, landed this way).
- **Manual entry** - add a lure any time with brand, description, price, quantity, and
  category, and optionally attach a photo you upload or take right there with your
  camera. These photos are yours, so they're stored under `data/lure_images/` and
  committed to the repo like any other user data.

**Category** is what links a tackle item to the forecast engine's lure suggestions - it's
one of the same lure types `core/lures.py` recommends (Football Jig, Squarebill
Crankbait, Wacky-Rigged Senko, and so on), picked from a dropdown when you add or edit an
item. Items imported from Cabela's were auto-tagged with a best-guess category based on
the product name; spot-check them (search/filter by category on this page) and correct
anything that looks off - a wrong category just means that item won't get matched to the
right forecast suggestion, not a real error. Items left "Not categorized / other" simply
don't participate in the ownership matching described below.

Quantity, price, and category can be edited (or the item deleted) from each card. Like
trip logs, inventory changes are committed and pushed back to GitHub when a
`GITHUB_TOKEN` is configured, so they survive Streamlit Cloud restarts.

### How inventory feeds the forecast

`core.lures.recommend()` takes an optional `inventory` argument (the same rows this page
reads/writes) and, for each lure it would otherwise recommend, checks whether any
in-hand item (quantity > 0) shares that lure's category. If so, the block is flagged
✅ **"In your tackle box"** with the specific brand/description/quantity - plus a photo
thumbnail per owned item (up to 4; extras are just counted) using `core.lure_inventory.
resolve_image_source()`, the same local-photo-wins-over-vendor-link rule the Lure
Inventory page itself uses - and that block is stable-sorted to the front of its choice
tier (first choice or second choice) - so the
best options you actually own surface first. Lures you don't have are left in place
tagged 🛒 as still-worth-trying suggestions. This only reorders and annotates; it never
adds, removes, or changes *which* lures a given day/segment/structure/forage combination
recommends - that's still entirely the season/structure/pressure/forage logic described
above.

One addition specifically for this: a **Medium-Diving Crankbait** lure type (6-12 ft,
e.g. Strike King 3XD, Rapala DT-8) was added to `core/lures.py` alongside the existing
Squarebill/Lipless/Deep-Diving crankbait types, since several inventory items are exactly
that depth class and neither existing crankbait profile fit them accurately. It's not
part of any season's default picks, but when your sonar reading (Lake Setup Options)
falls in its 6-12 ft zone, it swaps in for whichever shallower/deeper crankbait
the season pattern would otherwise have suggested - a depth-accuracy improvement on its
own, and also what lets an owned medium-diving crank actually get surfaced.

Category match is only half the story, though - owning *a* Medium-Diving Crankbait
doesn't mean you own it in *today's suggested color*. So each owned item's free-text
`description` is also checked against the block's suggested colors for the current
water clarity (`core.lures._color_tokens()` / `_color_matched_owned_items()` - a
simple, explainable keyword match, same philosophy as the rest of the engine, not a
real color model). Only items that share a color/pattern word with the suggestion
(e.g. "shad" in both "Green shad" and "Tennessee Shad") are shown as ✅ **"Color
match"** - an owned item in the same category but a different color is left out of
that block entirely rather than shown as a maybe-match, and if nothing you own
matches, the block falls back to the plain 🛒 "not in your inventory" treatment.
Because it's keyword-based against free text rather than a structured color field,
it can occasionally miss a real match (different wording) or flag a coincidental
one - it's meant as a helpful signal, not a guarantee.

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
app.py                  Entry point (streamlit run app.py) - wires up the sidebar
                         navigation (st.navigation/st.Page) with a title/icon per
                         page; holds no page content of its own
home.py                  Landing page content - today at a glance ("Today" in the
                         sidebar)
pages/
  1_7_Day_Forecast.py   Full week, drill into any day
  2_Lake_Map.py          Fish attractors + your own saved spots (click to add/edit)
  4_Trip_History.py      Filterable log of every trip (Spot Session is now the only
                         way to log one) + per-trip details + calibration status
  5_Lure_Inventory.py    Tackle inventory (brand/description/category/photo/price/qty)
  6_Spot_Session.py       Per-spot on-the-water conditions -> suggestions -> log activity
core/
  astro.py               Moon phase + solunar rise/transit/set
  weather.py              Open-Meteo integration + water-temp estimate
  scoring.py              1-10 activity scoring engine (shared by the forecast and
                           Spot Session pages via manual_segment_score())
  onwater.py               On-the-water condition bands (light/wind/visibility/water
                           temp/precipitation) used by the Spot Session page
  activity_log.py           Log-form vocabulary + inventory lure/trailer picker
                           helpers used by the Spot Session page's activity log
  lures.py                Lure/color/technique rule engine + tackle-inventory ownership matching
  spots.py                Curated general reference spots (data/nolin_spots.json) -
                           orphaned now that Log a Trip (its last caller) is removed
  lake_map.py              Folium map builder - fish attractors + your saved spots
  lake_spots.py             Your own saved-spot pins: read/write + git commit-back;
                           also bridges a spot's location type to the recommendation
                           engine's structure-type vocabulary for Spot Session
  storage.py              Trip log read/write + git commit-back (generic - reused by
                           lure_inventory.py and lake_spots.py too)
  calibration.py          Weight calibration from logged trips
  lure_inventory.py       Tackle inventory read/write + photo storage (category field
                           links each item to a core.lures lure type)
  bathymetry.py            Modeled depth grid + historic-topo + real-data blending
                           (not currently rendered on the Lake Map page - see "Data sources")
  historic_bathymetry.py   Loads depth points read from pre-dam USGS historical topo maps
  survey_points.py         Loads the angler's own Quickdraw CSV exports
  shoreline.py              Real digitized lake shoreline + point-in-polygon clip mask
  cover.py                  Pre-dam bottom-cover classification (wooded/cleared/channel)
  fish_attractors.py        Loads real KY Fish & Wildlife fish attractor GPS data
data/
  nolin_spots.json        Curated general reference spots (currently orphaned)
  lake_spots.csv          Your own saved Lake Map pins (grows over time)
  nolin_channel.json      Modeled river-channel centerline anchoring the bathymetry
  historic_bathymetry.csv Depth points read from pre-dam USGS historical topo maps
  nolin_cover.csv         Pre-dam bottom-cover cells, read from the same USGS topo sheets
  nolin_fish_attractors.csv Real fish attractors placed by KY Fish & Wildlife (KDFWR)
  nolin_shoreline.geojson Real lake shoreline, digitized from 1966 post-dam USGS topo sheets
  trip_log.csv            Logged trips (grows over time)
  lure_inventory.csv      Tackle inventory (grows over time; category column links
                           each item to a core.lures lure type)
  lure_images/            User-uploaded/captured lure photos
tests/                    pytest unit tests for astro/scoring/lures/inventory/lake_spots/onwater/activity_log
```

## Disclaimers

Forecast scores are a fishing-planning aid based on general bass-behavior heuristics,
not a guarantee. Water temperature is estimated, not measured. Map locations are
approximate. Always check current weather/lightning conditions before heading out.
