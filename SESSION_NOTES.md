# Session Notes / Development Log

This file is a running record of what's been built, why, and what's still
open - meant to let a fresh Claude session (or a future you) get up to
speed quickly without re-deriving context. See `NEW_SESSION_PROMPT.md` for
the copy-paste prompt that points a new chat at this file.

## Project objective

A largemouth bass fishing forecast app for **Nolin River Lake, KY**, built
with Streamlit and hosted on Streamlit Community Cloud, code in
`jjpvoskuil/Voskuil-Fishin-Magician`. Core goals, from the original ask:

- 7-day forecast, 1-10 activity scale, built from weather + moon phase +
  solunar theory.
- For any day in the window: best times to fish, where on the lake to fish
  (contour map), and what to throw (lure, color, presentation) in each
  time segment.
- Click anywhere on a lake map for a location-specific setup recommendation.
- Log real trips; let the model learn from logged outcomes over time.
- Claude has direct read/write access to the GitHub repo - no copy/paste
  round-tripping through the user.

## Architecture

```
app.py                        Entry point - sidebar navigation only (st.navigation/
                               st.Page), see entry 33
home.py                        Landing page content - today at a glance
pages/
  1_7_Day_Forecast.py          Full week, drill into any day, per-segment lure blocks
  2_Lake_Map.py                Click-anywhere map + location-specific recommendation
  3_Log_a_Trip.py               Trip logging form
  4_Trip_History.py             Logged trips + calibration status
  5_Lure_Inventory.py           Tackle inventory: brand/description/photo/price/qty
core/
  astro.py                     Moon phase + solunar rise/transit/set (Meeus low-precision algorithm)
  weather.py                    Open-Meteo integration + water-temp estimate
  scoring.py                    1-10 activity scoring engine, season staging
  lures.py                      Lure/color/trailer/depth/presentation rule engine
  thermocline.py                Seasonal thermocline estimate (feeds sidebar default)
  survey_points.py              Loads angler's own Quickdraw CSV exports
  historic_bathymetry.py        Loads depth points read from pre-dam USGS historical topo maps
  bathymetry.py                 Modeled depth grid + historic-topo + real-data blending + contour extraction
  spots.py                      Named lake spot data
  lake_map.py                   Folium map builder (contours + spot markers + click target)
  ui.py                         Shared "Lake Setup Options" sidebar + lure-block rendering
  storage.py                    Trip log read/write + git commit-back (commit_and_push
                                 is generic over a list of paths - lure_inventory.py
                                 reuses it rather than re-implementing git plumbing)
  calibration.py                Weight nudging from logged trip outcomes
  lure_inventory.py             Tackle inventory read/write + photo storage
  appstate.py                   Cached weather/weights/spots/inventory accessors, secrets handling
data/
  nolin_channel.json             River-channel centerline anchoring the modeled bathymetry
  nolin_spots.json                Named lake spots
  historic_bathymetry.csv         Depth points read from pre-dam USGS historical topo maps
  quickdraw/                      Angler-dropped Quickdraw CSV exports (ships empty)
  trip_log.csv                    Logged trips (grows over time, committed back to the repo)
  lure_inventory.csv              Tackle inventory (grows over time, committed back to the repo)
  lure_images/                    User-uploaded/captured lure photos (committed back to the repo)
tests/                          pytest unit tests, one file per core module
```

Deployment: Streamlit Community Cloud, auto-redeploys on push to `main`.
`GITHUB_TOKEN` in Streamlit secrets lets the deployed app itself commit
trip-log entries back to the repo (see `secrets.toml.example`).

## Development log (chronological)

1. **Initial build** - scoring engine, lure/color/technique rules, 8
   named lake spots on a Plotly map, trip logging + git-based persistence,
   5-page Streamlit app, pushed to GitHub.
2. **Contour map v1** - switched Plotly -> Folium/streamlit-folium
   specifically because Plotly's `Scattermapbox` click events only fire on
   plotted points, not arbitrary map background - Folium's `last_clicked`
   supports true click-anywhere. Added a MODELED depth surface (river-
   channel centerline + Gaussian cross-section) since no free bathymetric
   survey exists for Nolin Lake. Expanded the lure library to make sure
   crankbaits/jerkbaits/topwater show up broadly, not just their single
   best-case scenario. Added curated instructional video links per lure.
3. **Per-lure recommendation blocks** - restructured from flat "primary
   colors + also worth trying" lists into self-contained blocks (colors,
   trailer, depth, presentation, videos all bundled per lure), each with
   first-choice and second-choice sections.
4. **Lake Setup Options sidebar** - added shared surface-temp and
   sonar-fish-depth overrides so a real reading always beats the
   weather-only estimate; later simplified from checkbox-gated inputs to
   plain always-on number inputs per explicit user feedback, then made
   both fields mandatory (no more optional/skip semantics).
5. **Strike-up-biased depth targeting** - verified bass have upward-
   biased binocular vision, a blind spot below/behind, and an upward-
   hinging jaw, so they strike up more readily than down. Reaction/
   "column" lures now target 1-2 ft above a marked fish depth; bottom
   baits get count-down-to-depth guidance instead.
6. **Water clarity model** - Nolin normally runs greenish-brown (leaning
   brown); replaced a single 3-way clarity dropdown with a base stain
   color selector + independent "stirred up / muddy" checkbox (wind/rain
   can muddy any base color), resolved to one of 4 color-table keys.
7. **Thermocline depth** - initially a modeled, read-only estimate anchored
   to a real KDFWR data point (Kentucky Afield Outdoors, Lee McLellan, Jul
   2019: Nolin's thermocline runs ~15 ft in mid/late summer, grouped with
   Green/Barren/Rough River as similar mid-depth, clear hill-land
   reservoirs). Later converted to a direct sidebar input (matching the
   water-temp/fish-depth pattern) pre-filled from that seasonal model but
   always overridable - flags a caveat on the lure recommendation when a
   marked fish depth is below it (usually too oxygen-depleted to hold
   active bass).
8. **Forage selector** - added a multiselect (Gizzard Shad and Bluegill/
   Sunfish pre-checked as KDFWR-documented Nolin forage; Crawfish and
   Shiners/Minnows as add-ons) that nudges lure color/pattern choice and
   guarantees at least one forage-matched lure appears in the
   recommendation.
9. **Full sidebar wiring** - confirmed every Lake Setup Options value
   (clarity, structure, water temp, fish depth, thermocline, forage) feeds
   into every `recommend()` call on both pages that render lure
   recommendations (7-Day Forecast, Lake Map) - no page computes its own
   local copy of any of these anymore.
10. **Proprietary chart data - declined twice** - the user shared
    screenshots of a paid nautical charting app's contour/structure data
    (visible "BUY" watermark) and asked to use it for the map. Declined
    both times (including after the user clarified they'd personally
    purchased access) - a personal viewing license doesn't grant
    reproduction rights over the vendor's compiled survey data. Redirected
    to the angler's own recordable data instead.
11. **Garmin Quickdraw ingestion** - the user has a Garmin Striker 9sv that
    records Quickdraw Contours. Identified the open-source `qdc-converter`
    tool to export `.qdc`/`.qcc` files to a lon/lat/depth CSV. Built
    `core/survey_points.py` (loads/dedupes every CSV in `data/quickdraw/`)
    and a blending step in `core/bathymetry.py` (`_blend_real_survey_data`)
    that's inverse-distance-weighted, fully trusts real data at 0m, fades
    to the model by 50m, and can extend the map into un-modeled coves. This
    is the angler's own sonar data, not a scraped chart, so no copyright
    issue. Connected the user's local `~/Fishing` folder so they can drop
    new exports there over time; the workflow is: user drops a CSV, tells
    Claude, Claude copies it into `data/quickdraw/`, rebuilds/tests/pushes.
12. **Lure inventory page** - new `pages/5_Lure_Inventory.py` + `core/lure_inventory.py`,
    intentionally separate from `core/lures.py` (the recommendation rule engine) - this
    is a physical tackle-box tracker, not a scoring input. Seeded from the user's Cabela's
    order #W283763341 (20 lure line items; a spool of braided line and a tackle-storage
    box from the same order were excluded as not being lures) by reading the order-history
    page via the Claude in Chrome browser tools (the user was already logged in) and
    pulling brand/description/SKU/price/qty plus each item's Bass Pro CDN product-photo
    URL. Those photo URLs are linked directly rather than downloaded into the repo -
    verified the CDN URL works unauthenticated with a year-long cache header, so it's a
    stable public link, and linking (vs. storing a copy of the vendor's product
    photography) is the lighter-touch choice, consistent with this project's existing
    stance on not reproducing third-party proprietary content. Manually-added items work
    differently: the user's own uploaded/camera-captured photos are real user data, so
    those get saved into `data/lure_images/` and committed to the repo, same treatment
    as Quickdraw CSVs. Refactored `core/storage.py`'s `commit_and_push()` to take a list
    of paths (was hardcoded to just the trip log) so `lure_inventory.py` could reuse the
    same git commit-back plumbing instead of duplicating it.

13. **Historic-topo-derived bathymetry** - the user proposed building a bathymetry
    layer from pre-dam USGS topographic maps (Nolin River Lake was impounded in 1963):
    take a topo map from before the dam, take the post-dam map showing the 515' summer
    pool shoreline, and interpolate between them. Investigated USGS's Historical
    Topographic Map Collection (public domain, free via TopoView/The National Map) and
    found real pre-dam quads covering parts of the lake: Bee Spring, KY 1953 and
    Dickeys Mills, KY 1954 (the latter is literally the same map cell later re-surveyed
    and renamed Nolin Lake/Nolin Reservoir, KY 1966 once the dam was built - printed
    right on the 1966 sheet as "(FORMERLY DICKEYS MILLS QUAD)"). First attempt requested
    the wrong neighboring quad (Rhoda, KY) based on a bad guess at the tiling - it turned
    out to cover the Green River gorge through Mammoth Cave National Park, nowhere near
    Nolin Lake; corrected by cross-referencing the existing channel model's anchor
    coordinates against quad bounding boxes from the USGS API instead of guessing.

    Built a real pipeline: downloaded GeoTIFFs (user fetched them from USGS's S3-hosted
    archive and uploaded, since this sandbox's network is allowlisted and can't reach
    USGS/S3 directly - only the TNM metadata API via the fetch tool), warped pre/post-dam
    editions of the same quad onto a common pixel grid with `rasterio`, and verified
    alignment by eye (features line up pixel-for-pixel across editions). Confirmed the
    515' shoreline is directly labeled on the 1966/1966 sheets next to the blue water
    fill - no need to guess it. Built a region-adjacency-graph method to read 1953/1954
    ground elevations against that shoreline: threshold the scan for brown contour-line
    pixels, label the flat regions between lines, build a region graph via
    `skimage.segmentation.expand_labels`, then BFS the ring-distance (in 20 ft contour
    intervals) from the regions touching the current shoreline inward. Worked cleanly
    on a small, clean test area (two coves clipped at the western edge of the Bee Spring
    quad - see `data/historic_bathymetry.csv`, ~27 points, blended into
    `core/bathymetry.py` the same way Quickdraw data is).

    The same method broke down at the scale of the main lake basin (Dickeys Mills/Nolin
    Reservoir quad): text labels, roads, and stream crossings interrupt the scanned
    contour lines often enough that flood-fill region tracing leaks across gaps and
    merges dozens of elevation bands into one, collapsing the whole basin's estimated
    depth back to near-zero. A second attempt (ray-casting from each point to its
    nearest shore pixel, counting contour crossings) was more robust to isolated gaps
    but geometrically unsound in a winding valley - the nearest shore point isn't
    necessarily downhill-connected to where you're standing. Abandoned automated
    whole-basin digitization rather than ship numbers built on a shaky method.

    Pivoted (with the user's go-ahead) to a smaller, verifiable win: read real
    elevations directly off the 1954 Dickeys Mills sheet at (or near) the channel
    model's existing anchor points in `data/nolin_channel.json`, replacing guessed
    `depth_ft` values with historically-grounded ones. Found the channel model's
    anchors are a *smoothed* path, not a literal trace of the historic river - several
    anchors (Wax, a point near "Junction") land on hillsides 200-300+ ft above the
    valley floor, so reading elevation *at* those exact coordinates isn't meaningful.
    Traced the actual river through a montage of 31 crops from the dam upstream instead.
    Found a surveyed USGS benchmark (446 ft) right at Kyrock/Dismal Rock, essentially at
    the dam - high confidence, replaces the old 85 ft guess with a real 69 ft. The open
    valley stretch just upstream reads consistently ~490-500 ft off contour lines
    hugging the river (medium confidence). Beyond where the smoothed path leaves the
    river (roughly State Park onward), values are extrapolated along the general
    gradient rather than read directly (lower confidence) - `data/nolin_channel.json`
    and `data/historic_bathymetry.csv` document the source/confidence per point/batch.
    Net effect: the lake is now modeled as meaningfully *shallower* through most of the
    channel than the original guessed profile, with the true deep point concentrated
    tightly at the dam/gorge rather than spread gradually over the first mile.

    The user offered twice more during this session to supply depth data from other
    sources: once from "a contour app" (a commercial charting app) - declined, same
    reasoning as the earlier proprietary-chart declines (a personal subscription
    doesn't carry reproduction rights over the vendor's compiled data, doesn't matter
    if it's a few points instead of a full export) - and once to manually record
    lat/long/depth with their own depth finder, which is exactly what
    `core/survey_points.py`/`data/quickdraw/` already exists for. Generated
    `nolin_depth_points_needed.csv` (delivered to the user, not committed - it's an
    empty template for them to fill in) listing the specific low/medium-confidence
    channel points where a real reading would help most.

    Also fixed a latent bug surfaced by this work: `core/bathymetry.py`'s `_bounds()`
    only padded around the channel model's own points, so a real/historic point
    sitting outside that padding (like the Bee Spring coves, well west of the channel
    model's own footprint) could land right at or just outside the modeled grid's edge,
    where nearest-cell lookups and IDW blending get unreliable. `_bounds()` now widens
    to cover any historic/survey point outside the channel padding, with its own small
    margin - this was always a risk for Quickdraw data extending into new coves too,
    just hadn't been hit yet since `data/quickdraw/` still ships empty.

14. **Map page: visualize the data sources** - after entry 13's bathymetry work, the
    user asked to update the Lake Map page to actually illustrate the new data rather
    than leave it as invisible numbers behind the same-looking contour lines. Added
    `depth_source` to every point in `data/nolin_channel.json` ("benchmark" /
    "contour_read" / "extrapolated" - matches the confidence notes already written as
    inline comments during entry 13, now made structured/renderable instead of just
    prose). `core/lake_map.py` gained two new toggleable Folium layers: channel anchor
    points as colored circle markers (green/orange/gray by source), and the historic-
    topo cove points from `data/historic_bathymetry.csv` as small blue dots. Both
    default to visible alongside the existing contour/spot layers.

15. **Fix: contours crossing dry land** - the user reported (with a screenshot of the
    live map) that contour lines were rendering as diagonal streaks crossing both land
    and water, not following the real shoreline. Root cause: `data/nolin_channel.json`
    is only ~8-10 hand-placed anchor points joined by straight lines with a Gaussian
    cross-section - that centerline doesn't reliably run through the real (highly
    winding) lake; checked distances from each anchor to the real shoreline and found
    them off by 50m to over 1km in places. The old model's depth/contour extent was
    entirely defined by that centerline, so wherever the real lake bends away from the
    straight line between two anchors, the model kept reporting "water" over dry land.

    Fix: dug up real shoreline geometry instead of trusting the channel model's shape.
    Used the same cached 1966 post-dam USGS topo GeoTIFFs from entry 13 (Nolin
    Reservoir/Dickeys Mills quad + Bee Spring quad), re-thresholded for the water fill
    color (plus a second, lighter cyan tone used on the photo-revision patch directly
    over the pool at the dam, which the original threshold missed), extracted ~1,350
    shoreline polygons with OpenCV contour detection, filtered to the lake's known
    footprint to drop unrelated farm ponds elsewhere on the same map sheets, and saved
    them as `data/nolin_shoreline.geojson` (public domain, same USGS source as
    everything else in this bathymetry chain). New module `core/shoreline.py` loads
    these polygons and provides `shoreline_mask()` - a fast point-in-polygon test
    against a lat/lon grid (bbox-restricted per polygon so ~1,350 polygons against a
    220x252 grid still runs in ~0.02s).

    `core/bathymetry.py`'s `_depth_grid()` was restructured so WHERE there's water
    comes from this real shoreline (not the channel model's corridor shape anymore),
    and the channel anchors now only supply depth *values*: each wet grid cell gets the
    nearest anchor's target depth, ramped in (smoothstep) from 0 at the shore over a
    capped ~180m so mid-channel areas reliably reach full depth. The channel-anchor
    corridor is still used as a narrow fallback, but only where the real shoreline has
    zero coverage within 250m (covers small scan gaps) - it's deliberately not unioned
    in everywhere, since that would just reintroduce the original bug. Verified anchor
    points (Dam, Nolin Lake State Park, Wax, Dog Creek) get their small grid
    neighborhood pinned directly to their documented depth, since those are real
    surveyed/read values and shouldn't depend on how the shore-ramp happens to fall
    near them. `core/lake_map.py` gained a third (off-by-default) layer drawing the
    real shoreline outline itself, so turning it on next to the contour layer is a
    direct visual check that contours stay inside it.

    Verified via a matplotlib rendering of the raw grid + contours + real shoreline
    outline (no basemap) before and after - the "before" image showed a smooth diagonal
    tube ignoring the real winding shape; "after" shows contours hugging the actual
    coves and following the dendritic shoreline. `get_depth_at_ft` at all four verified
    anchors now returns their documented depth exactly.

16. **Pivot: drop depth contours, add real bottom-cover from the same topo sheets** -
    despite entry 15's fix, the user reported the live map still looked wrong ("none of
    the contours are accurate and most of it is on land"). Rather than attempt a third
    variation of depth-contour modeling, stepped back and reframed the actual goal: the
    user wants the app to forecast daily hotspots (wind, cover, structure, depth
    changes combined), not necessarily a standalone bathymetric chart. Presented a
    multi-phase strategy (structure/cover from topo, old-channel breakline, shoreline-
    geometry points/coves, wind/fetch scoring, user-contributed structure pins, all
    feeding a hotspot score) and let the user pick where to start via AskUserQuestion -
    chose "structure/cover from topo" first, and "no contour lines on the map for now,
    let's see what we get" for the depth question.

    Mid-request, the user also asked about https://usa.fishermap.org/depth-map/ as a
    possible data source ("it's a .org site so maybe it's OK"). Checked it: its depth
    data comes from Navionics and iBoating, repackaged onto a different domain - same
    proprietary compiled-chart problem already declined twice, domain TLD doesn't
    change the underlying data's licensing. Told the user directly and moved on.

    Implementation: reused the cached pre-dam 1953/54 USGS topo GeoTIFFs (same source
    as entries 13/15) but for a completely different signal - land cover, not
    elevation. Sampled colors and found the source sheets classify cleanly into wooded
    (green, G-R and G-B both large), cleared/cropland (near-white, all channels high
    and close together), and the original stream channel (blue, B channel elevated
    over R) - verified visually against both quads before committing to thresholds.
    Classified every pixel, aggregated into ~55m cells (majority-vote dominant class +
    per-class fraction + source pixel count as a rough confidence signal), filtered to
    cells falling inside the real digitized shoreline (data/nolin_shoreline.geojson,
    entry 15), and saved as `data/nolin_cover.csv` (3,068 cells: 605 wooded, 2,352
    cleared, 111 original-channel). New module `core/cover.py` (`get_cover_at`,
    `load_cover_cells`, mirrors the historic_bathymetry.py/shoreline.py loader pattern,
    cKDTree-backed nearest-cell lookup with an 80m default max distance).

    `core/lake_map.py`: removed the "Modeled depth contours" layer entirely; added a
    "Pre-dam bottom cover" layer instead (folium.Rectangle per cell, colored by
    dominant class, on by default) - this is now the map's primary content. The
    clicked-location popup shows bottom cover instead of a modeled depth claim.
    `pages/2_Lake_Map.py`: renamed from "Contour Map" to "Map", rewrote the info banner
    to describe the cover layer and explicitly caveat the still-present "Modeled
    depth" metric as a rough guess rather than a chart, and added a "Bottom cover"
    metric alongside it in the click-detail panel (`core/cover.get_cover_at`). Did NOT
    remove `core/bathymetry.py`'s depth model itself, or its use in
    `infer_structure_type`/lure recommendations - only the map's rendered depth-contour
    layer and the framing of the depth number shown to the user changed. The remaining
    phases of the hotspot strategy (old-channel breakline, shoreline-geometry points/
    coves, wind/fetch scoring, user-contributed structure pins) are queued for future
    rounds, prioritized by the user as needed.

17. **Real fish attractor data from Kentucky Fish & Wildlife (KDFWR)** - mid-request,
    the user asked if a Kentucky government site had a lake map with underwater
    structure they remembered finding before. Searched and found
    fw.ky.gov/Fish/Pages/fish_attractor_lakes.aspx: KDFWR publishes GPS-tagged fish
    attractor locations (brush piles, Christmas trees, pallet stacks, plastic
    structures, rock piles, reef balls) per lake, as GPX downloads meant for anglers to
    load straight into a GPS/depth finder - a genuinely different category of source
    than everything declined so far, since it's a state agency's own placement
    records published for exactly this public use, not a proprietary chart product.

    Could not fetch the actual GPX file automatically - `mcp__workspace__web_fetch`
    reached the KDFWR page fine but returned the linked .gpx as opaque binary content,
    and the Google My Maps mirror KDFWR also links to is on a domain the browser tool
    blocks navigation to. Asked the user to download it themselves and upload it -
    they did. Parsed with `xml.etree.ElementTree`: 346 waypoints, 7 structure types
    (177 Brush, 74 Christmas Trees, 53 Pallet Stack, 30 Plastic, 9 Spider Hump, 2 Reef
    Ball, 1 Rock), saved as `data/nolin_fish_attractors.csv` (ident, lat, lon,
    structure_type - about 40 idents are synthetic NRL-NOID-### placeholders where the
    source GPX had an embedded photo instead of a KDFWR ident string). New module
    `core/fish_attractors.py` mirrors the existing loader pattern.

    Sanity-checked positions against the real digitized shoreline (entry 15): about a
    third of the 346 points fall outside it, some by several hundred meters. Concluded
    this is expected (attractors are often placed intentionally close to the bank in
    shallow water) rather than a data problem on either side, and kept all 346 points
    unfiltered - this is the most authoritative point data in the project, real
    placements rather than anything derived or modeled, so it shouldn't be filtered
    against a less-precise derived shoreline.

    `core/lake_map.py` gained a new toggleable layer (on by default) plotting all 346
    attractors as colored CircleMarkers by structure type, with popups showing type
    and KDFWR ident. `pages/2_Lake_Map.py`'s info banner now mentions the attractor
    count alongside the cover-layer description.

18. **Fix: map fades/goes transparent when zoomed in** - the ~3,068-cell bottom-cover
    layer draws one `folium.Rectangle` per cell (weight=0, so no border stroke at
    all), sized to exactly meet its neighbors edge-to-edge in lat/lon space. Cell
    centers were laid out on a regular grid in the source topo sheet's own projected
    CRS, then converted to lat/lon - a projection that isn't perfectly axis-aligned
    with lat/lon, so an exact edge-to-edge fit left sub-pixel seams between adjacent
    rectangles. Invisible zoomed out, but as you zoom in far enough that a few meters
    becomes several screen pixels, those seams show the basemap through them, reading
    as the layer "fading." Checked nearest-neighbor cell-center spacing directly
    (scipy cKDTree): ~91% of cells are within 55m of their nearest neighbor. Fixed by
    (a) padding each rectangle's half-size from 27.4m to 30m so neighboring cells in
    the tightly-packed regions now overlap by a few meters instead of meeting exactly
    edge-to-edge, (b) giving each rectangle a `weight=1` border in its own fill color
    instead of no border, so any still-residual gap gets bridged by a matching-color
    line rather than showing blank map, and (c) `prefer_canvas=True` on the Folium
    map, the standard fix for SVG-per-shape anti-aliasing seams across many adjacent
    vector shapes. Genuinely isolated cells (no data within ~90m, mostly boundary/
    sparse-coverage cells, about 9% of the total) still render as separate rectangles
    with real gaps between them - that's accurate, not a rendering bug, since there's
    no cover data to fill in there. No headless-browser tooling is available in this
    sandbox to screenshot-verify pixel-by-pixel, so this was verified by direct
    nearest-neighbor distance analysis against the new rectangle size, not visually -
    worth a look on the live app to confirm.
19. **Cart import for Lure Inventory** - added a second batch of 13 lures (15 units,
    $139.85) to `data/lure_inventory.csv`, read live from the Cabela's cart via a
    connected browser session (the cart page requires the user's own login, which
    Claude has no way to access on its own). Followed the existing order-history
    import's row format exactly, including the same product-photo CDN URL pattern
    (SKU-keyed, just a different query-string tag: `$BPSSite_CartTN$` vs. the
    original `$BPSSite_orderhistory$`, both point at the same Bass Pro asset). Two
    SKUs (1784868, 3243224) were already in inventory from the original order and
    also sitting in the cart - kept as separate rows rather than deduped/merged,
    since the codebase has no existing dedup logic and the two batches represent
    different purchase events. Cart items aren't yet a confirmed purchase, so this
    batch is tagged with a distinct source string ("Cabela's cart (2026-08-07)")
    rather than an order number - worth reconciling against the real order once it
    ships, in case anything changes between cart and checkout.
20. **Second cart import** - same request, same day: 7 more lures (7 units, $38.53)
    added from a refreshed Cabela's cart, none overlapping the 31 SKUs already in
    inventory at that point. Same row format and CDN photo-URL pattern as entry 19.
21. **Tackle inventory feeds the forecast's lure suggestions; three new forage types** -
    the user wanted the 7-Day Forecast (and, for consistency with this project's
    "every page feeds the same shared inputs" rule, Lake Map too) to check its lure
    recommendations against the real tackle inventory (entry 12): show which
    recommended lures/plastics the angler already owns, while still suggesting ones
    they don't have. Mid-request, also added Threadfin Shad and Stonerollers to the
    forage multiselect (`FORAGE_OPTIONS`) - both offered as optional add-ons like
    Crawfish/Shiners rather than pre-checked defaults, since (unlike gizzard shad/
    bluegill) they aren't specifically documented as Nolin forage in the sources used
    elsewhere in this app.

    Design: added a `category` column to `data/lure_inventory.csv`/`LureItem`
    (`core/lure_inventory.py`) holding one of `core.lures.LURE_PROFILES`' keys - a
    plain string, not an enum/foreign key, so `lure_inventory.py` stays independent of
    `lures.py`; the matching happens on the `lures.py` side
    (`_group_owned_by_category()`). `recommend()` gained an optional `inventory`
    argument; when supplied, each resulting `LureBlock` is annotated with any owned
    item(s) sharing its category (`owned`/`owned_items`), and each choice tier
    (first/second) is stable-sorted so owned lures bubble to the top - the *set* of
    lures a given day/segment/structure/forage combination recommends is completely
    unchanged by inventory; ownership only affects flagging and ordering. `core/ui.py`
    renders a green "✅ In your tackle box: brand – description (qty N)" line when
    owned, or a muted "🛒 Not in your inventory yet" line otherwise. Both
    `pages/1_7_Day_Forecast.py` and `pages/2_Lake_Map.py` now pass `get_inventory()`
    through to every `recommend()` call.

    All 40 existing inventory rows (order-history + two cart imports, entries 12/19/20)
    were auto-tagged with a best-guess category based on product name/brand (e.g.
    "Thunder Cricket Swimjig" -> `chatterbait`, "KVD Rattling Square Bill" ->
    `squarebill_crankbait`). The Lure Inventory page got a required-at-a-glance
    Category selector on the add form, an editable Category dropdown in each item's
    Edit expander, a Category caption on every card, and a Category filter - so any
    auto-tag that looks wrong is a one-click fix, not a code change.

    One real gap surfaced during categorization: four items (two Strike King 3XD,
    a Rapala DT-8, a Bandit 300) are genuine medium-diving crankbaits (~6-12 ft) that
    didn't fit either existing crankbait profile (Squarebill 2-6 ft, Deep-Diving
    15-25 ft) - forcing them into either would have attached wrong depth guidance to
    a real product. Added a new `medium_diving_crankbait` profile to
    `core/lures.py`'s `LURE_PROFILES` rather than mis-tag them. It's deliberately
    *not* wired into any season's default first/second-choice picks (that would have
    meant auditing/re-testing all seven seasonal branches for a tackle-inventory
    feature) - instead, checked empirically that the existing "make sure a crankbait
    shows up" nudge never actually fires (every seasonal branch already includes one),
    so hanging the new profile off that nudge would have been dead code. Instead,
    added a separate, narrower mechanism: when a real sonar reading (`fish_depth_ft`,
    Lake Setup Options sidebar) falls in the 6-12 ft zone and no medium-diving crank is
    already picked, swap the first shallower/deeper crankbait already in that day's
    list for the medium-diving one. This is a genuine depth-accuracy fix independent
    of inventory (a squarebill or deep-diver picked by season alone may not match a
    9 ft sonar reading nearly as well), and it's also what lets an owned medium-diving
    crank ever get suggested/flagged. Verified against all 7 seasons x 6 segments x 5
    crank-eligible structures x a fixed depth/temp that the pre-existing "ensure a
    crank" nudge never fires (confirming it was safe to leave alone) before adding the
    new swap-based mechanism.
22. **Photo thumbnails on owned-lure blocks** - immediate follow-up to entry 21: the
    "In your tackle box" flag was text-only, and the user asked for an actual photo of
    each owned lure in the recommendation itself. Extracted the Lure Inventory page's
    existing local-photo-wins-over-vendor-link fallback logic into a shared
    `core.lure_inventory.resolve_image_source(item, images_dir)` helper (the page itself
    was refactored to call it too, replacing its inline duplicate of the same fallback),
    added `image_url`/`image_filename` to the dicts `core.lures._group_owned_by_category()`
    builds, and had `core/ui.py`'s `render_lure_block()` render up to 4 thumbnails (in
    columns, each captioned brand + description) per lure block, with a "+N more" note
    if a category has more owned items than that. No inventory/forecast-matching logic
    changed - this is purely a rendering addition on top of entry 21's `owned_items`.
23. **Fix: 7-Day Forecast crashing with "No weather data available for {d}"** - the user
    hit a hard crash (full-page Streamlit traceback, not a graceful in-app error) on the
    live deployed app. Root cause: every page computed "today" with a plain
    `date.today()`, which returns the *server's* local date - Streamlit Community Cloud
    runs its containers on UTC, while Nolin Lake is America/Chicago (UTC-5/-6). For
    roughly 5-6 hours every day (right around UTC midnight), the server's `date.today()`
    is already "tomorrow" relative to Chicago. Meanwhile `core/weather.py`'s
    `fetch_forecast()` asks Open-Meteo for `forecast_days=7` starting from the lake's own
    calendar day (`timezone=LAKE_TZ`), so during that window `pages/1_7_Day_Forecast.py`'s
    `score_week(bundle, date.today(), 7, ...)` was asking for one day past the last day
    Open-Meteo actually returned - `core/scoring.py`'s `score_day()` correctly raises
    `ValueError("No weather data available for {d}")` for that day, but nothing on that
    page (or `app.py`'s landing page) caught it, so the whole page crashed instead of
    degrading gracefully the way `pages/2_Lake_Map.py` already did (it wraps its
    `score_day()` call in `try/except ValueError` -> `st.error()`).

    Fix, two parts: (1) added `core.weather.lake_today()` (`datetime.now(ZoneInfo(
    "America/Chicago")).date()`) and replaced every "what's today at the lake" use of
    `date.today()` with it - `app.py`, both date pickers on `pages/1_7_Day_Forecast.py`
    and `pages/2_Lake_Map.py`, `pages/3_Log_a_Trip.py`'s trip-date bounds, and
    `core/ui.py`'s thermocline-default calls. Added `tzdata` to `requirements.txt` since
    some minimal Linux images (including, per this bug, whatever Streamlit Community
    Cloud's build uses) don't ship a system IANA tzdata database that `zoneinfo` can find
    on its own - the PyPI `tzdata` package makes `zoneinfo` resolve reliably regardless of
    the underlying OS. (2) Independent of the tz root cause, made the failure mode
    non-fatal: `score_week()` now skips (rather than raising for) any individual day
    outside the bundle's coverage, returning whatever days *are* available instead of
    aborting the whole list - covers this same symptom from any other cause too (a
    transient Open-Meteo gap, `get_weather_bundle`'s 1-hour cache TTL still holding a
    bundle fetched just before the lake's local-day rollover, etc.). `app.py` now catches
    `ValueError` around its single `score_day()` call with a friendly `st.warning()`
    instead of the misleading "Couldn't fetch weather data" message its outer
    `try/except Exception` was giving it (which implied the *fetch* failed, when really
    the fetch succeeded and only the date was wrong). `pages/1_7_Day_Forecast.py` now
    checks `len(week)` and shows `st.error()` + `st.stop()` if it's empty, or a
    `st.warning()` noting how many of 7 days came back if it's partial, rather than
    crashing on `week[0]` or silently rendering a shorter week with no explanation.
24. **Smaller, consistently-sized, crisper lure photos** - the user asked for the lure
    images (owned-lure thumbnails on the forecast pages, entry 21/22, and the Lure
    Inventory grid) to be smaller, uniform in size, and less blurry. Root cause of all
    three complaints: `st.image(src, width='stretch')` scales an image to fill its
    entire column - stretching/upscaling a modest-resolution vendor photo past its real
    resolution (blurry), and leaving every thumbnail a different height, since only the
    width is controlled and height just follows whatever the source photo's own aspect
    ratio happens to be (inconsistent sizing). `st.image()` has no built-in crop-to-square
    option to fix that.

    Fix: added `core.lure_inventory.image_data_uri_or_url()` (turns whatever
    `resolve_image_source()` returned into something an `<img>` tag's `src` can point
    at directly - a remote vendor URL passes through unchanged, still fetched
    client-side by the browser exactly as before, no new server-side network call; a
    local user-uploaded photo gets base64-encoded into an inline `data:` URI, since the
    browser can't reach the Streamlit server's filesystem path directly) and
    `core.ui.render_square_thumbnail()` (renders that as a fixed-size `<div>` with
    `object-fit: cover` via `st.markdown(..., unsafe_allow_html=True)` - crops to a
    perfect square at a size the caller picks, regardless of the source photo's
    resolution/aspect ratio). Deliberately did NOT reach for Pillow/`requests`-based
    server-side image downloading+cropping - the CSS approach gets the same visual
    result (fixed square, no upscale-blur) with strictly less surface area: no new
    dependency, no new network call, and no cache-invalidation-on-file-change edge case
    to think about.

    Replaced both call sites: `core/ui.py`'s `render_lure_block()` (owned-lure
    thumbnails, now 64px, still capped at `MAX_OWNED_THUMBNAILS`) and
    `pages/5_Lure_Inventory.py`'s inventory grid (now 160px). Neither page calls
    `st.image()` for lure photos anymore.
25. **Flag whether an owned lure actually matches today's suggested color** - user
    feedback with screenshots: a Medium-Diving Crankbait block suggested "Chartreuse/
    black back, Green shad" (Green-stained water), but the owned-item photos shown
    underneath it were a Tennessee Shad, Chili Craw, Bluegill, and Crawfish Orange
    Belly - none of which are actually chartreuse - with nothing in the UI saying so.
    Root cause: `_group_owned_by_category()` (entry 21) only ever matched owned items
    to a lure block by `category` (which lure *type* it is), never by color - every
    owned item in that category was shown next to the suggestion regardless of
    whether its real-world color had anything to do with it.

    Fix: added `core.lures._color_tokens()` (splits a color-suggestion or
    lure-description string into lowercase word tokens, dropping filler words like
    "back"/"pattern"/"skirt"). First pass tagged each owned item with a `color_match`
    bool and showed matched/unmatched items separately; per immediate follow-up
    feedback (entry 26) that was simplified further to just filter out non-matches
    entirely, so the code below describes the final shape, not the intermediate one.
26. **Simplify color-match to filter, not just flag** - follow-up to entry 25: instead
    of showing every owned item split into matched/unmatched groups, only show the
    ones that actually match today's suggested color; drop the rest entirely rather
    than noting them as "also on hand, different color."

    `_annotate_color_matches()` (entry 25's tag-everything version) was replaced with
    `core.lures._color_matched_owned_items()`, which returns only the owned items
    whose description shares a color/pattern token with the block's suggested colors
    for today's water clarity - non-matching owned items aren't included in
    `LureBlock.owned_items` at all anymore. This also changes what "owned" means for
    sorting purposes: `LureBlock.owned` (used to bubble a block to the front of its
    choice tier, entry 21) is now `bool(owned_items)`, so a block only bubbles up when
    you actually have the *right color* in hand, not just the right lure type - owning
    a Chili Craw crankbait no longer bubbles a chartreuse-suggested block to the top.
    Removed the now-redundant `owned_color_match` property (equivalent to `owned` once
    `owned_items` is pre-filtered to matches only).

    `core/ui.py`'s `render_lure_block()` simplified back to a single `st.success()`
    banner ("✅ Color match in your tackle box: ...") + thumbnails, since everything in
    `owned_items` is now guaranteed to be a color match - no more matched/unmatched
    split or mismatch warning. If nothing you own matches, the block just falls back
    to the existing 🛒 "not in your inventory yet" treatment, same as never having
    owned anything in that category. Verified against the user's exact reported case:
    with Tennessee Shad, Chili Craw, Bluegill, and Crawfish Orange Belly all owned in
    `medium_diving_crankbait` against a "Craw pattern, Brown/orange" suggestion, only
    Chili Craw and Crawfish Orange Belly (both share "craw"/"orange") are shown; the
    other two are dropped rather than shown-but-flagged.
27. **Rebuild the Lake Map page as a personal spot catalog, drop the forecast/bathymetry
    UI from it** - user request: keep only the fish attractor markers on the map (no
    layer-toggle checkboxes, always shown), remove the explanatory dialog about
    bathymetric/cover data, remove the activity-score + lure-recommendation panel on
    the right, and replace it with the ability to drop a pin and record structured
    info about that specific spot - name, type of location, bottom structure, main
    area depth, transition/drop-off depth, and how sharp that transition is.

    New module `core/lake_spots.py` mirrors `core/lure_inventory.py`'s storage pattern:
    rows live in `data/lake_spots.csv`, committed back via `core.storage.commit_and_push`
    when a `GITHUB_TOKEN` is configured. `LakeSpot` dataclass fields: `name`, `lat`,
    `lon`, `location_type` (new `LOCATION_TYPES` list - deliberately its own vocabulary,
    separate from `core.lures.STRUCTURE_TYPES`, since this catalog is no longer an input
    to the recommendation engine), `bottom_structure` (a list, stored pipe-joined in the
    CSV via `split_bottom_structure()`/manual joining, since a real spot is often more
    than one texture at once - new `BOTTOM_STRUCTURE_OPTIONS` list), `main_depth_ft`,
    `transition_depth_ft`, `transition_grade` (new `TRANSITION_GRADE_OPTIONS`: High/
    Medium/Low), and free-form `notes` - added as a reasonable extra field beyond what
    was asked for, since a place to jot anything that doesn't fit the structured fields
    (e.g. "best on a falling lake," "caught two here in May") seemed clearly useful for
    a personal spot log and the user invited additions. `nearest_spot_within()` matches
    a click's lat/lon to an existing saved spot within a tight tolerance (~9-11m,
    calibrated only to absorb float/CSV round-tripping, not to forgive an imprecise
    click) - since a marker click reports that marker's exact stored coordinates, this
    is what lets the page tell "clicked an existing pin" apart from "clicked a new
    blank location."

    `core/lake_map.py` rewritten from scratch: dropped the pre-dam bottom-cover layer,
    channel-depth-point layer, historic-topo-point layer, real-shoreline outline, and
    the `folium.LayerControl` that toggled them - now draws only real fish attractors
    (`core/fish_attractors.py`, unchanged) and the angler's saved spots, both always
    visible. A saved spot's marker turns red when it's the currently-selected one
    (matched via `nearest_spot_within`); an orange crosshair marks an unsaved candidate
    location when the click doesn't match any existing spot. `pages/2_Lake_Map.py`
    rewritten to match: the bathymetry-explainer `st.info()` dialog is gone, the entire
    right-column score/lure-recommendation panel (`recommend()`, `render_lure_
    recommendation()`, the date/segment/structure-type pickers, `render_lake_setup_
    sidebar()`) is gone, replaced by either a read-only detail view + "Edit this spot"
    expander (existing spot) or an "Add a new spot here" form (new location) - both
    read/write through `core.lake_spots`. The "Jump to a named spot" dropdown now jumps
    among the angler's own saved spots instead of the curated `data/nolin_spots.json`
    reference list.

    `data/nolin_spots.json`/`core/spots.py`/`get_spots()` were deliberately left alone -
    they're still used by `pages/3_Log_a_Trip.py` for picking a general area when
    logging a trip, a separate concern from the new per-pin spot catalog. Likewise,
    `core/bathymetry.py`, `core/cover.py`, `core/historic_bathymetry.py`,
    `core/shoreline.py`, and `core/survey_points.py` (and their data files/tests) were
    left in place, just no longer wired into the Lake Map page's UI - re-adding a
    depth/cover layer later (behind an explicit opt-in, not always-on checkboxes) is a
    clean follow-up if wanted, not something this round did.
28. **Bring back a layer toggle for the two remaining map layers** - immediate
    follow-up to entry 27: the fish-attractor and saved-spot layers were made
    un-toggleable (always on) when the old multi-layer checkbox control was removed,
    but the user asked for the ability to turn each on/off independently, just scoped
    to these two layers rather than the old five-layer set.

    `core/lake_map.py`'s `build_folium_map()` now wraps each layer in its own
    `folium.FeatureGroup` (`"Fish attractors (N)"`, `"My saved spots (N)"`, each
    labeled with a live count) and adds a `folium.LayerControl(collapsed=False)` back -
    much smaller than the old one since there are only two entries instead of five, and
    it's expanded by default so the toggles are visible without an extra click. The
    transient "new spot - not saved yet" crosshair marker (shown when the current click
    doesn't match a saved spot) is deliberately added directly to the map, outside both
    feature groups - hiding the "My saved spots" layer while you're mid-way through
    adding a new one shouldn't also hide the pin you're actively placing.
29. **Per-spot "Spot Session" page: enter on-the-water conditions, get suggestions,
    log activity** - follow-up to entry 27/28: a saved spot's detail panel on the
    Lake Map page now has a "🎯 Fish this spot now" button (sets `spot_id` in
    `st.query_params`, then `st.switch_page`s) that opens a new
    `pages/6_Spot_Session.py`, dedicated to that one pin.

    New `core/onwater.py` module holds the ecological band vocabulary the user
    supplied for this page's inputs (credited to the user, not derived): `LIGHT_
    CONDITIONS` (4 lux-based bands - Night, Crepuscular/Dawn-Dusk, Overcast/Diffuse
    Day, Direct High Sun - each with a proxy cloud-cover % for feeding the existing
    cloud-based scoring formula), `WIND_BANDS` (4 mph bands - Glassy, Light Ripple,
    Moderate Chop/Action Trigger, Heavy/Turbulent), `VISIBILITY_BANDS` (3 Secchi-depth
    bands - Clear, Stained, Dirty/Muddy), and `WATER_TEMP_BANDS` (5 metabolic bands -
    Cold/Lethargic, Pre-Spawn Transition, Peak Optimal Prime, Summer Stratified,
    Extreme Thermal Load). `resolve_water_clarity(secchi_ft, stain_color)` bridges the
    3-band Secchi system (turbidity only) to the 4-value `core.lures.WATER_CLARITY_
    OPTIONS` the color engine actually needs (which also encodes stain color): Clear
    and Dirty/Muddy map 1:1, but the middle "Stained" band is ambiguous about color, so
    the page asks a follow-up stain-color question only in that case, defaulting to
    "Brown stained" (Nolin's documented normal stain) if left unset. A small
    `precipitation_proxy()` turns a plain-language precipitation pick into the
    total-inches/max-storm-probability pair the storm-warning logic already expects.

    `core/scoring.py` was refactored, not duplicated: the pressure/moon/solunar/cloud/
    wind/season/storm formula that used to live only inline in `score_day()`'s
    per-segment loop was pulled out into a new pure `_segment_score(...)` helper, which
    `score_day()` now calls too (verified behavior-preserving - existing tests still
    passed immediately after the extraction, before anything new was added). A new
    `manual_segment_score(segment_name, season, avg_cloud_pct, avg_wind_mph, ...)`
    calls that same helper from hand-entered/on-the-spot inputs instead of a weather
    bundle, so the two entry points can never drift apart - a new cross-validation test
    feeds both paths equivalent inputs and asserts identical scores. `realtime_context_
    from_bundle()` opportunistically pulls in real pressure-trend and solunar-overlap
    data from a weather bundle when one is reachable (degrades to neutral defaults -
    0.0 trend, no solunar overlap - if not, e.g. the forecast API being unreachable).
    New `lake_now_naive()` returns "now" as a naive datetime in the lake's own
    timezone, matching this module's existing (if loosely-named) convention of passing
    naive-but-actually-local timestamps to `core.astro`, rather than introducing a
    real UTC/local mismatch by reaching for `datetime.utcnow()`.

    A new one-way `LOCATION_TYPE_TO_STRUCTURE_TYPE` dict in `core/lake_spots.py`
    bridges every `LOCATION_TYPES` value to a `core.lures.STRUCTURE_TYPES` value
    (asserted complete/valid at import time) - used only by the new page, so the
    spot catalog itself stays decoupled from the recommendation engine exactly as
    entry 27 intentionally left it.

    `pages/6_Spot_Session.py` ties it together: a "Conditions right now" form
    (water temp, Secchi/visibility + conditional stain color, wind, light condition,
    precipitation, exact start time, time-window segment, plus an optional
    "Additional details" expander for forage/fish-depth/thermocline) resolves water
    clarity and structure type, pulls in whatever real-time pressure/solunar context
    it can get, scores the segment, and calls the same `core.lures.recommend()` +
    `core.ui.render_lure_recommendation()` used by the 7-Day Forecast page - so this
    page's suggestions come from the identical lure/color engine, just fed by an
    on-the-water reading instead of a forecast. Below that, a "Log actual activity"
    form writes a `core.storage.TripEntry` (spot id/name, resolved structure/clarity,
    lure/color/technique, fish caught, `predicted_score` from this page's own scoring)
    into the same shared `data/trip_log.csv` that `pages/3_Log_a_Trip.py` already
    writes to, tagged `"source": "spot_session"` in its `conditions_json` blob - this
    is deliberately the same file, not a new one, since the user's stated direction is
    to eventually fold trip logging into one report database; this round just makes
    sure both entry points already accumulate into that one place, without touching
    `pages/3_Log_a_Trip.py` or `pages/4_Trip_History.py` themselves.
30. **Fix: "Fish this spot now" landed on an empty Spot Session page** - the user
    reported that clicking a saved spot on the Lake Map, then clicking "🎯 Fish this
    spot now," opened `pages/6_Spot_Session.py` showing "No spot selected" instead of
    that spot. Root cause: entry 29's handoff relied solely on `st.query_params`, set
    right before `st.switch_page()` in the same script run - but `st.switch_page`
    doesn't reliably carry query params set in that same run over to the new page's
    initial load in real browser navigation (this gap wasn't caught by the earlier
    `AppTest` verification because that test set `query_params` directly on the target
    page's own `AppTest` instance, rather than simulating a real button click on one
    page landing on another).

    Fixed by making `st.session_state["spot_session_target_id"]` the primary handoff
    channel - `pages/2_Lake_Map.py`'s button now sets both session state and
    query params before switching; `pages/6_Spot_Session.py` reads session state first,
    falling back to query params (so a manual refresh or a bookmarked/shared
    `?spot_id=...` link still resolves), then syncs both back once a spot is found so
    the page's own URL stays correct for a subsequent refresh. Verified with three
    `AppTest` scenarios against a throwaway spot: session-state-only (the real button
    flow), query-params-only (bookmark/refresh), and neither set (still shows the
    graceful "no spot selected" placeholder rather than crashing) - all three resolve
    correctly; full suite re-run clean afterward.
31. **Spot Session refinements: real time-window ranges, descriptive wind, inventory-
    driven logging, exact-time scoring** - a round of usability feedback on entry
    29/30's page, once it was actually usable in the browser:

    - **Session start is now manual, not auto-"now"** - `st.time_input(..., value=None)`
      instead of defaulting to `lake_now_naive().time()`, since the angler might fill
      this out before heading out or after getting home, not necessarily at the exact
      moment they started fishing. Required before "Get lure suggestions" proceeds
      (a blank submit shows a warning instead of silently guessing).
    - **Wind is now a descriptive band picker, not an mph number** - most anglers can
      judge "glassy vs. light ripple vs. whitecapping" by eye far more reliably than
      an actual mph figure. New `core.onwater.WIND_BAND_LABELS`/`wind_mph_for_band()`
      (a reverse lookup - representative mph within each band) lets the page ask for
      the band by name while the scoring formula still runs on an mph value
      underneath, same as a real forecast's `windspeed_10m`.
    - **Time window options now show today's real clock range** - "Dawn (5:52 AM-7:52
      AM)" instead of just "Dawn," using new `core.scoring.segment_time_ranges()`
      (factored out of `realtime_context_from_bundle()`'s existing sunrise/sunset
      lookup, so both share one implementation) when a weather bundle is reachable;
      falls back to bare segment names otherwise.
    - **Stirred-up/muddy checkbox** - `core.onwater.resolve_water_clarity()` gained a
      `stirred_up: bool = False` parameter that, when true, returns "Muddy" outright
      regardless of the Secchi reading or stain color - mirrors `core.lures.
      resolve_water_clarity()`'s existing base-stain + stirred-up-checkbox model used
      elsewhere in the app, applied to this page's Secchi-based model instead of
      replacing it.
    - **Forage no longer pre-populates** - the "Forage seen" multiselect now defaults
      to `[]` instead of `DEFAULT_FORAGE`, since pre-checking Gizzard Shad/Bluegill
      implied "seen" when the angler hadn't actually reported seeing anything yet.
    - **Thermocline input removed** - dropped the "Thermocline depth" field and the
      `thermocline_ft` argument to `recommend()` (which already defaults to `None`
      and degrades gracefully - `core.thermocline` itself is untouched, still used by
      the 7-Day Forecast/Log a Trip pages' sidebar).
    - **Scoring now uses the angler's entered start time, not wall-clock "now," as
      "the exact moment"** - previously, `realtime_context_from_bundle()`'s pressure-
      trend lookup and `manual_segment_score()`'s moon-phase lookup both silently used
      `lake_now_naive()` (whatever time it happened to be while the form was being
      filled out) rather than the time window the angler actually cares about. Both
      functions gained an optional `at_time: datetime` parameter (default `None` -
      still falls back to "now", so `score_day()`/`score_week()` and existing callers
      are unaffected); the page now combines today's date with the manually-entered
      session-start time (entry above) and passes that through, so "for that exact
      time of day" means the time the angler actually fished, not whenever they
      happened to be sitting at this page. A caption under the score now says so
      explicitly ("Scored for about 7:30 AM - your entered session start time").
    - **Log form: pick the lure (and trailer) from inventory, with color auto-fill** -
      new `core/activity_log.py` holds the picker/vocabulary helpers. The lure and
      (conditional) trailer selectboxes live *outside* `st.form(...)`, not inside it -
      `st.form` only delivers widget values to Python on submit, so a selectbox
      inside one can't reactively drive another widget's default the moment you pick
      it; moving the picker outside makes the whole page rerun immediately on
      selection, and the "Color used"/"Trailer color" text inputs (still inside the
      form) are keyed off the current pick's index (`key=f"...{lure_idx}"`) so they
      re-initialize with a fresh default - the picked item's own `description` field,
      the closest thing to a structured "color" this app has (same field
      `core.lures._color_tokens()` already keys off of elsewhere) - every time the
      pick changes, while still leaving the field freely editable afterward. Choosing
      "Other / not in inventory (enter manually)" (`activity_log.OTHER_LABEL`) shows a
      plain text field instead. The trailer picker is hidden outright only when the
      selected lure's inventory `category` maps to a `core.lures.LURE_PROFILES` entry
      that's positively known to never take one (crankbaits, jerkbaits, topwaters,
      etc. - `trailer: None`) - it defaults to *shown* for a manually-entered lure or
      an unrecognized/uncategorized item, since hiding a trailer option that might
      actually apply is worse than showing one that doesn't.
    - **New log fields**: time range the lure was fished (start/stop, both optional),
      depth fished (a primary-depth number plus a free-text "or several depths tried"
      note, rather than a mode-switching control, to sidestep the same forms-
      reactivity limitation above for a field that didn't need live auto-population),
      fish activity (`FISH_ACTIVITY_OPTIONS`, a `st.select_slider` from "Very active"
      to "Inactive / shut down"), forage type seen at logging time (reuses `core.
      lures.FORAGE_OPTIONS`, pre-filled from whatever was picked in the conditions
      form above but independently editable, since forage activity can change over
      the course of a session) plus forage activity level (`FORAGE_ACTIVITY_OPTIONS`),
      retrieve speed (`RETRIEVE_SPEED_OPTIONS`: Slow/Medium/Fast), and retrieve style
      (`RETRIEVE_STYLE_OPTIONS`: straight retrieve, twitch, jerk, stop-and-go, plus a
      few more common techniques added as a reasonable default set beyond what was
      explicitly asked for, same as this page's earlier `notes` field). None of this
      needed a `core/storage.py`/`trip_log.csv` schema change - it all packs into
      `TripEntry`'s existing flexible `conditions` dict (serialized as
      `conditions_json`), the same way `modeled_thermocline_ft` already did before
      this round removed it.

    Verified end-to-end via `AppTest`, simulating real interactions rather than
    pre-setting values directly (submitting the conditions form, picking an inventory
    lure and confirming the color field's value updated, picking a trailer-capable vs.
    trailer-incapable lure and confirming the trailer checkbox appeared/didn't, and
    submitting the log form and reading back the resulting `trip_log.csv` row) against
    throwaway spots/log rows, cleaned up afterward; full test suite (148 tests,
    including new `tests/test_activity_log.py` and additions to `tests/test_onwater.py`
    / `tests/test_scoring.py`) re-run clean.
32. **Score beyond pressure/moon: water temp, water clarity, forage, light rain +
    a "how was this derived" hover** - the user wanted the Spot Session score to
    actually use the rest of what they enter (water temp, clarity, forage), not just
    pressure trend and moon phase, and wanted transparency into how the number came
    together.

    `core.scoring._segment_score()` gained three new optional parameters -
    `water_temp_f`, `water_clarity`, `forage_present` - each **manual-entry-only**:
    `score_day()`/`score_week()` never pass them (their call site is unchanged), so
    the forecast-driven path's numeric output is byte-for-byte identical to before
    this round (verified by a new test asserting none of these labels ever appear in
    `score_day()`'s per-segment breakdown, on top of the full existing suite passing
    unmodified). Only `manual_segment_score()` supplies them, since a real Secchi
    reading or "did you see forage" observation only exists when someone is standing
    at the water. Water temperature reuses `core.onwater.water_temp_band()`'s bands
    (Cold/Lethargic penalty, Pre-Spawn Transition small bonus, Peak Optimal Prime
    bonus, Summer Stratified deliberately neutral since `season_summer_midday_penalty`
    already partially covers summer heat, Extreme Thermal Load penalty) - standard
    bass metabolic-rate-curve reasoning, not a novel model. Water clarity gives stained
    water (Nolin's documented "power-fishing window") a small bonus and muddy water a
    small penalty (harder to trigger reaction strikes on sight alone), leaving clear
    water neutral rather than asserting it's uniformly better or worse. Forage gives a
    small bonus when the angler reported seeing any forage type - absence isn't
    penalized, since not seeing forage isn't evidence there's none around.

    One new factor - a small bonus for light/steady rain short of storm level - was
    added as a **shared** enhancement instead (both `total_precip_in` and
    `max_precip_prob_pct` already exist in both paths from a real forecast bundle),
    reflecting the well-documented pattern that light rain reduces light penetration
    and fish wariness without the storm penalty's downside; a new test confirms
    `score_day()` picks this up too when a synthetic bundle carries light rain.

    `_segment_score()` now also returns a `breakdown` list - `(label, delta, detail)`
    for every factor that actually moved the score, base value included - alongside
    the existing `notes` list (kept as-is, since other code already reads it).
    `SegmentForecast` and `ManualScoreResult` both gained a `breakdown` field
    (defaulted via `field(default_factory=list)` so no other construction site needed
    updating). `pages/6_Spot_Session.py` turns this into the requested "little ? to
    hover over": `st.metric(..., help=...)` already renders a small hover-info icon
    next to a metric's value, so no new UI framework/component was needed - the page
    just formats `score_result.breakdown` into a markdown bullet list (one line per
    factor, "+delta — detail") and passes it as `help=`, plus a closing line noting
    the raw-total-vs-clamped-final score when clamping actually changed anything.

    Considered and deliberately left out for now: threading water temp/clarity into
    `score_day()` too (would change the general 7-Day Forecast's already-tested/
    deployed scores, which wasn't asked for - the request was specifically about the
    Spot Session page's own entered data); a light-condition-vs-clarity interaction
    bonus (e.g. extra penalty for clear water + direct high sun at midday) - the
    existing cloud-cover-proxy mechanism already captures most of that signal via
    `avg_cloud_pct`, and stacking a second, correlated bonus/penalty on the same
    underlying condition risks double-counting rather than adding real information;
    and species-specific forage bonuses (shad vs. bluegill vs. crawfish) - a single
    presence/absence signal keeps the rule explainable, matching this app's
    documented "no black box" scoring philosophy.
33. **Drop the "≈ N mph" wind caption; give the sidebar nav real titles/icons** - two
    small, unrelated pieces of feedback landed together.

    The wind band picker on the Spot Session page (entry 31) showed a caption like
    "≈ 6 mph" under the selectbox to make the underlying proxy value visible - removed
    per feedback that it wasn't wanted. `wind_mph_for_band()` itself is untouched
    (still used to drive `avg_wind_mph` for scoring), only the `st.caption()` line
    displaying it is gone.

    The sidebar page list was still using Streamlit's older file-based `pages/`
    auto-discovery, which (a) always listed the entry script itself as a page named
    "app" (derived from the filename `app.py`, which isn't a real page - it's just
    where the script starts), and (b) had no way to attach a per-page icon, only the
    filename-derived text label. Fixed by switching to the explicit `st.navigation`/
    `st.Page` API (Streamlit >=1.36; this app already runs 1.61): `app.py`'s previous
    landing-page content moved verbatim to a new `home.py` (byte-for-byte identical,
    including its own `st.set_page_config()` call), and `app.py` itself became a thin
    entry point that does nothing but build `st.navigation([st.Page(path, title=...,
    icon=...), ...])` for `home.py` + all six `pages/*.py` files (same relative paths,
    so the existing `st.switch_page("pages/2_Lake_Map.py")` / `st.switch_page("pages/
    6_Spot_Session.py")` calls between the Lake Map and Spot Session pages still
    resolve correctly - verified, not just assumed) and calls `.run()`. Titles now
    read "Today," "7 Day Forecast," "Lake Map," "Log a Trip," "Trip History," "Lure
    Inventory," "Spot Session" (same order/wording as before, just no more "app"),
    each with the same emoji icon that page's `st.set_page_config(page_icon=...)`
    already used for its browser-tab icon, so the sidebar and the tab now visually
    match. Every other page file is completely unchanged - each still calls its own
    `st.set_page_config()` (still safe under `st.navigation`, since `app.py` itself
    calls no Streamlit commands before handing off via `pg.run()`, so the target
    page's `set_page_config()` is still effectively "the first Streamlit command" for
    that run) - confirmed empirically (not just by reasoning about the API) by
    launching the real app with `streamlit run app.py`, screenshotting the rendered
    sidebar, and clicking through to the Lake Map page to confirm active-page
    highlighting and navigation both work; `AppTest.switch_page()` was also used to
    exercise all seven destinations (plus the two inter-page `switch_page` calls)
    programmatically, alongside the full test suite (unaffected - no `core/` logic
    changed).
34. **Retire `pages/3_Log_a_Trip.py`; rebuild Trip History as a filterable log** -
    realizes the "ultimate direction" flagged back in entry 29 (retiring the
    standalone log form once Spot Session could log directly), now that Spot Session
    has grown a full log-activity section (entry 31 onward) that's strictly richer
    than the old form ever was.

    `pages/3_Log_a_Trip.py` is deleted outright - no redirect stub, since
    `st.navigation` already removes it from the sidebar the moment its `st.Page(...)`
    entry is gone from `app.py`'s list. `home.py`'s intro bullets were updated to
    match: the "Log a Trip" bullet is gone, and the "Lake Map" bullet now mentions
    Spot Session's logging role. `core/lake_spots.py`'s module docstring, which
    referenced the deleted page by name, was reworded.

    `pages/6_Spot_Session.py`'s log form gained two new `conditions` keys,
    `lure_category`/`trailer_category` (the raw `core.lures.LURE_PROFILES` key, e.g.
    `"football_jig"` - only set when picked from inventory), specifically so Trip
    History's new "lure type" filter has a real category to filter on instead of
    fuzzy-matching the free-text `lure_used` field.

    `pages/4_Trip_History.py` is a full rewrite. Both logging paths already wrote into
    the same `data/trip_log.csv` via `core.storage.TripEntry` (entry 29), so no
    storage change was needed - the page now reads all rows, parses each row's
    `conditions_json` once up front, and derives a `lure_type` label per row (`core.
    lures.LURE_PROFILES[lure_category]["name"]`, or "Unspecified / manual entry" for
    rows without a category - covering both manually-typed lures and every pre-entry-
    34 logged row). Filters: date range, time of day (segment), location (spot name),
    lure type, water clarity, structure type, "only trips with a catch," and a free-
    text search across lure/color/notes - all combined with plain pandas boolean
    masking, no new dependency. The trips table and its three summary metrics (trips
    shown, total caught, catch rate) recompute over the *filtered* subset; the
    calibration status section deliberately keeps reading *all* logged rows
    unfiltered, since calibration is a property of the model as a whole, not of
    whatever slice the user happens to be looking at.

    The old "Raw conditions snapshots (debug)" JSON dump is replaced with a "Trip
    details" section - one expander per trip, titled `date · spot · segment`, showing
    a short always-present summary (lure, technique, catch count, predicted score,
    notes) plus a curated, human-readable list built from a `FIELD_SPECS` table of
    `(json_key, label, formatter)` tuples covering essentially every field either
    logging path can produce (water temp, secchi, wind band, light condition,
    pressure trend, moon phase, retrieve speed/style, trailer info, the legacy
    `modeled_thermocline_band_ft`, etc.), skipping whichever keys a given row doesn't
    have - so legacy Log-a-Trip rows and rich Spot Session rows both render sensibly
    without special-casing which page produced them, and a small `source` badge
    ("🎯 Spot Session" vs. "📝 Legacy") makes the origin obvious at a glance.

    Verified with the usual full suite + `AppTest` smoke test across the app entry
    point and every remaining page, plus a dedicated scratch `AppTest` script (not
    committed) that appended synthetic legacy- and Spot-Session-shaped trips to a
    backed-up copy of `data/trip_log.csv`, drove the new lure-type multiselect and
    catches-only checkbox through `AppTest`, confirmed the filtered count updated
    correctly, confirmed both trip types' expanders rendered without exceptions, then
    restored the original (empty, in this dev environment) trip log from the backup.
35. **Trip History's "Location" filter now resolves against the live saved-spot
    catalog** - it previously grouped trips by whatever `spot_name` string got frozen
    into the trip row at logging time, so renaming a saved spot on the Lake Map page
    would splinter its trip history across two different filter entries (the old
    name and the new one). Fixed by looking each trip's `spot_id` up against
    `core.appstate.get_lake_spots()` (the same live `data/lake_spots.csv` catalog the
    Lake Map page reads/writes) and using its *current* `name` for the Location
    filter, the trips table, and each trip-detail expander's title - falling back to
    the row's stored `spot_name` only when `spot_id` doesn't match any saved spot
    (a deleted pin, or a legacy row logged against `core.spots`'s separate reference-
    spot list, which uses its own unrelated ID namespace). Verified with a scratch
    `AppTest` script (not committed) that logged a trip against the one real saved
    spot with a deliberately stale `spot_name`, confirming the Location filter shows
    only the spot's current name and never the stale one.
36. **Clean up the 7-Day Forecast page's Lake Setup Options sidebar** - four requests
    landed together: drop the thermocline input, turn structure-type picking into a
    saved-spot-aware "Location" picker, stop pre-checking any forage, and tighten the
    whole sidebar's vertical footprint.

    The thermocline `st.number_input` (plus its seasonal-estimate caption) is gone,
    mirroring the same removal already done for Spot Session's conditions form back in
    entry 32 - `core.lures.recommend()` keeps its optional `thermocline_ft` parameter
    and caveat logic (still exercised directly by `tests/test_lures.py`), it's just
    that no page passes it anymore. `core/thermocline.py` is left in place, matching
    this codebase's pattern for other now-unwired modules (`core/spots.py`, entry 34) -
    it's a bigger piece of domain modeling than felt right to delete over a UI change,
    and a future page could still opt back into passing `thermocline_ft` without any
    changes to `recommend()` itself.

    "Structure type" is replaced with a **Location** dropdown listing the angler's own
    saved spots (`core.appstate.get_lake_spots()`, the same catalog the Lake Map page
    reads/writes) plus an "Other" option. Picking a saved spot resolves its structure
    type automatically via `core.lake_spots.LOCATION_TYPE_TO_STRUCTURE_TYPE` - the
    exact same lookup Spot Session already uses (entry 27) - so a spot's structure only
    needs to be recorded once, on the Lake Map page, and it's simply correct everywhere
    else it's used. Picking "Other" reveals a second, plain `STRUCTURE_TYPES` dropdown
    (the same list/default this page always had) for a spot that isn't saved, or isn't
    a specific spot at all. "Other" is the default selection, so behavior for anyone
    not using saved spots is unchanged from before.

    Forage's `multiselect` default changed from `DEFAULT_FORAGE` (Gizzard Shad +
    Bluegill/Sunfish pre-checked) to `[]`, matching the same "don't presume an answer
    the angler hasn't confirmed" change already made to Spot Session's forage picker
    (entry 32) - an empty selection now means "not specified" to the lure engine rather
    than silently asserting a forage base.

    Layout tightening: water stain + stirred-up, and water temp + fish depth, are each
    now a `st.columns(2)` pair instead of stacked full-width fields; both `st.divider()`
    calls and two multi-line captions ("Enter your own readings...", "These carry over
    to the other pages too" - the latter was also just stale, since Lake Map stopped
    calling this same sidebar function once Spot Session took over on-the-water
    recommendations) are gone, with their explanatory text folded into each widget's
    `help=` tooltip instead of a separate line - font size and every label stay exactly
    as they were, only the surrounding whitespace and standalone caption lines shrink.

    Verified with the full test suite (untouched - no `core/` behavior changed, only
    which optional arguments a page passes) plus a scratch `AppTest` script (not
    committed, since `pages/1_7_Day_Forecast.py` itself can't run end-to-end in this
    sandbox - see the standing Open-Meteo network note) that called
    `render_lake_setup_sidebar()` directly: confirmed the Location dropdown lists the
    one real saved spot plus "Other" (defaulting to "Other"), confirmed picking that
    spot hides the manual Structure Type dropdown and resolves the correct structure
    from its saved type, confirmed switching back to "Other" brings the manual dropdown
    back with the right default, and confirmed forage starts empty.
37. **Evidence-based scoring rebalance** - the user noticed the 7-Day Forecast's scores
    felt consistently too optimistic. Rather than treat this as something logged trips
    would eventually correct on their own, a quick Monte Carlo check (20,000 randomized
    but realistic day/segment combinations run directly through `_segment_score()`,
    scratch script, not committed) confirmed it quantitatively: mean score 7.0, median
    7.1, on a scale meant to center around 5 - with 53% of combinations scoring 7+ and
    only 9% at 4 or below. Per-factor breakdown showed it wasn't one bad weight but six
    separate factors (solunar, cloud cover, wind, moon phase, season, pressure trend)
    each mildly-to-moderately bonus-skewed and stacking in the same direction, against
    only precipitation pulling the other way - `core/calibration.py` can't fix this
    even given lots of logged data, since it only ever nudges 5 of the ~15 weight keys
    (`pressure_falling`, `pressure_high_stable_post_front`, `moon_new_full_bonus`,
    `cloud_overcast_bonus`, `wind_sweet_spot_bonus`) within ±35% of their existing
    (biased) defaults - it can't touch the base value or the other 8+ factors at all.

    Rather than just adding symmetric penalties everywhere, each factor was checked
    against outside research first and reweighted to match how well-supported it
    actually is - see README.md's "How the model works" section for the full
    citation list (a 2023 peer-reviewed *SN Applied Sciences* study testing 7
    commercial solunar services against 361 real freshwater trips found no predictive
    value at all, and found temperature to be the one variable that did predict catch
    rate; a detailed critique citing oceanographer Dr. David Ross and a controlled
    12-month single-lure experiment found no significant catch-rate difference by
    barometric pressure alone; Bassmaster's cold-front coverage confirms the
    "bluebird sky = tough bite" pattern is near-universal professional-angler
    consensus). Concretely:
      - `pressure_falling` 2.5→1.5, `pressure_high_stable_post_front` -2.0→-1.5,
        `pressure_rising_slow` -0.5→-0.4 - trimmed from the model's single biggest
        lever to something more proportionate to its contested evidence, while keeping
        it as a believable proxy for a front's real, better-evidenced side effects.
      - `solunar_major_bonus` 2.0→0.6, `solunar_minor_bonus` 1.0→0.3 - kept as a small
        token acknowledgment of a popular belief rather than dropped outright, given
        how weak the evidence is.
      - `moon_new_full_bonus` 1.5→0.6, plus a new `moon_quarter_penalty` (-0.5) and a
        new `MoonPhase.is_quarter_window` field (`core/astro.py`, same ~2-day-window
        pattern as the existing `is_new_or_full_window`) - moon phase is now genuinely
        two-sided (a real penalty near the quarter moons) instead of a one-way bonus
        that fired for about a third of every month with zero effect the other
        two-thirds. Deliberately kept as a simple discrete threshold+flag (matching
        every other factor's style) rather than a continuous curve, to stay
        consistent with the app's "no black box, every rule has a comment" philosophy.
      - `cloud_overcast_bonus` 1.2→1.0, plus a new `cloud_clear_sky_penalty` (-0.8) for
        `avg_cloud <= 25%` - genuinely two-sided now instead of bonus-only, matching
        the well-documented "bluebird skies = tough bite" pattern.
      - `wind_sweet_spot_bonus` 0.8→0.5, `wind_calm_or_high_penalty` -0.8→-0.5 - already
        two-sided, trimmed further since wind had literally zero measured effect in
        the one directly-relevant peer-reviewed study, the weakest evidence of any
        factor still in the model.
      - `score_day()`/`score_week()` now pass their own daily *estimated* water temp
        into `_segment_score()`'s existing metabolic-band bonus/penalty logic
        (`water_temp_cold_penalty`/`water_temp_prespawn_bonus`/`water_temp_prime_bonus`/
        `water_temp_extreme_penalty`, `core/onwater.py`'s `WATER_TEMP_BANDS`) - this
        logic already existed and was already tested for Spot Session's exact
        reading, it just wasn't wired into the forecast path before. This is the
        single factor real research found to actually matter, so it's now a shared
        enhancement rather than manual-only - `water_clarity`/`forage_present` stay
        manual-only, since neither has a forecast-API equivalent to estimate from.
      - `season_spring_fall_bonus`/`season_summer_midday_penalty`/`season_winter_penalty`
        were left untouched - metabolic/spawning-behavior seasonality is the
        best-evidenced factor in the whole model, not a rebalance target.

    Re-running the same Monte Carlo check afterward (same script, updated to also
    sample a water temp per iteration) gives mean 5.7, median 5.8 - both tails far
    more balanced (10-ceiling combinations dropped from 11.3% to 1.1%, 4-or-below
    combinations rose from 8.9% to 19.9%). Not forced all the way to exactly 5.0,
    since the remaining lift comes from season (the best-evidenced factor left) and
    residual wind/cloud effects under realistic input distributions, not from
    anything that still looks like a design flaw.

    `core/calibration.py` is untouched - it still only calibrates the same 5 legacy
    factor keys against their new (smaller, less biased) defaults, same known
    limitation as before regarding the uncalibrated factors (now including the two
    new ones, `moon_quarter_penalty` and `cloud_clear_sky_penalty`).

    Verified with the full test suite (two new/updated tests for `score_day()`'s new
    water-temp wiring - one forcing a deterministic cold-water estimate via a custom
    fake weather bundle regardless of what date the suite runs on, one confirming the
    intentionally-neutral Summer Stratified band still doesn't fire - plus two new
    tests confirming moon phase and cloud cover are each genuinely two-sided now) and
    the AppTest smoke test across all pages that can run in this sandbox.
38. **Start a Spot Session directly, without going through the Lake Map first** -
    previously the only way to reach `pages/6_Spot_Session.py` with a spot loaded was
    the Lake Map page's "🎯 Fish this spot now" button; landing on Spot Session with no
    spot selected was a dead end (an info message + a button back to the map). Added a
    `st.selectbox` of the angler's own saved spots (alphabetized, `get_lake_spots()` -
    the same `data/lake_spots.csv` catalog the Lake Map page and the 7-Day Forecast's
    Location picker, entry 36, both already read from) right on that dead-end screen,
    with a `"— choose a saved spot —"` placeholder as index 0 (same index-offset
    pattern `core/activity_log.py`'s `lure_picker_options()`/`OTHER_LABEL` already
    uses, for the same reason: robust against two spots ever sharing a name, since the
    real value is the list index, not the display string). Picking one sets
    `st.session_state["spot_session_target_id"]`/`st.query_params["spot_id"]` - the
    exact same two-channel handoff the Lake Map button already writes to, per the
    comment already on that code from entry 30's fix for the original "clicked a
    saved spot, got 'No spot selected'" bug - then calls `st.rerun()`, so the rest of
    the page (which only ever reads spot_id from those same two places) treats
    "arrived via this dropdown" identically to "arrived via
    the map," no separate code path needed. If the angler has no saved spots yet, the
    dropdown is skipped in favor of a caption pointing them at the Lake Map page to
    drop a pin first, rather than showing an empty/single-option selectbox.

    Verified with the full test suite (untouched - no `core/` logic changed, this is
    entirely inside `pages/6_Spot_Session.py`) plus two scratch `AppTest` scripts (not
    committed): one confirming picking a saved spot from the new dropdown lands on
    that exact spot's session screen with both handoff channels correctly set, one
    confirming the no-saved-spots-yet fallback (temporarily emptying a backed-up copy
    of `data/lake_spots.csv`) renders the caption instead of a dropdown with no
    exception - plus the usual AppTest smoke test across all pages that can run in
    this sandbox.
39. **Spot Session: session date field, collapsible sections, and per-fish catch
    records** - a bigger redesign of the "after the conditions form" half of
    `pages/6_Spot_Session.py`, driven by the angler wanting a real per-fish catch log
    instead of a single "bass caught" count + "biggest fish" pair:
    - Added a `st.date_input("Session date", ...)` right under the spot name/back
      button, defaulting to today and capped at today (`max_value=lake_today()`) so
      the angler can log a past session at this spot but never a future one. The
      `today` variable that used to feed `segment_time_ranges()`/`season_stage()`/
      `realtime_context_from_bundle()`/the trip's `trip_date` was renamed to
      `session_date` and now comes from this widget everywhere. No new error
      handling was needed for past dates - `core/scoring.py`'s
      `segment_time_ranges()`/`realtime_context_from_bundle()` already degrade
      gracefully (try/except, falling back to `None`/neutral defaults) for a date
      outside the current weather bundle's coverage window, the same fallback path
      that already fires whenever `bundle` itself is `None`.
    - "Suggestions for right now" and the old "Log actual activity" section (renamed
      "Add results") are each now their own `st.expander` - the suggestions one
      defaults open (`expanded=True`, since it's the main reason to visit this page),
      the new results one defaults closed (`expanded=False`, since it's an
      after-the-fact log entry, not something to stare at while fishing). Both can be
      independently opened/collapsed, per the ask.
    - Inside "Add results," the lure/trailer picker keeps the existing outside-form
      pattern (must live outside `st.form` so picking a different lure/trailer
      reruns immediately and the form's defaults/captions update in the same pass -
      form-internal widgets only trigger a rerun on submit). New alongside it: a
      "Fish caught on this lure in this time window" `st.number_input` (also outside
      the form, since it drives how many per-fish sections appear) and, for each
      fish, a species `st.selectbox` (`core/activity_log.py`'s new
      `FISH_SPECIES_OPTIONS = ["Largemouth Bass", "Spotted Bass", "Striped Bass",
      "Other (type in species)"]` - the angler's own requested vocabulary, not a
      strict biological list; free-text-extensible via "Other" so any imprecision
      versus Nolin's real regulated species costs nothing). Species selectboxes stay
      outside the form too, for the same reactivity reason: picking "Other" needs to
      reveal a free-text species field inside the form on the same rerun.
    - Inside the form: the existing lure/color/trailer/technique/depth/forage fields
      are unchanged; new fields are wind speed (`st.number_input`, mph) and wind
      direction (`st.selectbox`, `core/onwater.py`'s new `WIND_DIRECTIONS` - 8-point
      compass plus "Variable"/"Calm", distinct from the plain-language `WIND_BANDS`
      picker in the Conditions form above, which drives the live score rather than
      being a logged fact); "Notes" is now explicitly framed as notes for this
      lure/time-window rather than the whole session. The old flat "Bass caught"/
      "Biggest fish (lb)" number inputs are gone, replaced by one expander section
      per fish (index-matched to the outside-form species pickers) capturing weight,
      length, depth caught, retrieve speed (reusing `RETRIEVE_SPEED_OPTIONS`),
      retrieve style/action (reusing `RETRIEVE_STYLE_OPTIONS` - already covers the
      angler's "steady"/"stop-start"/"intermittent jerks" wording via "Straight
      retrieve (no action)"/"Stop-and-go"/"Twitch"/"Jerk", so no second vocabulary
      was invented), and per-fish notes.
    - On submit, `conditions["fish"]` stores the full list of per-fish dicts
      (`species`, `species_other`, `weight_lb`, `length_in`, `depth_ft`,
      `retrieve_speed`, `retrieve_style`, `notes`), plus new `wind_speed_mph`/
      `wind_direction` keys - all inside the existing flexible `conditions` JSON
      blob, no CSV schema change. `TripEntry`'s top-level `fish_caught`/
      `biggest_fish_lb` fields (read by Trip History's metrics and
      `core/calibration.py`'s factor-flag logic) are now *derived* from that list
      (`len(fish_records)` / `max(weights)` or `None`) rather than asked for
      separately, so nothing downstream needed to change and there's no
      double-entry to keep in sync.
    - `pages/4_Trip_History.py`'s per-trip detail expander got two new simple
      `FIELD_SPECS` rows (`wind_speed_mph`, `wind_direction`) and a dedicated
      renderer for the new `fish` list (one "Fish #N: species, weight, length,
      depth, presentation" line per catch, with notes as a caption underneath) -
      the existing generic `", ".join(v) if isinstance(v, list) ...` formatter
      would otherwise have shown a raw Python list-of-dicts string for any trip
      logged through the redesigned form.

    Verified with the full test suite (unchanged - no existing test logic touched)
    plus two scratch `AppTest` scripts (not committed): one confirming the date
    field, both expanders, and the reactive per-fish species picker (setting fish
    count to 2, picking "Other" for one, and seeing its free-text field appear on
    the same rerun without submitting); a second driving a full submission (2 fish,
    one plain species, one "Other" with free text, wind speed/direction filled in)
    through to `data/trip_log.csv`, confirming the persisted row's `conditions_json`
    has the expected `fish` list and `wind_speed_mph`/`wind_direction`, that
    `fish_caught`/`biggest_fish_lb` were correctly derived, and that
    `pages/4_Trip_History.py` renders that row (including the new per-fish lines)
    without raising - the test-added row was reverted from `data/trip_log.csv`
    afterward so no synthetic data was left behind.
40. **"Add results" reflow: image lure picker, grouped conditions, add-fish-as-you-go**
    - a follow-up to entry 39's per-fish redesign, changing HOW the same information
    gets entered rather than what's captured:
    - **Image lure/trailer picker.** A plain `st.selectbox` can't show a photo inside
      its own option list - no browser `<select>` element supports that - so "Lure
      used" (and, when "Used a trailer" is checked, "Trailer") is now a searchable
      card grid instead: a text search box over brand/description, then a 4-per-row
      grid of bordered cards (`core.ui.render_square_thumbnail` - the exact same
      thumbnail helper `pages/5_Lure_Inventory.py`'s browse grid already uses, so no
      new image-rendering code was written) each with a "Select" button. Picking one
      writes the item's `item_id` to `st.session_state`; a "Selected: ..." caption +
      "Clear" button underneath shows/undoes the current pick. This whole picker
      (`_visual_lure_picker()`, a new module-level helper in
      `pages/6_Spot_Session.py`) lives outside any `st.form` for the same reason the
      old plain selectbox did: a card click needs an immediate rerun so downstream
      fields (default color, trailer eligibility) update in the same pass, and a form
      only reruns on submit. It returns the selected inventory row or `None`, and
      every existing "is a lure selected or not" downstream check
      (`lure_can_take_trailer(selected_lure_item)`, the manual-entry fallback text
      inputs, `lure_category` in the saved conditions) keeps working completely
      unchanged - only the *picking* mechanism changed, not what gets stored.
    - **Grouped conditions.** Everything about the lure itself (the new picker, color,
      trailer, technique, depth fished) now renders together first under "Lure used,"
      followed by a "Conditions during this lure use" group holding exactly the six
      fields asked for, in that order: time range, wind speed/direction, fish
      activity, forage activity, forage type seen, notes. A "Fish caught" section
      comes last.
    - **No more st.form for this section at all.** Entry 39's design still wrapped
      most of "Add results" in `st.form(...)`, with only the lure/trailer/species
      pickers living outside it (forms can't contain plain `st.button`s, only a
      submit button, so anything needing a click-triggered rerun has to be outside).
      This round's new image-card picker and the new "Add fish" flow (below) both
      need that same click-and-rerun behavior throughout, so rather than split the
      section across a form/non-form boundary in two different places, the whole
      section dropped `st.form` and became one plain `st.button("Log this session")`
      that reads the current value of every widget already computed earlier in the
      same script run - the same pattern the lure picker already used. The trade-off
      (every widget change reruns the script, not just on submit) is the same one the
      lure/trailer/species pickers already accepted before this round; nothing here
      is newly expensive enough to need form-batching.
    - **Add fish, one at a time.** Replaces entry 39's "set a fish count, N sections
      appear" approach with an explicit "➕ Add fish" button that opens one blank
      entry (fish type - reusing `FISH_SPECIES_OPTIONS`, with "Other" free-text same
      as before; weight; length; depth caught at; presentation/technique via
      `RETRIEVE_STYLE_OPTIONS`; retrieval speed via `RETRIEVE_SPEED_OPTIONS`) with its
      own "Save fish"/"Cancel" buttons. Saving appends to a running list in
      `st.session_state[f"pending_fish_{spot_id}"]`, shown above the button as a
      compact "🐟 Fish #N: ..." line with its own "Remove" button, and increments a
      `st.session_state[f"fish_entry_seq_{spot_id}"]` counter that's folded into the
      new entry's widget keys - the standard Streamlit trick for getting genuinely
      blank widgets on the next "Add fish" open, since changing a widget's `key`
      makes Streamlit treat it as a brand-new widget rather than one that needs
      clearing. The per-fish `notes` field entry 39 had is dropped in this round -
      not asked for in the new field list, easy to re-add later if wanted. The
      pending list resets to empty (and the sequence counter to 0) right after "Log
      this session" successfully saves, but the lure/conditions fields above are
      deliberately left as they are, in case the next thing logged is another catch
      on the same lure a few minutes later.
    - `core.activity_log.lure_picker_options()`/`OTHER_LABEL` (the index-offset
      "Other" sentinel helper the old plain selectbox used) are now unreferenced by
      any page - left in place rather than deleted, same as this codebase's existing
      pattern for orphaned-but-still-tested modules (`core/spots.py`, entry 34;
      `core/thermocline.py`, entry 36); `tests/test_activity_log.py` still covers it
      directly. `pages/4_Trip_History.py`'s `retrieve_speed`/`retrieve_style`
      `FIELD_SPECS` rows are similarly now write-only-by-old-data - a trip logged
      before this round still has those top-level conditions keys and still renders
      them, a trip logged after this round doesn't set them at all (presentation is
      per-fish now), so the rows were commented rather than removed.

    Verified with the full test suite (unchanged) plus three scratch `AppTest`
    scripts (not committed): one exercising the image lure picker end-to-end
    (searching narrows the card grid, clicking "Select" persists the pick across a
    rerun, "Color used" auto-fills from the newly-picked item, same as before); one
    confirming the trailer picker (a second, independent instance of the same
    `_visual_lure_picker()` helper) behaves identically; and one driving the full
    "Add results" flow - search+select a lure, set wind speed/direction, add two
    fish one at a time (one plain species, one "Other" with free-text, checking the
    free-text field appears reactively), submit, and confirm the persisted
    `trip_log.csv` row's `conditions_json` (`fish` list, `wind_speed_mph`,
    `wind_direction`), that `fish_caught`/`biggest_fish_lb` were correctly derived,
    that `pages/4_Trip_History.py` renders the new row without raising, and that the
    pending fish list was empty again on the next rerun after submit. The test-added
    row was reverted from `data/trip_log.csv` afterward so no synthetic data was left
    behind.
41. **Trim the "Lure used" section down to just the picker + trailer selector** -
    a follow-up to entry 40: the manual "Lure name"/"Color used"/"Technique/
    presentation"/"Primary depth fished"/"Or, several depths tried" fields
    underneath the new image card picker were called out as unnecessary and
    removed, leaving just the card grid plus the "Used a trailer" checkbox (and,
    when checked, its own card grid/name/color fields - unchanged, explicitly kept).
    `lure_used`/`color_used` are still populated automatically from whichever
    inventory item is picked (label and description respectively - the exact same
    values the removed text fields used to default to, just no longer editable or
    shown), and are blank strings if nothing's picked, since there's no manual-entry
    fallback anymore. `technique_used` is now always `""`. `depth_fished_ft`/
    `depth_fished_varied_note` are no longer collected at all and were dropped from
    the saved `conditions` dict entirely (not just left `None`) - per-fish "depth
    caught at" already covers this in more useful, per-catch detail.
    `pages/4_Trip_History.py`'s `FIELD_SPECS` rows for those two keys got the same
    "only old trips still set this" comment already added for `retrieve_speed`/
    `retrieve_style` in entry 40, rather than being removed, so older history still
    renders correctly.

    Verified with the full test suite (unchanged) plus a scratch `AppTest` script
    (not committed) confirming the four removed widgets are gone, the trailer
    selector still works end to end, and a full submit (lure picked from inventory,
    no fish) produces a `trip_log.csv` row with a populated `lure_used`/`color_used`,
    an empty `technique_used`, and no `depth_fished_ft`/`depth_fished_varied_note`
    keys in `conditions_json` at all - plus confirming `pages/4_Trip_History.py`
    still renders that row without raising. The test-added row was reverted
    afterward.
42. **"Add results" no longer requires filling in Conditions first** - previously
    the whole rest of the page (Suggestions *and* Add results) sat behind
    `if not cond: st.stop()`, so logging a catch meant filling out the entire
    Conditions right now form and clicking "Get lure suggestions" even if the
    angler didn't care about the score/recommendation that trip - they just wanted
    to log what happened. That `st.stop()` is gone; `cond` can now be `None` for
    the rest of the script, and everything downstream was updated to tolerate it:
    - `structure_type` moved up to right after the spot header, since it only ever
      depended on the spot's own saved `location_type` (`LOCATION_TYPE_TO_STRUCTURE_TYPE`),
      never on `cond` - it just hadn't been computed that early before.
    - `water_clarity`/`season`/`avg_cloud_pct`/`avg_wind_mph`/`at_time`/`rt`/
      `score_result` are now all initialized to `None` and only computed inside
      `if cond:`. The "Suggestions for right now" expander only renders when `cond`
      is truthy; otherwise a caption points back at the Conditions form and
      explicitly says logging results doesn't need it.
    - "Add results" (header, caption, and the expander itself) moved out from
      under the old gate entirely and always renders now.
    - The "Log this session" submit handler builds `conditions` in two passes: the
      block of cond-derived keys (`pressure_trend_24h`, `moon_phase`, `wind_band`,
      `water_temp_f`, etc.) only gets added `if cond`, then the lure/trailer/wind/
      fish-activity/fish-list keys (which never depended on `cond`) always get
      added - so a result logged without conditions just has a smaller
      `conditions_json`, read exactly the same way Trip History's `FIELD_SPECS`
      loop already treats any other missing/empty key (skipped, not an error).
      `TripEntry.segment` falls back to the same `_guess_segment(hour)` heuristic
      the Conditions form's own Time window default already uses. `water_clarity`
      falls back to the literal string `"Unknown"` (distinct from all four real
      `core.lures.WATER_CLARITY_OPTIONS` values, so it can't be confused with a
      real reading). `predicted_score` is `None` - **`core.storage.TripEntry.predicted_score`
      changed from `float` to `Optional[float]`** to allow this (no reordering
      needed, since it had no default value before either).
    - `pages/4_Trip_History.py`'s per-trip detail expander now checks
      `predicted_score` for `None`/empty/NaN before formatting it, showing
      "Predicted score: n/a (no live conditions entered)" instead of a bare
      `/10` for these rows; the raw dataframe/CSV export just shows a blank cell,
      same as any other missing numeric field.

    Verified with the full test suite (unchanged) plus two scratch `AppTest`
    scripts (not committed): one confirming that landing on Spot Session and
    going straight to "Add results" - without touching Conditions right now at
    all - shows the expander (and no "Suggestions" expander), logs successfully,
    and produces a `trip_log.csv` row with a blank `predicted_score`,
    `water_clarity` of `"Unknown"`, no cond-derived keys in `conditions_json`, and
    that `pages/4_Trip_History.py` renders that row's "n/a" score line without
    raising; a second re-confirming the original full flow (fill Conditions,
    submit, get suggestions, then log results) still produces a populated score
    and real water clarity, unchanged from before this round. Both test-added rows
    were reverted from `data/trip_log.csv` afterward.

43. **Imported new tackle from Cabela's into `data/lure_inventory.csv`** (data-only
    change, no code touched) - the angler pointed me at their Cabela's cart plus two
    order-history pages and asked me to add anything new to their inventory, bumping
    quantity instead of creating a duplicate row for anything already in there. Signed
    into Cabela's myself was out of the question (entering credentials/passwords is a
    standing prohibition), so I asked the angler to sign in first, then read each page
    with Claude in Chrome once they confirmed. Findings: the cart had 6 line items
    (all qty 1); order `#W284504313` (shipped) had 6 line items (all qty 1); order
    `#W284273868` turned out to be a **canceled duplicate of the same order** - every
    line showed qty 0 and the order total was $0.00, so nothing was imported from it.
    Cross-referencing all 12 real line items against the existing 40-row inventory by
    SKU found two exact matches - SKU `2585737` (Thunder Cricket Swimjig -
    Chartreuse/White, already `item_id de225ccd`) and SKU `3227747` (Rapala DT
    Dives-To Crankbait - Bluegill, already `item_id 027a6e35`) - both bumped from
    quantity 1 to 2 via `core.lure_inventory.update_item()` rather than appended as
    new rows. The other 10 items were genuinely new and appended via
    `core.lure_inventory.append_item()`, each given a `category` matching the closest
    existing `core.lures.LURE_PROFILES` key by product type (e.g. the two more Thunder
    Cricket/Rattling Thunder Cricket baits as `chatterbait`, the two more KVD Perfect
    Plastics Blade Minnow colors as `weightless_soft_plastic`, the two more 3XD Series
    crankbait colors as `medium_diving_crankbait`, plus one `deep_diving_crankbait`,
    one `squarebill_crankbait`, one `spinnerbait`, one `football_jig`, one
    `lipless_crankbait`). Product photo URLs were built the same way entry-under
    existing rows already do - `https://assets.basspro.com/image/list/...{sku}.json?
    $BPSSite_orderhistory$` for the order-sourced items and the `$BPSSite_CartTN$`
    variant for the cart-sourced items - reverse-engineered from the existing CSV
    rather than scraped from the page DOM, since Chrome's accessibility-tree reader
    exposes image alt text but not `src` URLs. Verified with the full test suite
    (unchanged, still 161 passing), a scratch check confirming the inventory read back
    at 50 rows with no unintended duplicate SKUs among the 12 new/bumped items, and an
    `AppTest` smoke run of `pages/5_Lure_Inventory.py` confirming it still renders
    with no exception.

44. **"Scan a lure" - photo -> Claude vision -> Cabela's product lookup -> confirm ->
    inventory** - the angler asked whether they could take a picture of a lure in its
    package and have the app find its real details on Cabela's automatically. Two new
    core modules plus a new section at the top of `pages/5_Lure_Inventory.py`:
    - `core/lure_vision.py` (`identify_lure_photo()`) sends the photo to Claude's
      vision API (Anthropic SDK, tool-use forced to a structured `identify_lure` tool
      call) and reads back `visible`/`brand`/`product_name`/`search_query`/`notes`.
      Deliberately scoped to *just* reading the label well enough to build a search
      query, not to be the source of truth for price/SKU - see the "How the Cabela's
      lookup works" README section for why. Needs `ANTHROPIC_API_KEY` in secrets;
      without it the whole "Scan a lure" section shows a setup note and stays out of
      the way, same graceful-degradation pattern as `GITHUB_TOKEN` elsewhere.
    - `core/cabelas_lookup.py` (`search_lures()`) turns that query into real Cabela's
      product data. Cabela's search results are rendered client-side, so there's no
      HTML to scrape; instead this replicates the exact two JSON calls Cabela's own
      search box makes (confirmed by reading the site's own network traffic with
      Claude in Chrome while testing a search there): fetch a short-lived anonymous
      token from a first-party Cabela's endpoint, then POST it to Coveo's public
      search REST API (the third-party search platform their site runs on) for a
      plain-text query. Response `raw` fields (`sku`, `ec_brand`, `ec_name`,
      `ec_price`/`offerprice`, `fullimage`/`thumbnail`, `ec_category`) map cleanly to
      what the inventory needs - confirmed against a real query ("strike king thunder
      cricket swim jig white") that it returns the *exact* SKU (4500087) already
      imported by hand in entry 43. This is unofficial/reverse-engineered, not a
      documented API, so `search_lures()`/`_get_token()` fail soft (return `[]`/`None`)
      on any error rather than raising - a lookup failure just reads as "no matches",
      falling back to the existing manual "Add a lure" form.
    - `core/lures.py` gained `guess_category_from_text()` - an ordered keyword-rule
      heuristic (most-specific phrases checked first, e.g. "square bill" before the
      generic "crankbait" fallback) that formalizes the same by-hand categorization
      done in entry 43's Cabela's import, so both that import workflow and this scan
      feature can reuse one tested function instead of two copies of the same
      judgment calls. A new test asserts every key it can return is a real
      `LURE_PROFILES` key, so a typo here can't silently produce an uncategorizable
      tag.
    - UI flow: take/upload a photo -> "Identify this lure" -> Claude's read is shown
      -> Cabela's candidates render as an image-card grid (reusing
      `core.ui.render_square_thumbnail` directly on the search-result dicts, since
      they already carry an `image_url` key in the shape that function expects) ->
      picking one shows an editable confirm form (brand/description/price/quantity/
      category, category pre-filled from `guess_category_from_text()`) -> "Add to
      inventory" is the only thing that actually saves anything. If the matched SKU
      is already in inventory, confirming bumps that row's quantity via
      `update_item()` instead of creating a duplicate row - the same rule the angler
      asked for explicitly during entry 43's Cabela's import, now built into the UI
      instead of being something only I enforce by hand when running an import
      script.
    - Added `anthropic_api_key()`/`anthropic_model()` to `core/appstate.py` (same
      try/except-around-`st.secrets` pattern as `github_token()`), `anthropic>=0.40`
      to `requirements.txt` (only actually imported inside a try/except in
      `lure_vision.py`, so a stale/missing version there disables just this one
      feature, not the app), and documented `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` in
      `secrets.toml.example`.
    - Verified with new unit tests (`tests/test_cabelas_lookup.py`,
      `tests/test_lure_vision.py`, plus three new cases in `tests/test_lures.py` for
      `guess_category_from_text()`) that mock `requests`/a fake `anthropic` module
      rather than hitting the real network - 177 tests passing total, up from 161.
      Also confirmed via a real (interactive, not committed) Coveo query while
      building this that the token/search endpoints work and return the field names
      this code expects. **Caveat carried forward into the README**: this hasn't been
      exercised from a genuine non-browser HTTP client end-to-end (this sandbox's own
      network egress is allowlisted and blocks cabelas.com directly, so that
      verification could only be done through the browser) - if Cabela's bot
      mitigation ends up blocking the deployed app's server-side requests
      differently than a real browser's, the lookup step could fail even though the
      token/search endpoints and field mapping are confirmed correct. It fails soft
      either way, so the angler should just get "no matches found" rather than a
      broken page if that turns out to be the case - worth confirming with a live
      scan once this is deployed.

45. **Fix: "Scan a lure" was turning the camera on just from opening the Lure
    Inventory page** - reported immediately after the angler configured
    `ANTHROPIC_API_KEY` and tried the feature from entry 44. Root cause: Streamlit
    still runs a collapsed `st.expander`'s `with` block's Python on every rerun (it
    only hides the rendered result with CSS) - so `st.camera_input(...)`, which
    requests the webcam the moment its component mounts regardless of visibility,
    was being created on every page load even though the section looked closed. The
    old code made this worse by defaulting the "Photo" radio to "Take a photo", so
    even an *expanded* section would auto-mount the camera without the angler
    choosing to.
    - `st.expander("Scan a lure", ..., key="scan_expander")` now carries a `key`
      (supported since this app's pinned Streamlit >=1.36; confirmed present in the
      installed 1.61) so its collapsed/expanded boolean is readable from
      `st.session_state["scan_expander"]`. When it reads `False`, the whole rest of
      the section - in particular anything that could create `camera_input` - is
      skipped outright instead of just being visually hidden.
    - Within the expanded section, the camera is further gated behind an explicit
      **"📷 Turn on camera"** button (new `scan_camera_active` session-state flag) -
      switching the "Photo" radio to "Take a photo" alone no longer mounts
      `camera_input`; only that button click does. The radio's default was also
      swapped to "Upload a photo" first.
    - The camera turns itself back off (flag reset, widget stops being created next
      rerun, browser releases the device) the instant a photo is captured, on an
      explicit "Turn off camera" click, or whenever the section is collapsed again -
      re-expanding always starts from "camera off," never resuming a still-live feed.
    - Since the camera widget can now disappear at any moment, the captured photo's
      bytes/extension are copied into `st.session_state["scan_photo_bytes"/"scan_photo_ext"]`
      as soon as they're available (from either the camera or the uploader), and
      everything downstream (the "Identify this lure" button, the confirm form) reads
      from there instead of the widget's live return value - the widget disappearing
      no longer loses the photo. A "Remove photo" button clears it explicitly, and
      it's included in the same reset lists as `scan_result`/`scan_candidates`/
      `scan_selected` on both successful save and "Start over."
    - Verified with a scratch `AppTest` script (not committed) that walks the
      rendered element tree for anything camera-related in three states: section
      collapsed (zero camera elements, confirming the original bug is fixed);
      section expanded with "Take a photo" selected but before clicking "Turn on
      camera" (still zero); and after clicking it (exactly one `camera_input`
      appears). Full test suite unaffected (177 passing, no new cases needed since
      this is UI wiring/state-machine behavior AppTest already exercised directly).
      The pre-existing "Add a lure" form's own separate camera_input wasn't touched -
      its radio already defaults to "Upload a photo" first, so it doesn't reproduce
      this bug, and it's nested inside `st.form(...)` where widget changes don't
      trigger a rerun until submit anyway, which is a different (already documented)
      limitation, not this one.

46. **Fix (correction to entry 45): expanding "Scan a lure" showed nothing at all** -
    reported immediately after entry 45 shipped: the section would visually expand
    (chevron flips) but render an empty box, not even the "Photo scanning isn't set
    up yet" message when the key was missing - meaning the code was never reaching
    *any* branch that produces output. Root cause: giving `st.expander` a `key`
    alone does **not** make it report its expanded/collapsed state back to Python -
    per Streamlit's own docs, that also requires `on_change="rerun"` explicitly.
    Without it, clicking the expander is purely a client-side visual toggle that
    never triggers a script rerun, so `st.session_state["scan_expander"]` stayed at
    its initial default (`False`) forever - the code from entry 45 was unconditionally
    treating the section as collapsed and skipping all output, regardless of what the
    UI showed. One-line fix: `st.expander("Scan a lure", ..., key="scan_expander",
    on_change="rerun")`. Verified via `AppTest` that manually driving
    `st.session_state["scan_expander"]` between `True`/`False` (simulating what a
    real click + `on_change="rerun"` now produces server-side) correctly toggles
    between the full "Scan a lure" UI and rendering nothing, with no exception in
    either state or with/without `ANTHROPIC_API_KEY` configured - full click-and-
    persist behavior itself isn't independently exercisable through AppTest for this
    widget type, so the actual browser click path is worth a quick live check once
    deployed. Full test suite unaffected (177 passing).

47. **Spot Session "Add results": auto-save-and-reload, log multiple lures per visit,
    and a real fix for a mid-script `st.rerun()` state-loss bug.** The angler asked for
    two things: (1) saving a result should immediately reset the form and reload, ready
    to log another entry, without a manual page refresh; (2) a way to log more than one
    lure during the same time-at-the-spot, since previously each visit only supported
    one "Add results" submission before you had to leave the page. Asked to clarify
    what "same session" should mean (one combined multi-lure entry vs. several entries
    sharing conditions), the answer was explicit: **separate entry per lure** (no
    `TripEntry`/CSV schema change), **holding the same conditions** - i.e. wind/fish
    activity/forage activity/forage seen describe the whole time at the spot, not one
    lure, so they should carry forward to the next lure logged in the same visit rather
    than resetting.
    - Implementation: a per-spot `lure_entry_seq_{spot_id}` counter, bumped on every
      successful save, is folded into the keys of everything that's genuinely
      lure-specific (lure/trailer picker selections, lure start/end time, notes, the
      fish-caught list) so each save gives them fresh blank widget identities next
      render - a full reset. Wind speed/direction, fish activity, forage activity, and
      forage type seen keep **stable** keys (no seq folded in) so Streamlit's normal
      "existing session_state wins over a widget's coded default" behavior carries
      their values forward untouched. `st.rerun()` after a successful save makes the
      reset/carry-over visible immediately - `st.toast()` is used for the save
      confirmation instead of `st.success()`/`st.info()` specifically because those
      would get wiped out by that rerun before being seen. A live "📋 Already logged
      for this spot today: ..." caption (built fresh from `read_all_trips()` each
      render, filtered to this spot+date) makes each additional lure read as one
      cohesive visit even though it's still one row per lure under the hood.
    - **A real, non-obvious bug found and fixed along the way**, not just an AppTest
      artifact: the "carry over conditions" behavior worked in isolated testing but
      silently failed on the actual page - fish/forage activity (and, it turned out,
      *every* stable-keyed field including wind speed) snapped back to their coded
      defaults the instant a lure was picked, before "Log this session" was even
      clicked. Root cause: the lure/trailer picker's "Select" buttons call
      `st.session_state[...] = ...; st.rerun()` **mid-script**, the moment they're
      clicked - and Streamlit only preserves a widget's session_state across a rerun
      if that widget's key was already (re-)declared in the script run that triggers
      the rerun; a widget whose declaration line hasn't been reached yet when
      `st.rerun()` fires gets its state dropped, then reappears with its coded default
      on the next full run. The original layout declared "Conditions during this lure
      use" (wind/activity/forage-seen) *after* the "Lure used" picker section, so
      every lure pick wiped them. Fix: reordered the "Add results" section so
      "Conditions during this lure use" renders **first**, before the lure/trailer
      pickers - by the time a picker's "Select" click triggers its internal rerun,
      the condition widgets have already been declared/registered in that same run
      and survive it. Confirmed with a minimal isolated repro (a button that sets
      state + `st.rerun()`, placed before vs. after a `number_input`/`select_slider`
      pair with stable keys) that reproduces the loss when the rerun-triggering
      widget comes first and confirms the fix when the persisted widgets come first -
      this is real Streamlit widget-state-GC behavior, not an AppTest-only quirk, so
      it would have hit the deployed app too. The "Fish caught" sub-flow's own
      rerun-triggering buttons (Add fish/Remove/Save fish/Cancel) were already
      positioned after the conditions block, so they were never affected.
    - Verified via scratch `AppTest` scripts (not committed): conditions
      (wind/fish activity/forage activity) survive picking a lure and survive a full
      "Log this session" save+rerun; lure-specific fields (picker selection, notes)
      correctly reset to blank on the next entry; two lures logged back-to-back in one
      visit produce two separate `trip_log.csv` rows, each carrying the same
      wind/fish-activity/forage-activity values that were set once and never
      re-entered; the "Already logged for this spot today" caption appears and lists
      both entries. Full test suite unaffected (177 passing via `python3 -m pytest`;
      `pytest` alone in this environment resolves to a different interpreter missing
      `requests` - use `python3 -m pytest` here, not bare `pytest`).
    - Not done this round: an "edit a saved session" capability from the Trip History
      grid - asked for in the same round but explicitly a separate follow-up, since it
      needs its own `core.storage` update path (currently only `append_trip()` exists,
      no `update_trip()`) and UI design in `pages/4_Trip_History.py`.

48. **Fix (correction to entry 47): "Add results" collapsed shut after every save,
    reading as "nothing happened."** Reported immediately after entry 47 shipped -
    live-browser testing (via `claude-in-chrome`, since the reported symptom couldn't
    be reasoned out from code alone) confirmed the save itself, the lure-specific
    reset, and the condition carry-over from entry 47 all worked correctly on the
    deployed app; the actual problem was that `results_expander =
    st.expander("Log a lure/time-window result...", expanded=False)` had no `key`.
    Per the same rule documented in entry 46, an unkeyed expander's `expanded=`
    argument is only its *initial* default - on the `st.rerun()` that follows a save,
    it unconditionally re-collapses. Losing that much vertical content (the whole
    lure picker, conditions, fish list) shrinks the page by hundreds of pixels, and
    since the browser clamps scroll position to the new (shorter) page height, it
    *looks* exactly like the page jumped back to the top and the save did nothing -
    even though "Already logged for this spot today" had, in fact, updated just above
    the now-collapsed section.
    - Fix: gave it `key=f"results_expander_{spot_id}"` and `on_change="rerun"` (same
      pattern as `scan_expander`), and had the submit handler explicitly request it
      stay open across the save. That second part needed its own workaround:
      Streamlit forbids writing `st.session_state[key]` for a keyed widget *after*
      that widget has already been instantiated earlier in the same script run - and
      the submit button lives inside `with results_expander:`, i.e. structurally
      after the expander itself. Caught immediately by the `AppTest` verification
      script (a `StreamlitAPIException` on the direct-write attempt), not by manual
      testing - a good reminder to keep writing these scripts even for small fixes.
      Worked around with a deferred "pending reopen" flag: the submit handler sets a
      separate plain (non-widget) `results_expander_reopen_key`, and it's consumed
      right before the expander widget is created on the *next* run
      (`if st.session_state.pop(reopen_key, False): st.session_state[expander_key] =
      True`), which respects the "must set before instantiation" rule since that
      check now runs earliest in the fresh run.
    - This round is also the first time in this project that a reported bug was
      actually reproduced live (in the deployed Streamlit Community Cloud app via
      browser automation) rather than diagnosed purely by re-reading the code or
      through `AppTest`. That mattered here specifically because the underlying save
      logic was already correct - nothing in the Python state machine was wrong, so
      no amount of rereading the diff would have surfaced "the page height changes
      enough that the scroll position reads as snapping to the top." Worth resorting
      to for any future report where the code looks right but the described symptom
      doesn't obviously follow from it.
    - Verified via an extended `AppTest` script (not committed): the expander's
      tracked `session_state` value is `True` immediately after a save+rerun (was
      `False`/reset before this fix); condition carry-over and lure-specific reset
      from entry 47 still hold; two lures logged back-to-back both land in
      `trip_log.csv` with the same carried-over wind/fish-activity/forage-activity
      values. Also manually driven end-to-end in the actual deployed app (not just
      `AppTest`) - opened the section, set distinct condition values, picked a lure,
      saved, confirmed the section stayed open with the same conditions still shown
      and the lure picker reset to no selection, then repeated for a second lure in
      the same visit. Full test suite unaffected (177 passing via `python3 -m
      pytest`).

49. **Spot Session "Add results": split the single submit button into "Log this
    lure" and "Log this session."** After using entries 47/48's single-button flow,
    the angler asked for a clearer split matching how a real trip actually goes:
    several lure changes within one time at a spot, each of which should just log
    that lure and let you keep going, versus an explicit "I'm done here" action that
    also resets things for a genuinely new session later. The single "Log this
    session" button conflated both - clicking it always carried conditions forward,
    with no way to say "actually, close this one out."
    - **"Log this lure"** (the primary-styled button, left column) is exactly the
      old single-button behavior, renamed: saves the current lure/fish/notes as its
      own `trip_log.csv` row, resets the lure-specific fields (picker, trailer,
      timing, notes, fish list) via the existing `lure_entry_seq_key` bump, and
      keeps the "Conditions during this lure use" group (wind/fish activity/forage
      activity/forage seen) exactly as last entered - unchanged from entries 47/48.
    - **"Log this session"** (right column) is new. If a lure is currently picked,
      or a fish was logged, or notes were typed - i.e. there's real unsaved data -
      it saves that as its own row first (reusing the exact same save logic, now
      factored into a shared `_save_current_lure_entry()` closure so there's only
      one place that assembles a `TripEntry`), so clicking straight to "Log this
      session" after your last lure never silently drops it. If nothing's actually
      filled in, it skips the save entirely (a plain toast instead) rather than
      writing a blank/junk row - guarded by `has_pending_lure_data = selected_lure_
      item is not None or bool(fish_records) or bool(log_notes.strip())`. Either
      way, it then clears the conditions group back to its own coded defaults (0 mph
      wind, "Variable" direction, "Moderate"/"Moderate" activity, no forage seen)
      and leaves the section open and blank, ready for a genuinely new session -
      the whole point being that today's leftover wind reading shouldn't silently
      carry into a session you fish three hours later.
    - The conditions-reset hit the *exact* same Streamlit restriction entries 47/48
      already worked around for the expander's open state: you cannot write (or, it
      turns out, delete) `st.session_state[key]` for a keyed widget after that
      widget's already been instantiated earlier in the same script run, and the
      "Log this session" button lives well after the condition widgets are declared.
      Same fix shape: a `session_reset_pending_key` flag, set in the button handler,
      consumed (and only then are the five condition keys popped from
      `session_state`) right before those widgets are created on the *next* run -
      not by the handler that clicked the button.
    - Verified via `AppTest`: "Log this lure" still carries conditions forward
      across a save (wind 9.0/"Active" survived); "Log this session" with a lure
      picked but not yet individually saved correctly appends that lure's row
      *with the pre-reset conditions still attached to it* (both saved rows show
      wind 9.0, not the post-reset 0.0 - the reset only affects what the *next*
      entry starts from, not what was just written), then resets wind/fish activity
      back to their coded defaults for the next widget render; a second "Log this
      session" click with nothing pending appended zero new rows (`trip_log.csv`
      row count unchanged) instead of writing an empty entry. Full test suite
      unaffected (177 passing via `python3 -m pytest`).

50. **Spot Session: a persistent "📍 Location" picker at the top of the page.**
    Previously the only way to see/change which spot you were logging against was
    the one-time "Start a session at" dropdown shown *only* when no spot was
    selected yet - once a spot loaded (via the Lake Map's "🎯 Fish this spot now"
    button, or a `?spot_id=` link), the only way to switch spots was clicking
    "← Back to Lake Map" and starting over from there. The angler asked for a
    saved-spot picker that's always visible at the top, and for it to already show
    the right spot selected when arriving via the map click - no extra step.
    - The old "no spot yet" dropdown and the new "spot already loaded" dropdown are
      now the same `st.selectbox("📍 Location", ...)` element, just with slightly
      different option lists: the no-spot-yet branch keeps its `"— choose a saved
      spot —"` placeholder at index 0 (unchanged from before), while the
      already-loaded branch drops the placeholder entirely and its `index=` is
      computed to match whatever spot is actually current - so it always opens
      already pointed at the right one, never needing to be touched.
    - Getting "always pre-selected correctly regardless of how you got here" right
      needed the same pattern already used for `lure_entry_seq_key`-folded widget
      keys elsewhere on this page: the picker's `key` is
      `f"spot_picker_{spot['spot_id']}"` - i.e. it changes every time the loaded
      spot changes, for ANY reason (map click, a shared link, or picking a
      different spot from this same dropdown a moment ago). A fresh key means
      Streamlit treats it as a brand-new widget and applies the `index=` default
      fresh; a single fixed key would have kept whatever the angler last picked
      from the dropdown itself, ignoring a spot that arrived some other way (e.g.
      clicking a different pin's "Fish this spot now" button after already having
      one spot open) - Streamlit doesn't re-apply `index=` for an already-seen key
      no matter what code passes it on a later run.
    - When the dropdown's own selection differs from the spot actually loaded (the
      angler picked something new), it writes to `spot_session_target_id`/
      `?spot_id=` and calls `st.rerun()` - the exact same session_state-primary/
      query_params-fallback handoff the Lake Map's own button already used, so
      there's still only one navigation mechanism for "how do I load a different
      spot session" no matter which UI element triggers it.
    - Verified via `AppTest`: picking a spot from the placeholder dropdown
      navigates to the right spot (confirmed via the resulting `st.subheader`
      text, not just session_state, so the actual render is checked, not just the
      routing variable); that spot's own picker instance is then correctly
      pre-selected to itself (no placeholder, no extra click); landing directly
      with `spot_session_target_id` pre-set (simulating the Lake Map's button)
      shows the right spot's name in both the header and the picker with zero
      interaction needed; switching to a second spot via the dropdown while one is
      already loaded correctly navigates and re-renders around the new spot, with
      the new spot's own `spot_picker_<id>` key present in session_state afterward.
      Full test suite unaffected (177 passing via `python3 -m pytest`).

51. **Trip History: field mapping/filters caught up with Spot Session's newer
    fields, plus per-trip Edit and Delete.** Entries 31-50 added several fields to
    what Spot Session's "Add results" section logs (wind speed/direction, fish/
    forage activity, trailer details) and dropped one (`technique_used`, now
    always blank) - Trip History's grid/filters/detail view hadn't been updated to
    match. The angler also asked for a way to fix or remove a previously-logged
    trip without having to edit `trip_log.csv` by hand.
    - **Field mapping**: the grid's `display_cols` dropped the now-always-empty
      `technique_used` column and added `fish_activity`/`forage_activity` in its
      place (derived the same way `_lure_type`/`_location` already were - a flat
      column added to every row up front, since these live inside the
      `conditions_json` dict, not as their own `trip_log.csv` columns).
      `FIELD_SPECS` (the per-trip detail expander's field table) gained
      `trailer_category`, the one field from the trailer feature (entry 31) that
      hadn't made it into that list.
    - **New filters**: Fish activity, Forage activity, and Wind direction
      multiselects, plus an "Only trips using a trailer" checkbox - all derived
      via the same flat-column-then-`.isin()`/boolean-mask pattern the existing
      filters already used.
    - **Edit**: a real `st.button("✏️ Edit this trip")` per trip, but it lives
      inside the "Trip details" expander loop rather than as a grid cell - the
      pinned Streamlit version's `st.dataframe` doesn't support real per-row
      interactive buttons (only `st.column_config.LinkColumn`, which can only
      produce a clickable URL, not run navigation logic), while the detail
      expander loop already renders one real Streamlit container per trip. Only
      offered when `conditions["source"] == "spot_session"` and the trip's
      `spot_id` still resolves to a currently-saved spot - legacy "Log a Trip"
      rows and rows whose spot was since deleted have nowhere in Spot Session to
      edit them back into. Clicking it sets `spot_session_target_id`/
      `spot_session_edit_trip_id` (session_state) and `?spot_id=`/`?edit_trip=`
      (query params, same primary/fallback handoff pattern used everywhere else
      on this page) and calls `st.switch_page("pages/6_Spot_Session.py")`.
    - **Delete**: a two-step confirm (a plain button flips a `delete_confirm_<id>`
      session_state flag, which swaps in a "Yes, delete it"/"Cancel" pair) rather
      than deleting on the first click, since `core.storage.delete_trip()` is a
      real, permanent, un-undoable removal from `trip_log.csv`. Confirming pushes
      to GitHub the same way every other trip-log write does (via
      `commit_and_push`), so a delete on the deployed app persists past a
      restart same as a save does.
    - **`core/storage.py` gained two new functions**: `update_trip(entry)`
      (replaces the row whose `trip_id` matches `entry.trip_id`, rewriting the
      whole CSV - the file is small enough that a full rewrite per edit is not a
      real cost) and `delete_trip(trip_id)` (removes that row entirely, same
      rewrite approach). Both return `False` as a no-op if the `trip_id` isn't
      found (e.g. a stale link, or something else already removed it) rather than
      raising, matching `commit_and_push`'s "never raises, tell the caller so it
      can show a friendly message" convention.
    - **Spot Session edit mode** (`pages/6_Spot_Session.py`): landing with
      `spot_session_edit_trip_id` set switches the page into editing one specific
      already-logged trip instead of starting a new session.
      - A one-time prefill block (guarded by an `edit_prefill_done_key` flag, so
        it only runs once per edit visit and doesn't stomp on further edits the
        angler makes to the form) seeds every widget-backed `session_state` key
        the "Conditions right now" form and "Add results" section read - session
        date, wind speed/direction, fish/forage activity, forage type seen, the
        lure/trailer pickers (best-effort matched back to an inventory item by
        display label, since `conditions_json` only ever stored the resolved
        label/category, not the item's `item_id` itself - a renamed or
        since-deleted item just falls back to unselected), start/end time, notes,
        and the per-fish catch list. It bumps `lure_entry_seq_key` first so the
        lure/trailer/time/notes keys it seeds (which fold that sequence number
        into their key) are guaranteed unused, even if the same spot already had
        some unsaved lure entry in progress earlier in the same browser session.
        Same "must happen before that key's widget is instantiated in this run"
        rule as every other deferred-flag pattern already on this page.
      - "Conditions right now"'s own (unkeyed) widgets get their `value=`/
        `index=` defaults computed from the trip's stored condition snapshot too,
        so re-submitting that form (optional - conditions have always been
        optional here) reproduces close to the original score/suggestions rather
        than the normal blank-form defaults.
      - The "Log this lure"/"Log this session" pair is replaced by a single
        "💾 Save changes"/"Cancel edit" pair while editing - there's no "next lure
        in this session" concept when correcting one specific already-saved row.
        "Save changes" calls the same shared `_save_current_lure_entry()` helper
        as the normal flow, but branches to `update_trip()` (same `trip_id`,
        original `logged_at` preserved) instead of `append_trip()`.
      - **Caught during verification, not from the original design**: a plain
        "just fix the notes" edit - where the angler doesn't re-submit
        "Conditions right now" - was silently blanking `predicted_score` back to
        `None`, resetting `segment` to a guess based on the *current* wall-clock
        hour (not whenever the original session happened), and resetting
        `water_clarity` to `"Unknown"`, because all three are normally derived
        fresh from `cond`, which stays `None` unless that form is resubmitted.
        Fixed by falling back to the original trip's stored value for each of
        the three whenever `cond` is empty and a trip is being edited - a save
        should only ever change what was actually touched. Confirmed with a
        dedicated `AppTest` regression case using a synthetic row with
        distinctive non-default `segment`/`water_clarity`/`predicted_score`
        values (none of the angler's real logged trips have used "Conditions
        right now" yet, so this exact bug wouldn't have shown up against real
        data).
      - Minor, accepted cosmetic gap: seeding a keyed widget's `session_state`
        entry *and* passing that widget a separate hardcoded `value=`/`index=`
        default (as several of the prefilled widgets above still do) trips a
        one-time, backend-log-only Streamlit warning ("widget was created with a
        default value but also had its value set via the Session State API") -
        harmless (session_state always wins; nothing user-facing changes) and,
        because Streamlit only logs this once per process no matter how many
        widgets trigger it, fixing every remaining instance for a single log
        line wasn't judged worth the extra surface area. `session_date` was
        fixed properly (reads its own current `session_state` value back as its
        `value=` instead of a separate hardcoded default) since it was trivial.
    - **Test data cleanup**: `data/trip_log.csv` had carried 7 synthetic rows
      since entry "Add temporary sample trips to preview the new Trip History
      page" (commit `619c5c4`, before this session's numbered entries began),
      each tagged `conditions["_test_data"] = true` and a `[TEST DATA]`-prefixed
      note - identified via `git show` on that commit and removed by filtering on
      that tag, leaving all of the angler's real logged trips (`96c5a3d1`,
      `f964519c`, `bba469f1`, `bf8b6926`, `35d0e656`, `a838b1d5`) untouched.
    - Verified via `AppTest`: Trip History's new filters/columns/buttons all
      render without error and match expected values; clicking Edit sets the
      right `session_state`/query params before `switch_page` (which AppTest
      itself can't follow cross-page, since it runs each page file in
      isolation - a harness limitation, not an app bug); the delete confirm/
      cancel flow leaves the row alone on Cancel and removes exactly the target
      row (and no others) on confirm; Spot Session's edit mode pre-fills every
      field checked (conditions, lure/trailer selection matched by label, times,
      notes, fish list) and "Save changes" updates the same row in place (row
      count unchanged) rather than appending a duplicate; the
      segment/water_clarity/predicted_score preservation fix confirmed via the
      synthetic-row regression case described above. Full test suite unaffected
      (177 passing via `python3 -m pytest`).

52. **Trip History: a real 🔍 button on the grid, left of each row, jumping
    straight to that trip's detail.** Entry 51 put Edit/Delete inside the
    per-trip "Trip details" expander loop further down the page, since
    `st.dataframe` can't host real per-row buttons - but the angler wanted the
    button on the grid itself, not buried in a list they'd have to scroll to
    and find the right expander in.
    - `st.dataframe` was replaced with a genuine per-row grid built from
      `st.columns` (same technique the "Trip details" loop already used) -
      the only way to get a real, clickable `st.button` on each row in this
      pinned Streamlit version. Trimmed to six columns (🔍, Date, Location,
      Lure, Fish caught, Score) rather than all fourteen the old
      `st.dataframe` grid showed - `st.columns` doesn't get native
      sort/resize the way `st.dataframe` did, and fourteen manually-sized
      columns would be unreadably narrow. Every dropped field is still one
      click away.
    - Clicking 🔍 sets `trip_history_selected_id` and reruns; right below the
      grid (not gated on the current filters, and looked up against the
      *full* unfiltered trip list rather than the filtered one, so it keeps
      showing even if a filter change afterward would otherwise exclude that
      trip) a "📌 Selected trip" panel renders that trip's complete detail -
      literally "takes you to the record detail," with zero scrolling, since
      the panel appears immediately below the grid rather than requiring a
      scroll down to find the matching expander in the full list.
    - The full "Edit this trip"/"Delete this trip"/field-by-field/per-fish
      rendering logic (previously duplicated nowhere else, but about to be
      needed in two places - the new panel and the existing full list) was
      extracted into one shared `_render_trip_detail_body(row, key_prefix)`
      function. `key_prefix` exists because the SAME trip can now render
      twice on one script run (once in the "Selected trip" panel, once again
      in the full "Trip details" list below, since selecting a trip doesn't
      remove it from that list) - Streamlit raises on a duplicate widget key
      within one run, so the panel uses `key_prefix="selected"` and the list
      uses `key_prefix="list"`, giving every button (`Edit`, `Delete`, the
      delete confirm/cancel pair) a distinct key per call site. The one
      exception is deliberate: `delete_pending_key` is built from `trip_id`
      alone (no `key_prefix`), so starting a delete confirm from either
      rendering of the same trip shows the same pending "are you sure" state
      in both places, rather than two independent, easily-confusing ones.
    - Verified via `AppTest`: exactly one 🔍 button per real logged trip;
      clicking one sets `trip_history_selected_id` and renders the "📌 ..."
      panel with the right trip's date; both the panel's and the full list's
      Edit/Delete buttons for that same trip coexist on the same run without
      a duplicate-key crash (the concrete risk `key_prefix` exists to avoid);
      "✖ Close" clears the selection. Also caught a real formatting bug
      during this same verification pass: the new grid's fish-count column
      used an `:g` format spec on `biggest_fish_lb`, which crashes because
      that field comes straight off the CSV as a plain string (`read_all_trips`
      does no numeric coercion) - fixed by dropping the format spec, matching
      how the detail view already rendered this same field. Full test suite
      unaffected (177 passing via `python3 -m pytest`).

53. **Fixed: editing a trip's location mid-edit blanked out everything else.**
    Reported directly: "I edited the location from Stripe Point to Midnight
    Point and everything after that then changed as if it was a new record."
    Reproduced and root-caused via `AppTest` (not live browser this time -
    entry 51's edit-mode prefill logic was already proven correct in a live
    session for the *no-location-change* case, so the bug had to be
    specifically about changing spots mid-edit).
    - Root cause: `edit_prefill_done_key` (the one-time-seed guard from entry
      51) was keyed by `edit_trip_id` alone - `f"edit_prefill_done_{trip_id}"`.
      It gets set `True` the first time the prefill block runs, for whichever
      spot the angler landed on. But every widget that block seeds is itself
      keyed by spot_id (`f"log_wind_speed_{spot_id}"`,
      `f"log_notes_{spot_id}_{lure_seq}"`, etc. - see entry 51). Switching the
      "📍 Location" picker to a different spot while editing lands on a
      **different set of spot-scoped widget keys that have never been
      seeded** - but since `edit_prefill_done_key` was already `True` from
      the original spot, the prefill block's guard skipped re-running
      entirely, so those new-spot widgets just showed their normal blank
      defaults. Exactly the "changed as if it was a new record" symptom.
    - Fix: `edit_prefill_done_key` is now `f"edit_prefill_done_{trip_id}_{spot_id}"` -
      composite on both, so switching spots mid-edit is treated as "not yet
      prefilled for this (trip, spot) pair" and the seed block runs again,
      carrying the trip's lure/conditions/notes/fish data forward into the
      new spot's widget keys. `_exit_edit_mode()` now sweeps *every*
      `edit_prefill_done_<trip_id>_*` key (not just the current spot's) on
      Save/Cancel, so a stale `True` from a spot no longer being edited can't
      silently skip prefill if this same trip is ever edited again later in
      the same browser session.
    - This isn't just a prefill-cosmetics fix - `_save_current_lure_entry()`
      already built `spot_id`/`spot_name` from whichever spot is *currently*
      loaded (not the trip's original one), so "Save changes" after
      switching location now does exactly what was asked: moves the trip to
      the new spot (same `trip_id`, via `update_trip`) while keeping
      everything else that was filled in.
    - Verified via a dedicated `AppTest` regression case: edit a real trip at
      Stripe Island Point (confirming the original prefill first), switch
      the location picker to Midnight Point, confirm the edit banner is
      still showing and every previously-prefilled field (wind speed/
      direction, notes, lure selection, fish record) still shows the same
      values under the new spot's keys, then save and confirm the row
      updated in place (still 6 rows) with `spot_id`/`spot_name` now set to
      Midnight Point. A second check confirmed the ordinary no-location-
      change edit path (entry 51's original scenario) still works
      unchanged. Full test suite unaffected (177 passing via
      `python3 -m pytest`).

54. **Trip History grid: wide/scrollable again, plus inline editing that
    auto-saves.** Requested directly: "We used to be able to scroll over and
    see more fields. That would be ideal to have back. Also, it would be
    great if we can edit directly in the filter grid and have that update
    once edited." Entry 52's manual `st.columns`-per-row grid (built just to
    get a real 🔍 button on each row, since `st.dataframe`/`st.data_editor`
    can't host a real per-row button in this pinned Streamlit version - only
    `st.column_config.LinkColumn`, a clickable URL) had trimmed the grid down
    to 6 columns to make room for that button, losing the original 14-field
    `st.dataframe` view from before entry 52.
    - Replaced the manual grid with `st.data_editor` over the same 14 fields
      as the original pre-entry-52 `st.dataframe` (trip_date, segment,
      location, structure_type, water_clarity, lure type, lure_used,
      color_used, fish_activity, forage_activity, fish_caught,
      biggest_fish_lb, predicted_score, notes) - wide and scrollable again,
      `width="stretch"` plus the page's existing `layout="wide"`.
    - Only the columns that map onto a flat `trip_log.csv` field are
      editable: trip_date, segment, structure_type, water_clarity,
      lure_used, color_used, fish_caught, biggest_fish_lb, notes (via
      `st.column_config.DateColumn`/`SelectboxColumn`/`TextColumn`/
      `NumberColumn`). Location, lure type, fish/forage activity, and
      predicted score stay read-only (`disabled=[...]`) in the grid -
      location needs spot_id resolution and the other three live inside
      `conditions_json`, and both already have a correct, tested path
      through "✏️ Edit this trip" → Spot Session (entry 51/53) that a quick
      grid-cell edit would risk half-updating (e.g. changing `_lure_type`
      inline wouldn't touch the actual `lure_category` inside
      `conditions_json`, so the two would silently disagree).
    - Auto-save, no separate "Save" button: `st.data_editor` already commits
      an edit and reruns the script as soon as a cell is confirmed, so the
      page just diffs the freshly-edited DataFrame against the pre-edit one
      on every run (indexed by `trip_id`) and calls `update_trip()` for any
      row where a normalized value actually changed, then one
      `commit_and_push()` covering every changed trip in that run. The
      diff/normalize logic (`_grid_edit_diff`, `_normalize_grid_row`,
      `COLUMN_NORMALIZERS`) is deliberately pure pandas/stdlib with no
      Streamlit calls, specifically so it has real unit-test coverage -
      `st.data_editor` cells aren't reachable/editable through `AppTest` in
      this Streamlit/testing version (only read-only `st.dataframe` is), so
      this is the one part of the feature that *can* be exercised outside a
      live browser. Verified (scratch, not committed): unedited rows produce
      no diff even when `st.data_editor` hands back a different-but-equal
      representation (e.g. `datetime.date` vs the `pd.Timestamp` the grid was
      built with); two NaN `biggest_fish_lb` values on both sides don't
      false-positive as "changed" (`NaN != NaN` needs an explicit guard);
      clearing a numeric field normalizes to `None`/`0` correctly; a real
      edit is captured with the rest of that row's editable columns included
      alongside it (needed to rebuild a complete `TripEntry`, not just the
      touched cell).
    - Losing the per-row 🔍 button (no per-row buttons possible in
      `st.data_editor`, same constraint as `st.dataframe`) is offset with a
      "Jump to a trip's full detail" picker (a labeled `st.selectbox` +
      "🔍 View" button) right below the grid, which sets the same
      `trip_history_selected_id` session state the old button did and opens
      the same "📌 Selected trip" panel - so the wider Edit/Delete/per-fish
      detail flow is unchanged, just reached by picking from a dropdown
      instead of clicking a row.
    - Verified via `AppTest`: the page renders with no exceptions after the
      change; the jump picker lists exactly one option per real logged trip
      (5); selecting a trip and clicking "🔍 View" sets
      `trip_history_selected_id` and renders the matching "📌 ..." panel
      subheader, with `data/trip_log.csv` left byte-identical afterward
      (confirming the read-only AppTest pass makes no writes). Full test
      suite unaffected (177 passing via `python3 -m pytest`). The inline-edit
      auto-save path itself (the part `AppTest` can't reach) should get a
      live-browser check before calling this fully done.

55. **Spot Session: a live activity score now computes and saves automatically
    once "Conditions right now" is filled in - no button click needed.**
    Prompted by the user noticing `predicted_score` was blank on every real
    logged trip and asking whether it auto-calculates. Root cause: "Conditions
    right now" was an `st.form` gated behind a "Get lure suggestions" submit
    button - filling in the fields did nothing until that specific button was
    clicked, and since it read as being about *lure suggestions* (which an
    angler who already knows what they're throwing has no reason to care
    about), it was easy to skip straight to "Add results" and never trigger a
    score at all. Follow-up ask: "get a score once current conditions are
    filled in, even if I don't look at the lure suggestions."
    - Removed the `st.form`/`st.form_submit_button` around "Conditions right
      now" entirely - every field in that section (water temp, secchi/stain,
      wind, light, precipitation, session start time, time window, forage
      seen, fish depth) is now a bare widget outside any form, so each one
      reruns the script and updates `cond`/`score_result` live, the same way
      every other widget on this page already works.
    - Session start time is the only field with no default (deliberately
      blank - see its help text, "enter it yourself rather than relying on
      whatever time it happens to be"), so it's the natural gate: `cond` now
      gets built (and cleared, if start time is ever emptied back out) on
      every rerun based on whether start time has a value, instead of on
      whether a button was ever clicked. Every other field already had a
      sane default, so a score exists the moment a start time is entered,
      whether or not the "Suggestions for right now" expander (open by
      default, unchanged) is ever actually looked at - and `_save_current_
      lure_entry()` already read `cond`/`score_result` directly rather than
      caring how they got populated, so no changes were needed there or to
      any of its editing-mode fallback logic (still correctly keeps an
      already-scored trip's original score/segment/water_clarity when
      editing it without touching Conditions this visit - verified that
      specifically still holds).
    - Updated the stale "click Get lure suggestions" comments/captions
      throughout the file to match (the caption shown before a score exists,
      the header caption, and several inline comments describing the
      editing-mode fallback logic) - none of those were logic changes, just
      wording that referenced a button that no longer exists.
    - Verified via `AppTest` (with `data/trip_log.csv` backed up/restored
      around anything that wrote to it): no score metric renders and the
      "Enter a session start time..." caption shows before any time is
      entered; setting only the start time produces a score on that same
      rerun with no button anywhere in the flow (confirmed the old "Get lure
      suggestions" button no longer exists at all); changing another
      condition field (water temp) after that recomputes the score live too;
      a full "Log this lure" round-trip (start time filled in, Suggestions
      panel never touched) saved a row with a real numeric `predicted_score`;
      and editing one of the 5 real trips that was never live-scored (no
      `start_time` in its stored `conditions_json`) correctly shows no score
      and the "fill in a start time" prompt rather than conjuring one out of
      nowhere just because it's now in edit mode. Full test suite unaffected
      (177 passing via `python3 -m pytest`).

56. **7-Day Forecast: past time segments no longer keep changing score.**
    Reported directly: the angler noticed scores update live as the weather
    forecast/conditions change (intended, and liked) but wanted a segment
    whose window has already closed to stop moving - "the score should stay
    fixed as the last score recorded prior to that time range passing."
    Root cause: `pages/1_7_Day_Forecast.py` calls `core.scoring.score_week()`
    fresh on every page load, which recomputes every segment (including
    ones fully in the past) from whatever `get_weather_bundle()` currently
    holds - and that bundle refreshes hourly (`st.cache_data(ttl=3600)`), so
    a segment like this morning's Dawn window kept silently reflecting
    later weather refreshes/actuals hours after it closed.
    - Added `core/forecast_freeze.py`, a small new git-backed store
      (`data/segment_score_freeze.csv`, same commit-back pattern as
      `core/storage.py`/`core/lure_inventory.py`/`core/lake_spots.py` - a
      Streamlit Cloud sleep/wake restart would otherwise silently lose an
      in-memory-only freeze, which would defeat the whole point).
      `apply_freeze(day_forecast, now=..., path=...)` mutates a
      `DayForecast`'s segments in place: any segment whose `end <= now` gets
      either its already-frozen score/notes/solunar_overlap/breakdown
      reapplied (overriding whatever `score_day()` just recomputed), or - if
      this is the first time it's been observed as past - a new permanent
      row is written capturing its current score, which becomes that
      segment's value forever after. Segments still in progress or upcoming
      are left completely untouched, so the live-updating behavior for
      anything not yet past is unchanged. Wired into
      `pages/1_7_Day_Forecast.py` right after `score_week()`, called for
      every day in the week (a no-op for the 6 days that are always
      entirely future, since `score_week()` always starts at today - see
      that function) - only pushes to GitHub when something was actually
      newly frozen this run (the common case is nothing new).
    - Only today's date can ever have a mix of past/future segments, so the
      freeze file only ever needs to track one date at a time - rows for any
      other date are pruned automatically whenever a new segment gets
      frozen (not proactively on every load, to avoid a git commit on every
      single page view).
    - A day's `overall_score` (the plain average of its 6 segment scores,
      per `score_day()`) is recomputed from the corrected segment list
      whenever a frozen value overrides a freshly-computed one, so the
      day-level number a reader sees never disagrees with the segment cards
      underneath it - not just individual segment scores were flagged as an
      issue, so this was worth getting right even though it wasn't asked
      for explicitly.
    - `core/forecast_freeze.py`'s functions all take an optional `path`
      parameter defaulting to the real `FREEZE_PATH` constant (matching
      `core/lure_inventory.py`'s existing pattern) specifically so tests can
      inject a `tmp_path` instead of touching the real repo file - and
      `pages/1_7_Day_Forecast.py` passes `path=FREEZE_PATH` explicitly to
      `apply_freeze()` rather than relying on that default, since a Python
      default-argument value is bound once at function-definition time, not
      at call time - relying on it would have made the default silently
      immune to being swapped later (learned this the hard way debugging a
      scratch AppTest smoke test that kept writing to the real file no
      matter what it patched, before switching to passing `path=` explicitly).
    - Verified via a new `tests/test_forecast_freeze.py` (6 cases, using
      `tmp_path` and hand-built `SegmentForecast`/fake-day objects, no
      network needed): a still-in-progress segment is left untouched and
      nothing gets written; a segment observed past for the first time gets
      frozen but its OWN score isn't touched on that same call; a second
      call with a deliberately different fresh score for that same segment
      reapplies the original frozen value instead; `overall_score` is
      correctly recomputed only when a frozen override actually changes a
      segment's value; freezing a new date's segment prunes stale rows from
      a previous date; and notes/breakdown/solunar_overlap all round-trip
      correctly through the CSV's JSON-encoded columns. Also end-to-end
      smoke-tested the full page via `AppTest` with a fake weather bundle
      (this sandbox has no real network access to Open-Meteo) and a real
      `apply_freeze()` call: a mid-morning page load froze Dawn's score,
      and a second simulated page load - with a deliberately different fake
      weather bundle - confirmed Dawn's score held exactly steady instead of
      drifting to whatever the new data would have produced. Full test
      suite unaffected (183 passing via `python3 -m pytest`, 177 existing +
      6 new).

57. **Phone-friendliness pass: bigger sidebar toggle, reflowing multi-column
    rows, Trip History left as-is (light touch).** The angler wants to
    actually use this app standing at the lake on an iPhone. A prior session
    had already ruled out website-wrapper "conversion" tools (MobiLoud/
    Median/GoNative - they only add native packaging, they don't touch the
    underlying page layout) and identified three known problems: the
    collapsed sidebar's tiny toggle arrow, the 7-Day Forecast's wide
    multi-column rows squishing on a phone, and Trip History's `st.data_editor`
    grid (rebuilt in a prior session, entry 54) needing a fresh mobile check.
    Confirmed priorities with the angler before a big layout pass (per the
    session's own instructions): follow the suggested order (Spot Session/
    Today first in spirit, then sidebar toggle + 7-Day Forecast reflow, then
    Trip History), and for Trip History specifically, "light touch - keep the
    grid, improve scrolling" over a bigger stacked-card redesign.

    **Root-caused both known problems against the live deployed app**, not
    just by reasoning about Streamlit's CSS - `resize_window` (the Chrome
    tool) turned out not to actually shrink the rendered viewport in this
    sandbox (`window.innerWidth` stayed at desktop width - 1512px - no matter
    what size was requested; confirmed via `window.innerWidth`/`outerWidth`
    reads after resizing, not just assumed), so real mobile-viewport
    screenshots weren't obtainable here. Worked around it by discovering the
    real DOM testids (`stExpandSidebarButton`, `stHorizontalBlock`,
    `stColumn`, etc. - Streamlit Community Cloud actually serves the app
    inside an iframe under its own wrapper page, at `.../~/+/`, not at the
    top-level URL a user sees; had to navigate directly to that iframe URL to
    read testids at all, since the top-level document has none of the app's
    own content) and, since a `stHorizontalBlock`'s children lay out as
    percentages of *its own* width rather than the viewport, forcing that
    one element's width to 390px via injected inline styles - a valid way to
    simulate a phone-width container regardless of the surrounding window
    size, since flexbox wrapping is driven by the container's width, not
    `window.innerWidth` itself.
    - **Sidebar toggle**: confirmed live that `button[data-testid=
      "stExpandSidebarButton"]` (the "keyboard_double_arrow_right" icon
      button that appears once the sidebar is collapsed) is a 28x28px,
      low-contrast (rgba(38,39,48,0.6)) hit target - exactly the "small,
      easy-to-miss arrow" the angler described.
    - **Column squish**: confirmed live that `stHorizontalBlock` already has
      `flex-wrap: wrap` in this pinned Streamlit version - the actual root
      cause is that `st.metric`'s label/value elements have their own
      `white-space: nowrap` + ellipsis CSS, so a column's min-content width
      collapses to almost nothing and the row never needs to wrap; each
      column just truncates in place ("Thu ...", "6..."). Confirmed the fix
      (a real per-column `min-width`) by injecting it live and re-measuring:
      the 7-day score row went from one unreadable truncated row to a clean
      2-per-row grid at a simulated 390px width, and the 6-segment breakdown
      reflowed the same way.

    **Implementation** (`core/ui.py`'s new `inject_mobile_css()`, called once
    near the top of every page - home.py and all six `pages/*.py` files -
    right after each page's own `st.set_page_config()`, the same "first
    Streamlit call per page" pattern `st.navigation` already relies on):
    - The collapsed-sidebar button is enlarged (44x44px) and given a solid
      dark background + white icon, unconditionally (not gated to mobile
      only) - a clearer toggle helps on desktop too, and it only ever shows
      when the sidebar is already collapsed.
    - Below a 700px viewport-width media query, any `stHorizontalBlock` with
      3+ columns gets `flex-wrap: wrap` (redundant with Streamlit's own
      default, kept for clarity/robustness) and each of its columns gets a
      real `min-width`/`flex-basis` (120px) - **scoped via
      `:has(> [data-testid="stColumn"]:nth-child(3))`** so intentional
      2-column master/detail layouts (the Lake Map's map + detail panel, the
      7-Day Forecast's info + best-window pair, button pairs elsewhere) keep
      their original proportions instead of being forced to an even split.
      Modern `:has()` support (Safari 16.4+, 2023) was judged safe for an
      iPhone-focused fix in 2026. This one shared rule also reflows Trip
      History's three `st.columns(3)` filter rows and its 3-column summary
      metrics row, and Home's 4-column "Today at a glance" metrics, and
      Spot Session's various 3+/4-column groups - not just the two rows
      explicitly reported, since it's a single general-purpose fix rather
      than a per-page patch.
    - Trip History's own grid widget was deliberately left alone per the
      angler's "light touch" choice - only its caption above the grid was
      reworded to explicitly say "on a phone: swipe left within the grid
      itself, not the page" (the existing "Scroll right" wording read as a
      desktop mouse instruction). Verified the grid's own internal resize
      logic (glide-data-grid, a canvas-based widget) computes its pixel
      width via `ResizeObserver` at actual layout time, not from any CSS
      that could be overridden the same way the metric-column fix was - so
      unlike the two fixes above, its real touch/swipe behavior on a phone
      genuinely couldn't be verified from this sandbox (the same
      `resize_window` limitation that blocked true mobile screenshots), and
      is called out below as something to confirm live on a phone rather
      than something already checked.
    - **Investigated and deliberately did not implement** a custom
      `manifest.json`/`apple-touch-icon` for a polished Safari "Add to Home
      Screen" icon (the third, lower-priority step in the angler's suggested
      plan) - confirmed, by inspecting the live app's actual top-level
      document (not the iframe), that Streamlit Community Cloud's own
      wrapper page already ships its own `apple-touch-icon` and
      `manifest.json` (both pointing at generic `favicon_*.png`/Streamlit-
      branded assets under `.../-/build/`) - and that wrapper page, not
      anything in this repo, is what Safari actually reads when a user
      bookmarks the app, since the real app only ever renders inside an
      iframe. There's no hook in this repo's code that can override the
      *top-level* document's `<head>` on this hosting setup, so this item is
      not achievable here without a different hosting model - documented in
      the README rather than attempted.

    Verified with the full test suite (unchanged - `inject_mobile_css()` is
    pure CSS injection via `st.markdown(unsafe_allow_html=True)`, no logic
    touched; 183 passing) plus a scratch `AppTest` smoke script (not
    committed) confirming every page - home.py and all six `pages/*.py`,
    including 7-Day Forecast against a mocked weather bundle, same fixture
    shape as `tests/test_scoring.py`'s `_fake_bundle()` - still renders with
    no exception after adding the `inject_mobile_css()` call. Also verified
    via a fresh `git clone` into a new temp directory before pushing.

58. **Bug report: "Log this session" left the angler unsure whether it
    saved and the form didn't look like it reset.** Reported after a real
    on-the-water use: several lures logged fine with "Log this lure," but
    clicking "Log this session" afterward gave no clear signal anything
    happened. Investigated by reading the actual code path (entries 47-49)
    plus a scratch `AppTest` repro run against a copy of the real spot/lure
    data (`data/trip_log.csv` backed up and restored after, confirmed
    byte-identical before/after - no real data touched) - **found the
    underlying save/reset logic is correct, not broken**: with nothing new
    picked since the last "Log this lure" (the reported scenario), the row
    count correctly stayed unchanged (no duplicate/junk row - entry 49's
    `has_pending_lure_data` guard working as designed), and the "Conditions
    during this lure use" fields correctly reset to their coded defaults
    (confirmed by setting wind speed to a non-default 12.0 mph before the
    click and reading it back as 0.0 after). Also confirmed directly against
    the angler's own live app history: three separate `git log` commits
    ("Log trip ... from spot session") exist for the reported session, one
    per lure - all three really did save.

    So the data was never at risk - the actual gap is UX: the only
    confirmation was `st.toast()`, which is easy to miss on a phone, and if
    the "Conditions during this lure use" fields already happened to be
    sitting at their defaults for that whole visit (plausible - wind speed/
    fish activity aren't touched every time), there was **no visible change
    on screen at all** before vs. after clicking "Log this session," so it
    read as "nothing happened" even though everything worked. (Side note:
    confirmed via a minimal isolated repro that `AppTest`'s own `at.toast`
    collection doesn't capture a toast fired immediately before `st.rerun()`
    within the same script run - an `AppTest` harness limitation, not
    evidence the toast itself fails in the real deployed app; entries 47/48
    already established live in-browser that this same toast-before-rerun
    pattern does survive on the real Streamlit Cloud app.)

    Fix: a one-shot, non-toast confirmation banner. `log_session_submitted`'s
    handler now also sets `session_state[f"session_closed_banner_{spot_id}"]
    = True` alongside the existing `session_reset_pending_key`; a check at
    the top of "Add results" (`st.session_state.pop(...)`, so it renders
    exactly once and never lingers on a later, unrelated visit) shows
    `st.success("✅ Session closed - conditions cleared for a new session...")`
    - a persistent inline element rather than an ephemeral toast, so it's
    there to read regardless of whether anything else on the page visibly
    changed, and regardless of whether "Log this session" also had to save
    one last pending lure along the way (both branches set the flag).

    Verified via two scratch `AppTest` scenarios (not committed, same
    backed-up/restored `trip_log.csv` protocol): nothing pending (matches
    the report) - row count unchanged, banner renders, and is gone on a
    later unrelated rerun; something pending (a lure picked but never
    individually logged) - row count +1 *and* the banner renders in the same
    run. Full test suite unaffected (183 passing) plus the usual `AppTest`
    smoke test across every page.

59. **New Development page: an in-app punch list, replacing "just tell Claude at
    the start of a session."** The angler wanted a place to jot down app fixes/
    adjustments as they notice them, referenceable by a stable number across
    sessions ("let's do #7 next"), rather than re-describing an issue from memory
    or relying on SESSION_NOTES.md's "Known limitations" section (written by
    Claude, after the fact, not meant as an angler-facing intake list). Scoped to
    exactly what was asked: an auto-assigned item number, a description, and a
    "mainly associated with" page dropdown, checked off (not deleted) when done.

    New `core/dev_tasks.py` mirrors `core/lure_inventory.py`'s storage pattern
    (dataclass + `data/dev_tasks.csv` + git commit-back via
    `core.storage.commit_and_push`) with one deliberate difference: `task_no` is
    a small human-friendly int, not a uuid - the whole point is a number the
    angler can say out loud. `_next_task_no()` assigns existing-max + 1, and
    there's **no `delete_task`** - a "Done" item stays in the list (and keeps its
    number) rather than disappearing, so a past reference to "#12" still resolves
    to something even after it's finished; a "Show completed items" checkbox on
    the page hides them by default instead. New `pages/7_Development.py` (added
    last in `app.py`'s `st.navigation` list) has an "Add an item" form up top and
    an inline-editable `st.data_editor` grid below (Done checkbox, description,
    page - same auto-save-on-edit pattern as Trip History's grid, diffed
    directly against the pre-edit `DataFrame` each rerun rather than as an
    extracted pure function - Trip History's `_grid_edit_diff` precedent exists
    but its own diff logic still only ever got scratch, not committed, test
    coverage either, since real `st.data_editor` cell edits aren't reachable
    through `AppTest` regardless of how the diff code is structured).

    Verified with a new `tests/test_dev_tasks.py` (12 cases: empty-file read,
    task_no assignment/increment, whitespace stripping, update by int or str
    task_no, mark_done/reopen_task, a documented caveat test showing a hand-edit
    that removes the highest-numbered row *can* cause number reuse since nothing
    else tracks a persistent counter, the real page-title list staying in sync
    with `PAGE_OPTIONS`, and the dataclass's `to_row()` keys matching
    `FIELDNAMES`) - full suite 195 passing (183 + 12 new). Also an `AppTest`
    smoke pass across all seven pages (home + six `pages/*.py`, 7-Day Forecast
    against a mocked weather bundle) confirming no exception, plus a dedicated
    scratch `AppTest` script (not committed) that actually filled in and
    submitted the "Add an item" form end-to-end - typed a description, picked a
    page, clicked submit, then re-read `data/dev_tasks.csv` directly (`st.data_
    editor` grid edits themselves aren't reachable through `AppTest`, so the
    grid's diff/save logic was instead traced by hand against a throwaway CSV
    outside the Streamlit runtime) - confirmed task #1 was assigned, persisted
    with the right description/page/status, and immediately reflected in the
    grid's "N open" caption on the very next render. `data/dev_tasks.csv` starts
    committed as an empty (header-only) file, ready for the angler's first entry.

60. **Development page: added explicit per-item Edit/Delete buttons, and reworked
    the list from an `st.data_editor` grid to plain widgets.** Requested right
    after entry 59 shipped - the angler wanted an explicit button to edit a
    previously-entered item or delete it outright (delete was deliberately left
    out of entry 59). Used the request as a reason to reconsider the grid choice
    too: this page is exactly the kind of thing the angler would use standing at
    the lake to jot something down, and Trip History's `st.data_editor` grid
    (glide-data-grid under the hood) still has unverified real-phone touch/swipe
    behavior (entry 57's open item) - so the punch-list's own item rows were
    rebuilt as plain `st.checkbox`/`st.text_area`/`st.selectbox`/`st.button`
    cards instead, the same widget family already proven mobile-friendly
    elsewhere (Spot Session's live-conditions inputs). Each item is now a
    bordered container: a "Done" checkbox that saves the instant it's toggled
    (no separate save step, matching the original ask), and an "✏️ Edit or
    delete" expander with an editable description/page + "Save changes" button,
    plus a "🗑️ Delete" button behind the same two-step confirm pattern Trip
    History uses for deleting a trip (permanent, no undo).

    Deleting an item raised the numbering question the angler's original request
    didn't need answered: with `task_no` derived from "current max in the file"
    (entry 59's original scheme), deleting the *highest*-numbered item would let
    the next new item silently reuse that same number for something unrelated -
    fine for a uuid, actively confusing for an id specifically meant to be
    memorized and said out loud. Fixed by backing `task_no` assignment with a
    small persisted counter file (`data/dev_tasks_counter.txt`, next to
    `data/dev_tasks.csv`) that only ever increases - `delete_task()` never
    touches it, so a deleted number is never reissued regardless of which item
    (highest-numbered or not) gets removed. Bootstraps itself from the existing
    CSV's highest `task_no` the first time it's needed if the counter file
    doesn't exist yet (covers the real `data/dev_tasks.csv`, which already had
    one live item - #1, added by the angler through the deployed app between
    these two sessions - committed before this counter file existed).

    Verified with 4 new/replaced `tests/test_dev_tasks.py` cases (`delete_task`
    removing a row, deleting a missing task_no returning `False`, and two
    number-reuse regression cases - deleting the highest-numbered item and
    deleting a middle item, confirming neither's number is reissued - plus a
    bootstrap test simulating the real pre-counter-file `dev_tasks.csv`) - full
    suite 199 passing (195 + 4 net new). Also the usual `AppTest` smoke pass
    across all seven pages, plus a dedicated scratch `AppTest` script (not
    committed, run against a temporary second item added alongside the real
    #1 - restored `data/dev_tasks.csv` to its exact pre-test state afterward)
    that drove the new buttons directly: edited an item's description via its
    Edit panel and confirmed the save persisted, then deleted that same item
    through the two-step confirm flow and confirmed both the row's removal
    *and* that the next `append_task()` call skipped straight past the deleted
    number rather than reusing it.

61. **Development punch list #1: log small fish as a group; Trip History fish
    weights now shown as lb-oz.** Two related requests in one round - the
    Development page's one open item, plus a follow-up asked mid-session.

    **Group entries for small fish** (`pages/6_Spot_Session.py`'s "Add fish"
    form): a new "Log as a group of small fish (all under 1 lb)" checkbox
    swaps the Weight/Length inputs for a "How many fish" count (min 2) and an
    optional "Approx weight each (lb, capped at 1)" - no length field, since a
    group entry isn't meant to track individual measurements. Every fish
    record (`conditions["fish"]`, unchanged storage shape otherwise) now
    carries a `count` field, defaulting to 1 for a normal single-fish entry
    and set to the entered count for a group; older logged rows with no
    `count` key are treated as 1 everywhere this is read (`fish.get("count")
    or 1`), so nothing needed a data migration. `fish_caught` on save is now
    `sum(f.get("count") or 1 for f in fish_records)` instead of
    `len(fish_records)`, so a 3-fish group entry correctly counts as 3 toward
    the trip's catch total (and Trip History's "Total bass caught"/"Trips
    with a catch" metrics, which read that same field) even though it's one
    row in the pending-fish list. The pending-fish summary line and Trip
    History's per-fish detail renderer (`pages/4_Trip_History.py`) both show
    `"N x Species"` and `"~weight each"` for a count > 1, unchanged single-
    fish rendering otherwise.

    **Lb-oz weight display** (Trip History only, per explicit scope - Spot
    Session's own "Weight (lb)"/"Approx weight each" inputs are unchanged,
    still plain decimal, since that's still the fastest way to type a number
    standing at the lake): new `core.activity_log.format_weight_lb_oz()` /
    `parse_weight_lb_oz()` convert a decimal-pound float to/from a string
    like `"3 lb 8 oz"` (rounds to the nearest ounce - fish weight was never
    recorded to hundredths-of-a-pound precision to begin with, so this loses
    nothing meaningful). Applied to the per-trip detail panel's "biggest X
    lb" summary line and every per-fish weight in the detail list's per-fish
    renderer (both already existing render paths, entry 39/52's
    `_render_trip_detail_body`), and to the inline-editable grid's "Biggest
    fish" column, which changed from a `NumberColumn` to a `TextColumn` -
    `COLUMN_NORMALIZERS["biggest_fish_lb"]` now parses the cell's lb-oz (or
    plain-decimal, still accepted) text back to a float for both the auto-
    save diff check and the value actually written to `trip_log.csv`, so the
    grid's existing auto-save-on-edit behavior (entry 54) needed no other
    changes. Verified against every one of the angler's real logged trips
    (not just synthetic ones) via a scratch `AppTest` script - all render
    correctly as lb-oz with no exceptions, e.g. an existing 0.75 lb entry
    reads "12 oz", a 2.1875 lb entry reads "2 lb 3 oz".

    New `tests/test_activity_log.py` cases (10) cover
    `format_weight_lb_oz`/`parse_weight_lb_oz` directly: whole-pound and
    pound-plus-ounce formatting, under-1-lb-shows-ounces-only, the 16 oz ->
    next-whole-pound carry case, blank/None/NaN handling, both lb-oz and
    plain-decimal parsing, and a round-trip check on whole-ounce values.
    `python3 -m pytest tests/ -q` passes at 209 (199 + 10 new) - `pytest`
    alone isn't installed in this sandbox by `requirements.txt` (a dev-only
    dependency, not something the deployed app needs), so `pip install
    pytest --break-system-packages` first if starting fresh here. Also
    verified via two scratch `AppTest` scripts (not committed, `data/
    trip_log.csv` backed up/restored around both): one driving the actual
    "Add fish" group flow end-to-end (check the group box, set count=3 and
    weight=0.6, save, "Log this lure") and confirming the saved row's
    `fish_caught` is `3` and its one `fish` record has `count: 3`; a second
    loading that trip in Trip History's detail panel and confirming it
    renders `"Fish caught (3):"` / `"3 x Largemouth Bass, ~10 oz each"`. A
    full `AppTest` smoke pass across every page that can run in this sandbox
    (mocked weather bundle for home.py/7-Day Forecast, same fixture shape as
    `tests/test_scoring.py`'s `_fake_bundle()`) also caught that running the
    real 7-Day Forecast page against a fake bundle writes real (fake-
    derived) rows into `data/segment_score_freeze.csv` - reverted that file
    to its committed state before pushing, since freeze data belongs to the
    real deployed app's real weather, not this session's test bundle. Marked
    Development punch-list item #1 "Done" (`data/dev_tasks.csv`) at the end
    of this round.

62. **Rework of entry 61 per punch-list items #2/#3, which superseded #1 mid-
    session.** While entry 61 was in progress, the angler had also been
    working directly in the live deployed app: they deleted item #1 (the
    terse original ask this session started from) and replaced it with two
    much more specific items - #2 (the "Add fish" weight field itself should
    be a single manual "lb - oz" text field, e.g. "3 - 8", dash pre-filled,
    no +/- steppers) and #3 (split "Add fish" into two real paths: a full
    entry for scoreable fish 1 lb+, and a separate button opening a bare
    species+count block for non-scoreable fish under 1 lb - no weight/
    length/depth/presentation fields on that path at all). Entry 61's
    checkbox-based "group of small fish" design didn't match either - it
    kept a decimal weight input and still asked for depth/retrieve fields on
    a "grouped" entry. Surfaced this to the angler (via AskUserQuestion)
    once discovered; they chose "push what's done, then rework to match
    #2/#3" rather than holding the already-tested entry-61 commit back.

    **Item #2** (`pages/6_Spot_Session.py`'s "Add fish" form): the "Weight
    (lb)" `st.number_input` is now a plain `st.text_input("Weight (lb - oz)",
    value="0 - 0", ...)` - a single field, dash pre-filled, parsed on save
    via `core.activity_log.parse_weight_lb_oz()` (extended with a new dash-
    separated-shorthand branch, e.g. "3 - 8" or "3-8" -> 3.5, checked before
    the existing lb/oz-word and plain-decimal fallbacks; a two-number split
    with no dash, e.g. "3 8", still works too - same idea, no dash). An
    invalid oz part (>= 16, e.g. "3 - 20") isn't a real lb-oz pair and falls
    through every parse branch to `None` rather than being misread. One
    genuine platform limitation, called out to the angler rather than
    silently skipped: Streamlit's built-in widgets have no way to make
    typing into a sub-part of a field overwrite it without selecting/
    backspacing first (the literal "no backspacing required" ask) - that
    needs a real custom JS component (a full build/packaging step this app
    doesn't have), not just `unsafe_allow_html`. What's implemented is the
    closest achievable version: one text field, "xx - xx" format, dash
    already there to type over, no numeric steppers (a `text_input` never
    has them, unlike `number_input`).

    **Item #3**: the checkbox from entry 61 is gone. "Fish caught" now shows
    two buttons when nothing is being added - "➕ Add fish (1 lb+)" and "➕
    Log small fish (under 1 lb)" - backed by a single `adding_fish_mode_
    {spot_id}` session-state value (`None` / `"scoreable"` / `"small"`,
    replacing entry 61's/the original page's boolean `adding_fish_{spot_id}`
    flag - renamed since it now tracks which of two flows is open, not just
    whether one is). "Add fish (1 lb+)" is entry 61's/the original full form
    (species, the new lb-oz weight field, length, depth, presentation,
    retrieve speed) with `count` always `1`. "Log small fish" is a new,
    intentionally bare form: species picker + a single "Total number of this
    type caught" count (`min_value=1`) - nothing else; on save every other
    field (`weight_lb`, `length_in`, `depth_ft`, `retrieve_speed`,
    `retrieve_style`) is explicitly `None`. Both still append to the same
    `conditions["fish"]` list per lure, unchanged storage shape from entry
    61 (a `count` field, defaulting to 1 for a normal entry) - `fish_caught`
    on save is still `sum(f.get("count") or 1 for f in fish_records)`, so a
    4-fish "small fish" entry plus two scoreable singles still correctly
    totals 6, verified directly.

    Pending-fish summary line and Trip History's per-fish renderer both
    already handled a missing/None weight and a `count > 1` display from
    entry 61 - no further change needed there beyond already using
    `format_weight_lb_oz()` (entry 61) for the weight bit.

    Verified via `python3 -m pytest tests/ -q` (211 passing - 209 + 2 new
    dash-format parser cases in `tests/test_activity_log.py`) and two scratch
    `AppTest` scripts (not committed, `data/trip_log.csv` backed up/restored
    around both): one confirming the "small fish" flow produces a record
    with only `species`/`count` set and everything else `None`, that the
    "scoreable" flow's dash-format weight field ("3 - 8") parses to `3.5`,
    that an untouched default ("0 - 0") saves as `weight_lb: None` (not
    `0.0`), and that a mixed small+scoreable save produces the correct
    summed `fish_caught`; a second confirming every page (including Spot
    Session's edit mode, loaded against a real logged trip) still renders
    with no exception under the renamed `adding_fish_mode_` key. As with
    entry 61, running the real 7-Day Forecast page against a fake bundle
    during the smoke pass wrote fake-derived rows into `data/
    segment_score_freeze.csv` again - reverted before committing, same as
    last time. Marked Development punch-list items #2 and #3 "Done."

63. **Punch-list #4: the "Used a trailer" picker only shows real trailer-style
    baits now, not the whole tackle box.** Previously `_visual_lure_picker()`
    was called with the same full `inventory_items` list for both "Lure
    used" and "Trailer," so worms, senkos, and finesse baits (e.g. Z-Man's
    TRD line - explicitly named in the ask) showed up as trailer candidates
    even though they're standalone rigged baits, not something added onto
    another bait's hook.

    New `core.lures.TRAILER_ELIGIBLE_CATEGORIES = {"texas_rig_creature",
    "weightless_soft_plastic"}` - deliberately narrow, matching the two
    trailer TYPES this app's own `LURE_PROFILES` already documents ("Craw
    trailer," "Paddle-tail swimbait trailer"; `weightless_soft_plastic` is
    also where `guess_category_from_text()` already tags a standalone
    "swimbait," so this reuses that existing convention rather than
    inventing a new category). `is_trailer_eligible(item)` checks category
    first, then a keyword safety net (`TRAILER_EXCLUDE_KEYWORDS = ("worm",
    "senko", "trd", "stick bait", "stickbait")`) on the item's own brand/
    description text, so a TRD is excluded even if it were ever mis-
    categorized - same "no black box" keyword-matching philosophy as
    `_color_tokens()` elsewhere in this module. Checked against the
    angler's real inventory before committing to this design: every one of
    the 6 trailers actually logged so far is a Strike King Rage Tail Craw
    (`texas_rig_creature`) or a KVD Blade Minnow (`weightless_soft_plastic`)
    - the filter doesn't regress any real historical usage - and the
    angler's `finesse_shaky_head`-tagged Z-Man "Finesse TRD" rows confirm
    the keyword safety net's specific TRD callout wasn't hypothetical.

    `pages/6_Spot_Session.py`'s trailer call site now pre-filters
    `inventory_items` through `is_trailer_eligible()` before passing it to
    `_visual_lure_picker()` - the "Lure used" picker above it is completely
    unaffected, still shows the whole tackle box. `_visual_lure_picker()`
    gained an optional `empty_message` parameter so the trailer picker's
    empty state reads correctly ("No trailer-style baits... found") instead
    of the generic "No lures in your tackle box yet" when the *filter*, not
    an actually-empty inventory, is why nothing's showing.

    One edge case *not* specifically handled, documented here rather than
    engineered around since it doesn't affect any real data today: editing
    a trip whose logged trailer somehow falls outside
    `TRAILER_ELIGIBLE_CATEGORIES` (e.g. re-categorized after the fact) would
    prefill `selected_id` but the picker's own lookup (against the filtered
    list) wouldn't find it, silently showing "no trailer selected" rather
    than resolving it - the manual trailer-name text fallback still works
    in that case, so it's not a dead end, just not perfectly seamless.

    Verified with new `tests/test_lures.py` cases (7): every
    `TRAILER_ELIGIBLE_CATEGORIES` key is a real `LURE_PROFILES` entry;
    craw/swimbait categories pass, every worm-style category
    (`texas_rig_worm`, `wacky_rig_senko`, `finesse_shaky_head`,
    `carolina_rig`) and every host-bait category
    (`football_jig`/`chatterbait`/`spinnerbait`/`swim_jig`/`buzzbait`) fail;
    the TRD keyword safety net fires even against a category that would
    otherwise pass; and the two real historical trailer products both pass.
    `python3 -m pytest tests/ -q` passes at 217 (211 + 6 new). Also a
    scratch `AppTest` script (not committed, `data/trip_log.csv` backed
    up/restored): picked a real
    chatterbait as the lure, checked "Used a trailer," and confirmed the
    rendered trailer card grid's "Select" buttons only ever correspond to
    `texas_rig_creature`/`weightless_soft_plastic` inventory rows - no
    worm-style item's button ever appears - while the main "Lure used"
    picker's buttons still include worm-style items, confirming the filter
    is trailer-only. Full page smoke pass unaffected; `data/
    segment_score_freeze.csv` reverted afterward per the now-standard note
    from entries 61/62. Marked Development punch-list item #4 "Done."

64. **Punch-list #5: default the "Conditions right now" and "Lake Setup
    Options" fields to real early/mid-summer Nolin numbers instead of
    generic placeholders.** The ask: water temp 85°F, water color Green
    stained, water clarity 2.5', fish depth 8'. Field names matched Spot
    Session's "Conditions right now" form exactly; asked the angler whether
    to also touch the 7-Day Forecast's separate "Lake Setup Options"
    sidebar (similar but not identical fields, different current defaults)
    - confirmed "update both."

    `pages/6_Spot_Session.py`: changed the four `_cond_*` default
    computations that feed the (unkeyed) "Conditions right now" widgets -
    `_cond_water_temp_f` 75.0→85.0, `_cond_secchi_ft` 3.0→2.5,
    `_cond_stain_idx` now defaults to `STAIN_COLOR_OPTIONS.index(...)` 0
    ("Green stained," was 1/"Brown stained"), `_cond_fish_depth_ft`
    fallback 0.0→8.0. These only apply when `editing_cond` is empty (a new
    session, not editing a past one) - editing an existing trip still shows
    whatever was actually logged for it, unchanged.

    `core/ui.py`'s `render_lake_setup_sidebar()`: `default_water_temp_f`
    75.0→85.0 and `default_fish_depth_ft` 10.0→8.0 in the signature.
    Deliberately did *not* repoint the shared `core.lures.DEFAULT_BASE_STAIN`
    constant to "Green stained" for the stain dropdown, since that same
    constant also doubles as the color-palette fallback key in
    `recommend()` (`profile["colors"].get(water_clarity,
    profile["colors"][DEFAULT_BASE_STAIN])`) - repointing it would have
    silently changed lure-color fallback behavior everywhere, a much bigger
    blast radius than "what does this one dropdown start on." Added a new
    `default_base_stain: str = DEFAULT_BASE_STAIN` parameter instead (falls
    back to the old constant if an out-of-range value is ever passed), and
    `pages/1_7_Day_Forecast.py`'s call site now passes
    `default_base_stain="Green stained"` explicitly - the shared constant
    itself, and every other place that reads it, is untouched.

    One nuance worth recording: the 7-Day Forecast sidebar's water-temp
    default is already always overridden at the call site
    (`default_water_temp_f=week[0].water_temp_f`, the real forecasted
    estimate for today), so the 85.0 signature default is a fallback for
    any future caller that doesn't pass its own value, not something
    visible on today's page - the angler's actual water-temp complaint
    (estimate reads low vs. reality) is separately punch-list item #7, not
    touched here.

    Verified with the full suite (no new test cases - this is default-value
    wiring, not new logic; `python3 -m pytest tests/ -q` still passes at
    217) plus a scratch `AppTest` script (not committed) against a real
    saved spot: confirmed Spot Session's "Conditions right now" renders
    Water temperature 85.0, Water visibility/Secchi depth 2.5 (which lands
    the reading in the "Stained" band, so the stain dropdown appears and
    defaults to "Green stained"), and fish depth 8.0; confirmed the 7-Day
    Forecast sidebar's Water stain defaults to "Green stained" and Fish
    depth to 8.0 (water temp showed the mocked forecast's own estimate, as
    expected). Full-page smoke pass across every page clean; `data/
    segment_score_freeze.csv` reverted afterward. Marked Development
    punch-list item #5 "Done."

65. **Punch-list #6: label every period-of-day dropdown with its real clock
    range.** Ask: "In any drop down that lists the period of the day (Dawn,
    Morning, afternoon, etc.) also should the time range that this
    represents in parathesis." Audited every page for a Dawn/Morning/
    Midday/Afternoon/Dusk/Night dropdown: Spot Session's own "Time window"
    picker already did this (`_segment_option_label()`, entry from an
    earlier session, unchanged); the 7-Day Forecast page shows segment time
    ranges too but only as read-only expander/success-box text, not a
    dropdown, so out of scope. That left two spots on `pages/
    4_Trip_History.py`: the "Time of day" filter `multiselect`, and the
    inline-editable grid's "Time of day" `SelectboxColumn`.

    Both reuse a new pure helper, `segment_display_label(name, seg_ranges)`
    ("Dawn" + a `core.scoring.segment_time_ranges()` lookup ->
    "Dawn (5:52 AM-7:52 AM)", or `name` unchanged if no range is known for
    it) - same formatting Spot Session already used, just factored out so
    it's directly unit-testable (no Streamlit calls) rather than
    copy-pasted. Neither dropdown corresponds to one specific trip's date
    (the filter spans the whole trip history; the grid column covers every
    row at once with a single shared option list), so both use *today's*
    actual sunrise/sunset-derived ranges as a representative reference
    point rather than claiming to be that exact historical trip's real
    times - called out in both widgets' `help` text since the windows shift
    a few minutes day to day.

    The filter `multiselect` was the easy case: `st.multiselect` has a
    `format_func` parameter, so the underlying selected values stay plain
    segment names (still compared directly against `df["segment"]` for
    filtering) while only the on-screen text gets the range suffix - zero
    risk of the label leaking into stored/filtered data.

    The grid's `SelectboxColumn` has no such display/value split - whatever
    string is in its `options` list is both what's shown *and* what gets
    written back into the cell on edit. Repointing that column's options
    straight at labeled text would have meant a saved trip's `segment`
    field could end up literally holding `"Dawn (5:52 AM-7:52 AM)"` instead
    of `"Dawn"`, breaking every other place in the app that expects a bare
    `SEGMENTS` value (filtering, `_guess_segment()`, `recommend()` calls,
    etc.) - unacceptable for a field this load-bearing. Solved with a
    strictly one-way-at-a-time translation at the widget boundary: a new
    `segment_label_maps(canonical_options, seg_ranges)` builds both
    `label_by_name` and its exact inverse `name_by_label`; a throwaway copy
    of the grid's data (`grid_editor_input`, not the real `grid_display`
    used for diffing) gets its `segment` column relabeled before being
    handed to `st.data_editor`, and the instant `edited_grid` comes back
    from the widget, its `segment` column is translated straight back to
    plain names via `name_by_label` - before the existing `_grid_edit_diff`
    diff/save logic ever sees it. `grid_display` itself (the diff
    baseline, and everything downstream of it) never holds a labeled
    value, so a saved trip's `segment` is exactly what it always was.

    Verified with the full suite (unchanged behavior, no new logic beyond
    label formatting; `python3 -m pytest tests/ -q` still passes at 217 -
    this page's pure helpers have never had committed pytest coverage,
    same reasoning as the existing `_norm_text`/`_grid_edit_diff` note in
    the file's own comments: `st.data_editor` isn't reachable from AppTest
    in the pinned Streamlit/testing version). Checked
    `segment_display_label`/`segment_label_maps` directly by extracting
    their real source via `ast` and `exec`-ing just those two definitions
    in isolation (not a hand-copied duplicate) - confirmed the label
    round-trips back to the exact original name for every canonical
    segment plus `""` and an unrecognized legacy value, and that all
    labels are unique. A scratch `AppTest` run against a mocked weather
    bundle confirmed the real, in-page filter multiselect's `format_func`
    produces genuine ranges (e.g. `"Afternoon (2:00 PM-7:15 PM)"`) with no
    exception; the grid's `SelectboxColumn` itself couldn't be exercised
    the same way (the AppTest limitation above), so its correctness rests
    on the verified-in-isolation `segment_label_maps()` round-trip plus the
    page rendering with no exception. Full-page smoke pass across every
    page clean; `data/segment_score_freeze.csv` reverted afterward, `data/
    trip_log.csv` confirmed byte-identical before/after. Marked
    Development punch-list item #6 "Done."

66. **Follow-up to #6: Morning/Midday/Afternoon now scale proportionally
    with actual daylight, not fixed 11 AM/2 PM clock cutoffs.** After
    seeing the real ranges item #6 now displays, the angler asked whether
    every window was actually consistent with real sunrise/sunset and
    proportionally adjusted - the honest answer was "partially": Dawn,
    Dusk, and Night (`core/scoring.py`'s `_segment_windows()`) were always
    genuinely tied to the day's real sunrise/sunset, but Morning's end and
    Midday's end were hardcoded to `11:00`/`14:00` regardless of season, so
    Midday was always exactly 3 hours long year-round and Morning/Afternoon
    only changed length as an incidental side effect of Dawn/Dusk sliding
    around those two fixed posts, not a deliberate seasonal scaling.
    Flagged this as a real change to the scoring engine's segmentation
    (feeds `score_day()`/the 7-Day Forecast's actual per-window scores and
    `recommend()` calls, not just display labels) rather than a cosmetic
    tweak, and confirmed the angler wanted it changed before touching it.

    New `_segment_windows()`: computes the "daytime interior" (Dawn's end
    to Dusk's start) and splits it into three *equal* proportional thirds
    for Morning/Midday/Afternoon, replacing the `sunrise.replace(hour=11,
    ...)`/`sunrise.replace(hour=14, ...)` cutoffs entirely. Dawn (sunrise
    ±1h) and Dusk (sunset ±1h) are untouched; Night (dusk's end to next
    day's dawn's start) was already fully real and untouched. Chose equal
    thirds specifically because it's the most literal, least-opinionated
    reading of "adjusted proportionately" - no domain-specific weighting
    (e.g. a longer Afternoon bite window) was asked for, and equal thirds
    is trivial to verify and explain; can be reweighted later if the
    angler wants Morning/Midday/Afternoon in different proportions to each
    other.

    Confirmed the actual behavior change with real Nolin dates: mid-August
    (sunrise 6:20 AM/sunset 8:15 PM) now gives Morning/Midday/Afternoon
    each ~3h58m; mid-December (sunrise 7:50 AM/sunset 5:30 PM) gives each
    ~2h33m - all three windows visibly compress together in winter instead
    of Midday staying frozen at 3h while Morning/Afternoon absorb all the
    change. `score_day()`'s per-segment weather inputs (avg cloud/wind)
    were already whole-day averages, not per-segment, so this only changes
    each segment's own start/end (used for solunar-overlap detection, the
    "Best window" pick, and each window's `recommend()` call), not the
    cloud/wind/pressure/moon scoring math itself.

    One related approximation deliberately left alone: Spot Session's
    `_guess_segment(hour)` (pages/6_Spot_Session.py, used only to pick a
    reasonable initial "Time window" default before a session start time
    is entered) still uses its own separate fixed-hour cutoffs
    (`<7`/`<11`/`<14`/`<18`/`<20`), which were already an approximation of
    the *old* fixed-clock segmentation and now drift a bit further from
    the real proportional windows in the shoulder seasons. Not fixed here -
    it's just a rough starting guess the angler can freely correct via the
    dropdown itself before saving, not the source of truth for the actual
    time-of-day window a session gets scored/recommended against; wiring
    it to the real weather-bundle ranges instead is a fine future
    improvement if it turns out to guess wrong often enough to matter.

    Verified with 3 new `tests/test_scoring.py` cases: Dawn/Dusk/Night
    still compute to the exact real sunrise/sunset-derived bounds;
    Morning/Midday/Afternoon are contiguous and each exactly one-third of
    the daytime interior (within a second, allowing for timedelta division
    slop); and all three visibly shrink on a short winter day relative to
    a long summer day while Night visibly grows. `python3 -m pytest
    tests/ -q` passes at 220 (217 + 3 new). Full-page smoke pass across
    every page clean with no exception; `data/segment_score_freeze.csv`
    reverted afterward, `data/trip_log.csv` confirmed untouched. Not a
    numbered punch-list item (a direct follow-up question about #6, not a
    new list entry), so nothing new to mark in `data/dev_tasks.csv`.

67. **Follow-up to entry 66: Spot Session's `_guess_segment()` now uses the
    real proportional windows too, instead of its own separate fixed-hour
    cutoffs.** Entry 66 deliberately left this alone as a known, pre-
    existing approximation; asked to fix it for consistency once the real
    windows existed to check against.

    `_guess_segment(hour, now=None)` (pages/6_Spot_Session.py) now checks
    `now` against the module-level `seg_ranges` (segment_time_ranges() for
    the session's date, already computed a little further down the script
    for the "Time window" dropdown's own labels - see entry 63/the
    original `_segment_option_label()` work) and returns whichever real
    segment's window actually contains it. One gap those windows alone
    don't cover: `now` between midnight and *today's* Dawn belongs to the
    tail end of *last night's* Night window, not today's, since
    `seg_ranges["Night"]` only spans tonight's dusk through tomorrow's
    dawn - handled with an explicit `now < seg_ranges["Dawn"][0]` check
    before falling through. Still falls back to the original fixed-hour
    cutoffs (`<7`/`<11`/`<14`/`<18`/`<20`) when no weather bundle is
    available (offline, or the session date's outside the forecast
    window's coverage) or `now` isn't passed - a reasonable rough
    approximation, same role the whole function always played, just no
    longer the primary path when real data exists. `hour` stays a required
    positional arg (the fallback still needs it); `now` is optional so
    every existing caller's shape barely changes. Both call sites (the
    "Conditions right now" segment default, and the "Add results" fallback
    when logging a result with no conditions filled in) now compute
    `lake_now_naive()` once into a local and pass it as both `hour` and
    `now`, instead of calling `lake_now_naive()` a second time.

    Verified by extracting the real, just-edited `_guess_segment` source
    via `ast` (same not-a-duplicate technique as entry 65's grid-helper
    check) and exercising it directly against real mid-August proportional
    windows: confirmed it now correctly resolves 11:30 AM to "Midday" and
    8:00 PM to "Dusk" (both would have been silently wrong under the old
    fixed-hour cutoffs - "Morning" and "Afternoon" respectively), confirmed
    the pre-dawn (2:00 AM, 4:59 AM) case correctly resolves to "Night," and
    confirmed the no-bundle/no-`now` fallback path still returns the
    original fixed-hour answers unchanged. `python3 -m pytest tests/ -q`
    still passes at 220 (no scoring-engine logic changed, just this page's
    own default-guessing wiring). A live scratch `AppTest` run against a
    mocked bundle confirmed the "Time window" dropdown's actual pre-
    selected default reflects a real proportional-window label end to end,
    not just the isolated function. Full-page smoke pass across every page
    clean; `data/segment_score_freeze.csv` reverted afterward, `data/
    trip_log.csv` confirmed untouched. Not a numbered punch-list item.

68. **Punch-list #7: add live lake level, and fix the water-temp estimate
    that was reading well below real conditions.** Two-part ask: "Also all
    the current lake level to the data shown. Also, can you look at where
    you get the water temperature from? It is always much lower than
    actual. Please make sure this is surface temperature."

    **Lake level.** No live gauge was already wired up, and the angler
    wasn't sure of the exact source ("I think the corp of engineers has a
    site that records this, but not sure what it is"). This dev sandbox has
    no outbound network access at all (confirmed - even a plain `curl` to
    Open-Meteo times out), so used `WebSearch`/`WebFetch` instead of
    guessing at an endpoint from memory: found USGS site 03310900 ("Nolin
    Lake near Kyrock, KY," a Corps-operated reservoir monitored by USGS
    under their usual cooperative agreement), and directly hit the real
    `waterservices.usgs.gov/nwis/iv` API to confirm it live before writing
    any code - it reports 3 parameters (precip, gage height, and parameter
    code 62614 "Lake or reservoir water surface elevation above NGVD 1929,
    ft"), the last of which returned a real reading of 515.34 ft at fetch
    time, right at/near the 515 ft normal summer pool this app's own footer
    caption already quotes - strong confirmation this is the right gauge.
    No water temperature parameter exists at this site, so the estimate
    below is still necessary.

    New `core/lake_level.py`: `fetch_lake_level(site_id=USGS_SITE_ID)` hits
    that same endpoint (`parameterCd=62614`, `period=P1D`), parses the JSON
    down to `value.timeSeries[0]` (`sourceInfo.siteName` +
    `values[0].value[-1]` for the most recent reading), and raises on any
    failure - same "raise, let the caller degrade gracefully" convention as
    `core.weather.fetch_forecast()`. New `core.appstate.get_lake_level()`
    wraps it with `st.cache_data(ttl=15min)` (shorter than the weather
    bundle's 1h TTL, matching USGS's ~5-15min real telemetry cadence).
    `home.py` fetches it in its own independent `try/except` (a USGS outage
    shouldn't block the weather-derived metrics above it, or vice versa),
    adds a 5th "Lake level" metric to "Today at a glance" showing the live
    reading plus a `delta` of how far above/below the 515 ft normal pool
    it currently sits (`delta_color="off"` - neither direction is
    inherently good/bad for fishing), and falls back to an explanatory
    caption instead of the metric when the fetch fails, rather than an
    alarming `st.error` (a missing "nice to have" reading isn't the same
    severity as a failed forecast).

    **Water temperature.** Root-caused two compounding bugs in
    `core.weather.estimate_water_temp_f()`, confirmed both numerically
    before touching any code:

    1. The "5-day trailing average" had no real 5 days to average for
       TODAY specifically. `fetch_forecast()` never passed Open-Meteo's
       `past_days` parameter, so the returned `hourly`/`daily` arrays start
       exactly at today's local midnight - nothing earlier. For `d=today`,
       the old window (`d - 5 days` through `d`'s midnight) could only ever
       match that single first hourly value (the coldest part of the day,
       right after midnight) - simulated the real production bundle shape
       and confirmed the estimate collapsed to ~76.5°F, essentially just
       that one midnight reading, not a 5-day trend at all.
    2. Even with genuine 5-day history, the formula averaged ALL 24 hourly
       readings a day (dragging the number down with overnight lows a
       reservoir surface doesn't track nearly as closely as it tracks
       daytime heating) and then subtracted another flat 4°F on top of
       that already-low average - simulated with a realistic diurnal air
       curve and confirmed even a proper 5-day average still landed around
       77.8°F, well below the angler's real Spot Session readings for the
       same stretch of days (83.0-88.9°F, mid-August 2026).

    Asked the angler how thorough to make the fix (structural bugs only,
    vs. also retuning the seasonal baseline curve using real logged data as
    ground truth) - chose "fix everything." Changes, all in
    `core/weather.py`:
    - `fetch_forecast()` now requests `past_days=WATER_TEMP_TREND_PAST_DAYS`
      (5) alongside `forecast_days` - real history, not just forecast, is
      now actually present in the bundle every time, not just once `d` is
      5+ days out into the week. Confirmed this doesn't add unwanted extra
      days to the 7-Day Forecast page itself: `score_week()`/`score_day()`
      look up specific dates (`start + i` for `i in range(days)`), they
      don't iterate whatever's in the bundle, so the padded-in past days
      are only ever reachable via `estimate_water_temp_f()`'s own trailing
      window, not shown as extra forecast days.
    - `estimate_water_temp_f()` switched from a raw all-hours average of
      `bundle.hourly["temperature_2m"]` to a trailing average of
      `bundle.daily["temperature_2m_max"]` (each day's actual high) for the
      `WATER_TEMP_TREND_PAST_DAYS` days strictly before `d` - a much better
      proxy for what's actually warming the surface layer. The flat "-4"
      offset became "-3" applied to the daily-high average instead of the
      (already much lower) all-hours average.
    - The seasonal baseline curve (`60 + 24*sin(2π*(day_of_year-105)/365)`,
      peak 84°F around day 196/mid-July) was retuned to
      `60 + 27*sin(2π*(day_of_year-124)/365)` (peak ~87°F around day
      215/early August) - the old curve's best day was already below
      several real August readings, and a reservoir's actual thermal lag
      tends to push peak surface temps later than the solar solstice.
      Explicitly still a best-effort model outside the one narrow window
      (mid-August 2026) real ground truth currently covers - noted in the
      function's own docstring as a candidate to revisit once trips get
      logged across more of the year, rather than treated as fully solved.
    - This isn't purely cosmetic: `season_stage()`'s bands are keyed on
      `water_temp_f` thresholds (80°F = summer_peak), so mid-August now
      correctly classifies as `summer_peak` instead of the old estimate's
      `post_spawn_summer` - a real accuracy improvement to lure/season
      selection app-wide, not just the Home page's displayed number.

    Fixed two `tests/test_scoring.py` cases the new (correctly higher)
    estimate broke - not by reverting behavior, but by fixing what were
    genuine test gaps the old, artificially-low estimate had been masking:
    `test_manual_segment_score_matches_score_day_for_equivalent_inputs`
    wasn't actually passing an equivalent `water_temp_f` into
    `manual_segment_score()` (silently relied on the old estimate always
    landing in the no-op 77-84°F band); now passes `day.water_temp_f`
    explicitly, matching what the test's own name claims to verify.
    `test_score_day_water_temp_summer_stratified_band_stays_neutral`'s
    fixture parameter (`air_temp_f=84.0`) no longer lands in its target
    band under daily-high-based averaging - changed to `66.0`, documented
    inline why a cooler input value is now what's needed. Also updated
    `_fake_bundle()`/`_fake_bundle_with_air_temp()` themselves (shared
    across most of `test_scoring.py`) to pad `daily` back
    `WATER_TEMP_TREND_PAST_DAYS` days before `d`/today, matching the real
    past_days-extended shape `fetch_forecast()` now requests - without
    this, every test's trailing-average window would silently find zero
    days and fall through to the seasonal-only branch, leaving that whole
    code path untested even though this is exactly the fix meant to keep
    it populated.

    New coverage: `tests/test_weather.py` gained 6 cases (`fetch_forecast`
    actually requests `past_days` - via `monkeypatch.setattr(mod.requests,
    "get", ...)`, same mocking convention as `test_cabelas_lookup.py`;
    `estimate_water_temp_f` falls back to seasonal-only with no daily data
    and still lands in the real 83-89°F range for mid-August; only days
    strictly before `d` are averaged, not `d` itself or later; only days
    inside the trailing window count, confirmed by adding an "outside the
    window" day and checking the result doesn't move; a genuinely hot vs.
    cold recent trend moves the estimate in the right direction; and a
    representative low-90s recent-highs trend lands the estimate inside the
    angler's real 83-89°F logged range). New `tests/test_lake_level.py`
    (5 cases, same `monkeypatch` convention, using the real JSON shape
    confirmed against the live API above): requests the right site/
    parameter, parses the most recent reading correctly, takes the LAST
    value when multiple are present (not the first), raises on zero
    readings, and raises (doesn't swallow) on a network failure so `home.py`
    is the one that decides how to degrade. `python3 -m pytest tests/ -q`
    passes at 231 (220 + 11 new).

    Verified end to end with a scratch `AppTest` smoke run (mocked weather
    bundle + mocked `get_lake_level`) across every page: no exceptions;
    `home.py`'s metrics read "Est. water temp = 86.5°F" (vs. the old
    formula's ~77-79°F for the same fixture) and "Lake level = 515.34 ft
    +0.3 ft vs. normal pool" as a real 5th metric; a second run simulating
    a USGS outage confirmed the graceful 4-metric-plus-caption fallback
    with no exception. `data/segment_score_freeze.csv` reverted afterward,
    `data/trip_log.csv` confirmed untouched. Marked Development punch-list
    item #7 "Done."

69. **Follow-up to #7: a real (not estimated) surface water temperature
    source, plus dissolved oxygen % saturation.** After #7 shipped, the
    angler asked whether any site publishes the actual lake surface
    temperature, flagging one candidate themselves (lake-ready.com, "a beta
    site... use it if you can't find anything else").

    Checked lake-ready.com directly with a real browser (`mcp__claude-in-chrome`,
    since this domain wasn't reachable through `WebFetch`) on both its main
    dashboard and its "Fishing Outlook" subpage - it does not actually
    publish water temperature anywhere on the site, despite the name. Told
    the angler this honestly rather than wiring up a source that doesn't
    exist, and searched further per their reply ("forget this site. Can you
    keep looking a bit for a government site that might have it?"):
    - USACE's modern CWMS Data API (`cwms-data.usace.army.mil`) - confirmed
      Nolin Lake is a registered location (`/locations?office=LRL`), but no
      working/documented timeseries query was found after several attempts
      (400s, robots.txt blocks, 404s on the swagger/api-docs paths).
      Abandoned, inconclusive.
    - USGS's Water Quality Portal for the lake gauge - has historical
      readings, but discontinued since 2017. Not usable for current
      conditions.
    - USGS site 03311000 - a genuinely live feed, but it's the
      tailwater/river gauge below the dam (cooler water already released
      through the dam), not the lake's own surface. Flagged this as a real
      accuracy tradeoff (a cold bias, ~74.5°F vs. the true ~86°F surface)
      rather than quietly proposing it.
    - The legacy USACE Louisville District report
      (`lrl-wc.usace.army.mil/reports/wq/NRR.html`) - a real, periodic
      (roughly biweekly) manual survey with actual surface temp + dissolved
      oxygen readings. Reachable via a real browser but not via `WebFetch`
      (SSL certificate verification errors against this domain) - disclosed
      to the angler as an open risk for the deployed app's server-side
      `requests` calls specifically, since it couldn't be verified through
      that exact code path.

    Reported all of this honestly (no ideal source exists) and asked how to
    proceed. Angler's call: **"Add the periodic USACE survey anyway"** -
    shown as a clearly-dated secondary reading alongside the daily estimate,
    accepting the staleness and unverified-domain-reliability tradeoffs.
    Mid-turn, a second ask arrived: **"if you can find oxygen saturation as
    well, that would be awesome!"** - so this became a temp + DO% feature,
    not just temp.

    Inspected the real report's HTML directly via the browser tools
    (`document.body.innerHTML`) to design the parser against the actual
    markup rather than guessing: a single plain `<table>`, one `<tr>` of 5
    `<td>`s per depth ("Station", "Date, Time" as `YYYYMMDD, HHMM`, "Depth
    (ft)", "Water Temperature (deg C)", "Dissolved Oxygen (mg/l)"), blank
    `<tr></tr>` rows as station separators, and a `<th>`-based header row
    that never collides with a data-row regex. Two stations profiled:
    "Tailwater" (river water below the dam - same wrong-location problem as
    the USGS 03311000 gauge, so deliberately excluded) and "Dam Site" (the
    lake's own vertical profile, depth 0 through 90 ft) - the depth-0 "Dam
    Site" row is the real lake surface reading.

    Chose a small stdlib `re` regex over adding `beautifulsoup4`/`html5lib`
    as a new dependency: confirmed via `pip show`/`python3 -c "import ..."`
    that neither is installed in this sandbox (only `lxml` is present, and
    only as an already-installed transitive dependency of `pikepdf`/
    `python-docx`/`python-pptx`, not something in `requirements.txt` or
    guaranteed present in the deployed Streamlit Cloud environment) - matches
    this codebase's existing minimal-dependency philosophy already used for
    `core.cabelas_lookup`'s own regex-based scraping, and the report's
    markup is regular enough (one `<tr>` of 5 `<td>`s per row, always) that a
    full HTML parser isn't needed.

    For dissolved oxygen % saturation (not just raw mg/l), used the standard
    APHA Standard Methods 4500-O / Elmore-Hayes polynomial for sea-level DO
    saturation concentration as a function of temperature
    (`14.652 - 0.41022T + 0.0079910T² - 0.000077774T³`), times a barometric
    correction for Nolin Lake's ~515 ft elevation
    (`(1 - 2.25577e-5 * elevation_m)^5.25588`), then
    `measured_mg_l / saturation_concentration * 100`. Hand-verified this
    against the real reading (30.3°C, 10.66 mg/l, 515 ft) before writing any
    code: ~147% - plausible afternoon photosynthetic supersaturation for a
    warm, productive summer reservoir surface, and cross-checked for
    plausibility against this app's own `core.onwater.WATER_TEMP_BANDS`
    "severe oxygen stress" framing, which lines up with the same report's
    near-zero deep-water DO readings (0.02-0.14 mg/l below ~30 ft).

    New `core/lake_water_quality.py`: `fetch_surface_water_quality()` GETs
    the report, regex-matches every 5-`<td>` row, keeps the first "Dam
    Site"/depth-"0" match, parses the `YYYYMMDD, HHMM` timestamp, converts
    °C to °F, and computes the saturation % above (reusing
    `core.lake_level.NORMAL_SUMMER_POOL_FT` for the elevation input) -
    raises on any failure (bad HTTP, no matching row), same "raise, let the
    caller degrade gracefully" convention as `fetch_lake_level()`/
    `fetch_forecast()`. New `core.appstate.get_surface_water_quality()`
    wraps it with a 6-hour `st.cache_data` TTL (much longer than the other
    sources - USACE only republishes this roughly every 1-2 weeks, no
    benefit to polling more than a few times a day, and it's a non-API
    legacy page worth not hammering). `home.py` fetches it in its own
    independent `try/except` (same pattern as lake level - a stale/
    unreachable USACE page shouldn't block the weather- or USGS-derived
    metrics, or vice versa) and shows it as a caption below "Today at a
    glance" rather than folding it into the metric row - it's explicitly
    dated ("USACE Dam Site survey, 8/06") and explicitly contrasted against
    the "Est. water temp" metric above it ("this is a periodic manual
    survey, not a live/daily feed"), so it can't be mistaken for a live
    reading. Falls back to simply not showing the caption on fetch failure,
    same graceful-degradation shape as lake level.

    New `tests/test_lake_water_quality.py` (6 cases, `monkeypatch.setattr(mod.requests,
    "get", ...)` convention, using the real HTML shape captured from the
    live page via the browser tools): requests the right URL; picks the
    Dam Site depth-0 row specifically (not Tailwater, not a deeper Dam Site
    row - confirmed by including both a Tailwater row and a deep Dam Site
    row in the fixture and checking neither wins); parses the observation
    datetime correctly; the saturation-% calc lands in a plausible
    140-155% range for the real reading; raises `ValueError` when no
    matching row exists (e.g. a page with only Tailwater data); raises
    (doesn't swallow) on a network failure. `python3 -m pytest tests/ -q`
    passes at 237 (231 + 6 new).

    Verified end to end with a scratch `AppTest` smoke run: first with all
    three external fetches mocked to fail (this sandbox has no outbound
    network access at all, confirmed again here), confirming no exception
    and the existing lake-level fallback caption still renders correctly;
    then with a fully mocked `WeatherBundle` + `LakeLevel` +
    `SurfaceWaterQuality` (reusing `tests/test_scoring.py`'s `_fake_bundle`
    shape) to render the real success path - confirmed the new caption
    reads exactly "🌡️ Most recent real surface reading (USACE Dam Site
    survey, 8/06): 86.5°F, dissolved oxygen 10.66 mg/l (~147% saturation).
    This is a periodic manual survey, not a live/daily feed - the "Est.
    water temp" above is today's model-based estimate." alongside the
    existing 5 metrics, with no exception. `data/segment_score_freeze.csv`/
    `data/trip_log.csv` confirmed byte-identical (`md5sum`) before and
    after every run. Not a numbered punch-list item (a direct follow-up to
    #7, discussed conversationally) - no `data/dev_tasks.csv` change needed.

70. **Punch-list #8: cap owned-lure suggestions to a #1/#2 top-2, and
    suggest real Cabela's products to buy when nothing's owned.** Two-part
    ask, both scoped to "any page that suggests lures to use": "if I don't
    have that in my inventory please show options from Cabelas.com that I
    should consider buying. Only show a max of 2 best options from cabelas.
    Also, if you show options from my inventory, only show the top 2
    recommendations in each category... with a #1 and a #2 choice."

    Both the 7-Day Forecast and Spot Session pages already funnel every
    lure block through the same shared `core.ui.render_lure_recommendation`/
    `render_lure_block`, so both parts of this only needed to change in one
    rendering path (plus one ranking function) to cover every page, rather
    than being wired into each page separately.

    **Top-2 owned items, ranked #1/#2.** Before this, a `LureBlock`'s
    `owned_items` (already filtered to color-matched-only, see entry on the
    "Color-match filtering" feature) could be any length - every matching
    item was joined into one run-on success message, and the thumbnail
    section separately capped display at 4 photos with a "+N more" caption.
    `core.lures._color_matched_owned_items()` now sorts matches by quantity
    on hand (descending, most in reserve first, stable for ties) and slices
    to a new `MAX_OWNED_ITEMS_PER_BLOCK = 2` before ever reaching the block
    - so `owned_items` itself is never longer than 2, not just capped at
    render time. `core.ui.render_lure_block()` shows each as its own
    `**#1**`/`**#2**` line instead of one joined string. The now-redundant
    4-photo/"+N more" thumbnail cap in `core/ui.py` was removed (dead code
    once the source list itself maxes out at 2) rather than left in place,
    since it wasn't a separate feature, just an artifact of the old
    unbounded list.

    **Real Cabela's buy suggestions when nothing's owned.** Reused
    `core/cabelas_lookup.py`'s existing `search_lures()` (built for the
    Lure Inventory page's "Scan a lure" flow) rather than building a second
    integration - it already returns real brand/name/price/photo/SKU data
    for a text query and fails soft (`[]`) on any lookup problem, which is
    exactly the "worth considering, no black box" shape this needed.
    New `core.appstate.get_cabelas_suggestions(query, num_results=2)` wraps
    it with a 24h `st.cache_data` TTL - important here specifically because
    the 7-Day Forecast page calls `recommend()` once per segment per day
    (~28 calls), and without caching, every lure block with nothing owned
    would trigger its own live Cabela's round trip on every page load, for
    what's usually the same handful of repeating lure names (e.g.
    "Squarebill Crankbait" shows up across many days/segments) - a day's
    staleness is a non-issue for "worth considering buying," unlike a price
    feed. `core.ui.render_lure_block()`'s previously-unconditional "🛒 Not
    in your inventory yet" caption is now only the fallback for when
    `get_cabelas_suggestions()` comes back empty (lookup failure, or
    genuinely no matches) - otherwise it shows up to `MAX_CABELAS_SUGGESTIONS
    = 2` product cards (thumbnail via the existing `render_square_thumbnail()`
    - `resolve_image_source()` already works unmodified against a Cabela's
    result dict, since it just falls through to the plain `image_url` key
    when there's no local `image_filename`), brand/name/price, and a
    `**#1**`/`**#2**` label matching the owned-items styling above.

    New `core.cabelas_lookup.search_page_url(query)`: the mapped Coveo
    `raw` fields `map_result()` reads (sku/brand/description/price/image/
    categories) don't include a stable per-product-page URL - none was
    found in this module's existing field list, and rather than guess at
    an unverified field name, this links each suggestion to Cabela's own
    live site search for that product's brand + name, which should surface
    the same product at or near the top.

    Design choice: kept `core.lures.recommend()` itself free of any
    network I/O - the top-2/#1/#2 ranking is pure list logic (belongs in
    `core/lures.py`, stays unit-testable the way it already was), while the
    Cabela's lookup (I/O, needs caching, needs Streamlit's cache decorator)
    lives entirely in the `core/ui.py` render layer, matching how
    `core/lures.py` has never done its own I/O even for the inventory data
    it's handed (that's always fetched by the caller and passed in).

    Verified the two-step Coveo flow before touching this module further:
    this dev sandbox still has no outbound network access at all (confirmed
    again - both `waterservices.usgs.gov` in punch-list #7 and now
    `www.cabelas.com`'s token endpoint fail with the same sandbox
    `ProxyError`/403), and this session's real-browser tool
    (`mcp__claude-in-chrome`) declined permission when tried here, so the
    Coveo raw-field shape wasn't independently re-verified this round -
    relied on `core/cabelas_lookup.py`'s existing, already-shipped
    `map_result()`/`search_lures()` (used for months by "Scan a lure"
    without a reported field-shape issue) rather than assuming any new
    field exists that hasn't already been confirmed working.

    New tests: `tests/test_lures.py` gained
    `test_owned_items_are_capped_at_top_2_ranked_by_quantity` (3
    color-matched items on hand, quantities 1/5/3 - only the top 2 by
    quantity come back, most-stock first) and
    `test_owned_items_tie_on_quantity_keeps_original_order` (3 items tied
    at quantity 2 - the first 2 in original order come back, confirming the
    sort is stable rather than reordering ties arbitrarily).
    `tests/test_cabelas_lookup.py` gained
    `test_search_page_url_url_encodes_the_query` and
    `test_search_page_url_handles_blank_query`. `python3 -m pytest tests/ -q`
    passes at 241 (237 + 4 new).

    Verified end to end with two scratch `AppTest` smoke runs on
    `pages/1_7_Day_Forecast.py` (both pages funnel through the same shared
    `core.ui.render_lure_block`, so exercising this once covers both): one
    with a mocked inventory item and a mocked `core.appstate.search_lures`
    returning 2 fake products, confirming both a `**#1**` owned-item line
    and a "Search Cabela's" link render with no exception; a second with
    empty inventory and `search_lures` mocked to return `[]`, confirming
    the plain "worth picking one up" fallback caption renders instead (and
    the Cabela's-specific caption does not) - the graceful-degradation path
    still works exactly as before this change. `data/trip_log.csv`
    confirmed byte-identical before/after; `data/segment_score_freeze.csv`
    picked up an unrelated freeze write from the smoke run itself (today's
    real date has genuinely-past segments) and was reverted with `git
    checkout` afterward, same as the pollution-check convention used all
    session. Marked Development punch-list item #8 "Done."

71. **Punch-list #9: auto-fill "Time window" from the entered session start
    time.** Ask: "When I enter the current conditions, automatically fill
    in the period of the day (dawn, morning, etc.) based on the start time
    I input." On the Spot Session page's "Conditions right now" section,
    the "Time window" dropdown (Dawn/Morning/Midday/Afternoon/Dusk/Night)
    always defaulted from the real current clock time via `_guess_segment()`
    - independent of whatever the angler typed into "Session start time"
    right above it, even though that field's own help text already
    explains it's deliberately NOT tied to "now" ("you might do that before
    heading out or after you're done"). So logging a morning session in the
    evening, or planning one ahead of time, left the Time window on
    whatever segment it currently was in real life, not the one the entered
    start time actually falls in.

    Root cause was really about *when* the guess got computed, not the
    guessing logic itself - `_guess_segment()` already took an arbitrary
    `now: datetime` and checked it against `seg_ranges` (the same real
    sunrise/sunset-derived windows the dropdown's own labels show), it just
    always got called with `lake_now_naive()` (the real current time) at a
    point in the script *before* the `start_time` widget below it had even
    been rendered - `_cond_segment_name` (the dropdown's default `index=`)
    was computed at line ~385, `start_time = c6.time_input(...)` not until
    line ~442. Moved that computation down to right after the `start_time`
    widget instead, so it can read the *current run's* actual entered
    value: `_guess_dt = datetime.combine(session_date, start_time) if
    start_time is not None else lake_now_naive()`, then
    `_guess_segment(_guess_dt.hour, _guess_dt)` same as before. Falls back
    to real "now" only when start_time hasn't been entered yet (still a
    reasonable live default before the required field's filled in).

    Verified empirically (via a scratch `AppTest` two-widget script) exactly
    how a Streamlit selectbox without an explicit `key=` behaves before
    relying on it: passing a new `index=` on a rerun DOES override the
    widget's current value when the computed index has changed since the
    last run, but a manual pick in the widget survives any rerun where the
    computed index stays the same as it already was - i.e. this is exactly
    "auto-follow the input it's derived from, but don't fight a real manual
    override in between," without needing any extra state-tracking code.
    That's the exact behavior wanted here, so no explicit `key`/session_state
    juggling was added - just reordering the existing computation to see
    the right value at the right time. Updated `_guess_segment()`'s
    docstring (now called with either the entered start time or "now",
    depending on the caller/state, not always "now") and added a `help=`
    string on the dropdown itself explaining the auto-fill.

    No new unit tests - `_guess_segment()`'s own logic (the actual
    guessing/window-matching) is unchanged and already covered by its
    existing design; what changed is purely *when* it's called and with
    *what* argument inside a Streamlit page script, which isn't something
    `pytest` exercises for this codebase (no `pages/*.py` file is unit
    tested directly - see `core/scoring.py`/`core/lures.py` for where the
    actual testable logic lives). `python3 -m pytest tests/ -q` still
    passes at 241 (unchanged from before this entry).

    Verified end to end with a scratch `AppTest` run against
    `pages/6_Spot_Session.py` (mocked weather bundle, inventory, and a
    single fake saved spot loaded via `spot_session_target_id`) driving the
    actual widget interactions in sequence: start time 8:00 AM -> "Morning
    (7:00 AM-11:00 AM)"; 1:00 PM -> "Midday (11:00 AM-3:00 PM)"; 8:30 PM ->
    "Dusk (7:00 PM-9:00 PM)"; 6:00 AM -> "Dawn (5:00 AM-7:00 AM)" - each
    matching the real proportional sunrise/sunset-derived windows for the
    synthetic bundle used, not fixed clock cutoffs. Then confirmed the
    override behavior explicitly: manually picked "Midday" while start time
    stayed at 6:00 AM, changed an unrelated field (water temperature) and
    confirmed "Midday" was still selected (override survives unrelated
    reruns), then changed start time again to 8:30 PM and confirmed the
    dropdown snapped to "Dusk" (an actual start-time change still re-drives
    it, as intended). `data/trip_log.csv` confirmed byte-identical
    before/after; `data/segment_score_freeze.csv` untouched this round
    (Spot Session doesn't write to it). Marked Development punch-list item
    #9 "Done."

72. **Punch-list #10: replace the lux-based "Light conditions" dropdown
    with a real sky-condition/cloud-cover scale.** Ask: "For the Light
    Conditions field, let change the dropdown to better describe the sky;
    i.e. no/minimal clouds, partly cloudy, overcast, etc. (feel free to
    suggest other sky conditions)."

    First traced what the field actually does before touching it: grepped
    every use of `light_condition` and found its only real downstream
    effect is `core.onwater.cloud_proxy_for_light_condition()` -> feeds
    `avg_cloud_pct` into `manual_segment_score()`. The old 4-option scale
    (`Night`, `Crepuscular (Dawn/Dusk)`, `Overcast / Diffuse Day`, `Direct
    High Sun`) conflated two different things into one field: time-of-day
    light level (already captured separately by the page's own "Time
    window" dropdown, `segment_name`) and actual cloud cover (this field's
    one real job). That conflation had a genuine, if minor, side effect
    worth calling out: `"Night"` mapped to a cloud-proxy of 20.0, which
    fell inside `core.scoring._segment_score()`'s `avg_cloud <= 25`
    "clear/bright bluebird tough-bite" penalty band - a penalty whose
    entire rationale is glare/high-sun visibility, applied at full
    darkness. Confirmed `core.lures.recommend()`'s own `low_light`
    lure-selection logic is driven by `segment_name` (Dawn/Dusk/Night),
    not by this field at all, so nothing about lure selection depends on
    keeping a time-of-day option here.

    Replaced the vocabulary with the National Weather Service's own
    published sky-condition terminology - oktas (eighths of the sky
    covered by opaque clouds) - confirmed via `WebSearch`/`WebFetch`
    against NOAA's own forecast glossary
    (https://forecast.weather.gov/glossary.php?word=sky+condition) rather
    than relying on memory for the exact breakpoints: Clear/Sunny (0/8),
    Mostly Clear/Mostly Sunny (1-2/8), Partly Cloudy/Partly Sunny (3-4/8),
    Mostly Cloudy (5-7/8), Cloudy/Overcast (8/8). This is the one band
    table in `core/onwater.py` that now follows a real public standard
    rather than user-supplied thresholds - called out explicitly in the
    module's own docstring, since every other band there (wind, visibility,
    water temp) is still deliberately hand-specified domain input, not
    modeled from a source.

    New `_LIGHT_CONDITION_CLOUD_PROXY` values are each band's real okta-
    range midpoint converted to a percent, chosen specifically so they land
    on the correct side of `core.scoring._segment_score()`'s two existing
    thresholds rather than just being "reasonable-sounding" numbers: Clear/
    Sunny (5.0) and Mostly Clear (20.0) both fall under the 25% clear-sky-
    penalty cutoff; Mostly Cloudy (75.0) and Overcast (95.0) both clear the
    60% overcast-bonus cutoff; Partly Cloudy (45.0) sits deliberately in the
    untouched neutral middle - the same three-way split a real forecast's
    `cloudcover` reading would produce. Also fixes the "Night" oddity above
    as a side effect: a clear night sky and a clear midday sky both now
    correctly read "Clear / Sunny" (proxy 5.0, still triggers the clear-sky
    penalty - correctly, since bright/clear skies matter for light
    penetration regardless of whether the sun's up) instead of Night
    silently landing in that penalty band under an unrelated label.

    Backward compatibility for already-logged trips was a real constraint,
    not an afterthought - `data/trip_log.csv` has 22 real trips with
    `conditions_json.light_condition` values from the old vocabulary ("20
    x Crepuscular (Dawn/Dusk)", 1 Direct High Sun, 1 Night). Checked every
    call site before changing anything: the Spot Session "edit trip"
    prefill (`_cond_light_idx = LIGHT_CONDITIONS.index(...) if ... in
    LIGHT_CONDITIONS else 2`) already had a safe fallback for an unmatched
    value (same existing pattern used for stain_color/wind_band/
    precipitation elsewhere on that page), and `cloud_proxy_for_light_
    condition()` already defaulted unmatched lookups to a neutral 40.0 -
    both were already written defensively enough that the vocabulary swap
    needed zero extra migration code. Trip History's own `light_condition`
    column (renamed "Light condition" -> "Sky condition" for consistency)
    reads the raw string with no revalidation against the current options
    list at all, so old trips just keep showing their real historical
    value under the new column header, exactly as they should - it's a
    factual record of what was true that day, not something that needs to
    match today's vocabulary. Internal identifiers (the `light_condition`
    variable/dict key, `LIGHT_CONDITIONS`/`LIGHT_CONDITION_INFO` module
    names) were deliberately left unchanged - only the on-screen label
    ("Light conditions" -> "Sky conditions") and the option strings/values
    themselves changed, keeping the diff scoped to what the user actually
    asked to change.

    Updated `tests/test_onwater.py`: split the old single "covers every
    condition + spot-checks two options" test into
    `test_cloud_proxy_for_light_condition_covers_every_condition` (still
    just range-checks every current option) and a new
    `test_cloud_proxy_for_light_condition_straddles_the_scoring_thresholds_
    correctly` (explicitly asserts each of the 5 new bands lands on the
    intended side of the 25/60 thresholds, including Partly Cloudy's
    neutral middle) plus a new
    `test_cloud_proxy_for_light_condition_falls_back_to_neutral_for_
    unrecognized_value` (a retired option string, plus blank/None, all
    return the 40.0 fallback rather than raising) - covering the backward-
    compatibility contract explicitly rather than just trusting it by
    inspection. `python3 -m pytest tests/ -q` passes at 243 (241 + 2 new -
    net add of 2 since one old test was split into two, with a case added
    to each half).

    Verified end to end with two scratch `AppTest` runs: `pages/6_Spot_
    Session.py` (mocked weather bundle, inventory, one fake saved spot) -
    confirmed the dropdown now reads "Sky conditions" with options `['Clear
    / Sunny', 'Mostly Clear', 'Partly Cloudy', 'Mostly Cloudy', 'Overcast']`
    (default "Partly Cloudy," the neutral middle), and that selecting
    "Overcast" doesn't raise. `pages/4_Trip_History.py` run against the
    *real* `data/trip_log.csv` (with its 22 old-vocabulary trips, no
    mocking) - confirmed no exception, i.e. the real historical data
    genuinely round-trips through the renamed column without special-
    casing. `data/trip_log.csv`/`data/segment_score_freeze.csv` confirmed
    byte-identical (`md5sum`) before and after both runs. Marked
    Development punch-list item #10 "Done."

73. **Punch-list #11: persist in-progress form entries across a page
    navigation.** Ask (page: "General / whole app"): "If I begin to enter
    data on a page and then leave a page, save the information entered
    that far so if I go back it is already populated with what I entered."
    Audited every page's forms for the actual gap: Spot Session's "Add
    results" section (`log_*` keys) and every other page's forms were
    already keyed and therefore already persisted correctly - the one real
    gap was Spot Session's "Conditions right now" section (water temp,
    Secchi depth, stain color, stirred-up, wind, sky conditions,
    precipitation, start time, forage seen, fish depth), whose widgets had
    never been given an explicit `key=` at all, so a page navigation (or
    even certain reruns) would silently drop whatever had been typed in.

    Keying these widgets collided with punch-list #9's "Time window"
    auto-follow-start_time behavior, which specifically relied on that
    dropdown staying keyless so a plain `index=` recompute could re-drive
    it on every start-time edit. Reconciled by keeping "Time window" keyed
    (so a manual pick survives navigation, matching every other field) but
    only explicitly reseeding its session_state value on the two runs that
    should actually redrive it - entering edit mode for the first time
    (prefers the trip's own saved segment), or start_time changing to a
    value not already reacted to (tracked via a small "last start time
    seen" sentinel key) - leaving every other rerun (including an
    unrelated field edit) untouched. Along the way, switched "Time window"
    from baked, session-date-formatted option strings (e.g. "Dawn (5:52
    AM-7:52 AM)") to raw `SEGMENTS` names plus a `format_func` that
    computes the display string at render time - the raw name is what's
    actually persisted now, so a later session-date edit can never leave a
    stale formatted label that no longer matches any current option (a
    real crash risk the old baked-string design would have had once
    keyed).

    Also root-caused, via careful empirical scratch testing rather than
    guessing (4 throwaway `AppTest` scripts, each isolating one
    hypothesis), a genuine Streamlit gotcha that the first two attempts at
    keying these widgets both ran into: passing a `value=`/`index=`
    argument to a widget *at all* - even one computed by reading back from
    `st.session_state.get(key, default)`, the same pattern this codebase's
    pre-existing `session_date` widget already used - still trips
    Streamlit's "widget was created with a default value but also had its
    value set via the Session State API" warning, specifically on any run
    where the edit-prefill block earlier in the script had just explicitly
    assigned that same key. The clean fix: call
    `st.session_state.setdefault(key, hardcoded_default)` immediately
    before the widget (only ever writes on a key's first-ever creation, so
    it never collides with the prefill block's explicit assignment), then
    construct the widget with `key=` alone - no `value=`/`index=` argument
    at all. Verified warning-free across `number_input`, `selectbox`,
    `checkbox`, and `time_input`, then applied it to all ten "Conditions
    right now" widgets and, opportunistically (same root cause, one-line
    fix, directly adjacent to this entry's own new prefill-block writes),
    to the pre-existing `session_date` widget too - `session_date` predates
    this entry, but as a keyed widget fed by the same prefill block it had
    the identical wart. Left the same class of warning on the "Add
    results" section's `log_*` widgets (e.g. `log_wind_speed_*`)
    deliberately unfixed: those widgets already persist correctly
    (functionally) and predate this entry entirely, the warning is a
    server-console log line only - never shown in the app's own UI - and
    fixing every remaining instance of it project-wide is a separate
    cosmetic cleanup, not part of what this ask requested.

    Scope: kept to Spot Session's "Conditions right now" section (the one
    confirmed real persistence gap) plus the one adjacent `session_date`
    fix above. Other pages' add/edit forms (Lake Map's spot form, Lure
    Inventory's add-lure form, Development's add/edit task form) were
    checked and already persist correctly via existing keyed widgets, so
    nothing there needed changing despite the "General / whole app" scope
    tag on this ask.

    No new pure-logic unit tests - the change is Streamlit
    widget/session_state wiring inside a page script, not testable
    business logic (same reasoning as entry 71's "Time window" work).
    `python3 -m pytest tests/ -q` still passes at 243 (unchanged).

    Verified end to end with a scratch `AppTest` script (not committed)
    against the real `data/lake_spots.csv`/`data/trip_log.csv`: (1) filled
    in water temp, Secchi depth, stirred-up, wind, sky conditions,
    precipitation, and fish depth on a fresh (non-edit) session, then
    constructed a brand-new `AppTest` instance seeded with the same
    `session_state` dict (simulating a real navigate-away-and-back) and
    confirmed every field, and the widgets themselves, still showed the
    entered values; (2) opened a real logged trip in edit mode and
    confirmed its saved conditions still prefill correctly with no
    exception; (3) re-confirmed "Time window" still auto-follows a start-
    time edit (6:30 AM -> Dawn, 1:00 PM -> Midday); (4) re-confirmed a
    manual "Time window" override ("Night") survives an unrelated field
    edit (water temp) afterward. Also confirmed, via the same harness, that
    no Streamlit session-state warning fires on any of the above runs for
    the widgets this entry touched (only the pre-existing, out-of-scope
    `log_wind_speed_*`-class warning remains, on an edit-mode run, for
    fields this entry didn't touch). Ran the standard `AppTest` smoke pass
    across the app entry point and every page reachable in this sandbox
    (`app.py`, `home.py`, Lake Map, Trip History, Lure Inventory, Spot
    Session, Development - the 7-Day Forecast page is unreachable here
    since it calls the live Open-Meteo API with no fallback and this
    sandbox's proxy blocks that host, a pre-existing environment
    limitation unrelated to this entry) - all rendered with no exception.
    `data/trip_log.csv`/`data/segment_score_freeze.csv` confirmed byte-
    identical (`md5sum`) before and after every run. Marked Development
    punch-list item #11 "Done."

74. **Punch-list #12: "Conditions during this lure use" wind field - use the
    same band categories as the session-start reading, and default it
    sensibly.** Ask (page: Spot Session): "In conditions during lure use,
    lets change wind speed to just wind and use the same dropdown
    categories as for the session start. This field should also default to
    whatever I entered in the session conditions for wind. For wind
    direction, set the default to SW."

    Replaced the raw "Wind speed (mph)" `number_input` in "Conditions
    during this lure use" with a `selectbox` over the same
    `WIND_BAND_LABELS` (Glassy/Light Ripple/Moderate Chop/Heavy) as
    "Conditions right now"'s own "Wind" field, and changed "Wind
    direction"'s default from `WIND_DIRECTIONS[8]` ("Variable") to "SW".

    The "default to whatever I entered in the session conditions for wind"
    part needed more than a plain one-time default: this widget (like every
    other widget in "Conditions during this lure use") is instantiated on
    *every* script run regardless of whether its expander is open, which
    includes the very first run of a brand-new session - before the angler
    has touched "Conditions right now" at all. A plain `st.session_state.
    setdefault(key, wind_band_choice)` would lock in "Conditions right
    now"'s own still-unedited default ("Light Ripple") the instant the page
    loads, not whatever the angler actually picks there a moment later.
    Solved with the same auto-follow-until-manually-overridden
    reconciliation already established for "Time window" (punch-list #9/
    #11): a "last cond wind seen" sentinel key tracks the most recent
    "Conditions right now" Wind value this field has already synced from;
    any run where that value has changed re-syncs this field to match,
    while a manual pick here sticks across every other rerun (including
    navigating away and back, same as everything else on this page since
    #11) - only an actual "Conditions right now" Wind change, not just any
    rerun, ever overrides a manual pick. Entering edit mode is handled the
    same way "Time window" handles it: the edit-prefill block seeds this
    field from the trip's own logged value first, and the sync logic below
    just records that run's cond-wind reading as "already seen" rather than
    immediately overwriting the freshly-prefilled value.

    Backward compatibility: this page's own "conditions during lure use"
    section stores its wind reading as a new `wind_band_logged` string key
    now, not the old `wind_speed_mph` float - a real, structural type
    change (float mph -> band string), not just a rename, so the two keys
    can't share a slot the way #10's light_condition vocabulary swap could.
    `data/trip_log.csv` has 26 real trips, 12 of them with a real (nonzero)
    `wind_speed_mph` value logged before this change. The edit-mode prefill
    checks for `wind_band_logged` first (any trip saved after this change),
    then falls back to converting a legacy `wind_speed_mph` reading through
    `core.onwater.wind_band()` (the same mph->band function `wind_band()`
    that `tests/test_onwater.py::test_wind_band_boundaries` already covers)
    so editing an old trip still prefills a sensible band instead of
    silently landing on the generic default. Newly-saved trips simply don't
    write `wind_speed_mph` at all anymore (left absent, not backfilled) -
    Trip History's `FIELD_SPECS` keeps both `("wind_speed_mph", "Wind speed
    (logged)", ...)` (for old rows) and a new `("wind_band_logged", "Wind
    (logged)", str)` (for new ones) side by side, since a given row will
    only ever have one or the other.

    No new pure-logic unit tests - same reasoning as entries 71/73 (this is
    Streamlit widget/session_state wiring in a page script, and the one
    real logic dependency, `wind_band()`'s mph->label conversion, is
    already covered by existing tests). `python3 -m pytest tests/ -q`
    still passes at 243 (unchanged).

    Verified end to end with a scratch `AppTest` script (not committed)
    against the real `data/lake_spots.csv`/`data/trip_log.csv`: (1) a fresh
    session's lure-use "Wind" field matched "Conditions right now"'s Wind
    field, and "Wind direction" defaulted to SW; (2) changing "Conditions
    right now"'s Wind *before* the lure-use field had ever been manually
    touched still updated the lure-use field to match, confirming the
    sync-not-just-setdefault design actually matters in the realistic
    "fill in Conditions right now first" flow; (3) opening the one real
    logged trip with a nonzero legacy `wind_speed_mph` (3.0 mph) in edit
    mode prefilled "Glassy" - confirmed against `wind_band(3.0)["label"]`
    directly, not just "didn't crash"; (4) saved a real new trip via the
    actual "Log this lure" button (not just calling internal functions) and
    confirmed the saved row's `conditions_json` had `wind_band_logged`
    set to the picked value and `wind_speed_mph` absent - `data/
    trip_log.csv` backed up before this step and restored immediately
    after, confirmed byte-identical (`md5sum`) once restored. Also ran the
    standard `AppTest` smoke pass across the app entry point and every page
    reachable in this sandbox (same set as entry 73) - all rendered with no
    exception. Marked Development punch-list item #12 "Done."

75. **Punch-list #13: 3-day historical trend charts for the Home page's
    "Today at a glance" data, with a longer trend for the USACE data since
    it updates less often.** Ask (page: Today/Home): "Can you add a set of
    3 day historical trend charts for the data listed on the Today page?
    For the data from the corp of engineers, lets do a longer trend since
    that is update[d] less frequently."

    Asked two clarifying questions before building, since both had real
    architectural implications: (1) which of the 5 "Today at a glance"
    metrics should get a chart - proposed skipping Moon phase (a
    deterministic cycle, not monitored data, so a 3-day chart of it
    wouldn't show anything meaningful) and charting the other 4; angler
    picked that. (2) How to handle the USACE trend specifically - the live
    USACE report (`core/lake_water_quality.py`) only ever has the CURRENT
    reading, confirmed by re-reading punch-list #69's own exhaustive
    source search (no external API publishes a real historical time series
    for this lake's water temp/DO) - so charting a real trend at all meant
    starting a local archive from today forward rather than fabricating
    history. Proposed exactly that, angler agreed ("Yes, start logging
    from today").

    Investigated what data was actually already on hand before writing any
    fetch code: `core.weather.fetch_forecast()` already requests
    `WATER_TEMP_TREND_PAST_DAYS` (5) days of real past weather alongside
    the forecast (added for punch-list #7's water-temp estimate), and
    `score_day(bundle, d, weights)` already computes and returns
    `overall_score`, `water_temp_f`, AND `pressure_trend_24h` together for
    any date `d` the bundle covers - so 3 of the 4 charted metrics needed
    zero new fetches, just calling the same already-imported `score_day()`
    for `today-2`, `today-1`, `today` instead of just `today`. Lake level
    needed one real change: `core.lake_level.fetch_lake_level()` only ever
    requested `period: "P1D"` and returned the single latest reading -
    added `fetch_lake_level_history(site_id, days=3)` as a separate
    function (not a refactor of the existing, already-tested
    `fetch_lake_level()`, to avoid any regression risk to a working, real-
    money-path live source) requesting a wider `period` and returning
    every reading in the window (typically ~100-300 points at USGS's
    15-60 min telemetry cadence) instead of just the last one.

    New `core/water_quality_log.py`: a small local CSV
    (`data/water_quality_log.csv`) recording every USACE reading this app
    has ever fetched, keyed by `observed_at` so re-fetching the same still-
    current survey (which happens on most reruns, since USACE only
    republishes every 1-2 weeks) is a cheap no-op via `append_if_new()`
    rather than a duplicate row. Same git-committed-CSV persistence
    pattern `data/trip_log.csv` (`core/storage.py`) and `data/
    lure_inventory.csv` (`core/lure_inventory.py`) already established -
    reused `core.storage.commit_and_push()` directly rather than writing
    new git plumbing, exactly as that function's own docstring invites.
    `home.py` calls `append_if_new()` right after its existing
    `get_surface_water_quality()` fetch, and only reaches the git commit
    when a row was actually newly added (i.e. essentially never, except
    the rare rerun where USACE has genuinely republished) - wrapped in the
    same "nice to have, don't block the page" `try/except Exception: pass`
    treatment already used for lake level and water quality on this page,
    so a write failure or git conflict here degrades silently rather than
    surfacing as an error to the angler for a background archival side
    effect they didn't directly trigger. `core/appstate.py` gained two
    thin cached wrappers matching this page's existing convention:
    `get_lake_level_history()` (same 15-min TTL as `get_lake_level()`,
    same live source, just a wider request) and `get_water_quality_log()`
    (a short 60s TTL, since it's a cheap local file read, not a network
    fetch - just enough to avoid re-reading the file on every single
    rerun).

    Chart layout: a "📈 3-day trends" expander (`expanded=True`, directly
    below "Today at a glance") with a 2x2 grid - Activity score, Est. water
    temp, Pressure trend (24h), and Lake level - shown only if there's
    genuinely at least 2 days of forecast trend data or a lake-level
    history to show (so a fully-failed weather+USGS fetch just skips the
    whole expander rather than rendering four empty charts). A separate
    "🌡️ USACE surface reading history" expander (`expanded=False`, since
    it's the least immediately actionable of the two - a slow-moving
    secondary reading, not a decision-driving trend) only appears once
    at least one reading has ever been logged, and shows a plain
    informational caption (not a pointless single-point chart) when
    exactly one reading exists so far - explicitly telling the angler this
    will fill in over the next several weeks rather than looking like a
    broken/empty chart. Both sections use `st.line_chart` (no new
    dependency - `pandas`, already used by `pages/4_Trip_History.py`, is
    the only import needed; this is this app's first use of a chart
    widget anywhere).

    New tests: `tests/test_lake_level.py` gained 4 cases for
    `fetch_lake_level_history()` (requests the wider `period`, returns
    every reading oldest-first - not just the last one, raises on zero
    readings, raises on a network failure - same conventions as the
    existing `fetch_lake_level()` tests it sits next to). New
    `tests/test_water_quality_log.py` (7 cases): creates the log file with
    just a header if missing; a genuinely new reading gets appended and
    returns `True`; the exact same reading again is a no-op and returns
    `False`; a second, genuinely different survey date does get added;
    `parsed_log()` returns real `datetime`/`float` types, not raw CSV
    strings; a corrupted/malformed row is skipped rather than raised on
    (so one bad row can't take down the whole chart); the CSV column order
    matches the `FIELDNAMES` constant. `python3 -m pytest tests/ -q`
    passes at 254 (243 + 11 new).

    Verified end to end with a scratch `AppTest` script (not committed)
    against `home.py`, patching `core.appstate`'s cached accessors directly
    (confirmed this works even though `home.py` does `from core.appstate
    import get_weather_bundle, ...` - AppTest re-execs the whole script
    fresh on every `at.run()`, so that import statement re-resolves
    against whatever's patched on the `core.appstate` module at that
    moment, same as a live rerun would): (1) full success path (a real
    multi-day fake bundle shaped like `tests/test_scoring.py`'s own
    `_fake_bundle()`, fake lake-level history, and a 2-row fake USACE log)
    - both expanders render, no exception; (2) weather fetch failing but
    lake level + USACE still available - "📈 3-day trends" still renders
    (lake level chart only) and doesn't block the rest of the page; (3) an
    empty USACE log - that expander doesn't render at all; (4) exactly one
    USACE log row - shows the "only one survey logged so far" caption, not
    a chart; (5) `append_if_new()` against a real temp file genuinely adds
    a new reading and no-ops on an exact repeat. Ran the standard `AppTest`
    smoke pass across the app entry point and every page reachable in this
    sandbox (same set as entries 73/74, `home.py` itself included with its
    real - unmocked, so all-sources-failing - fetch path) - all rendered
    with no exception, confirming the existing graceful-degradation
    behavior still holds with the new code in place. `data/trip_log.csv`/
    `data/segment_score_freeze.csv` confirmed byte-identical (`md5sum`)
    before and after every run; `data/water_quality_log.csv` (newly
    created this entry, header row only - this sandbox has no outbound
    network access to actually fetch a real USACE reading to seed it, so
    the deployed app will record its own first real row organically)
    likewise confirmed unchanged by any test run, since every test used
    either a temp path or a mocked `append_if_new`. Marked Development
    punch-list item #13 "Done."

76. **Punch-list #14: suggest lures/trailers missing from inventory, with a
    Cabela's shopping link.** Ask (page: Lure Inventory): "On the lure
    inventory page, lets add a section that suggest lures that I don't have
    that fill gaps in types of bass lures and trailers to use for nolin
    lake. Also add a button on these suggestions that would automatically
    add this to my cart in cabelas.com"

    Asked one clarifying question before building, about the "automatically
    add to cart" button specifically: `core/cabelas_lookup.py`'s own
    docstring already documents that Cabela's site search (via Coveo) never
    exposes a stable per-product URL, only `sku`/`brand`/`description`/
    `price`/`image_url`/`categories` - so there's no link to point a button
    at even for a single click-through, let alone genuine cart automation,
    which would also need the angler's own authenticated Cabela's session
    (not available to a server-side Streamlit app) and crosses into this
    session's own safety-rule boundary around purchases/credentials
    regardless. Proposed the honest version instead - a "Search Cabela's"
    link to that item's live search results, the same pattern punch-list
    #8's existing lure-suggestion cards already use - and the angler picked
    that ("Yes, link to Cabela's search results").

    Investigated whether "lures" and "trailers" needed separate gap-tracking
    logic before writing anything: `core.lures.TRAILER_ELIGIBLE_CATEGORIES`
    (`texas_rig_creature`, `weightless_soft_plastic`) turned out to already
    be two ordinary entries in `LURE_PROFILES` itself, not a separate
    taxonomy - so a single gap check across all 20 `LURE_PROFILES` keys
    naturally covers "lure types and trailers" exactly the way the angler's
    own ask grouped them, with nothing extra needed.

    New `core.lures.find_inventory_gaps(inventory)` reuses the module's
    existing `_group_owned_by_category()` helper (already used elsewhere in
    `core/lures.py`) and returns every `LURE_PROFILES` key with no owned
    row, or where every owned row is at quantity 0 - in `LURE_PROFILES`'
    own definition order (a rough most-versatile-to-most-niche curation)
    rather than alphabetical, so the page's gap list reads as a sensible
    priority order. Extracted `core.ui.render_cabelas_suggestions(query,
    found_caption, empty_caption, num_results)` out of the existing
    `render_lure_block`'s "nothing color-matched on hand" branch (punch-list
    #8) as a shared helper - both the original block and the new gap
    section need the identical "look up via the cached
    `core.appstate.get_cabelas_suggestions`, render thumbnail/brand/
    description/price + a Cabela's search link per result, or fall back to
    an empty-state caption" behavior, just with different caption wording
    for their different contexts. `pages/5_Lure_Inventory.py` gained a new
    "🎯 Fill your tackle gaps" expander (above the inventory grid, collapsed
    by default) that calls `find_inventory_gaps()` against the already-
    loaded inventory and renders one bordered card per gap category (name +
    up to 2 Cabela's suggestions via the new shared helper), or a "nothing
    to fill" success message if there are none.

    New tests: `tests/test_lures.py` gained 7 cases for
    `find_inventory_gaps()` - empty inventory returns all 20 categories;
    owned categories are excluded; a quantity-0 row still counts as a gap;
    unrecognized `category` values are ignored; the two trailer-eligible
    categories are included when unowned (confirming no separate trailer
    logic is needed); a fully-stocked inventory (one of everything) returns
    no gaps; and the returned order matches `LURE_PROFILES`' own definition
    order. `python3 -m pytest tests/ -q` passes at 261 (254 + 7 new), with
    `data/trip_log.csv`/`data/segment_score_freeze.csv` confirmed
    byte-identical (`md5sum`) before and after.

    Verified end to end with a scratch `AppTest` script (not committed)
    against `pages/5_Lure_Inventory.py`, mocking `core.appstate.
    get_inventory` (works because the page re-execs its own top-level
    imports fresh every `at.run()`) and `core.ui.get_cabelas_suggestions`
    (has to be patched at `core.ui`, not `core.appstate` - `core/ui.py` is
    an ordinary cached-import module, not re-exec'd per run, so patching
    where the name is actually bound in `core.ui`'s own namespace is what's
    needed to reach `render_cabelas_suggestions`'s internal call). Real
    synthetic inventory rows were built via `core.lure_inventory.
    LureItem(...).to_row()` rather than hand-built dicts, after hand-built
    fixtures twice raised `KeyError` (`price`, then `item_id`) from
    pre-existing, unrelated inventory-grid code further down the page that
    reads every CSV field on every row - a reminder that real rows always
    carry the full `FIELDNAMES` schema and test fixtures should build
    through the real dataclass rather than guessing which fields matter.
    Four scenarios covered: (1) empty inventory shows all 20 gaps with
    mocked suggestion cards, no exception; (2) a fully-stocked inventory
    shows the "nothing to fill" success message; (3) a partial inventory
    (one owned category) shows only the genuinely-unowned categories as gap
    cards - checked specifically for the bolded `**Football Jig**`
    gap-header form, since the inventory grid's own (pre-existing, unrelated)
    `st.write(row["description"])` for the owned row coincidentally also
    renders "Football Jig" as plain unbolded markdown; (4) a gap category
    with no Cabela's matches falls back to the plain empty-state caption
    instead of raising. Also ran the standard `AppTest` smoke pass across
    the app entry point and every page reachable in this sandbox (same set
    as entries 73-75) - all rendered with no exception.
    `data/trip_log.csv`/`data/segment_score_freeze.csv`/
    `data/water_quality_log.csv`/`data/lure_inventory.csv` confirmed
    byte-identical (`md5sum`) before and after every run in this entry.
    Marked Development punch-list item #14 "Done."

77. **Punch-list #15: 14-day trend charts on the Home page, and get the
    USACE oxygen/water-temp trend actually populated.** Ask (page: Today/
    Home): "For the today page, lets make the trend charts go out 14 days.
    Also, I thought we added the oxygen saturation and temperature trends
    from the government site. Can we get those added?"

    Two separate pieces. First, extended the four existing "Today at a
    glance" trend charts (activity score, est. water temp, pressure trend,
    lake level - added in punch-list #13) from 3 days to 14. Added a new
    `core.weather.HOME_TREND_CHART_PAST_DAYS = 14`, kept deliberately
    separate from the existing `WATER_TEMP_TREND_PAST_DAYS = 5` rather than
    just bumping that constant - `WATER_TEMP_TREND_PAST_DAYS` is a tuned
    model parameter (`estimate_water_temp_f()`'s own trailing-average
    window, validated against real Spot Session readings per punch-list
    #7), not a chart-length knob, and conflating the two would mean any
    future chart-length change quietly retunes the water-temp estimate
    too. `fetch_forecast()`'s `past_days` request now asks Open-Meteo for
    `max()` of the two (confirmed via their docs that `past_days` supports
    up to 92, so 14 is well inside range), so both the model and the chart
    get enough real history from one fetch. `home.py`'s trend-day range
    became `range(HOME_TREND_CHART_PAST_DAYS - 1, -1, -1)` (was the
    literal `(2, 1, 0)`), `get_lake_level_history(days=...)` now passes the
    same constant instead of a literal `3`, and the expander title/caption
    text now read "14-day" throughout instead of a mix of hardcoded "3-day"
    text.

    Second, the USACE oxygen-saturation/water-temp trend: investigated and
    found it actually WAS already built, in punch-list #13 - the "🌡️ USACE
    surface reading history" expander - but `data/water_quality_log.csv`
    had zero rows logged (just the header), so per that section's own `if
    wq_log:` guard, nothing rendered at all on Home, which is why it looked
    unbuilt. Root cause: this sandbox has no network path to USACE's report
    page (`https://www.lrl-wc.usace.army.mil/reports/wq/NRR.html`) - a
    direct `requests.get()` hit a proxy 403, and even the WebFetch tool
    failed on that same domain's `robots.txt` with an SSL certificate
    verification error - so nothing running in this session (including the
    Streamlit Cloud deploy's own periodic fetch, if it's hit the same kind
    of restriction, though that's unconfirmed) had ever successfully
    completed the fetch-and-log step yet. Worked around this by reaching
    the live page through the angler's own connected Chrome browser
    (`mcp__claude-in-chrome__navigate` + `get_page_text`) instead, which
    isn't subject to this sandbox's network restrictions. That confirmed
    two things directly against the real, current page: (1) the only
    reading it has ever published is the same Aug 6, 2026, 2:00 PM "Dam
    Site" 0 ft survey already referenced as the hand-verification example
    in `core/lake_water_quality.py`'s own docstring (30.3°C, 10.66 mg/l DO)
    - so this is genuinely the CURRENT reading, not stale test data, and
    (2) the report page itself still only ever shows one survey at a time,
    no history section or archive link anywhere on it - reconfirming
    punch-list #69's exhaustive search that no real historical time series
    exists for this station from any source. Ran the real, extracted
    values (temp_c=30.3, do_mg_l=10.66, observed_at=2026-08-06T14:00)
    through the app's own actual conversion/saturation-formula code
    (`core.lake_water_quality._do_saturation_concentration_mg_l()`) rather
    than computing by hand, then called the real `core.water_quality_log.
    append_if_new()` to add it - so the seeded row is exactly what the
    app's own fetch-and-log pipeline would have produced had it been able
    to reach the page itself, not a fabricated or manually-typed value.
    `data/water_quality_log.csv` now has one real row (86.5°F, 10.66 mg/l
    DO, 146.9% saturation, 8/6/2026 2:00 PM). Nothing more than this one
    reading is available anywhere to seed - by design (see
    `core/water_quality_log.py`'s own docstring), the trend will keep
    filling in only as USACE publishes new surveys (roughly every 1-2
    weeks); a genuine second point still needs to wait for that, or for a
    future session to re-check the live page the same way. With one row,
    the expander now renders the "only one USACE survey logged so far
    (8/06/2026)" message (previously the whole section didn't show at
    all); it'll switch over to the actual two-line trend chart once a
    second real survey is logged.

    Updated `tests/test_weather.py`'s
    `test_fetch_forecast_requests_past_days_for_the_water_temp_trend` to
    assert `past_days == max(WATER_TEMP_TREND_PAST_DAYS,
    HOME_TREND_CHART_PAST_DAYS)` instead of the old hardcoded
    `WATER_TEMP_TREND_PAST_DAYS`, plus an explicit assertion that
    `HOME_TREND_CHART_PAST_DAYS >= WATER_TEMP_TREND_PAST_DAYS` so a future
    reader doesn't have to re-derive which constant currently wins.
    `python3 -m pytest tests/ -q` passes at 261 (no net-new tests needed
    beyond that one update - `find_inventory_gaps`/#14's tests etc. are
    unaffected). Verified end to end with a scratch `AppTest` script (not
    committed) against `home.py`, with a fresh fake `WeatherBundle`
    covering a real 14-day-plus-forecast window (built fresh for this
    entry rather than reusing `tests/test_scoring.py`'s `_fake_bundle()`
    helpers, since those are intentionally sized around
    `WATER_TEMP_TREND_PAST_DAYS` (5), not the new 14-day window) and 14
    fake `LakeLevel` readings: (1) confirms the expander's title reads
    "📈 14-day trends" and both it and the USACE expander render with no
    exception; (2) mocking `core.appstate.get_water_quality_log` to return
    exactly the real seeded row confirms the single-reading caption
    (including the "8/06/2026" date) renders correctly; (3) mocking a
    second, different reading alongside it confirms the two-point case
    renders both the water-temp and DO charts with no exception. Also ran
    the standard `AppTest` smoke pass across the app entry point and every
    page reachable in this sandbox (same set as entries 73-76) - all
    rendered with no exception. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/lure_inventory.csv` confirmed
    byte-identical (`md5sum`) before and after every run in this entry;
    `data/water_quality_log.csv` confirmed unchanged by every *test* run
    (all mocked), separate from the one deliberate real append described
    above. Logged this ask as punch-list item #15 (it arrived as a direct
    follow-up request rather than through the Development page UI) and
    marked it "Done."

78. **Punch-list #16: put the USACE reading on the same metrics line as
    water temp/lake level, and shrink the font so it fits.** Ask (page:
    Today/Home): after seeing a live screenshot of the deployed Home page
    showing a red "Couldn't fetch live weather data right now: 429 Client
    Error: Too Many Requests" error from Open-Meteo, the angler said "there
    is no USACE data either. If the data was there, I want the latest
    reading to be up on the same line as the water temp, lake level, etc.
    Also note that the font on these readings needs to be smaller so it
    fits across the page."

    First, explained the 429 itself (not a bug from #15's changes): Open-
    Meteo's free tier is IP-rate-limited (600 calls/min, 5,000/hour,
    10,000/day - confirmed via their own pricing page), Streamlit Community
    Cloud apps commonly share outbound IPs with many other hosted apps, and
    this app's own weather fetch is cached for an hour so it alone comes
    nowhere close to those thresholds - most likely either shared-IP
    congestion from unrelated apps, or a burst right after the redeploy
    that shipped #15 (a restart clears Streamlit's in-memory cache).

    But investigating "there is no USACE data either" found a real bug, not
    just a transient 429: the entire "Today at a glance" block - all 4
    weather-derived metrics AND the lake-level tile AND the USACE caption -
    lived inside `if bundle is not None: try: ...`, even though `lake_level`
    and `water_quality` are both fetched independently, several lines
    earlier, in their own separate try/excepts. So a weather-only failure
    (like the 429 just seen) hid lake level and the USACE reading too, even
    on a rerun where both of those fetched perfectly fine on their own -
    exactly what the angler was seeing.

    Fixed by decoupling: `today = score_day(...)` is still only computed
    when `bundle` is available, but the metrics-row rendering now triggers
    on `if today or lake_level or water_quality:` and builds a
    `st.columns(n_cols)` row sized to however many of the (up to 6) tiles
    actually have data - each source contributes its own tile(s)
    independently instead of the whole row living or dying with the
    weather fetch. The "Best window today" info box, warnings, and
    calibration caption stay gated on `today` specifically (those
    genuinely do need the scored forecast). The USACE reading moved from a
    separate `st.caption()` below the row into its own `st.metric("USACE
    water temp", ...)` tile inside that same row, with dissolved-oxygen
    mg/l, saturation %, and the survey date moved into the tile's `help=`
    tooltip (hover/tap) rather than a full sentence of caption text below -
    both because that's what "same line" means literally, and because a
    6-tile row has no room left for a paragraph underneath each one.

    For the font-size ask, added `core.ui.inject_compact_metric_css
    (container_key, value_rem, label_rem)` - wraps `st.metric()`'s
    `stMetricValue`/`stMetricLabel`/`stMetricDelta` CSS testids in a
    font-size override, scoped to one `st.container(key=...)` wrapper
    (Streamlit renders that as a `st-key-<key>` class - confirmed against
    the installed Streamlit 1.61.1's own `elements/layouts.py` docstrings)
    rather than `inject_mobile_css()`'s existing site-wide `:nth-child(3)`
    column-count selector, which would have also shrunk unrelated wide rows
    on other pages (e.g. the 7-Day Forecast's per-day and time-of-day
    rows). home.py's "Today at a glance" row is now wrapped in
    `st.container(key="today_at_a_glance_metrics")` with
    `inject_compact_metric_css("today_at_a_glance_metrics")` called inside
    it, so only this one row's metric font shrinks (value ~1.15rem, label/
    delta ~0.72rem, down from Streamlit's default ~2.25rem/~0.875rem) -
    six tiles now fit across a normal desktop width without wrapping.

    No new pytest-level tests needed (this is page-layout/CSS, not new
    core logic), but ran a scratch `AppTest` script (not committed) against
    `home.py` covering exactly the bug and the fix: (1) everything
    succeeds - confirms all 6 metric tiles render in the expected order
    (`Activity score, Est. water temp, Moon phase, Pressure trend (24h),
    Lake level, USACE water temp`); (2) weather fetch raises (simulating
    the 429) but lake level and USACE both succeed - confirms "Today at a
    glance" STILL renders, with exactly `[Lake level, USACE water temp]`
    as its only two tiles, alongside the existing weather `st.error()` -
    this is the actual regression case, and it now passes; (3) everything
    fails - confirms no exception and no "Today at a glance" subheader at
    all (the `if today or lake_level or water_quality:` guard correctly
    suppresses an empty section rather than rendering an empty row).
    `python3 -m pytest tests/ -q` still passes at 261 (unchanged - no test
    file touched this entry). Also ran the standard `AppTest` smoke pass
    across the app entry point and every page reachable in this sandbox
    (same set as entries 73-77) - all rendered with no exception.
    `data/trip_log.csv`/`data/segment_score_freeze.csv`/
    `data/water_quality_log.csv`/`data/lure_inventory.csv` confirmed
    byte-identical (`md5sum`) before and after every run. Logged this ask
    as punch-list item #16 and marked it "Done."

79. **Punch-list #17: the USACE tile still wasn't showing - fall back to
    the last logged reading when the live fetch fails.** After #16 shipped,
    the angler sent a live screenshot of the deployed Home page: weather
    had recovered (no more 429), "Today at a glance" now correctly showed
    5 tiles including Lake level, but there was still no "USACE water
    temp" tile - "The USACE data is still not showing with the other
    data."

    #16's fix was actually working correctly (the tile renders whenever
    `water_quality` is truthy, independent of the weather bundle) - the
    real problem is that `get_surface_water_quality()`'s LIVE fetch has
    apparently been failing on the deployed app the same way it fails from
    this dev sandbox: entry 76 already found this sandbox gets a proxy 403
    AND a WebFetch SSL error against `lrl-wc.usace.army.mil`, and entry 77
    already suspected (but couldn't confirm) production might be hitting
    something similar. This screenshot is that confirmation - a run where
    weather clearly succeeded still had no USACE tile, meaning
    `water_quality` was None, meaning the live USACE fetch itself failed
    on that run.

    Rather than keep depending on a fresh successful fetch every single
    page load - USACE only republishes this survey every 1-2 weeks
    anyway, so "fresh this run" was never really the point, and the one
    real reading already sitting in `data/water_quality_log.csv` (seeded
    in entry 76) is still perfectly valid to show - added a fallback in
    home.py: when `get_surface_water_quality()` fails, look at
    `get_water_quality_log()`'s last row and build a `SurfaceWaterQuality`
    from it (`SurfaceWaterQuality(**logged[-1])` - `parsed_log()`'s dict
    keys line up exactly with the dataclass's field names) to display
    instead. A new `is_live_reading` flag tracks which case is active
    purely for the tile's own honesty: the help tooltip already always
    states the real survey date, but now it also says "USACE's own site
    couldn't be reached just now, so this is the last reading logged
    locally" specifically when showing the fallback, so the tile never
    reads as more current than it actually is. The `append_if_new()`/
    commit-back logic right above this is untouched and still only ever
    acts on a genuinely fresh fetch - the fallback value is display-only,
    never re-logged (avoids any risk of the same reading being written
    twice or the "only log a survey we haven't seen before" logic getting
    confused).

    Ran a scratch `AppTest` script (not committed) covering exactly this:
    (1) live fetch fails, a real reading is logged - "USACE water temp"
    tile still renders with the logged value (86.5°F) and the help text
    contains "couldn't be reached just now"; (2) live fetch succeeds -
    tile shows the fresh value instead, with no fallback note in the help
    text; (3) live fetch fails AND nothing is logged yet - no tile, no
    exception (matches the very first deploy's state, before entry 76
    seeded anything). `python3 -m pytest tests/ -q` still passes at 261
    (no core logic changed, same as entry 78 - this is page code only).
    Also ran the standard `AppTest` smoke pass across the app entry point
    and every page reachable in this sandbox (same set as entries 73-78) -
    all rendered with no exception. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/water_quality_log.csv`/
    `data/lure_inventory.csv` confirmed byte-identical (`md5sum`) before
    and after every run. Logged this ask as punch-list item #17 and
    marked it "Done."

80. **Punch-list #18: show DO saturation on the metrics line too, and make
    the "USACE surface reading history" section show something even with
    one point.** After confirming #17's fix worked (a fresh screenshot
    showed "USACE water temp" now on the "Today at a glance" line
    alongside the other five tiles), the angler said: "The USACE water
    temp is there but not the oxygen saturation data. Can we also show
    that and show it in the USACE charts that currently show nothing."
    That second screenshot showed the "🌡️ USACE surface reading history"
    expander open, displaying only the "Only one USACE survey logged so
    far (8/06/2026)..." caption - no numbers, no chart - which is
    technically correct (a "chart" of one point is meaningless) but does
    read as showing nothing at all.

    Two changes, same spirit as the "put it on the line, don't bury it in
    a caption" push from #16. First, added a second "Today at a glance"
    tile, "USACE DO saturation" (`f"{do_saturation_pct:.0f}%"`), next to
    the existing "USACE water temp" tile - both now read straight off
    `water_quality_display` (the #17 fallback-aware value) and share a
    `survey_note` string built once for the survey-date/live-vs-fallback
    framing, referenced from both tiles' `help=` text so the two don't
    duplicate that explanation differently. `n_cols` in the metrics row
    is now `... + (2 if water_quality_display else 0)` - up to 7 tiles
    total. Second, reworked the "USACE surface reading history" expander's
    single-point branch: instead of only a caption, it now also renders 3
    `st.metric()` tiles (surface water temp, dissolved oxygen mg/l, DO
    saturation %) reading directly off `wq_log[0]`, so the one real
    reading on hand is actually visible there, not just referenced by
    date. The multi-point branch gained a third `st.columns()`/
    `line_chart()` pair for `do_saturation_pct` (previously only water
    temp and DO mg/l were charted there, even though DO saturation was the
    number the angler had actually asked about back in the original #15
    USACE ask) - `st.columns(3)` instead of `st.columns(2)` in both
    branches now.

    Ran a scratch `AppTest` script (not committed) covering all three
    cases: (1) a fresh USACE reading -> both "USACE water temp" and
    "USACE DO saturation" tiles render on "Today at a glance", with the DO
    tile's value confirmed as "147%" for the same Aug 6 reading used
    throughout this session; (2) a single-row USACE log -> the history
    expander's three metric labels ("Surface water temp", "Dissolved
    oxygen", "DO saturation") are all present, confirming real numbers
    show instead of just the caption; (3) a two-row USACE log -> all three
    chart captions ("Surface water temp (°F)", "Dissolved oxygen (mg/l)",
    "DO saturation (%)") are present, confirming the third chart renders
    alongside the original two. `python3 -m pytest tests/ -q` still passes
    at 261 (page code only, no core logic changed, same as entries 78-79).
    Also ran the standard `AppTest` smoke pass across the app entry point
    and every page reachable in this sandbox (same set as entries 73-79) -
    all rendered with no exception. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/water_quality_log.csv`/
    `data/lure_inventory.csv` confirmed byte-identical (`md5sum`) before
    and after every run. Logged this ask as punch-list item #18 and marked
    it "Done."

81. **Punch-list #19: drop the USACE water-temp tile for dissolved oxygen,
    merge the USACE charts into the same trends dropdown, chart from the
    first point.** Ask (page: Today/Home): "lets remove the USACE water
    temp from the top and add the USACE dissolved oxygen. For the USACE
    charts, lets show those with even just the one data point and not as
    a separate dropdown of USACE charts.... just with the other charts."

    Two changes, both continuing the same "put it on the line, don't bury
    it in its own corner" direction from #16-#18. First, on "Today at a
    glance": removed the "USACE water temp" tile (the "Est. water temp"
    tile already covers water temp on this row, and USACE's own real
    surface temp is still charted below, just no longer tiled up top) and
    added "USACE dissolved oxygen" (`f"{do_mg_l:g} mg/l"`) alongside the
    existing "USACE DO saturation" tile - both now the mg/l and %
    readings the angler actually wanted visible, sharing the same
    `survey_note` help-text framing built in #18. `n_cols`'s `water_quality_
    display` term stays `2` (still 2 USACE tiles, just a different pair).

    Second, and the bigger structural change: removed the separate "🌡️
    USACE surface reading history" expander entirely and folded its three
    series (surface water temp, dissolved oxygen mg/l, DO saturation %)
    into the same "N-day trends" expander as the weather/lake-level
    charts, so there's one dropdown for every trend on the page instead of
    two. Rebuilt that section around a `trend_items` list of `(caption,
    pd.Series)` pairs - built conditionally per source (weather-derived
    trio only if `len(trend_forecasts) >= 2`, lake level only if
    `lake_level_history`, the three USACE series only if `wq_log`) - then
    rendered `3` at a time via `st.columns(len(row_items))` inside one
    loop, rather than the old fixed 2x2 grid plus a separate fixed-3-
    column USACE block. USACE's own index (`wq_idx`, however many real
    surveys have been logged) is deliberately its own x-axis, not forced
    onto the 14-day weather window - a `pd.Series` with a different index
    length/labels renders in `st.line_chart()` exactly like any of the
    others, so this needed no special-casing to sit in the same grid.

    Also dropped #18's single-point special case (3 `st.metric()` tiles
    instead of a chart, added last entry specifically because "a chart of
    one point is meaningless") per this ask's explicit "show those with
    even just the one data point" - `st.line_chart()` on a length-1
    `pd.Series` just renders a single dot, which turns out to read
    perfectly fine now that it's sitting alongside the other, fuller
    charts rather than alone in its own section looking sparse. The old
    "Only one USACE survey logged so far..." caption is gone too; the
    merged section's closing caption now just states how many USACE
    readings are logged and since when, unconditionally.

    Ran a scratch `AppTest` script (not committed) covering: (1) a single
    logged USACE reading - confirms "USACE water temp" is no longer among
    the metric labels, "USACE dissolved oxygen" and "USACE DO saturation"
    both are, there's exactly one expander with "day trends" in its label
    (no separate USACE expander), all three USACE chart captions appear
    inside it, and the old "Only one USACE survey logged" text is gone;
    (2) two logged readings - confirms the merge and charting still hold
    with more data. `python3 -m pytest tests/ -q` still passes at 261
    (page code only, same as entries 78-80). Also ran the standard
    `AppTest` smoke pass across the app entry point and every page
    reachable in this sandbox (same set as entries 73-80) - all rendered
    with no exception. `data/trip_log.csv`/`data/segment_score_freeze.csv`/
    `data/water_quality_log.csv`/`data/lure_inventory.csv` confirmed
    byte-identical (`md5sum`) before and after every run. Logged this ask
    as punch-list item #19 and marked it "Done."

82. **Punch-list #20: fix the Y-axis scale on the temperature charts to
    45-95°F.** Ask (page: Today/Home): "can you change the scale on the
    temp charts to be between 45 degrees and 95 degrees."

    `st.line_chart()` (used for every chart in the merged "14-day trends"
    expander from entry 81) auto-scales its Y axis to the data's own min/
    max, with no parameter to pin it - confirmed by inspecting the
    installed Streamlit 1.61.1's actual `line_chart()` signature. A small
    real swing (a degree or two) then fills the whole chart height and
    reads as far more dramatic than it is - exactly what a fixed 45-95°F
    band (the real range Nolin Lake's surface plausibly sees across a
    season) fixes. Since `st.line_chart()` has no such parameter, added
    `core.ui.render_line_chart(col, series, y_domain=None)`: with
    `y_domain=None` it's exactly the old `col.line_chart(series)`
    (unchanged for every non-temperature chart); with `y_domain=(lo, hi)`
    it builds a raw `alt.Chart(...).mark_line().encode(x=..., y=alt.Y(...,
    scale=alt.Scale(domain=[lo, hi])))` and calls `col.altair_chart()`
    instead - the documented Streamlit escape hatch for anything
    `st.line_chart()` doesn't expose. `x=alt.X("x", sort=None, ...)`
    matters here specifically: Vega-Lite's default sort for a nominal
    (string) field is alphabetical by value, which would scramble this
    app's "Mon 8/17"/"Tue 8/18"-style day labels; `sort=None` (which
    serializes as an explicit `"sort": null` in the Vega-Lite spec, not
    just an absent key - confirmed by comparing both dict outputs
    directly) tells Vega-Lite to keep the data's own point order instead.

    `home.py` gained `TEMP_CHART_Y_DOMAIN = (45, 95)` and now builds each
    `trend_items` entry as a 3-tuple `(caption, series, y_domain)` instead
    of 2 - `y_domain` is `TEMP_CHART_Y_DOMAIN` for exactly the two °F
    series ("Est. water temp (°F)", "USACE surface water temp (°F)") and
    `None` for everything else (activity score, pressure trend, lake
    level, USACE dissolved oxygen mg/l, USACE DO saturation %) - so only
    the two temperature charts get the fixed scale; every other chart on
    the page keeps auto-scaling exactly as before.

    This is genuinely new core logic (not just page layout, unlike entries
    78-81's home.py-only changes), so it got real committed unit tests
    this time instead of only a scratch `AppTest` script - new
    `tests/test_ui.py` (4 cases, using a tiny `_FakeCol` stand-in that
    just records what gets called on it, no Streamlit runtime needed):
    `y_domain=None` calls `col.line_chart(series)` with the exact Series
    and never touches `altair_chart`; `y_domain=(45, 95)` calls
    `col.altair_chart()` instead, and the resulting chart's own
    `.to_dict()` has `encoding.y.scale.domain == [45, 95]` and
    `width == "stretch"`; a second, different domain `(0, 10)` proves nothing's
    hardcoded inside the function itself; and the `x` encoding's `sort`
    key is confirmed present with value `None` (not just absent) via
    `.to_dict()`, directly verifying the alphabetical-sort bug this
    guards against. `python3 -m pytest tests/ -q` now passes at 265 (261 +
    4 new). Also ran a scratch `AppTest` script (not committed) against
    the real `home.py` with both temperature series present, confirming
    the page renders with no exception and both "Est. water temp (°F)"/
    "USACE surface water temp (°F)" captions appear (the Altair spec
    correctness itself is what `tests/test_ui.py` checks - AppTest has no
    accessor to introspect a rendered Altair chart's own encoding, so this
    scratch run's job is purely "does wiring it into the real page still
    work end to end"). Ran the standard `AppTest` smoke pass across the
    app entry point and every page reachable in this sandbox (same set as
    entries 73-81) - all rendered with no exception. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/water_quality_log.csv`/
    `data/lure_inventory.csv` confirmed byte-identical (`md5sum`) before
    and after every run. Logged this ask as punch-list item #20 and
    marked it "Done."

83. **Punch-list #21: "Not in your inventory" Cabela's suggestions were
    showing nothing at all, on both the 7-Day Forecast and Spot Session
    pages.** Ask (page: 7-Day Forecast, with a follow-up covering Spot
    Session too): "For lure suggestions not in my lure inventory we were
    supposed to go out to Cabelas.com to give 2 top choices with pictures
    and all the other information that I have for lures in my inventory,
    but nothing is showing up. Can you correct this?" / "This is also the
    case for spot session lure suggestions. Please correct this as well."

    Confirmed the page-to-render wiring itself was correct - both pages
    already go through the same shared call chain
    (`render_lure_recommendation` -> `render_lure_block` ->
    `core.ui.render_cabelas_suggestions` -> `core.appstate.
    get_cabelas_suggestions` -> `core.cabelas_lookup.search_lures`), so a
    single root cause and a single fix in the shared `core/ui.py` helper
    covers both surfaces.

    Root-caused with real evidence rather than guessing, the same way the
    USACE data gap (entry 79) was diagnosed: this sandbox's own network
    can't reach `www.cabelas.com` at all (proxy `403 Forbidden`, same
    pattern as USACE/Open-Meteo earlier this session), so I used
    `mcp__claude-in-chrome__javascript_tool` to call both Cabela's/Coveo
    endpoints directly from the angler's own real Chrome browser session
    (bypassing this sandbox's restriction): the token endpoint
    (`https://www.cabelas.com/api/v2/10651/prod/coveo/getCoveoToken`)
    returned a real token in exactly the shape `_get_token()` expects, and
    POSTing that token to Coveo's search API
    (`https://platform.cloud.coveo.com/rest/search/v2`) with the exact
    same request shape `search_lures()` sends back real product data (2
    real BOOYAH squarebill crankbaits, brand/price/SKU all present) - so
    the integration itself, and this app's code, are not broken.

    Then checked the *live deployed app* directly (browsing to
    `https://voskuil-fishin-magician.streamlit.app/`, navigating past its
    wrapper iframe to the app's own inner frame URL so the real page DOM -
    not just the Streamlit Cloud chrome - was reachable for scrolling/
    reading) and reproduced the actual bug: on the 7-Day Forecast page, a
    "Walking Topwater (Spook-style)" lure block not in the angler's
    inventory showed only the plain "🛒 Not in your inventory yet - worth
    picking one up for this presentation." caption, with no product cards,
    no pictures, and (before this fix) no link at all - confirming the
    live product search genuinely returns nothing when called from this
    app's own server, even though the identical endpoints work fine from a
    real browser on the same network. Same conclusion as the USACE
    investigation: a server-side-only restriction (most likely Coveo/
    Akamai bot-mitigation fingerprinting Streamlit Community Cloud's
    outbound requests at the TLS/network level, which a `User-Agent`
    header alone can't spoof around), not a bug in this app's own logic.

    Implementation: two changes.
    - `core/ui.py`'s `render_cabelas_suggestions()` now always renders a
      "Search Cabela's" link (via the existing pure, network-free
      `core.cabelas_lookup.search_page_url()`) even in the empty/failed-
      lookup fallback path, not just when live products were found. This
      directly fixes "nothing is showing up" - the angler always gets a
      genuinely useful, always-working link to Cabela's own search results
      for that lure category, independent of whether the live Coveo
      product lookup happens to succeed on any given page load. The
      "found products" path (cards with photos/brand/price) is unchanged.
    - `core/cabelas_lookup.py`'s `_BROWSER_HEADERS` gained `Accept`,
      `Accept-Language`, `Referer`, and `Origin` headers a real browser tab
      always sends (previously only `User-Agent`) - a best-effort
      improvement in case header content (not just TLS fingerprint) is
      part of what's getting these requests filtered from Streamlit
      Cloud's servers. Documented plainly in the module's own comments
      that this may not be the actual fix if the real blocker is TLS/
      network-level fingerprinting rather than header content - hence why
      the `core/ui.py` fallback-link fix above doesn't depend on this
      working.

    No test coverage previously existed for `render_cabelas_suggestions()`
    at all (confirmed via `grep`) - added scratch (uncommitted) `AppTest`-
    based verification for both paths: the empty-lookup fallback now shows
    the expected caption *and* a `[Search Cabela's](https://www.cabelas.
    com/search?q=Walking+Topwater+%28Spook-style%29)` markdown link built
    from the lure block's own name; the found-suggestions path still shows
    exactly 2 product cards each with their own correctly-built per-product
    search link, unchanged from before. `python3 -m pytest tests/ -q`
    still passes at 265 (this fix didn't add new committed test coverage
    itself, matching this session's own precedent that only genuinely new
    core logic like entry 82's `render_line_chart()` gets committed unit
    tests - this change is presentation-layer wiring, verified the same
    way every other `core.ui` rendering helper in this session has been:
    scratch `AppTest` runs). Ran the standard `AppTest` smoke pass across
    the app entry point and every page reachable in this sandbox (same set
    as entries 73-82) - all rendered with no exception. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/water_quality_log.csv`/
    `data/lure_inventory.csv` confirmed byte-identical (`md5sum`) before
    and after every run; scratch scripts deleted afterward. Logged this ask
    as punch-list item #21 and marked it "Done."

84. **Punch-list #22: try to make the live Cabela's lookup actually work in
    production, and add a curated fallback as a safety net either way.**
    Ask (page: 7-Day Forecast/Spot Session, direct follow-up to entry 83):
    "Everything now comes up as search cabelas....can the app actually
    search cabelas automatically and populate with the 2 best options
    available?" - after presenting two options (try a TLS-impersonation
    fix server-side, and/or build a curated fallback cache), the angler
    said: "try option a and set up B as a safety net."

    First ruled out a third option before starting: could this app fetch
    Cabela's/Coveo directly from the *browser* (client-side JS embedded in
    the page) instead of server-side, sidestepping the block entirely?
    Tested live via `mcp__claude-in-chrome__javascript_tool` - a `fetch()`
    to Cabela's token endpoint from this app's own deployed domain
    (`https://voskuil-fishin-magician.streamlit.app`) failed outright
    ("Failed to fetch"), while the identical call from `cabelas.com`
    itself (same technique used in entry 83) succeeded - confirming
    Cabela's endpoint is CORS-restricted to their own origin, so a
    client-side call from this app's own page can never work regardless of
    what's blocking the server-side path. Ruled out, moved on.

    **Option A (try to fix the live lookup):** the leading theory from
    entry 83 was that Cabela's/Coveo's bot-mitigation checks the actual
    TLS handshake, not just the `User-Agent` header - a plain `requests`/
    urllib3 connection has a completely different TLS fingerprint from a
    real Chrome browser no matter what headers are set. Installed
    `curl_cffi` (a `requests`-API-compatible HTTP client backed by a
    patched libcurl that can impersonate real browsers' TLS/JA3
    fingerprints) and swapped it in for both of `core/cabelas_lookup.py`'s
    live calls (`_get_token()`'s GET, `search_lures()`'s POST), passing
    `impersonate="chrome124"` (matching the Chrome version already claimed
    in `_BROWSER_HEADERS`' User-Agent). curl_cffi's `get`/`post` functions
    are close enough to plain `requests`' that the rest of the module's
    logic (`.raise_for_status()`, `.json()`, try/except fails-soft
    contract) needed no changes. Added `IMPERSONATE_BROWSER = "chrome124"`
    as a named constant and a dedicated test
    (`test_search_lures_impersonates_a_real_browser_tls_fingerprint`)
    asserting both calls actually pass that kwarg through - the point of
    this change, not just an implementation detail. Existing tests'
    `_fake_get`/`_fake_post` stand-ins needed `**kwargs` added to their
    signatures (they were failing silently before this was caught - a
    `TypeError` for the new unexpected `impersonate` kwarg was getting
    swallowed by `search_lures()`'s own broad `except Exception: return
    []`, so the test failure showed up as "0 results" rather than an
    obvious error). Documented plainly in the module's own docstring that
    this is still not a guaranteed fix - if Cabela's/Coveo is blocking by
    IP/network reputation rather than fingerprint, no amount of TLS or
    header spoofing gets around that, which is exactly why option B exists
    regardless of whether this works. This sandbox's own network can't
    reach `cabelas.com` at all (confirmed since entry 83), so whether this
    actually fixes production can only be confirmed by the angler checking
    the live app after this deploys.

    **Option B (curated fallback cache, the safety net):** `LureBlock.name`
    (what `core.ui.render_cabelas_suggestions()` is ever queried with, for
    this specific punch-list #8 use case) only ever comes from
    `core.lures.LURE_PROFILES`' 20 fixed `"name"` values - a small, closed
    vocabulary, not arbitrary text (confirmed via `grep`) - which makes a
    pre-captured cache actually tractable, unlike the Lure Inventory page's
    "Scan a lure" flow (`core.cabelas_lookup.search_lures()` called
    directly there with an arbitrary vision-model-guessed query), which
    intentionally does NOT get this fallback and keeps its existing
    "no matches -> manual Add a lure form" behavior unchanged.

    Captured real product data for all 20 categories via the same
    real-browser technique validated in entry 83 (`javascript_tool`
    executing on `cabelas.com`'s own origin, fetching a token then
    querying Coveo search directly) - large batch JS output kept hitting
    the tool's truncation limit, so results were staged into `window.*`
    variables in the page's own JS context and paged out in small chunks
    across several calls rather than requested all at once. The obvious
    category-name-as-query approach came back empty for 7 of the 20
    categories ("Texas-Rigged Worm", "Wacky-Rigged Senko", etc. aren't how
    products are actually named/tagged in Cabela's catalog) - retried
    those with more natural search terms ("Ribbon Tail Worm", "Senko
    Worm", "Finesse Worm", etc.) until all 20 had 2 real matches. Two
    "Blade Bait" picks (SteelShad Original/Mini Series) came back with a
    broken `ec_name` field on Bass Pro's own catalog side - literally the
    literal string `"++STEELSHAD ORIGINAL SERIES"`, quotes included, not a
    truncation or parsing bug on this app's end (confirmed by trying a
    second, differently-worded blade-bait query and a completely different
    brand/SKU, which had the exact same `"++...++"`-wrapped placeholder
    pattern) - real SKU/brand/price, just an unpopulated product-name
    template, so those two descriptions were manually cleaned up to
    something readable rather than shown verbatim or dropped. Confirmed
    the image URL Coveo returns (`fullimage`) is a deterministic template
    keyed only by SKU (`.../fn_select:jq:.../{sku}.json`) by comparing
    several real responses, so the cache stores that reconstructed URL
    rather than needing 40 separate network round-trips.

    New `data/cabelas_picks_cache.csv` (40 rows: 20 categories x 2 picks,
    columns `category,rank,sku,brand,description,price,image_url,
    captured_at`) and new `core/cabelas_picks_cache.py`
    (`get_cached_picks(category)`, an exact-match lookup returning results
    in the same dict shape `core.cabelas_lookup.map_result()` produces, so
    callers can treat live and cached results identically) - same
    small-CSV-plus-thin-reader-module pattern as `core/water_quality_log.py`
    (entry 68-ish), including the same "missing file -> [] rather than
    raising" fails-soft contract.

    Wired in at `core.appstate.get_cabelas_suggestions()`: tries the live
    `search_lures()` first, falls back to `get_cached_picks()` if that
    comes back empty, and now returns `(suggestions, is_live)` instead of
    a plain list - a breaking change to that function's return shape, but
    it has exactly one caller (`core.ui.render_cabelas_suggestions()`,
    confirmed via `grep` - the Lure Inventory "Scan a lure" flow calls
    `search_lures()` directly, untouched by this change), which now
    unpacks the tuple and, when `is_live` is `False`, adds a caption
    ("🛈 Cabela's live search couldn't be reached just now - showing picks
    saved from a previous lookup...") so the angler always knows whether
    what's on screen is a live check or a saved pick - same "be honest
    about what's live vs. saved" pattern as entry 79's USACE fallback note.

    Test coverage: new `tests/test_cabelas_picks_cache.py` (6 cases) -
    missing file, unrecognized category, rank-sorted output in the mapped
    dict shape, skipping rows with unparseable rank/price, blank-query
    handling, and (importantly) a coverage guard that loads the real
    shipped `data/cabelas_picks_cache.csv` and asserts every single
    `core.lures.LURE_PROFILES` category actually has 2 real picks with a
    non-empty SKU/description - this is the test that would catch a future
    `LURE_PROFILES` addition silently losing its fallback coverage. New
    `tests/test_appstate.py` (first-ever test file for that module, 4
    cases) covers `get_cabelas_suggestions()`'s live-hit/live-miss-falls-
    back-to-cache/both-miss/cap-to-num_results branches by monkeypatching
    `appstate.search_lures`/`appstate.get_cached_picks` directly - confirmed
    the `@st.cache_data`-wrapped function is still directly callable
    outside a full Streamlit runtime (with a "no runtime found" warning,
    same as every other scratch `AppTest`-adjacent check this session has
    made), and used a distinct query string per test case specifically to
    avoid the 24h cache silently returning a stale result from an earlier
    test's monkeypatch. `python3 -m pytest tests/ -q` now passes at 276
    (266 + 10 new: 6 cache + 4 appstate).

    End-to-end scratch verification (not committed): monkeypatched
    `appstate.search_lures` to always return `[]` (simulating the live
    lookup failing exactly as confirmed in production) and rendered the
    real "Walking Topwater (Spook-style)" block - the exact block the
    angler's original screenshot-equivalent bug report reproduced against
    in entry 83 - through the real, unmodified `render_cabelas_suggestions()`.
    Confirmed it now shows 2 real Livingston Lures product cards (photo,
    brand, description, price, working per-product "Search Cabela's" link)
    plus the "showing picks saved from a previous lookup" caption, instead
    of the plain empty-inventory text the angler originally reported. Also
    ran the standard `AppTest` smoke pass across every page reachable in
    this sandbox (same set as entries 73-83) - all still render with no
    exception; confirmed (as already known/documented) that
    `pages/1_7_Day_Forecast.py` itself still can't be smoke-tested directly
    in this sandbox (Open-Meteo is blocked here, unrelated to this change).
    `data/trip_log.csv`/`data/segment_score_freeze.csv`/
    `data/water_quality_log.csv`/`data/lure_inventory.csv` confirmed
    byte-identical (`md5sum`) before and after every run; scratch scripts
    deleted afterward.

    `requirements.txt` gained `curl_cffi>=0.7` (ships a compiled
    libcurl-impersonate binding via a manylinux wheel, not a pure-Python
    package - a small deploy risk worth naming, though the wheel installed
    cleanly in this sandbox and manylinux wheels are broadly compatible).
    Logged this ask as punch-list item #22 and marked it "Done" - but
    flagged to the angler that Option A's actual effectiveness in
    production can only be confirmed by checking the live app after
    deploy, since this sandbox can't reach Cabela's at all to verify it
    directly.

85. **Punch-list #23: redesign the Spot Session page's whole logging flow -
    one consolidated conditions block (weather-defaulted), pick lures
    before starting, a locked-in Start/End Session, and a per-catch popup
    with weight/length sliders and a multi-select "type of hit" field.**
    Ask (page: Spot Session): "Lets work on Spot session page again. This
    is the way I want it to flow. I want to log all current conditions at
    once, including the conditions when I start to use a lure. So the top
    of the page will have all the current condition fields and all the
    fields from conditions while using lure in one block in the
    beginning... Also, for all the weather related conditions default the
    field to current weather grabbed from the weather website you are
    using (with the ability to override). After that is entered, I want to
    then be able to get lure suggestions that I can select. If I don't
    select any of the recommendations, I want to then go to my lure
    inventory and pick the lures I want to use. I also want to be able to
    select multiple lures... Once all that is selected, I want to click a
    button that starts the session. This will lock in the start time and
    the time window... Once the session starts, as I catch fish, I want to
    be able to click on a lure I am using button... that will pop up a
    fish entry window to enter lbs and inches these should be sliders...
    type of fish drop down... and type of hit... multiple choice... Once I
    log a fish, I hit a button to record that fish and go back to fishing
    ... There should then be a button that ends the session. This will
    lock in the time the session ended and open up a new session start
    page." Four clarifying questions were asked up front (fish-entry
    fields, species-list flexibility, save timing, start-time-capture
    semantics); only the first was answered directly ("lets also keep the
    retrieve style but remove the depth" - interpreted as keep both
    `retrieve_style` and `retrieve_speed`, drop `depth_ft`), so the other
    three were carried forward as explicit stated assumptions (allow an
    "Other" species option; save each fish immediately on Record rather
    than batching; auto-capture the real start time when Start Session is
    clicked rather than a pre-session manual field) and confirmed by the
    angler afterward ("all the assumptions look good").

    This was the single largest change of the session - effectively a
    full rewrite of `pages/6_Spot_Session.py` (previously 1434 lines) plus
    new shared vocabulary in `core/onwater.py`, `core/activity_log.py`,
    and `core/lures.py`. Broken into two rounds: first the small,
    independently-testable building blocks, then the page rewrite itself.

    **Weather-default reverse mappings (`core/onwater.py`):** the module
    already had forward mappings (band label -> representative mph/cloud%/
    precip proxy, for driving the scoring formula from a hand-picked
    dropdown) but nothing going the other direction (a live forecast
    reading -> which dropdown option to default to). Added
    `light_condition_for_cloud_pct(pct)` (bucketed at the midpoints between
    each band's own existing proxy value, so a cloud% that exactly matches
    a band's proxy round-trips back to that same band), `precipitation_
    option_for_forecast(precip_in, precip_prob_pct)` (same midpoint
    approach across both the amount and probability proxies - either
    signal alone crossing its threshold is enough to bump the bucket, so a
    confident probability with a low modeled amount still warns the
    angler), and `wind_direction_for_degrees(deg)` (standard 8-point
    45-degree-sector compass bucketing; deliberately can't return "Calm"
    from direction alone, callers should check the paired wind-speed
    reading for that). 26 new/updated tests in `tests/test_onwater.py`,
    including explicit round-trip-through-each-band-own-proxy cases for
    both reverse mappings.

    **New fish-entry vocabulary (`core/activity_log.py`):**
    `FISH_SPECIES_OPTIONS` replaced with the angler's exact 6-species list
    (Largemouth/White/Crappie/Smallmouth/Walleye/Catfish) plus a trailing
    "Other" catch-all (confirmed via `grep` this constant is only ever
    read by this one page, so the swap was safe); new `HIT_TYPE_OPTIONS`
    (Hard hit/Light hit/Double tap/Swallowed/Fouled/Surface hit, used as a
    multiselect since a strike can legitimately match more than one); new
    `WEIGHT_SLIDER_OPTIONS` ("<1 lb" through "10 lb") and
    `LENGTH_SLIDER_OPTIONS` ("<13 in" through "26+ in") for the two
    `st.select_slider` fields the angler asked for, each with a
    `..._for_slider_option()` reverse-conversion helper back to the
    decimal lb/in this app stores everywhere else - same representative-
    value-per-band approach `core.onwater`'s `wind_mph_for_band()`/
    `precipitation_proxy()` already established (e.g. "<1 lb" stores as
    0.5 lb, "26+ in" stores as 27.0 in). New tests in
    `tests/test_activity_log.py` cover every option's round-trip plus
    blank/unrecognized-input handling.

    **`item_id` added to `LureBlock.owned_items` (`core/lures.py`):** the
    old edit-mode code matched a saved lure back to an inventory row by
    re-parsing its display label (`_find_inventory_item_by_label()`,
    fragile against renames), because `_group_owned_by_category()` never
    carried the row's real `item_id` through. Added it (confirmed safe via
    `grep` of `tests/test_lures.py` - no test asserts the full owned-item
    key set, only individual keys) so the new "+ Add to session" quick-add
    buttons on a lure recommendation card can add the exact inventory row
    directly, no label-matching needed.

    **The page rewrite itself.** Old architecture: a single "Conditions
    right now" section gated the whole score/recommendation panel behind
    a required "session start time" field, entered manually before
    fishing (an awkward fit for "I'm already standing at the water"); a
    separate, largely-duplicate "Conditions during this lure use"
    sub-section (a second Wind field, a near-duplicate forage-seen field);
    one lure logged at a time via an "Add results" expander with "Log
    this lure"/"Log this session" buttons; two separate, mutually
    exclusive "Add fish" flows (a full scoreable form vs. a species+count-
    only "small fish" shortcut) with a manual dash-separated "lb - oz"
    text field for weight and no way to record how a fish hit.

    New architecture: one `render_conditions_block()` merges both old
    sections into a single set of fields (Water temp, Secchi depth, stain
    color, stirred up, one Wind field, wind direction, Sky conditions,
    Precipitation, one Forage-seen field, Fish activity, Forage activity,
    Fish-holding depth), with every weather-related field's *first-ever*
    default coming from `_weather_defaults()` (nearest-hour row from
    `core.weather.hourly_rows_for_date()`, converted via the new
    `core.onwater` reverse mappings above, water temp from the existing
    `estimate_water_temp_f()`) rather than a hardcoded literal - always
    still a normal, freely overridable widget from then on (same
    `st.session_state.setdefault()`-then-bare-`key=` pattern the old page
    already used, just seeded from a live reading instead of a constant).
    A live "Suggestions for right now" panel (score + `core.lures.recommend()`
    output) is always shown once conditions are entered, computed against
    the current wall-clock time/segment as a rolling preview - no more
    "fill in a start time first" gate, since there's no separate
    conditions step anymore.

    Lure selection is new: recommendation cards (still rendered via the
    unmodified `core.ui.render_lure_block()`, so this stays in sync with
    the 7-Day Forecast page) get a "+ Add to session" button per owned
    item; a new `_multi_lure_picker()` (multi-select sibling of the
    existing single-select `_visual_lure_picker()`) offers the whole
    tackle box as a searchable card grid where each card toggles
    membership instead of picking exactly one; a manual "not in my
    inventory" text entry rounds it out. All three write into the same
    running "lures for this session" list (removable, shown above the
    picker), which `▶ Start Session` requires to be non-empty.

    `▶ Start Session` captures `lake_now_naive().time()` as the real start
    time, re-derives the time window from it via the existing
    `_guess_segment()`, appends one `TripEntry` per selected lure (empty
    fish list, `lure_end_time=None`), and stores an `active_session_<spot_id>`
    dict in `session_state` (trip_id/label/entry_kwargs/fish per lure) -
    committed and pushed once as a single batch. While a session is
    active, the page shows one button per lure (with a running catch
    count) instead of the setup form; clicking one opens a fish-entry
    `st.dialog` (weight/length `st.select_slider`s, species dropdown,
    `HIT_TYPE_OPTIONS` multiselect, kept `retrieve_style`+`retrieve_speed`,
    no `depth_ft`) - `st.dialog` was the correct primitive for exactly
    this "tap a lure, get a popup, keep fishing" interaction Streamlit
    offers. Recording a catch immediately rebuilds and `update_trip()`s
    that one lure's row (fish list, `fish_caught`, `biggest_fish_lb`) and
    pushes - per the angler's confirmed assumption, no batching until
    session end. Already-recorded fish are listed under each lure button
    (with their own Remove, for correcting a mis-tap without leaving the
    page). `⏹ End Session` stamps `lure_end_time` on every lure's row in
    one more batched push, clears the active-session state, and shows a
    one-shot "session closed" banner on the fresh setup view that follows.

    Trip History's "Edit this trip" link still works (simplified, not
    dropped) - editing reuses the exact same `render_conditions_block()`
    (seeded from the trip's own saved values, with backward-compatible
    fallbacks for both the old separate `wind_band`/`wind_band_logged`
    fields), a single-lure `_visual_lure_picker()`, a kept (edit-only)
    trailer sub-flow for correcting older trips' trailer data, and an
    inline (non-dialog) fish-list editor using the same new per-fish
    fields - `Save changes` calls `update_trip()` once, same as before.
    Old two-mode (scoreable vs. "small fish" count-only) fish entry is
    gone everywhere, including edit mode, in favor of one consistent
    per-fish form. Trailers were deliberately dropped from the *new*
    multi-lure session-setup flow specifically (the angler's redesign ask
    never mentioned them) - edit mode still supports them for legacy data,
    and they're straightforward to add back to session setup later if
    wanted. `pages/4_Trip_History.py`'s per-fish renderer got one small
    additive change - it now shows a fish's `hit_types` list when present,
    alongside the presentation info it already showed.

    Verification: `python3 -m pytest -q` passes 295 (276 + 10 onwater + 9
    activity_log). Full scratch `AppTest` walkthroughs against this page
    specifically (not committed) confirmed both paths end-to-end against
    real saved data: (1) new session - selected a spot, entered
    conditions, quick-added a recommended owned lure, Start Session
    (verified the new `TripEntry` row and its `conditions_json`), opened
    the fish dialog, filled every field, Record (verified `fish_caught`/
    `biggest_fish_lb`/the fish list all updated on that exact row), End
    Session (verified `lure_end_time` got stamped); (2) edit mode against
    a real *legacy*-schema logged trip (old separate `wind_band`/
    `wind_band_logged` fields) - confirmed every field prefilled
    correctly (including re-matching the previously-logged lure by label)
    and Save changes updated that row in place. One real `AppTest`-only
    quirk surfaced and worked around during this verification, worth
    recording: `st.dialog`'s "stay open across an interaction inside it"
    behavior isn't fully simulated by `AppTest` bare mode - the SAME
    opening button has to be re-clicked (from a freshly-fetched widget
    reference, not a stale one) on every single subsequent `.run()` for
    the simulated dialog to keep rendering, unlike real browser sessions
    where Streamlit tracks that internally. Confirmed this is a test-
    harness-only quirk (the documented, standard `st.dialog` pattern this
    page uses is unchanged from Streamlit's own official example) and not
    a bug in the shipped code. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/water_quality_log.csv`/
    `data/lure_inventory.csv` confirmed byte-identical (`md5sum`) before
    and after every test run that touched them (the `AppTest` walkthroughs
    above did write real rows while running - reverted via `git checkout`
    immediately after each). Logged this ask as punch-list item #23 and
    marked it "Done".

86. **Punch-list #24/#25: trailer-attach dialog + gated trailer picker for
    lure selection, mid-session lure-swap ("🔄 Change"), and 1-oz-granularity
    fish weight slider.** Two follow-up asks sent in chat right after entry
    85 shipped, both scoped to `pages/6_Spot_Session.py`.

    Ask #1 (page: Spot Session, logged as punch-list #24): "I did forget
    about the trailers. Let's do this... when I select lures, it should
    only show lures from my tackle box and no trailers should be
    selectable. Once I select a lure, [a] dialog box should open to add a
    trailer. If I select yes, the trailer options only show. Once I select
    a trailer for that lure, it should take me back to allow selecting
    another lure or start the session (as is now). If I remove a lure, it
    also should remove the trailer. Once I have all the lures selected and
    start a session, I also want a button by each lure to allow me to
    change. Clicking this button would remove that lure from active use in
    that session and log the time that lure was retired. Then I should be
    able to pick a new lure at anytime to add to the active list. If I
    change a lure, the new lure start time should be automatically logged
    within the same ongoing session." No clarifying questions needed - the
    ask was fully specified.

    **Trailer-gated lure pickers:** both `_multi_lure_picker()` (tackle-box
    card grid) and the recommendation quick-add buttons now filter out
    anything `core.lures.is_trailer_eligible()` flags as a trailer-only
    category (`TRAILER_ELIGIBLE_CATEGORIES = {"texas_rig_creature",
    "weightless_soft_plastic"}`) before rendering - a trailer can now only
    enter a session attached to a real lure, never picked standalone.

    **`_trailer_dialog` (`st.dialog`):** every lure "+Add" click now routes
    through a new `_handle_lure_add_click()` gate - if
    `core.lures.lure_can_take_trailer()` says the lure's category can carry
    one (recommendation-block items pass a synthetic
    `{"category": block.key}` since owned items in a rec card don't carry
    their own `category` key), a dialog opens with a "used a trailer with
    this lure" checkbox that, when checked, swaps in a trailer-only
    selectbox (`is_trailer_eligible` items, plus a manual-entry fallback);
    otherwise the lure is added directly, no dialog. "Add lure" attaches
    `final_lure["trailer"]` and adds to the pending list (or straight into
    the active session, for mid-session adds - see below); "Cancel"
    discards. Removing a lure from the pending list (unchanged Remove
    button) removes its whole dict, trailer included, for free.

    **Mid-session lure swap:** the active-session view now splits lures
    into active (each with its own catch-count button plus a new "🔄
    Change" button) and retired (collapsed into a "Retired lures (N)"
    expander showing fish count and start/end time). "🔄 Change" calls a
    new `_retire_lure()` - stamps `conditions["lure_end_time"]` with the
    real current time and `update_trip()`s that row, marks
    `lure["retired"] = True` in session state. A new "➕ Add a lure to this
    session" expander (same `_multi_lure_picker()`/manual-entry pair, now
    parameterized with `mode="active"`) lets a fresh lure be added at any
    point via a new `_add_lure_to_active_session()`, which reuses the
    locked-in session's `base_conditions`/segment/date/spot (now stored on
    `active_session_<spot_id>` alongside everything already there) and
    stamps a fresh `lure_start_time` - a real new `TripEntry` row, same
    session. `_end_session()` was fixed to skip already-retired lures
    (`if lure.get("retired"): continue`) so it no longer overwrites a
    retired lure's real (earlier) end time with the session's own later
    one - caught during implementation via code review, not a live bug
    report.

    One implementation bug found and fixed before this was considered
    done: the trailer dialog's widget keys were first built from a
    monotonically-incrementing per-spot counter
    (`_next_trailer_dialog_seq()`), bumped every time
    `_handle_lure_add_click()` decided to open the dialog. That broke
    `AppTest`'s required "re-click the same opening button on every
    `.run()` to keep the simulated dialog alive" workaround (see entry 85)
    - each keep-alive re-click re-triggered `_handle_lure_add_click()`,
    which bumped the counter again and handed the dialog a fresh, blank set
    of widget keys mid-interaction, discarding whatever had just been
    entered (surfaced as a `StopIteration` on the now-vanished old
    checkbox key). Fixed by replacing the counter with a stable
    `_trailer_dialog_lure_key()` derived from the lure's own `item_id` (or
    a hash of its label, for a manual entry) - repeated opens of the same
    lure's dialog now reuse the same keys, with a deferred
    `trailer_dialog_reset_pending_...` flag (consumed at the top of the
    dialog function, set right before the closing `st.rerun()` on a
    successful add) clearing stale values the next legitimate time that
    lure's dialog opens, without violating Streamlit's rule against writing
    to an already-instantiated widget's `session_state` key mid-run.

    Ask #2 (page: Spot Session, logged as punch-list #25, sent mid-turn
    while ask #1 was still being verified): "one other change... on the
    fish weight slider, please make it slide in increments of 1 oz from
    <1lb to +7lbs." `core.activity_log.WEIGHT_SLIDER_OPTIONS` (previously
    11 hand-typed whole-pound options, "<1 lb" through "10 lb") is now
    built programmatically - `["<1 lb"] + [_format_weight_option(oz) for oz
    in range(16, 112)] + ["+7 lb"]`, 98 options spanning "1 lb" through "6
    lb 15 oz" in exact 1-oz steps, generated rather than hand-typed to rule
    out a spacing typo across that many values.
    `weight_lb_for_slider_option()` was rewritten around three regex cases
    ("<1 lb" -> 0.5, a leading "+" sentinel -> matched value + 0.5, and a
    literal "X lb[ Y oz]" reading -> `round(lb + oz/16, 4)`) instead of a
    fixed whole-pound lookup.

    Verification: `python3 -m pytest -q` passes 297 (295 from entry 85 + 2
    new weight-slider tests: one-ounce-increment parsing, and a spacing
    check asserting every consecutive pair of the 96 real options is
    exactly 1/16 lb apart). No committed test exercises the trailer dialog
    or lure-swap flow end-to-end (both are `st.dialog`/session-state-heavy
    UI flows, consistent with how entry 85's fish-entry dialog was
    verified) - confirmed instead via scratch `AppTest` walkthroughs
    covering: tackle-box/recommendation pickers no longer offering trailer-
    only items; the dialog-gated vs. direct-add paths; trailer data landing
    correctly in a new row's `conditions_json`; removing a pending lure
    removing its trailer with it; "🔄 Change" stamping a retired lure's own
    earlier end time and leaving it alone through End Session while still-
    active lures get the later session-end timestamp; and a mid-session
    add producing a real new `TripEntry` with the locked-in session's
    conditions/segment/date carried over. `data/trip_log.csv`/
    `data/segment_score_freeze.csv`/`data/water_quality_log.csv`/
    `data/lure_inventory.csv` confirmed byte-identical (`md5sum`) before
    and after every test run that touched them, `data/trip_log.csv`
    reverted via `git checkout` immediately after each scratch `AppTest`
    run. Logged as punch-list items #24 and #25 and marked both "Done".

87. **Punch-list #26: lightweight multi-user support ("who's fishing") plus
    hardening the auto-push against two anglers saving at once.** Ask
    (verbatim, logged when #26 was filed): "do you think it is possible to
    have multiple users for this app? I fish with my son and it would be
    great if we each could log in and do our selections under our user
    names. It would still be nice for the data to be combined for trip
    history and future analytics, but would like the flexibility to log
    our own activity and have it stamped with our user ID." Two options
    were on the table: real OIDC logins via `st.login()`, or a simple
    non-password "who's fishing" name picker. Went with the picker (option
    1) - no accounts, no OAuth app to stand up, and this is a private
    deployment shared by a small number of known anglers. Names: seeded
    with John/Matthew/Alex plus a growable "Other" - pick "Other," type a
    name, and it's saved as a real dropdown choice from then on.

    Also flagged as a related hardening item regardless of which option:
    the deployed app auto-commits/pushes on every single log action
    (`core.storage.commit_and_push()`), and two anglers logging from
    separate devices at nearly the same moment could hit a non-fast-forward
    push rejection the way a manual push once did. Worked this half first,
    since it didn't depend on the angler names. `commit_and_push()` now
    retries a rejected push (matched on `[rejected]`/`non-fast-forward`/
    `fetch first` in stderr - anything else, e.g. a real auth failure,
    fails immediately without retrying) up to 3 attempts: fetch the remote
    branch, `git rebase FETCH_HEAD` onto it, and try the push again. A
    rebase conflict aborts the rebase and reports back "please retry the
    save" rather than leaving the local repo mid-rebase. Wrote real
    integration tests for this against actual bare-git-repo fixtures
    (`git init --bare`), not just mocked subprocess calls, specifically to
    catch what mocking would have missed: a genuine concurrent two-device
    push, replayed with real git plumbing in `tests/test_storage.py`.

    That test surfaced a real discovery along the way, not just a
    passing/failing assertion: a plain `git rebase` on two independent
    *appends* to the *end* of the same CSV file conflicts every time,
    regardless of how many unrelated rows already exist above the appended
    ones - git's default 3-way merge treats "new last line" as an edit to
    the old last line's context on both sides and can't tell the two
    appends apart. Reproduced this by hand in scratch repos before trusting
    it. The fix: `.gitattributes` now marks every `data/*.csv` file
    `merge=union` (git's built-in union merge driver, no extra `git config`
    needed - it just has to be present in a commit both sides share), which
    keeps both sides' differing lines instead of blocking on this specific
    shape of conflict. Verified the known tradeoff by hand too: `merge=union`
    does NOT catch a genuine same-row edit from two devices at once - it
    silently produces two duplicate rows rather than blocking, which is
    still much better than losing one save outright, but is worth knowing
    about if a duplicate-looking row ever turns up in Trip History.
    Documented this tradeoff in both `.gitattributes`'s own comments and
    `commit_and_push()`'s docstring, and in this README's Trip logging
    section. `tests/test_storage.py` (7 tests) covers: no-token/no-op
    short-circuits, a simple success, the real concurrent-push-then-rebase-
    retry scenario end to end, a non-retryable failure not retrying, giving
    up after `max_push_retries`, and a genuine rebase conflict aborting
    cleanly (using `data/notes.txt`, not a CSV, so union merge doesn't mask
    it and the conflict test still exercises a real conflict).

    With that landed, moved to the angler names. `core/anglers.py` is a new
    small module, same shape as `core/dev_tasks.py`/`core/lake_spots.py`:
    `data/anglers.csv` (single `name` column) seeded with
    `DEFAULT_ANGLERS = ["John", "Matthew", "Alex"]` on first read if the
    file doesn't exist yet, `read_anglers()` (case-insensitive de-duped,
    first spelling wins), and `add_angler()` (rejects blank/whitespace-only
    and case-insensitive duplicates, silently no-ops rather than raising).
    `core/appstate.get_anglers()` wraps `read_anglers()` with the same
    60s-TTL `st.cache_data` pattern as `get_inventory()`/`get_lake_spots()`/
    `get_dev_tasks()`. Deliberately did NOT add `angler` as a new top-level
    column to `data/trip_log.csv`/`core.storage.FIELDNAMES` - the real,
    already-committed file has an old header without it, and
    `append_trip()` is a pure append with no header rewrite, so a new
    trailing column would misalign `csv.DictReader` for every future read.
    Followed this codebase's existing convention instead (same as
    `lure_category`/`trailer_used`/etc.): `angler` lives inside
    `TripEntry.conditions` (serialized as `conditions_json`), no CSV schema
    migration needed.

    Spot Session (`pages/6_Spot_Session.py`) gained a "🎣 Who's fishing"
    selectbox right under the spot picker - roster options plus "Other,"
    which reveals a text input when picked. The widget's own key
    (`active_angler`) is deliberately page-wide, not scoped to a spot, so
    it keeps whatever was last picked as you move between spots in the same
    browser session rather than resetting - but that meant the edit-mode
    prefill (loading a *specific* past trip's own stored angler) needed its
    own one-time guard scoped to `edit_trip_id` alone (`
    angler_prefill_done_{edit_trip_id}`), not to the widget's key, so
    opening a different trip to edit re-prefills correctly instead of
    leaving whatever angler happened to be "active." `_build_base_conditions()`
    took a new `angler` parameter threaded through both the new-session
    "Start Session" and edit-mode "Save changes" paths. A new
    `_save_new_angler_if_needed()` helper calls `add_angler()` right before
    a trip is actually saved when "Other" was picked with a typed name, and
    both save paths conditionally add `ANGLERS_PATH` to that save's git
    push alongside `TRIP_LOG_PATH` only when a genuinely new name was added
    - an existing-roster pick never touches `data/anglers.csv` at all.
    Trip History (`pages/4_Trip_History.py`) got a fourth filter column
    ("Angler," multiselect) and a read-only "Angler" grid column, reading
    the same `conditions["angler"]` field back out per row (blank/missing
    for any trip logged before this round, same graceful-degradation
    pattern as every other optional condition field on this page).

    Verification: `core/anglers.py` covered by 7 new unit tests
    (`tests/test_anglers.py` - seeding, dedup, add/reject cases) plus one
    new `core/appstate.get_anglers()` passthrough test; full suite now 312
    passing (was 304 before this round). No committed test drives the Spot
    Session page's angler UI end-to-end (same reasoning as every other
    `st.dialog`/session-state-heavy flow on this page) - confirmed instead
    via a scratch `AppTest` walkthrough against the real spot/data files:
    the picker renders with the right options; picking "Other" reveals the
    text input; starting a session with a brand-new typed name lands that
    exact name in the new trip row's `conditions_json["angler"]` AND
    persists it to `data/anglers.csv`; opening that same trip in edit mode
    correctly prefills the picker from the trip's own stored angler even
    with a *different* angler "active" in session state at the time
    (proving the prefill reads the trip, not the stale active pick); and
    the newly-typed name shows up as a real dropdown option on a fresh page
    load afterward. Also ran the full `AppTest` smoke pass across the app
    entry point and all 7 pages (per standing practice), including a
    specific check that Trip History's new Angler filter widget renders
    without error against the real, mostly angler-less legacy trip log.
    `data/trip_log.csv`/`data/lure_inventory.csv`/`data/lake_spots.csv`/
    `data/dev_tasks.csv`/`data/water_quality_log.csv` confirmed
    byte-identical (`md5sum`) before and after every scratch run that
    touched them; `data/trip_log.csv` reverted via `git checkout` and the
    fresh `data/anglers.csv` the scratch run created deleted immediately
    after, before committing the real, clean, defaults-only
    `data/anglers.csv` this feature actually ships with. Logged as
    punch-list #26 and marked "Done".

88. **Punch-list #27: reorder the sidebar pages.** Ask (verbatim): "Lets
    reorder the app pages as follows: Today, 7 Day Forecast, Lake Map,
    Spot Sessions, Trip History, Lure Inventory, Development." The only
    change needed was the order of the `st.Page(...)` entries in
    `app.py`'s `st.navigation([...])` list - that list, not the pages'
    numeric filename prefixes, is what actually controls sidebar order
    (the prefixes are leftovers from the old file-based `pages/`
    auto-discovery this app stopped using once `st.navigation`/`st.Page`
    landed - see `app.py`'s own docstring). Moved `Spot Session` up to sit
    right after `Lake Map` and before `Trip History`; left every page's
    filename untouched (renaming them to match the new numeric order would
    have touched every test/README reference to those paths for zero
    functional benefit, since the filenames no longer drive anything).
    README's "Project layout" file listing reordered to match, with a note
    added clarifying that the list order there is cosmetic/documentation
    only. Verification: full suite still 312 passing (untouched by this
    change); a scratch `AppTest` run parsed `app.py`'s own AST to confirm
    the six `st.Page(title=...)` calls now appear in the exact requested
    order (`AppTest` itself doesn't expose the rendered sidebar's labels
    directly, so reading the source was the reliable check); the standing
    full-page `AppTest` smoke pass (entry point + all 6 pages) still comes
    back clean; `data/trip_log.csv`/`data/lure_inventory.csv`/
    `data/lake_spots.csv`/`data/dev_tasks.csv`/`data/water_quality_log.csv`/
    `data/anglers.csv` all confirmed byte-identical (`md5sum`) before and
    after. Logged as punch-list #27 and marked "Done".

89. **Punch-list #28: rename the Tackle Box (formerly "Lure Inventory") page.**
    Ask (verbatim): "Lets change the name of lure inventory page to 'Tackle
    Box'." Scope call: rename every *user-visible* string (sidebar nav title
    in `app.py`, the page's own `st.set_page_config`/`st.title`, cross-page
    help text/captions that reference "the Lure Inventory page" from 7-Day
    Forecast and Spot Session, the punch-list page-tagging dropdown's option
    in `core/dev_tasks.py`'s `PAGE_OPTIONS`, and README) plus every code
    comment/docstring that documents "the Lure Inventory page" as a current-
    state proper-noun reference (`core/appstate.py`, `core/cabelas_lookup.py`,
    `core/cabelas_picks_cache.py`, `core/lure_inventory.py`, `core/lure_vision.py`,
    `core/lures.py`, and the matching test-file comments) - all a plain
    `Lure Inventory` -> `Tackle Box` swap, safe as a blanket replace since
    the actual filenames use an underscore (`Lure_Inventory.py`) rather than
    a space and were never touched by it. Deliberately did NOT rename any
    file or Python identifier (`pages/5_Lure_Inventory.py`, `core/lure_inventory.py`,
    `read_all_items()`, etc.) - the ask was about the page's displayed name,
    and this codebase already treats a page's filename as internal/cosmetic
    only, not the source of its displayed title (see entry 88, same round).
    Also deliberately left every *historical* mention of "Lure Inventory"
    alone - this dev-log's own past entries, and the `page` column on
    already-logged punch-list rows #14/#28 in `data/dev_tasks.csv` - since
    those are a record of what was true at the time, the same reasoning as
    never rewriting old commit messages; `PAGE_OPTIONS`'s existing "an
    unrecognized `page` value gets unioned into that row's own edit dropdown
    instead of being coerced" behavior (`pages/7_Development.py`) already
    means those old rows keep working fine without a data migration.
    README's "Lure inventory" section additionally got its own heading
    reworded to "Tackle Box (lure inventory)" and its opening sentence
    de-duplicated (it used to read "The Tackle Box page ... is a tackle-box
    tracker," an artifact of the plain string swap landing next to the
    section's own pre-existing "tackle-box tracker" phrasing). Verification:
    full suite still 312 passing; a scratch `AppTest` run confirmed the
    Tackle Box page's own rendered `st.title` really reads "🧰 Tackle Box"
    and that `app.py`'s nav titles contain "Tackle Box" and no longer
    contain "Lure Inventory"; the standing full-page smoke pass across the
    entry point and all 7 pages stayed clean; all six `data/*.csv` files
    confirmed byte-identical (`md5sum`) before and after. Logged as
    punch-list #28 and marked "Done" - no open punch-list items remain as
    of this entry.

90. **Punch-list #29: an in-progress Spot Session "reset" after a real-world
    field test, following a dropped/reconnected connection.** Ask (verbatim,
    reported after actually fishing with the redesigned page): "I put in the
    current conditions, pick lures and started logging fish. However, if
    there was a few minute delay between fish and I clicked the lure button
    to enter fish, it would go back to a session start again. It would have
    the conditions and same spot still there from the prior session but it
    then showed lure suggestions and below that, the lures I selected were
    gone... my cell coverage is spotty in some areas that I fish, so maybe it
    dropped out. Either way, if it does drop out, it should just continue as
    an offline app until a connection is restored and then the data captured
    offline can sync up."

    Root cause: `active_session_{spot_id}` (which lures are active/tappable,
    right now) has only ever lived in `st.session_state` - in-memory on the
    server, tied to one browser session. Spotty cell coverage dropping the
    WebSocket, a phone locking its screen mid-session (iOS/Android commonly
    suspend a backgrounded tab's JS entirely rather than just pausing it,
    tearing the connection down for real), or the server itself restarting
    all wipe that in-memory state, and the next successful reconnect gets
    treated as a genuinely new browser session with empty `session_state` -
    matching the report exactly: spot/conditions rode along fine (those
    already travel via `st.query_params`, see entry 34), but the active-lure
    buttons vanished and the page fell back to the pre-session builder.

    True "continue offline, sync later" isn't achievable on this platform:
    every interaction in a Streamlit app - clicking a button, opening a
    dialog, anything - is a live round trip to the Python server; there's no
    offline-capable client-side code, no service worker, nothing that could
    keep working with zero connectivity short of rearchitecting this as a
    different kind of application entirely (a native app or a from-scratch
    PWA with local storage + background sync) - out of scope for a
    Streamlit-based tool. Explained this limitation directly rather than
    promising something the stack can't do.

    What IS achievable, and turned out to close nearly the whole practical
    gap: no data was ever actually being lost in the first place. Every
    lure added to a session and every fish caught already gets written to
    `data/trip_log.csv` immediately (`append_trip()`/`update_trip()` +
    push, right in `_add_lure_to_active_session()`/`_record_fish()`/the
    Start Session handler - see their own docstrings, this was true well
    before this round). The only thing that was ephemeral was the BROWSER'S
    knowledge that a session was in progress. So the fix rebuilds that view
    from disk instead of trying to prevent the disconnect: new
    `_open_session_rows()`/`_reconstruct_active_session()` in
    `pages/6_Spot_Session.py`, hooked in right where `active_session_{spot_id}`
    is read - if it's missing, look for today's trip rows at this spot that
    are still "open" (no `lure_end_time` yet) before falling through to the
    pre-session builder, and rebuild the exact same active-session shape
    from them if found. Sessions are grouped by their shared
    `conditions["start_time"]` (the one value every lure in a session
    carries unchanged, captured once at Start Session) since there's no
    explicit session id stored anywhere - a properly `⏹ End Session`-ed
    group has every row's `lure_end_time` stamped and is correctly left
    alone (verified this specific negative case too, not just the recovery
    path). A one-time "Reconnected - picked this session back up..." info
    banner (popped from session_state after one render, so it doesn't
    nag on every rerun) tells the angler what happened. One known,
    documented gap: a persisted row never recorded which inventory item_id
    a lure was, only its display label, so a reconstructed lure's item_id
    is always `None` - the "already added" dedupe check in
    `_add_lure_to_active_session()` won't catch re-picking the exact same
    inventory item after a reconnect (shows up as a harmless second row,
    not data loss - clean up manually via Trip History if it happens).

    Verification: full suite still 312 passing (all page-level logic, no
    core/ changes, consistent with this page's existing test-coverage
    pattern). Two scratch `AppTest` walkthroughs against real spot/data:
    (1) start a session with one lure, directly mutate that lure's saved
    row to simulate "a fish was already landed" (independent of any browser
    session, exactly like `_record_fish()` itself would have left it),
    then point a BRAND NEW `AppTest` instance (genuinely fresh
    `session_state`, simulating the reconnect) at the same spot - confirmed
    it reconstructs the in-progress session with the correct active lure
    AND its already-logged fish intact, shows the header/banner instead of
    the pre-session builder (asserted no "Start Session" button rendered),
    and that End Session from that reconstructed instance still works
    correctly with no duplicate trip rows created; (2) start and PROPERLY
    end a session, then load a fresh instance at the same spot/date and
    confirm it does NOT get resurrected as "in progress" - only a genuinely
    open session should ever rebuild. Also ran the standing full-page smoke
    pass across the entry point and all 7 pages, clean. `data/trip_log.csv`
    (the only file this touched) confirmed reverted to byte-identical
    (`md5sum` + `git checkout`) after every scratch run. Logged as
    punch-list #29 and marked "Done."

91. **Punch-list #30 (SOMEDAY/MAYBE, logged Open): scoped true offline field
    logging and a possible public-app rebuild - not built, research
    preserved for whenever it's picked up.** After entry 90 shipped the
    reconnect-resilience fix, the angler asked what TRUE offline capability
    (works with zero signal, syncs later) would actually take, since some
    areas of the lake have real, sustained dead zones (this morning's
    reported issue was most likely his phone locking, per his own read, but
    the dead-zone question is separate and real). Researched rather than
    guessed at the constraints:
    - Confirmed via caniuse.com that iOS Safari has never supported the Web
      Background Sync API (`registration.sync`) - no WebKit roadmap signal
      either. Any offline design for this app's actual users (phones) can't
      rely on it; sync has to be "try when the app is reopened with
      signal," not silent background sync.
    - Confirmed iOS Safari DOES support Service Workers/Cache API/IndexedDB
      well enough for a real offline-capable PWA (home-screen web apps get
      Safari's own storage quota per WebKit's 2023 policy update), but
      Safari's Intelligent Tracking Prevention can evict script-writable
      storage after ~7 days with no user interaction - fine for a same-day
      sync, a real constraint for anything meant to sit unopened longer.
    - Confirmed on the Streamlit community forum that Streamlit itself has
      no official PWA/offline support and a maintainer's stated reason:
      "the frontend always requires a connection with the backend Streamlit
      server." This isn't a missing feature to request, it's this
      framework's actual architecture - genuinely not fixable inside
      Streamlit.
    - Real offline-first field-data tools (ODK Collect, KoboCollect, ArcGIS
      Field Maps, Fulcrum, GoCanvas) are consistently NATIVE mobile apps,
      not PWAs or web apps, precisely because of the iOS limitations above
      plus needing robust camera/GPS access.

    Presented three tiers: (A) no-code workflow mitigation - jot catches in
    the phone's own Notes/voice memo app in a dead zone, batch-enter once
    back in range (works today, costs nothing, and entry 90's fix means
    re-entering won't lose or duplicate anything); (B) a small standalone
    offline "catch logger" PWA (new codebase, local IndexedDB storage, a
    small serverless sync relay since a GitHub push token can't safely live
    in client-side JS) - real but bounded engineering, roughly a multi-day
    side project; (C) a full native/cross-platform rebuild, the way
    professional tools actually solve this.

    The angler's follow-up reframed this as a possible future public-app
    rebuild (better look/feel too, not just offline), so this entry scopes
    tier C at a high level rather than committing to any tier now: (1) data
    layer - real database (e.g. Postgres via Supabase/Neon) replacing
    trip_log.csv-in-git for genuine concurrent multi-user writes, real
    accounts/auth replacing both "no auth" and the who's-fishing name tag,
    a real API layer (FastAPI fits well - `core/scoring.py`/`core/lures.py`/
    `core/weather.py` etc. are plain Python with no Streamlit dependency,
    so most of the actual fishing logic carries over behind API endpoints
    rather than being rewritten); (2) a React Native or Flutter mobile app
    (one codebase, both stores) with on-device SQLite for full offline
    read/write and sync-on-reconnect, native camera/GPS instead of browser
    widgets; (3) a separately designed public web frontend for
    browsing/planning without installing an app; (4) public-readiness
    hardening - rate limits/caching on external calls (Open-Meteo, USGS,
    USACE, Cabela's lookup, the Claude vision lure-scanner) that are fine
    at 2 users but need real per-user caps at scale, real non-free
    hosting/ops, a privacy policy (anglers are protective of their spot
    locations), and a scope call on single-lake (everything right now -
    bathymetry, shoreline, fish attractors - is Nolin-specific data) vs.
    multi-lake. Explicitly a genuine rebuild as a different KIND of project
    (months, real staging/prod environments, app-store review cycles) -
    not an incremental feature on this codebase. Logged as punch-list #30
    and deliberately left "Open" (not "Done") - this is a someday/maybe
    item to revisit, not something built this round.

92. **Punch-list #31: paired the fish-weight slider with manual lb/oz (and
    length with manual inches) entry fields, two-way synced - the 1-oz
    slider alone was "really touchy" for real on-the-water use.** Verbatim
    ask: "On the fish weight slider when entering a caught fish, it is
    really touchy given it is in 1 oz increments. Two ideas to improve; 1)
    lets change the top end to +5lbs instead of +7lbs and then right to the
    right of the slider, lets add manual fields for lbs and ozs. The slider
    should also populate the manual fields as it slides. This way I can get
    close and then manual enter is needed. I should also be able to just
    straight manual enter and the slider would then adjust to that weight.
    This is less of an issue with the inches, but lets do the same thing
    but keep the slider range as is for now." Two changes:

    - `core.activity_log.WEIGHT_SLIDER_OPTIONS`' top end narrowed from a
      "+7 lb" open-ended catch-all to "+5 lb" (`WEIGHT_SLIDER_TOP_LB = 5`,
      a new constant rather than a hardcoded literal, same rationale as
      every other named constant in this module) - trims 16 fiddly
      1-oz steps off the slider's far end that real catches here rarely
      reach anyway; the "+5 lb" catch-all and the new manual field both
      still handle a genuine outlier. Two new functions,
      `nearest_weight_slider_option()`/`nearest_length_slider_option()`,
      snap an arbitrary decimal lb/in value to its closest slider option
      (clamped to the two open-ended catch-alls outside the concrete
      range) - the reverse direction of the existing
      `weight_lb_for_slider_option()`/`length_in_for_slider_option()`,
      needed so a manual entry can move the slider to match.
    - `pages/6_Spot_Session.py` gained `_weight_input()`/`_length_input()`,
      each rendering its slider plus one or two `st.text_input` manual
      fields (`st.text_input`, not `st.number_input` - this app has
      avoided `number_input`'s built-in +/- steppers since punch-list #2/
      entry 62's original "no +/- buttons" ask, and the same reasoning
      applies here) using the `on_change`-callback two-way-sync pattern
      this project's own widget rules already document: moving the slider
      (`on_change=_slider_changed`) writes the manual field(s) to match;
      typing into a manual field (`on_change=_manual_changed`) re-derives
      the slider's nearest position. The manual fields are the real
      source of truth for the value these functions return (full 1-oz/
      any-decimal-inch precision, not limited to the slider's own bands) -
      the slider is a fast, rough starting point per the angler's own
      framing ("get close and then manual enter"), not the final say. An
      oz value of 16+ typed into the manual field carries over into lb
      automatically (`lb, oz = lb + oz // 16, oz % 16` - e.g. "20" oz
      becomes 1 lb 4 oz) so there's no mental math needed at the water.
      Both call sites - the live "Log a fish" dialog (`_fish_entry_dialog`)
      and edit mode's "Add a fish" block - swapped their old
      `st.select_slider` + `weight_lb_for_slider_option()`/
      `length_in_for_slider_option()` pair for a single call to the new
      helper; `_new_fish_from_form()`'s signature changed from
      `(..., weight_option, length_option, ...)` to
      `(..., weight_lb, length_in, ...)` accordingly, storing the already-
      resolved decimal values directly instead of converting from a slider
      label. Length's slider RANGE is unchanged (`LENGTH_SLIDER_OPTIONS`
      untouched) per the angler's explicit "keep the slider range as is
      for now" - only the manual-field pairing is new there.

    Verification: `tests/test_activity_log.py` updated (top-end tests
    changed from "+7 lb"/7.5 to "+5 lb"/5.5, `WEIGHT_SLIDER_TOP_LB == 5`
    asserted, four new tests for `nearest_weight_slider_option()`/
    `nearest_length_slider_option()` covering in-range snapping,
    below/above-range clamping to the two catch-alls, and blank/garbage
    input) - full suite 316 passing. A scratch `AppTest` walkthrough
    (uncommitted) seeded a real active session with one lure at a real
    tackle spot, opened the "Log a fish" dialog, and used the widgets'
    real `.set_value()`/`.click()` interaction API (not raw
    `session_state` writes, which bypass `on_change` entirely and don't
    reflect what actually happens at click-time) to confirm: correct
    default seeding (slider "<1 lb" seeds manual fields to 0 lb/8 oz, the
    band's own representative value); moving the weight slider to "3 lb 4
    oz" updates the manual fields to match; typing lb=2/oz=20 into the
    manual fields snaps the slider to "3 lb 4 oz" with the oz carrying
    over into lb correctly; the same slider->manual and manual->slider
    sync for length, including a half-inch manual value (21.5) the
    whole-inch slider itself can't represent, snapping to its nearest
    whole-inch option; and that clicking "✅ Record" with those manually-
    typed values lands the exact precise `weight_lb`/`length_in` (3.25 and
    21.5, not slider-rounded values) in the resulting trip-log row's
    `conditions_json["fish"]` entry. Also re-ran the standing full-page
    smoke pass across the entry point and all 7 pages (needed a proper
    fake weather bundle and lat/lon on the fake spot this time, since
    `1_7_Day_Forecast`/`2_Lake_Map` both need real-shaped forecast/spot
    data to render - not a regression from this change, just this round's
    scratch mocks needing to be more complete than a bare `None`/no-`lat`
    stub). `data/trip_log.csv` and every other data file confirmed
    byte-identical (`md5sum`) before and after every scratch run. Logged as
    punch-list #31 and marked "Done."

93. **Punch-list #32: added a "❌ Cancel Session" button (discards an
    in-progress session's rows entirely) and a per-fish catch timestamp
    surfaced in Trip History.** Verbatim ask, delivered mid-turn while #31
    was still in progress: "Once you are done with the last request, lets
    add a cancel session button for once a session starts, in case I want
    to test sessions or simply just want to start a session over without
    recording any of it. Separately, when I log a caught fish, this should
    be time stamped and show up in the trip history detail for that fish."
    Two independent changes to `pages/6_Spot_Session.py` (and one small
    addition to `pages/4_Trip_History.py`):

    - **Cancel Session.** New `_cancel_session(spot_id)`, placed right
      next to `_end_session()` for the contrast: where `_end_session()`
      stamps a real end time on every still-active lure and KEEPS
      everything logged, `_cancel_session()` calls `core.storage.
      delete_trip()` (the same row-removal primitive Trip History's own
      "🗑️ Delete this trip" already uses) on every `trip_id` the active
      session created, then drops `active_session_{spot_id}` from
      `session_state` - restoring the exact same clean "no session"
      state as a fresh page load, with nothing from that session left in
      `trip_log.csv`. The trip_ids to delete come from the in-memory
      `active["lures"]` list (not a fresh disk scan), so this can only
      ever reach the rows THIS session itself created, never anything
      else logged at this spot earlier. Wired up as a second button next
      to "⏹ End Session," gated behind the same two-step "are you sure"
      confirm pattern Trip History's own delete flow established
      (`cancel_session_confirm_{spot_id}` pending flag -> a warning
      showing exactly how many lures/fish would be discarded -> "Yes,
      cancel it" / "Keep session") since this permanently destroys data
      with no undo, same reasoning as every other irreversible action in
      this app. A new `session_canceled_banner_{spot_id}` flag (popped
      and shown once, same pattern as the existing
      `session_closed_banner_{spot_id}`) tells the angler what happened
      on the next render: "❌ Session canceled - nothing from that session
      was saved."
    - **Fish catch timestamp.** `_new_fish_from_form()` now stamps every
      fish record with `"caught_at": lake_now_naive().time().isoformat()`
      at the moment it's built - the same convention `lure_start_time`/
      `lure_end_time` already use, so it round-trips through
      `conditions_json` with zero schema changes. New
      `_format_fish_time()` (Spot Session) /
      `_format_fish_caught_at()` (Trip History) - genuinely identical one-
      liners kept as two separate functions rather than a shared import,
      since each page already has its own small set of private per-fish
      display helpers and this is consistent with that - render it as
      "8:15 AM" (Python's `%-I:%M %p`, the same format this page's own
      time-window labels use) and slot it into `_fish_summary_bits()`
      (Spot Session's active-session fish list and edit-mode fish list)
      and Trip History's own separate per-fish bits builder in
      `_render_trip_detail_body()`, both right after the species name.
      Both are fail-soft: a fish record logged before this existed simply
      has no `caught_at` key, and the formatter returns `None` for a
      missing/unparseable value, which both call sites already treat as
      "skip this bit" like every other optional per-fish field.

    Verification: full suite still 316 passing (both changes are
    page-level UI/display logic, no core/ changes, consistent with this
    page's existing test-coverage pattern). A scratch `AppTest` script
    (uncommitted) covered both features against real trip-log rows: (1)
    seeded an active session with two lures/rows, clicked "❌ Cancel
    Session" then "Yes, cancel it," and confirmed both rows were actually
    gone from `trip_log.csv`, the active session was cleared from
    `session_state`, and the page fell back to the pre-session builder (no
    "⏹ End Session" button present, i.e. genuinely back to a clean slate,
    not just visually reset); (2) separately confirmed the confirm step's
    "Keep session" path backs out cleanly with the row still intact and
    the session still active; (3) recorded a fish via the real "✅ Record"
    button/`_record_fish()` path and confirmed the saved row's
    `conditions_json["fish"]` entry carries a real `caught_at` value; (4)
    loaded Trip History against that same data and confirmed the EXACT
    formatted time label (not just any "AM"/"PM" substring on the page)
    appears in its rendered per-trip detail markdown. Also re-ran the
    standing full-page smoke pass across the entry point and all 7 pages,
    clean. `data/trip_log.csv` and every other data file confirmed
    byte-identical (`md5sum`) before and after every scratch run - one
    early `md5sum` comparison briefly looked like a mismatch on
    `data/dev_tasks.csv` until double-checked against `git show HEAD:...`,
    which confirmed it actually matched the just-pushed #31 commit exactly
    and the "before" snapshot being compared against was simply stale
    (captured earlier in the same session, before #31's own commit).
    Logged as punch-list #32 and marked "Done."

94. **Investigated a "Cancel Session doesn't reset the page" report (false
    alarm - stale browser tab, not a bug) and shipped punch-list #33: a
    collapsed-by-default suggestions panel, and st.pills instead of
    st.multiselect for "Type of hit" (a phone-cutoff dropdown bug).**
    Shortly after #32 shipped, the angler reported "If I cancel a session
    and confirm, it looks like it is not resetting the page to start a new
    session." Rather than guess, re-verified `_cancel_session()`/the
    confirm button flow two ways: the original synthetic-seed scratch test,
    and a new one driving the REAL button flow end to end (▶ Start
    Session -> add a lure via the real tackle-box picker -> log a fish via
    the real dialog -> ❌ Cancel Session -> Yes, cancel it) - both correctly
    deleted every row, cleared `active_session_{spot_id}`, and landed back
    on the builder (no "⏹ End Session" button present). With no bug
    reproducible in the code and the fix having only pushed ~9 minutes
    earlier, asked the angler what he specifically saw and whether he'd
    tried a fresh page load; he confirmed a retry worked - the first
    attempt was against a browser tab that hadn't picked up the redeploy
    yet, not a real defect. No code change from this - noted here so a
    future "it's not resetting" report isn't re-investigated from scratch
    without first ruling out a stale tab again.

    Same message then asked for two more Spot Session tweaks:

    - **"lets have the lure suggestion block stay closed until opened
      manually."** The "Suggestions for right now" expander's
      `expanded=True` (it opened by default every time the session-builder
      view rendered, pushing the actual "Lures for this session" section
      further down) changed to `expanded=False` - one line, still one tap
      away.
    - **"when I select the type of hit when entering a fish on my phone,
      it cuts off the last selectable item (surface)....lets make this
      selection block be scrollable so I can scroll to that on my
      phone."** Before patching CSS blind, actually opened the live
      deployed app in a real browser and inspected the rendered DOM
      directly (this project's own established standard for mobile CSS
      work - see `core.ui.inject_mobile_css()`'s own docstring on the
      column-reflow fix, "verified directly against the live deployed
      app, not just reasoned about"). Confirmed Streamlit's multiselect
      dropdown (`[data-testid="stMultiSelectDropdown"]`, a `position:
      fixed` popover wrapping a `[role="listbox"]`) already sets
      `max-height: 300px` / `overflow-y: auto` on the option list, so the
      underlying CSS wasn't naively broken - the real culprit is almost
      certainly the classic mobile-web gap between the *layout* viewport
      a fixed popover is positioned against and the actual, smaller
      *visual* viewport once the phone's browser chrome/keyboard is
      accounted for, which no fixed pixel height can reliably track.
      Rather than chase that blind (no way to verify a CSS-only fix
      against a real phone's dynamic viewport from here), took the more
      robust path: swapped the "Type of hit" field from `st.multiselect`
      to `st.pills(..., selection_mode="multi")` in both call sites
      (`_fish_entry_dialog` and edit mode's "Add a fish" block) - pills
      render every option as an always-visible, directly tappable chip
      (wrapping onto a second line on a narrow screen) with no popover to
      get cut off at all, sidestepping the failure mode entirely rather
      than patching around it. `st.pills` returns a plain list in multi
      mode, so nothing downstream (`_new_fish_from_form`, the
      `", ".join(...)` display bits, `conditions_json["fish"]` storage)
      needed to change. Also added general defensive CSS to
      `core.ui.inject_mobile_css()` for every OTHER selectbox/multiselect
      dropdown in the app (not just this one): a `dvh`-based (dynamic
      viewport height, tracks the real visible viewport rather than the
      layout one) cap on both the popover and its inner listbox, plus
      `overscroll-behavior: contain` so a touch-drag inside the list can't
      get grabbed by the page's own scroll instead - hardening for the
      same underlying mobile-viewport class of bug anywhere else it might
      show up, not a substitute for the pills fix on the one dropdown
      actually reported broken.

    Verification: full suite still 316 passing (no core/ changes - pure
    page-level widget swap + CSS + one `expanded=True`->`False`). A
    scratch `AppTest` script (uncommitted) confirmed the "Suggestions for
    right now" expander's `.proto.expanded` is `False` on first render,
    that the new pills widget exposes the complete, unhidden option set
    (`Hard hit`/`Light hit`/`Double tap`/`Swallowed`/`Fouled`/`Surface
    hit`), and - selecting `"Surface hit"` specifically, the exact option
    reported unreachable - that clicking "✅ Record" lands both selected
    hit types correctly in the saved row's `conditions_json["fish"]`
    entry. Also re-ran the standing full-page smoke pass across the entry
    point and all 7 pages, clean. `data/trip_log.csv` and every other data
    file confirmed byte-identical (`md5sum`, `dev_tasks.csv` checked
    against `git show HEAD:...` per entry 93's earlier note) before and
    after every scratch run. Logged as punch-list #33 and marked "Done."

95. **Punch-list #34: added a session-level "Session end time" to Trip
    History, and re-verified (didn't just reason about) that "⏹ End
    Session" reliably ends the session and stamps the real time.**
    Verbatim ask: "in trip history, lets add a session end time that is
    stamped when I end a session in spot session. Also, can you confirm
    that ending a session with the button actually ends it and time
    stamps? I thought I had ended my sessions this morning, but it shows a
    lure end time of around 11am and I think I ended my last session at
    about 9am and the others were ended before that." Two parts:

    - **The confirm.** Pulled the angler's own real trip data (his live
      testing since #33 shipped had already pushed real commits to
      `main`, which this session's local clone picked up via the
      standing `git fetch` + `git rebase` step before its own next push)
      and found the actual rows: three lures from a session started at
      `07:01:36`, all three sharing the identical `lure_end_time`
      `11:13:04.996201` - the exact "one single End Session click stamps
      the same 'now' on every still-active lure" signature the code is
      supposed to produce, not a bug pattern (e.g. not three different
      times, not a stale/reconstructed value). Re-verified the button
      itself with a fresh scratch `AppTest` driving the REAL flow (Start
      Session with 2 lures -> retire one early via "🔄 Change" -> End
      Session) and confirmed: the button genuinely clears the active
      session and falls back to the builder (not just visually - no "⏹
      End Session"/lure buttons left); the stamped time provably falls
      within the actual `[before-click, after-click]` wall-clock window,
      not some earlier or later value; and a lure retired early keeps its
      own real, earlier `lure_end_time` rather than getting overwritten
      by the later End Session stamp. The mechanism checks out as working
      correctly. The most likely explanation for the 11:13am timestamp
      not matching the angler's own "~9am" recollection: punch-list #29's
      reconnect-resilience design means an End Session click that never
      reaches the server (a dropped connection - his own reported spotty
      lake coverage) simply never happens; the session stays genuinely
      "open" on disk until whichever click actually lands. If he tried at
      ~9am on a dead spot and it didn't take, the still-open session
      would have been sitting there (silently, with no error to see)
      until reconnecting and successfully clicking again later - which
      would read exactly like this data. Told him this finding rather
      than asserting a fix, since there's no code bug to point to here.
    - **The actual ask.** `_end_session()` (`pages/6_Spot_Session.py`) now
      stamps a `"session_end_time"` key into EVERY lure's conditions dict
      when "⏹ End Session" is clicked - retired lures included, not just
      the still-active ones `lure_end_time` already covers. Deliberately
      a separate field from `lure_end_time`, not a rename/reuse of it:
      for a lure retired early via "🔄 Change," `lure_end_time` is
      correctly that lure's own earlier real swap-out time, while
      `session_end_time` is the one shared "the whole session actually
      closed at X" moment - conflating the two would have silently
      overwritten the more precise per-lure timestamp #29's original
      design already preserves. `pages/4_Trip_History.py`'s `FIELD_SPECS`
      gained a `("session_end_time", "Session end time", str)` entry,
      placed right next to the existing `"start_time"` ("Session start
      time") for the same session-level grouping, rather than down by
      the existing lure-level `"Lure end time"` entry.

    Verification: full suite still 316 passing (page-level change only,
    no core/ changes). The same scratch `AppTest` script that re-verified
    End Session's own reliability (above) also confirmed both rows a
    2-lure session produces carry a real `session_end_time` within the
    correct click window; that the lure retired early keeps its distinct,
    earlier `lure_end_time` while still getting the later
    `session_end_time`; that the lure still active at End Session time
    gets `lure_end_time == session_end_time` (both stamped together, as
    expected); and that Trip History actually renders the new "Session
    end time" label. Also re-ran the standing full-page smoke pass across
    the entry point and all 7 pages, clean. `data/trip_log.csv` confirmed
    matching `git show HEAD:...` exactly before and after the scratch run
    (the file's own md5 had shifted since entry 93/94's baseline simply
    because the angler's own live testing had genuinely added new
    committed rows in between - checked against the current HEAD, not a
    stale earlier-session snapshot, per the now-standing practice from
    entry 93). Logged as punch-list #34 and marked "Done."

96. **Punch-list #35: pressure trend is now computed per time-of-day
    segment, not once for the whole day.** Prompted by: "can you take a
    look at the 7 day forecast score (and anywhere the score is listed).
    There is a cold front coming through tonight at 4AM so I would have
    thought the scores would be a bit higher for this afternoon and
    evening ahead of the front."

    Root cause, confirmed by reading (not guessing at) `core/scoring.py`:
    `score_day()` computed `p_trend = pressure_trend_hpa_per_24h(bundle,
    noon)` exactly ONCE per day, anchored at 12:00 PM, then reused that
    single value for every one of the day's six segments (`_segment_score()`
    calls). So a front sliding through overnight, in the afternoon, or
    any time other than "was pressure already falling at noon" never
    triggered `_segment_score()`'s `pressure_falling` bonus for the
    segments it actually affected.

    Before touching anything, spent real effort ruling out a much simpler
    "just stale cached weather data" explanation, since a quick reproduction
    initially looked contradictory: the live app displayed "+0.3 hPa" for
    today's headline 24h pressure trend, but a fresh, exact-same-formula
    calculation against LIVE Open-Meteo data (pulled via `javascript_tool`'s
    real internet access in a Claude-in-Chrome tab open on the live app -
    this sandbox's own `bash` has no outbound network to Open-Meteo,
    confirmed failing with a proxy 403 both this session and previously)
    came back -1.7 hPa for the identical noon-anchored comparison - itself
    already past the falling-pressure threshold. Reproduced this three
    times (different lat/lon precision, different `past_days`/`forecast_days`,
    a full page reload of the live app to rule out a stale browser tab) and
    got a consistent ~-1.6 to -1.7 hPa every time, while the live app kept
    showing +0.3 hPa even right after a fresh reload - meaning the gap is
    real staleness in the app's own `get_weather_bundle()` (`@st.cache_data
    (ttl=60*60)`, server-side, shared across all sessions) against Open-
    Meteo's own model output shifting in the time since that cache last
    filled, not a browser-tab or reproduction-script artifact. Left the
    1-hour TTL itself alone (out of scope for this ask, and Home/7-Day's
    "at a glance" headline number staying a reasonably fresh once-an-hour
    snapshot rather than hammering Open-Meteo every page load is a
    deliberate, sane tradeoff) - flagging it here in case a future "why
    doesn't this match what I'm seeing on my phone" report traces back here.

    Also used that same live-data access to directly confirm the fix
    hypothesis before writing any code: recomputed the 24h trend anchored
    at each segment's own representative hour (Dawn ~6 AM, Afternoon ~4 PM,
    Night ~11 PM) instead of always noon, and got genuinely different,
    correctly-falling values for the segments after the front (Afternoon
    -2.2, Night -1.9) versus the still-flat segments before it (Morning
    -0.6) - confirming the per-segment approach would actually change the
    right segments' scores, not just add noise.

    **The fix.** `SegmentForecast` (`core/scoring.py`) gained its own
    `pressure_trend_24h: float` field. Inside `score_day()`'s per-segment
    loop, each segment now computes `pressure_trend_hpa_per_24h(bundle,
    segment_midpoint)` at ITS OWN midpoint (`start + (end - start) / 2`)
    and feeds that into `_segment_score()`, instead of the single
    noon-anchored `p_trend` shared by every segment. `DayForecast.
    pressure_trend_24h` (the day-level, noon-anchored number) is
    deliberately left alone and unchanged - it's still what Home/7-Day
    Forecast's "24h pressure trend" at-a-glance summary line shows; only
    each segment's own score and lure recommendation now use that
    segment's own trend. `pages/1_7_Day_Forecast.py`'s lure-recommendation
    call (`recommend(...)`) was passing `day.pressure_trend_24h` per
    segment too (same bug, different symptom - lure picks, not just
    scores) - switched to `seg.pressure_trend_24h`. Deliberately did NOT
    touch `pressure_trend_hpa_per_24h()`'s underlying 24-hour, same-hour-
    of-day lookback window itself - real Open-Meteo hourly pressure data
    for Nolin Lake confirmed a genuine ~12-hour semidiurnal atmospheric
    "pressure tide" layered under the real frontal signal, and that
    same-hour-24h-ago comparison is precisely what cancels the tide out;
    shortening the window would reintroduce that noise, not fix anything.
    Checked `manual_segment_score()`'s real caller (Spot Session's "right
    now" live score, via `realtime_context_from_bundle()`) for the same
    class of bug and found it already anchors at the actual current/entered
    time (`at_time or lake_now_naive()`), not noon - no change needed there,
    since it was never sharing one fixed-time value across multiple
    segments in the first place.

    Verification: added `test_score_day_computes_pressure_trend_per_
    segment_not_once_at_noon` to `tests/test_scoring.py` - a synthetic
    bundle where pressure steps down 3 hPa at exactly 3 PM today (a
    front, not a uniform trend) - asserting Dawn/Morning stay at 0.0
    (before the front) while Dusk/Night correctly show -3.0 and fire the
    "Falling pressure ahead of a front" note, which the old noon-shared
    value could never have produced. Also updated
    `test_manual_segment_score_matches_score_day_for_equivalent_inputs`,
    which fed `day.pressure_trend_24h` into `manual_segment_score()` to
    compare against Dawn's score - now correctly feeds `dawn.
    pressure_trend_24h` instead, since those two are no longer the same
    number. Full suite: 317 passing (was 316; +1 net test). A scratch
    `AppTest` run against the real `pages/1_7_Day_Forecast.py` (mocking
    `get_weather_bundle`/`get_inventory`/`get_spots`/`github_token` and
    `apply_freeze`, the same afternoon-front synthetic bundle as the new
    unit test) confirmed the actual rendered page's Dusk metric tooltip
    now reads "Falling pressure ahead of a front - bite often turns on."
    while Dawn's does not, and that the page still renders with no
    exception. No data files touched by any of this (core/pages/tests
    changes only) - `data/*.csv` md5s confirmed identical before/after
    the scratch run. Logged as punch-list #35 and marked "Done."

97. **Punch-list #36: fixed the "Search Cabela's" links (7-Day Forecast's
    lure suggestions, Lure Inventory's gap-filling cards) 404ing on
    Cabela's site.** The angler sent a screenshot: clicking through landed
    on Cabela's own "OOPS! The page you are looking for can't be found"
    page, with the search box showing literal `+` characters
    ("Gambler+Gambler+GOAT+Swim+Jig+-+Crappie+-+5/16+oz.") instead of
    spaces, and correctly guessed the `+` encoding was the problem.

    Investigated by actually driving Cabela's live site rather than
    guessing at a fix: `core.cabelas_lookup.search_page_url()` was
    building `https://www.cabelas.com/search?q=<quote_plus(query)>` - a
    plausible-looking but never-verified guess at their search route.
    Tested that exact URL live and found the real bug is bigger than the
    `+`-vs-`%20` encoding: `/search?q=Gambler` 404s even for a single bare
    word with no special characters at all - `/search` simply isn't
    Cabela's real search path. Found the actual route by typing "Gambler"
    into Cabela's own live search box and watching where the page actually
    navigated: `https://www.cabelas.com/SearchDisplay#q=Gambler` - a URL
    FRAGMENT (`#...`), not a query string (`?...`), since their search is
    a single-page-app view. That also explains the literal `+` the angler
    saw: a fragment isn't parsed as `application/x-www-form-urlencoded`
    the way a query string is, so `+` was never going to be read as a
    space there no matter how it got encoded - only `%20` reliably means
    space in a fragment. Confirmed the fix live with the angler's own
    exact query text (real result: "6 Results for 'Gambler Gambler GOAT
    Swim Jig - Crappie - 5/16 oz.'", top hit "Gambler GOAT Swim Jig" - the
    actual lure) and a second query containing a raw `/` in the middle of
    a word ("Strike King 3XD Chartreuse/Black" - real result: 5 relevant
    crankbait results, no encoding of the `/` needed).

    **The fix.** `search_page_url()` now builds
    `https://www.cabelas.com/SearchDisplay#q=<quote(query)>` -
    `urllib.parse.quote()` (percent-encodes spaces as `%20`) in place of
    `quote_plus()` (encoded them as literal `+`). Both existing tests
    (`test_search_page_url_url_encodes_the_query`,
    `test_search_page_url_handles_blank_query`) updated to check the new
    route/encoding instead of the old, wrong one.

    Verification: full suite 317 passing (same count - two tests updated
    in place, none added/removed, since this was a pure link-format bug
    with no new branch/edge case to cover beyond what those two tests
    already exercised). No data files touched (`core/cabelas_lookup.py`
    and its test file only). Logged as punch-list #36 and marked "Done."

98. **Punch-list #37: grounded lure recommendations in real, documented
    Nolin Lake fishing experience, and added a personal catch-history
    nudge.** The angler asked, in plain terms, how a suggested lure gets
    picked - "Ideally the recommendation is based on the data in the app
    plus known information about the lake and real bass fishing experience
    on the lake." Answered honestly first: the lure engine was, until now,
    entirely generic bass-biology/tackle-industry knowledge (upward strike
    bias, standard seasonal patterns) with zero Nolin-specific grounding
    except forage species and water color - trip history only fed the
    numeric activity-*score* weights (`core.calibration.py`), never lure
    choice. The angler's follow-up was direct: "influence the lure choice
    by my actual experience... pull in any real experience data for nolin
    lake... general information is really not all the helpful. Particularly
    if it is a lure that I don't have in my tackle box." Two clarifying
    questions (via AskUserQuestion) got answered: show the sourcing in the
    UI (not hidden), and be cautious with personal-history promotion, with
    the explicit added instruction to weight *where* a lure was used/is
    planned to be used, not just whether it was ever used anywhere.

    **Real Nolin Lake research, done before writing any code.** Used
    WebSearch/WebFetch to find actual documented Nolin experience rather
    than guessing: Omnia Fishing publishes a genuinely detailed,
    season-by-season largemouth bass pattern breakdown SPECIFIC to Nolin
    Lake (structure/lures/colors/depths/forage for pre-spawn through
    winter) at omniafishing.com/w/nolin-lake-2-fishing-reports/fishing-
    patterns - by far the best-structured real source found. Corroborated
    with two more independent real sources: a first-hand Nolin angler's own
    forum post (fishin.com "Nolin Lake Tips?" thread) describing bluff
    walls with nearby channels, ~45 ft dam-face points fished on drop shot,
    and dawn/dusk topwater ("the jumps") with poppers and white super
    flukes; and KDFWR's own official 2026 Fishing Forecast PDF, which calls
    out Nolin BY NAME with one specific tactical note - "During late spring
    through summer, best results are often at night." Also checked (and
    ruled out as too thin to use) fishbrain.com, lake-link.com, and
    fishingstatus.com - genuinely searched, not cherry-picked for
    convenient results. A real Nolin fishing guide's (Wyatt Pearman, via
    fishtips.com) paid-tip-content TITLES ("Winter time cranking," "Nolin
    Lake Summer Time Offshore Fishing") independently corroborated the
    Omnia data's winter-cranking and summer-offshore patterns without
    needing to buy the actual paid content.

    **core/lures.py's season branches rewritten** to lead with this
    Nolin-specific data instead of generic seasonal bass knowledge, with
    every source cited inline in the code comments AND in the rationale
    text a reader actually sees (not just buried in comments) - e.g.
    winter's rationale now reads "Nolin's own documented winter pattern
    (Omnia Fishing) targets rock piles/boulders near channel swings and
    deep-access points with long-pause jerkbaits and 7-12 ft crankbaits; a
    local Nolin guide's own paid tip content is literally titled 'Winter
    time cranking.'" Generic picks that weren't contradicted by any of this
    stayed on as second choices rather than being deleted outright, so a
    real pattern a source didn't happen to mention doesn't just vanish.
    Two lure categories new to this app's taxonomy - **Drop Shot** (15-45
    ft, bottom-style, sourced from the forum's ~45 ft dam-point tip) and
    **Soft Swimbait (paddle tail)** (2-12 ft, column-style, sourced from
    Omnia's post-spawn/fall data) - were added because the research
    surfaced them as real Nolin patterns with no existing home in the
    20-category taxonomy. Real Cabela's product entries for both (found via
    the same Coveo API call `core/cabelas_lookup.py` already uses, driven
    directly through the Chrome browser tab's real internet access since
    this sandbox has none) were added to `data/cabelas_picks_cache.csv` so
    punch-list #22's "not in your tackle box" fallback suggestions cover
    them too. `guess_category_from_text()`'s keyword map also got a real
    fix while touching this: "swimbait" used to route to
    `weightless_soft_plastic` (an honest workaround from before a real
    swimbait category existed, its own comment openly admitted as much) -
    now routes to the new `soft_swimbait`, while "fluke"/"soft jerkbait"
    correctly stay on `weightless_soft_plastic` (a genuinely different,
    darted-not-swum presentation); added a "drop shot" keyword too. Left
    `TRAILER_ELIGIBLE_CATEGORIES` alone (still `weightless_soft_plastic`,
    not swapped for the new `soft_swimbait`) - real existing tests lock in
    that choice and swapping it would be an unrelated behavior change to
    the trailer picker with no angler ask behind it.

    **Personal history: new `core/lure_history.py`, deliberately
    conservative.** `lure_track_records(trip_rows, situation)` scores each
    past trip against the CURRENT situation and - this was the key design
    fix after an early version's own test caught it - requires a real
    LOCATION match (same spot, or same structure type when no spot is
    known) as a hard gate, not just one contributor to a blended score;
    water clarity/light-level/water-temp closeness are tracked but never
    enough to qualify a trip on their own, matching the angler's explicit
    "where the lure was used... and where it is planned to be used"
    framing. A lure category only gets a track record once at least 2 such
    location-matched trips exist (`MIN_SIMILAR_TRIPS`, mirroring
    `core.calibration.py`'s "wait for a minimum sample" philosophy for
    score-weight nudging) - one lucky fish never promotes anything.
    `core.lures.recommend()` gained `trip_history`/`spot_id` parameters:
    for a lure category already in the season's first/second-choice picks
    with a matching track record, its `LureBlock.note` (an existing but
    previously-always-empty field - dormant since whenever it was added,
    never wired to anything) gets the real numbers ("📈 Your own history: 2
    of 3 similar trips landed fish, best 2.1 lb..."); for a fish-producing
    lure category NOT already in either tier, up to 2 get injected into
    second-choice with the same note, explicitly flagging "not currently a
    top seasonal pick... even if it's not in your tackle box yet" - the
    exact "before I decide to go out and buy that lure" case from the
    angler's own words. A lure tried enough times in a similar spot but
    never actually caught anything on never gets promoted, even though it
    clears the minimum-sample gate (a real unit test locks this in).
    `core.ui.render_lure_block()` now renders `block.note` as its own
    `st.info()` line at the top of each card, not buried in a caption -
    per the angler's stated preference (via AskUserQuestion) to see
    sourcing rather than have it silently blended in. Both real callers
    updated: `pages/1_7_Day_Forecast.py` passes `trip_history` (no
    `spot_id` - that page's "structure type" is a general Lake Setup
    selection, not a specific spot); `pages/6_Spot_Session.py` passes both
    `trip_history` AND `spot_id` (the actual spot being fished), for the
    strongest possible match. New cached `core.appstate.get_trip_history()`
    (5 min TTL, same reasoning as the existing `get_calibrated_weights()`)
    feeds both.

    Verification: added `tests/test_lure_history.py` (7 new tests covering
    the minimum-sample gate, the hard location-match requirement including
    the case that initially failed and drove the location-gate redesign,
    biggest-fish tracking, and the note text itself) and 5 new
    `recommend()`-level integration tests in `tests/test_lures.py`
    (no-history-passed behaves identically to before; an already-picked
    lure gets annotated; a fish-producing lure not in the season pattern
    gets injected with the right note; a lure with real matching history
    but zero catches never gets injected; history from a genuinely
    different spot/structure is correctly ignored) plus 3 new
    `guess_category_from_text()` cases for the swimbait/fluke/drop-shot
    keyword changes. One pre-existing test
    (`test_owned_lures_sort_before_unowned_within_each_tier`) had to be
    updated - it hardcoded winter's OLD first-choice order (football_jig
    first), which the Nolin-sourced rewrite legitimately changed. Full
    suite: 329 passing (was 317; +12 net new tests). A scratch `AppTest`
    run against the real `pages/1_7_Day_Forecast.py` (mocking
    `get_weather_bundle`/`get_inventory`/`get_spots`/`get_trip_history`/
    `github_token` and `apply_freeze`, with a synthetic 2-trip carolina_rig
    track record) confirmed the actual rendered page shows real "Your own
    history: 2 of 2 similar trips landed fish, best 2.5 lb..." info boxes
    on lure cards, not just in isolated unit tests. `data/*.csv` md5s
    confirmed identical before/after the scratch run except for the
    deliberate, real `data/cabelas_picks_cache.csv` addition (4 new rows,
    Drop Shot + Soft Swimbait picks). Logged as punch-list #37 and marked
    "Done."

99. **Punch-list #38: fixed a real crash in Tackle Box's "Scan a lure"
    flow.** The angler sent a screenshot: `streamlit.errors.
    StreamlitDuplicateElementKey` on the Tackle Box page when trying to add
    a lure, traceback pointing at `pages/5_Lure_Inventory.py` line 169 -
    `st.button("Use this", key=f"scan_pick_{cand['sku']}", ...)` inside the
    "Scan a lure" results grid. Root cause: `core.cabelas_lookup.
    search_lures()` can genuinely return the same SKU more than once for a
    single query - confirmed as a real Coveo behavior, not a caller bug (a
    product can apparently surface under more than one matched facet/
    variant grouping) - and the page keyed each result card's button
    directly by SKU with no de-duplication or index fallback, so two
    candidates sharing a SKU produced two Streamlit elements with the
    identical key, crashing the whole page render (not just that button).

    **The fix, at the source.** `search_lures()` (`core/cabelas_lookup.py`)
    now dedupes its mapped/filtered results by SKU before returning,
    keeping first-occurrence order (still "best match first," per the
    function's own docstring) - fixed once so every current and future
    caller of this function is covered, not just the one page that
    happened to surface the crash. `pages/5_Lure_Inventory.py`'s own
    button key also got `enumerate()`'d index added
    (`scan_pick_{idx}_{cand['sku']}`) as cheap defense-in-depth on top of
    the real fix - a key collision there is a full-page crash, not a
    cosmetic bug, so it's worth the extra safety margin even though the
    root cause is now fixed upstream.

    Verification: added `test_search_lures_dedupes_results_that_share_a_
    sku` to `tests/test_cabelas_lookup.py` (same monkeypatched-network
    pattern as the existing `search_lures()` tests in that file) -
    confirms a duplicate-SKU Coveo response comes back with the dupe
    dropped, first occurrence kept, order preserved. Full suite: 330
    passing (was 329; +1). A scratch `AppTest` run against the real
    `pages/5_Lure_Inventory.py` (mocking `get_inventory`/
    `anthropic_api_key`, with `scan_candidates` seeded directly in session
    state as two entries sharing a SKU - the exact pre-dedupe shape that
    crashed the real page, to prove the PAGE itself is robust regardless
    of where a candidate list comes from, not just that `search_lures()`
    happens to dedupe now) confirmed the page renders with no exception
    and both result cards' "Use this" buttons render distinctly. No data
    files touched. Logged as punch-list #38 and marked "Done."

100. **Punch-list #39: requested a fix for blurry iPhone camera captures
    in Tackle Box's "Scan a lure" flow.** The angler reported that photos
    taken with a computer's webcam were sharp enough for Claude to read
    the label text off, but the same "Take a photo" flow on an iPhone
    came out blurry - despite looking crisp in the moment the photo was
    snapped on the phone's own screen.

    **Root cause.** `st.camera_input()` (used by both the AI-scan flow at
    `pages/5_Lure_Inventory.py`'s "Take a photo" mode, and the manual
    "Add a lure" form's own photo field) is a browser `getUserMedia()`
    live-video-stream widget, not the phone's native camera app - it's
    fundamentally different from what `st.file_uploader`'s "Take Photo"
    option would use. On mobile Safari/iOS in particular, `getUserMedia()`
    is well known to often default to a lower or inconsistent resolution
    and to grab a frame from a continuous-autofocus video stream rather
    than triggering a discrete, full-resolution still-photo capture the
    way the native camera app does - a very plausible explanation for
    "looked crisp when I took it, came out blurry in the app." Confirmed
    via `inspect.signature(st.camera_input)` (Streamlit 1.61.1, the
    version this app runs) that the widget accepts a previously-unused
    `resolution: "480p" | "720p" | "1080p" | None` parameter, defaulting
    to `None` - which the widget's own docstring says lets the browser
    pick "a resolution determined by the browser," i.e. exactly the
    unpredictable/often-low-resolution behavior being reported. Reading
    the installed library's source (`streamlit/elements/widgets/
    camera_input.py`) confirmed `"1080p"` maps to a requested capture
    height of 1080px (`_RESOLUTION_TO_HEIGHT = {"480p": 480, "720p": 720,
    "1080p": 1080}`) and is sent to the browser as a "best-effort" request
    - the browser selects the closest resolution it actually supports,
    so this isn't a hard guarantee, but it's a real, low-risk request for
    a sharper capture instead of leaving it entirely up to the browser's
    own default.

    **The fix.** Added `resolution="1080p"` to both `st.camera_input(...)`
    call sites in `pages/5_Lure_Inventory.py` - the AI-scan flow's camera
    (`key="scan_camera"`) and the manual "Add a lure" form's own camera
    field - so both request the sharpest resolution the widget supports,
    on every device, not just iPhones. Also added a caption under the
    AI-scan flow's "Turn on camera" button noting that on some phones
    this in-browser camera can still come out softer than a normal photo,
    and suggesting "Upload a photo" → the phone's own "Take Photo" option
    (which does use the native camera app/sensor) as a fallback if a
    capture still looks soft after this change - since `resolution` is
    only a request, not a guarantee, and a full visual before/after
    comparison isn't something this sandboxed, camera-less dev
    environment could actually confirm.

    Verification: a scratch `AppTest` (mocking `get_inventory`/
    `anthropic_api_key`, driving the "Take a photo" radio option and the
    "Turn on camera" button for the AI-scan flow, and the manual form's
    own "Take a photo" radio option) confirmed both `st.camera_input`
    widgets render with no exception and their underlying proto now
    carries `resolution_height: 1080`, i.e. the parameter is correctly
    wired through to what the browser is actually asked for. Full test
    suite: 330 passing (unchanged - this is a UI parameter change with no
    new unit-testable logic of its own). No data files touched. Logged as
    punch-list #39 and marked "Done."

## Key design decisions & rationale

- **No proprietary chart scraping, ever** - bathymetry and thermocline
  defaults are built from verifiable public sources (USACE gauge, KY State
  Parks/GNIS, Census TIGER geocoding, KDFWR articles) or the angler's own
  recorded data, never from a commercial chart product, even one the user
  has personally paid to view.
- **Explainable, rule-based scoring/lure engine** - `core/scoring.py` and
  `core/lures.py` are intentionally not a black box; every weight/rule has
  an inline comment explaining the fishing-knowledge rationale.
- **Trip logging + lightweight self-calibration** - `core/calibration.py`
  compares catch-success rates between trips where a factor was present vs.
  absent, nudging default weights within a capped range only once enough
  samples exist per side (`MIN_SAMPLES_PER_SIDE=4`, `MAX_NUDGE_FRACTION=0.35`).
- **Git-based persistence, no external database** - trip logs and now
  Quickdraw survey CSVs are committed straight into the repo so Streamlit
  Cloud restarts don't lose data.
- **All "Lake Setup Options" are direct inputs, no optional/skip
  semantics** - per explicit user feedback, water temp, fish depth, and
  thermocline are always-active number inputs seeded with sensible
  defaults, not checkbox-gated or skippable.

## Known limitations / open items

- `core/bathymetry.py`'s `get_depth_at_ft()` selects a grid cell via
  `np.searchsorted` (nearest insertion point), not a true nearest-neighbor
  search - functionally fine once real Quickdraw data is dense along a
  traveled path, but worth tightening if single-point precision ever
  matters more.
- The real shoreline digitization (`data/nolin_shoreline.geojson`, entry 15)
  is only as good as its source color threshold - it was widened once
  already to catch a second water tint at the dam, but other spots on the
  two source quads could in principle have their own unusual symbology and
  end up as a small gap (filled only if within 250m of a channel anchor via
  the corridor fallback, otherwise just missing from the map rather than
  wrongly shown as land - a gap reads as "no data," which is a safe
  direction to fail in). If a user-reported spot looks wrong, check
  `core/shoreline.py`'s color thresholds against that specific area of the
  source GeoTIFFs first.
- Depth values away from the four verified anchors (Dam, Nolin Lake State
  Park, Wax, Dog Creek) are still a smoothstep ramp from shore to the
  nearest anchor's target depth, capped at ~180m - a modeling
  simplification, not a measurement, same caveat as always for anything
  that isn't Quickdraw/historic-topo real data. As of entry 16, this is no
  longer rendered as contour lines on the map (see below) but still backs
  `get_depth_at_ft`/`infer_structure_type` and the "Modeled depth" metric
  on the Lake Map page - both explicitly labeled as a rough guess now.
- (entry 16) No depth contour lines are drawn on the map - two attempts at
  deriving them from public data didn't hold up well enough to trust. The
  map's primary layer is now real bottom cover (`data/nolin_cover.csv`,
  `core/cover.py`) instead. This is intentionally a pivot away from trying
  to fix the depth-contour approach a third time, not a temporary gap -
  re-adding rendered depth contours would need either real survey data or
  a materially different modeling approach, not just another tuning pass
  on the existing one.
- `data/nolin_cover.csv` cells are only as good as the same color
  thresholds used for the shoreline work - same caveat as above about
  unusual symbology on the source sheets producing a gap (reads as no
  data, not wrong data). `n_px` in each row is a rough per-cell confidence
  signal (more classified source pixels = less noisy majority vote); low
  `n_px` cells near contour-line-dense terrain are the least trustworthy.
- Remaining phases of the hotspot-forecast strategy discussed with the
  user but not yet built: an old-channel/breakline reference line traced
  from the same pre-dam topo (tractable as a single line per branch, not a
  full depth surface), shoreline-curvature-derived points/coves (no new
  data needed, just geometry analysis on data/nolin_shoreline.geojson),
  wind/fetch exposure scoring per candidate spot using the real shoreline
  plus the existing weather integration, and a way for the user to drop
  pins for docks/brush piles/timber they know about (extending the
  Quickdraw pattern) - all queued, prioritize with the user before
  starting any of them.
- `data/quickdraw/` ships empty - no real survey data has been ingested
  yet. Next step is the user exporting their first Quickdraw trip and
  handing it over.
- Historic-topo bathymetry only covers the dam/channel anchor points
  (`data/nolin_channel.json`) plus two small coves at the western edge of
  the Bee Spring quad (`data/historic_bathymetry.csv`, ~27 points) - most
  of the lake is still the Gaussian channel model, now anchored to better
  depth values but not shaped by real contours off the channel centerline.
  Full automated contour digitization across the main basin was tried and
  abandoned (see dev log entry 13) - gaps in the historical scans break
  flood-fill region tracing past a small, clean area. Extending real
  coverage further means either: (a) the user filling in
  `nolin_depth_points_needed.csv` (delivered separately, not committed -
  ask the user if they still have it) with their own depth-finder readings
  at the listed low/medium-confidence points, which is the fastest path
  and reuses the existing Quickdraw blending, or (b) a more careful
  semi-manual digitization pass (hand-correcting contour line gaps in the
  problem areas before running the region-graph method) if someone wants
  to pick the automated approach back up.
- `pages/3_Log_a_Trip.py` uses a flat water-clarity dropdown (defaulting
  to "Brown stained") rather than the base-stain + stirred-up toggle used
  on pages 1 & 2 - intentional, since it's recording a historical
  observation for one specific day, not a live/ongoing condition toggle.
- Forage and thermocline values used during a forecast/map session aren't
  yet fed back into `core/calibration.py`'s weight-nudging - only pressure
  trend, moon phase, cloud cover, and wind currently participate in
  calibration.
- (entry 32) The new water-temp/water-clarity/forage/light-rain scoring factors
  aren't wired into `core/calibration.py` either, for the same reason as the note
  above - `_factor_flags()` only tracks the original five factors. Since these new
  ones are manual-entry-only (only ever populated via Spot Session logs, tagged
  `"source": "spot_session"` in `conditions_json`), extending calibration to cover
  them is a clean, scoped follow-up once there's enough spot-session log volume to
  make it worthwhile - not something this round did.
- (entry 21) All 40 existing `data/lure_inventory.csv` rows were auto-tagged with a
  best-guess `category` from product name/brand, not hand-verified item by item -
  spot-check on the Lure Inventory page (search/filter by category) and correct any
  that look wrong; a wrong category just means that item won't get matched to the
  right forecast suggestion, not a functional error. Any newly manually-added item
  defaults to "Not categorized / other" until you pick one.
- (entry 21) `medium_diving_crankbait` only ever gets suggested via the fish-depth
  swap (sonar reading in the 6-12 ft zone) - it has no seasonal first/second-choice
  picks of its own the way the other crankbait types do. If it should show up more
  often (e.g. as part of specific seasonal patterns rather than only a depth-driven
  swap), that's a follow-up worth doing deliberately (touching all 7 seasonal
  branches + their tests), not something this round did opportunistically.
- No automated CI - verification is manual: `pytest tests/ -q`, an
  `AppTest`-based smoke test across the app entry point and all pages
  (including sidebar interaction), and a fresh `git clone` + re-test before
  every push, done every round in this project.
- (entries 25/26) Color matching is keyword-based against each owned item's free-text
  `description` - it has no structured "color" field to work from, so it can miss a
  real match (and now, since entry 26, hide an owned item from a block entirely) if
  the description uses different wording than the suggestion (e.g. a synonym neither
  string shares), or very rarely flag an unrelated coincidental word match. If this
  turns out to be inaccurate often enough to be annoying, the more reliable fix is a
  structured `color` tag on inventory items (same pattern as the
  `category` field, entry 21) rather than tuning the keyword list further.
- (entry 27) The new saved-spot catalog (`data/lake_spots.csv`) is entirely disconnected
  from the recommendation engine right now - `location_type`/`bottom_structure` on a
  saved spot don't feed `core.lures.recommend()`'s `structure_type` input the way the
  Lake Map page's old structure-type picker used to. Wiring a saved spot's info into a
  recommendation (e.g. "get lure suggestions for this spot") would be a natural
  follow-up, not something this round did, since the request was specifically to
  replace the score/lure panel with spot info, not to also re-connect them.
- (entry 27) `nearest_spot_within`'s matching tolerance (~9-11m) assumes marker clicks
  report their exact stored coordinates, which holds for streamlit-folium's normal
  click behavior - but if two saved spots ever end up closer together than that
  tolerance, clicking one could resolve to the other. Not expected to come up in
  practice (real fishing spots are rarely that close together), but worth knowing if a
  future report describes "wrong spot's details showing up."
- (entry 29) The Spot Session page's activity score is an approximation, not a
  measurement: light condition stands in for cloud cover, the precipitation pick
  stands in for actual rain totals/storm probability, and pressure trend/solunar
  overlap only factor in when a weather forecast happens to be reachable at that
  moment (silently omitted, with a caption saying so, if not). It's meant to be "close
  enough to suggest a starting lure," not a substitute for the 7-Day Forecast page's
  API-driven numbers.
- (entry 29) The user's stated "ultimate" direction - retiring `pages/3_Log_a_Trip.py`
  in favor of the Spot Session log, and building a report database from accumulated
  logs to refine future forecasts/suggestions - was explicitly called out as future
  work, not part of this round. This round only made sure both logging paths write
  into the same `data/trip_log.csv` so that consolidation stays possible later;
  `pages/3_Log_a_Trip.py` and `pages/4_Trip_History.py` are untouched.
- (entry 31) The log form's "Color used"/"Trailer color" auto-fill copies the picked
  item's whole free-text `description` (e.g. `KVD Perfect Plastics Blade Minnow - KVD
  Magic, 4-1/2", 8-pack`), not an isolated color name - same underlying limitation as
  entries 25/26's color-match filtering (no structured `color` field on inventory
  items yet). It's pre-filled and freely editable, so trimming it down to just the
  color words before submitting is expected, not a bug.
- (entry 31) `core.activity_log.lure_can_take_trailer()` only knows a lure's trailer
  eligibility when it maps to a recognized `core.lures.LURE_PROFILES` category - a
  manually-entered lure name or an inventory item marked "Not categorized / other"
  always shows the trailer option (permissive default), even for something that
  obviously wouldn't take one (e.g. typing "topwater popper" by hand). Tightening this
  would mean guessing a category from free text, which this app deliberately avoids
  doing anywhere else.
- (entry 31) "Depth of water fished" in the log form is a plain number plus an
  independent free-text "or several depths tried" note, rather than a single control
  that switches modes - a deliberate simplification to avoid a `st.form` reactivity
  limitation (a mode-switching radio can't hide/show other form fields until the form
  is submitted) for a field that doesn't need live auto-population the way the lure/
  color picker does. Both fields are always visible and both optional.
- (entry 34) `core/spots.py`/`data/nolin_spots.json` (a small curated list of general
  reference spots from public sources, distinct from the angler's own
  `data/lake_spots.csv` pins) is now orphaned - its only real caller was the deleted
  `pages/3_Log_a_Trip.py`'s spot picker. `pages/1_7_Day_Forecast.py` still imports
  `get_spots` from `core.appstate` but never actually calls it (a dead import that
  predates entry 34). Left in place rather than deleted, matching this codebase's
  existing pattern of leaving unwired modules in place with a documented note (e.g.
  `core/bathymetry.py`) - either wiring it into a page again or removing it outright
  would be a deliberate follow-up, not an incidental cleanup.
- (entry 36) `core/thermocline.py` (`estimate_thermocline_ft`, `default_thermocline_input_ft`)
  and `core.lures.recommend()`'s `thermocline_ft` parameter / `thermocline_caveat` logic
  are now fully unreachable from any page's UI - Spot Session dropped its thermocline
  input in entry 32, and the 7-Day Forecast page dropped its own in entry 36, and
  neither page passes `thermocline_ft` to `recommend()` anymore. Only
  `tests/test_lures.py` still exercises the caveat logic directly. Left in place rather
  than deleted (same reasoning as the `core/spots.py` note above) since it's real,
  sourced domain modeling that a future page could wire back in without any changes to
  `recommend()` itself - just something to know if a report ever says "the thermocline
  caveat never shows up."

- (entry 57) Trip History's `st.data_editor` grid's actual touch/swipe
  behavior on a real phone hasn't been verified - this sandbox's Chrome
  automation `resize_window` tool doesn't actually shrink the rendered
  viewport (`window.innerWidth` stays at desktop width no matter what size
  is requested), and glide-data-grid (the canvas widget behind
  `st.data_editor`) computes its own pixel width via `ResizeObserver` at
  real layout time, which can't be forced the same way the metric-column
  reflow fix was verified (by constraining one element's own width via
  injected CSS). Worth a real-phone check; if horizontal swipe turns out to
  be unreliable, the "redesign as stacked cards on narrow screens" option
  (declined this round in favor of a lighter touch) is the fallback.
- (entry 57) A custom `manifest.json`/`apple-touch-icon` for Safari's "Add to
  Home Screen" isn't achievable through this repo's code on Streamlit
  Community Cloud - the real app only ever renders inside an iframe under
  Streamlit Cloud's own wrapper page, and that wrapper page (already shipping
  its own generic Streamlit-branded `apple-touch-icon`/`manifest.json`, not
  anything from this repo) is what Safari actually reads when bookmarking,
  since it's the top-level document. Would need a different hosting model
  (self-hosted, or a host that serves the app directly with no wrapper
  iframe) to customize.
- (entry 87) The `.gitattributes` `merge=union` fix for concurrent CSV
  appends does NOT catch a genuine same-row edit made from two devices at
  once during a rebase retry - it silently keeps both differing versions as
  two separate rows rather than blocking the push. Better than silently
  losing one save (the previous behavior), but if a duplicate-looking row
  ever turns up in Trip History, this is why - not a new bug.
- (entry 87) The "who's fishing" angler picker (punch-list #26) is a name
  tag, not authentication - nothing stops picking someone else's name, and
  there's no password. Fine for this app's private, small-shared-group
  deployment; would need real logins (`st.login()`/OIDC, the option
  declined this round) if that ever stops being true.
- (entry 90) This app cannot work with zero connectivity - every
  interaction is a live round trip to the Python server, by Streamlit's
  own architecture, so "keep working while fully offline" isn't achievable
  without rearchitecting this as a different kind of app entirely (native,
  or a from-scratch PWA with local storage + background sync). What
  entry 90 actually fixed is the practical consequence anglers hit in the
  field - a dropped/reconnected session no longer loses track of an
  in-progress Spot Session, since it's rebuilt from already-saved data. If
  the connection is down at the exact moment a button is tapped, that tap
  itself still just fails/spins the same as any web app would - there's no
  local queueing of an action taken while offline.
- (entry 90) A session reconstructed after a reconnect can't recover which
  inventory item_id a lure was (only its saved display label - `item_id`
  was never itself written to disk) - re-picking that same inventory item
  again after a reconnect won't be caught by the "already added" dedupe
  check the way it would in an unbroken session. Shows up as a harmless
  extra row for the same lure, not lost data; clean up via Trip History if
  it ever happens.

## Operating notes

- GitHub repo: `jjpvoskuil/Voskuil-Fishin-Magician`, branch `main`.
- Claude pushes directly via `git push` over
  `https://x-access-token:<PAT>@github.com/jjpvoskuil/Voskuil-Fishin-Magician.git`
  - the PAT is only ever used inline in that URL inside shell commands,
  never echoed back in a chat response and never committed to any file.
  **A fresh PAT should be provided each session** rather than reusing one
  from a prior conversation.
- Streamlit secrets (`GITHUB_TOKEN`) let the *deployed* app commit trip-log
  entries back on its own - separate from the PAT Claude uses locally
  during a dev session.
