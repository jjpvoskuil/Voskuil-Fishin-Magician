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
app.py                        Landing page - today at a glance
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
  `AppTest`-based smoke test across all 5 pages (including sidebar
  interaction), and a fresh `git clone` + re-test before every push, done
  every round in this project.

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
