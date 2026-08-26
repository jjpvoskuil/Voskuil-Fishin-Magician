# Voskuil Fishin' Magician 🎣

A 7-day largemouth bass fishing forecast app for **Nolin River Lake, KY**, built with Streamlit.

Picking this project back up in a new Claude chat? Use [`NEW_SESSION_PROMPT.md`](NEW_SESSION_PROMPT.md)
to kick things off, and see [`SESSION_NOTES.md`](SESSION_NOTES.md) for the full development history,
key decisions, and known open items.

## Using it on a phone

The app is usable from a phone browser, not just desktop. Two things that used to make it
rough on a phone are fixed: the sidebar's collapse/expand toggle is now a real, high-contrast
button (Streamlit's default is a tiny low-contrast arrow easy to miss on a touchscreen), and
wide multi-column rows (the 7-Day Forecast's day-by-day score row, its time-of-day breakdown,
and "Today at a glance") reflow into a readable stacked layout below a phone-width breakpoint
instead of squishing into unreadable slivers - see `core.ui.inject_mobile_css()`, called near
the top of every page. Trip History's punch-list #55 redesign replaced its old wide,
sideways-swiping `st.data_editor` grid with a stack of collapsed session cards (plain
widgets, same mobile-friendly pattern as Spot Session and the Development page) - no
horizontal scrolling needed to browse or edit a trip from a phone anymore.

Add the app to your home screen from Safari (Share -> Add to Home Screen) for a one-tap icon -
this works today at zero cost. One caveat: Streamlit Community Cloud serves the app inside an
iframe under its own wrapper page, and that wrapper page - not this repo - owns the `<head>`
Safari actually reads when you bookmark it, including its `apple-touch-icon`/`manifest.json`
(confirmed by inspecting the live app: both already point at Streamlit's own generic
`favicon_*.png`/`manifest.json`, not anything this repo could serve). So the home-screen icon
will carry Streamlit's default branding rather than a custom one - there's no code change in
this repo that can override it on this hosting.

## What it does

- **1-10 daily activity score** for largemouth bass, built from barometric pressure trend,
  moon phase, solunar major/minor windows, cloud cover, wind, and season/water-temp estimate.
- **"Today at a glance"** on the Home page - up to seven metric tiles in one compact row (smaller
  metric font than Streamlit's default so all seven fit across a normal page width - see
  `core.ui.inject_compact_metric_css()`): activity score, estimated water temp, moon phase, and
  24h pressure trend (all from today's weather-derived score), plus real USGS lake level and two
  tiles for the current USACE reading - dissolved oxygen (mg/l) and DO saturation % each get their
  own tile (surface water temp and the survey date are in each tile's hover text; USACE's own
  surface temp is charted below rather than tiled here, since "Est. water temp" already covers
  temperature on this row) - each of those last three is its own independent fetch, so a weather
  outage (e.g. Open-Meteo's free-tier rate limit) only removes the four weather-derived tiles,
  never hides lake level or the USACE tiles if either of *those* fetched fine. The two USACE tiles
  fall back to the most recent reading in `data/water_quality_log.csv` whenever the live fetch
  itself fails (the USACE report page has turned out to be unreachable from some hosting
  environments) - it's a periodic survey anyway, not something that needs a fresh successful fetch
  on every single page load to be worth showing, and each tile's hover text always states the real
  survey date either way, plus a note when it's showing that cached fallback rather than a
  just-fetched reading.
- **14-day trend charts** on the Home page ("📈 14-day trends", below "Today at a glance") - one
  expander with every trend on this page, not split across separate dropdowns: activity score,
  estimated water temp, and 24h pressure trend for the last 14 days (recomputed from the same
  weather data already fetched for today - `core.weather.fetch_forecast()` requests
  `HOME_TREND_CHART_PAST_DAYS` (14) days of real past weather alongside the forecast, so no extra
  live calls are needed), a real USGS lake-level trend covering the same window, and the periodic
  USACE water-quality survey - surface water temp, dissolved oxygen (mg/l), and DO saturation % -
  charted on its own real-survey timeline rather than forced onto the 14-day window (since that
  live USACE report only ever has the CURRENT reading, this app records its own local archive,
  `data/water_quality_log.csv`, git-committed like the trip log, every time it fetches a fresh
  survey, and charts it starting from the very first point - even a single real reading renders as
  a genuine chart rather than a "not enough data yet" placeholder - filling in further as USACE
  republishes, roughly every 1-2 weeks). `HOME_TREND_CHART_PAST_DAYS` is kept separate from
  `WATER_TEMP_TREND_PAST_DAYS` (5, the water-temp estimate model's own tuned trailing-average
  window - see `core/weather.py`) so changing one never silently retunes the other;
  `fetch_forecast()` requests the larger of the two. The two °F charts (est. water temp, USACE
  surface water temp) use a fixed 45-95°F Y-axis (`home.py`'s `TEMP_CHART_Y_DOMAIN`) instead of
  auto-scaling, so a real but small swing doesn't fill the whole chart height and read as more
  dramatic than it is - every other chart on this page still auto-scales. See
  `core.ui.render_line_chart()` for how the fixed range is drawn (a raw `st.altair_chart()` with an
  explicit `alt.Scale(domain=...)`, since plain `st.line_chart()` has no way to pin its Y axis).
- **Time-of-day breakdown** (Dawn / Morning / Midday / Afternoon / Dusk / Night) with the
  best window(s) to fish each day. Every window's real clock range tracks that day's
  actual sunrise/sunset: Dawn and Dusk are a real hour either side of sunrise/sunset,
  Night is whatever's left overnight, and Morning/Midday/Afternoon each get an equal
  third of the daylight left in between - so all six windows genuinely grow and shrink
  with the season instead of a couple of them sitting on fixed clock-time cutoffs.
  Today's scores update live as the weather forecast
  refreshes throughout the day - except a window whose end time has already passed, which
  locks in at whatever score it had the moment it closed instead of continuing to drift
  as later weather data comes in (a forecast for a time that's already over isn't a
  forecast anymore). That locked-in score, and the day's overall score recomputed to
  match, survive app restarts - see `core/forecast_freeze.py`.
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
  "🎯 Fish this spot now" to open a page dedicated to that pin, already selected - or
  open the Spot Session page directly and pick a saved spot from the "📍 Location"
  dropdown right at the top, no trip through the map required. That dropdown stays at
  the top even once a spot's loaded, so switching to a different saved spot is always
  one click away without going back to the map first. Pick a session date (defaults to
  today; pick an earlier date to log a past session) right under the spot name, then
  the page walks through one flow: enter conditions, get suggestions and pick your
  lure(s), start the session, log fish as you catch them, end the session.
  **Conditions** is a single consolidated block covering everything about right now
  and about how you're about to fish it (water temp, visibility/Secchi depth + stain
  color/stirred-up override, wind band + direction, sky condition, precipitation,
  forage seen, fish activity, forage activity, and the depth fish are showing up on
  electronics) - every weather-related field defaults from the live forecast the
  moment the block first appears (nearest-hour wind speed/direction, cloud cover, and
  precipitation from Open-Meteo, water temp from the same estimate the Home page
  shows), so there's normally nothing to type unless what you're actually seeing
  differs from the forecast - every field stays a normal, freely overridable widget
  either way, and whatever you've entered sticks around if you navigate away and back.
  Below that, a live **"Suggestions for right now"** panel (collapsed by default -
  expand it whenever you actually want to see it) shows the activity score (hover
  the ⓘ for the full factor-by-factor breakdown) and the same lure/color
  recommendation engine the 7-Day Forecast page uses, scored against the current
  moment as a rolling preview - no button to click, it just updates as you adjust
  conditions. Each recommended lure you already own shows a **"+ Add to session"**
  button right on its card - one click adds that exact item to a running "Lures for
  this session" list shown below (with its own "Remove", which also removes any
  trailer attached to it). Don't want a suggested one, or want more than one rod
  ready to switch between? An "➕ Add from tackle box" section offers the same
  searchable photo-card grid as before, except every card toggles "added" instead of
  picking just one, so you can queue up as many lures as you're bringing to the spot;
  a plain text box below it covers anything not in your inventory. Every tackle-box
  item is selectable here (punch-list #46) - including craw/creature baits and
  weightless soft plastics that can also ride as a trailer on another lure, since
  those are commonly fished on their own too (a Texas-rigged creature bait, a
  weightless fluke). Separately, adding any lure whose category can actually carry a
  trailer (jigs, chatterbaits, spinnerbaits, buzzbaits, swim jigs - crankbaits/
  jerkbaits/topwaters etc. skip this) still pops up an "Add a trailer?" dialog: check
  "used a trailer with this lure" and the same dialog switches to a trailer-only
  picker (your tackle box's trailer-eligible items only, or type one in by hand),
  then "Add lure" queues the pair together; "Cancel" backs out with nothing added.
  So a craw bait can end up in your session either as its own standalone lure pick,
  or nested as another lure's trailer, or (if you like) both at once as two separate
  queued entries - whichever matches how you're actually fishing it that trip. Once at least one lure is queued, **"▶ Start Session"** locks everything
  in: it stamps the real current time as the session's start time, re-derives the
  time-of-day window from that exact moment (e.g. "Dawn"), and writes one entry per
  selected lure to the trip log - your conditions snapshot, that start time, and an
  empty catch list on each. From there the page switches to an **active-session
  view**: one button per active lure (each showing a running catch count) alongside
  its own **"🔄 Change"** button, plus a collapsed "Retired lures" section for
  anything you've already swapped out. Land a fish? Tap the lure you were using - a
  popup opens with a weight slider (1 oz increments from "<1 lb" up through "4 lb 15
  oz", then an open-ended "+5 lb") with manual **lb**/**oz** text fields right next to
  it, and a length slider ("<13 in" through "26+ in") with its own manual **in** text
  field. Both pairs are two-way synced: dragging the slider updates its manual fields
  to match, and typing into a manual field snaps the slider to its nearest position -
  the 1-oz slider alone turned out too easy to overshoot by feel on the water, so the
  manual fields are the real precision entry (typing an ounce value of 16 or more
  carries over into pounds automatically, e.g. "20" oz becomes 1 lb 4 oz), with the
  slider as a fast rough starting point. The dialog also has a species dropdown
  (Largemouth/White/Smallmouth Bass, Crappie, Walleye, Catfish, or type in your own), a
  multiple-choice "Type of hit" field (Hard hit/Light hit/Double tap/Swallowed/Fouled/
  Surface hit - a strike can genuinely be more than one of these) shown as tappable
  pill buttons rather than a dropdown, so every option is always visible and reachable
  on a phone with nothing to scroll past, and retrieve
  style/speed. **"✅ Record"** saves that catch immediately (it's
  written and pushed to that lure's trip-log row right away, not batched until the
  session ends) and reopens a blank form so you're straight back to fishing; the
  button's catch count updates, and an expander under each lure lists everything
  logged on it so far (each with its own "Remove", in case of a mis-tap). Every
  catch is stamped with the real clock time it was recorded, shown alongside it
  both here and on Trip History's per-trip detail (e.g. "Largemouth Bass, 11:01 AM,
  3 lb 4 oz..."). Switching
  baits mid-session doesn't mean starting over: tap **"🔄 Change"** on the lure you're
  putting down and it retires from active use, stamped with the real time you swapped
  off it (its catches and time window stay exactly as logged); then use the "➕ Add a
  lure to this session" section (the same trailer-gated tackle-box grid/manual entry
  as session setup) to bring a new lure into the same ongoing session, with its own
  fresh start time logged automatically. When you're done at this spot, **"⏹ End
  Session"** stamps the real end time on every still-active lure's row (already-
  retired lures keep the earlier time they were actually swapped out at) and drops
  you back at a fresh, blank Conditions setup - ready for the next spot or the next
  session here later. It also stamps a session-level end time on every lure in the
  session (retired or not) - shown on Trip History as "Session end time," separate
  from each lure's own "Lure end time" - so there's a real record of exactly when
  the whole session was actually closed. Next to it, **"❌ Cancel Session"** does the opposite: it
  discards everything logged so far this session - every lure and fish it created -
  entirely, rather than keeping it, for testing sessions or just wanting a clean
  restart without any of it saved. It asks you to confirm first ("Cancel this
  session? ... can't be undone") since there's no way to get a canceled session's
  data back. Each lure still lands as its own row in the trip log (no
  combined/bundled entry), so Trip History's per-trip filtering and detail view keep
  working exactly as before; a "📋 Already logged for this spot" line above Conditions
  lists everything already saved for the selected date. It all writes into the same shared
  trip log the **Trip History** page reads from - Spot Session is the only way to log
  a trip; see "How the model works" below for the condition bands behind this page's
  inputs. Made a mistake on a past trip, or just want to fix it up? Corrections now
  happen entirely on the **Trip History** page itself (punch-list #55) - see that
  section below - rather than through a handoff back to this page.
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
  feed for either: your water surface temp reading (pre-filled from the forecast's
  estimate for today, so there's normally nothing to change here), and the depth
  you're marking fish at on your electronics (e.g. a Garmin Livescope/sonar unit,
  defaults to 8 ft) - these always drive the seasonal pattern used for lure selection
  and the depth-to-run/countdown guidance on every lure block. A **Location** dropdown
  lists your own saved spots (from the Lake Map page) - pick one and its structure type
  is filled in automatically, the same way Spot Session resolves it; pick "Other" to
  set a structure type by hand instead.
- **Water clarity as a real visibility reading (punch-list #49)** - the Lake Setup
  Options sidebar used to ask for water color as a plain three-way Clear/Green
  stained/Brown stained dropdown, with no actual visibility input; it now uses the
  same Secchi-depth model Spot Session's own condition form has always used
  (`core.onwater.resolve_water_clarity()`/`visibility_band()`): enter how far down you
  can see a light-colored object (defaults to 2.5 ft, Nolin's typical "Stained" band -
  1.5-4 ft), and a stain-color picker (Green stained vs. Brown stained) only appears
  when that reading actually lands in the ambiguous middle "Stained" band, since a
  Secchi reading alone can't tell green tint from brown tint. A reading above 4 ft
  resolves straight to Clear, below 1.5 ft straight to Muddy, no extra pick needed
  either way. A separate "stirred up / muddy right now" checkbox still always
  overrides straight to Muddy regardless of the reading, for right after wind or heavy
  rain, exactly as before. Same default (2.5 ft, Green stained when asked) as the
  three-way dropdown used to resolve to, so this is a more accurate input with no
  change to the out-of-the-box behavior.
- **Forage selector** - pick which baitfish/prey are actually available (Gizzard Shad,
  Threadfin Shad, Bluegill/Sunfish, Crawfish, Shiners/Minnows, Stonerollers). Nothing is
  pre-checked - an empty selection means "not specified" rather than assuming a forage
  base you didn't actually confirm. Nudges lure color/pattern choice toward what the
  bass are actually keyed on, and makes sure at least one forage-matched lure shows up
  in the recommendation.
- **Trip logging** - the Spot Session page's log section records what actually happened
  (lures, catches, water conditions, forage seen) so the model can calibrate its
  weights against your own results over time. Every lure and catch is saved the
  instant it happens, not batched until the session ends - so if a dropped
  connection (spotty cell coverage, phone locking mid-session) makes an
  in-progress session look like it reset, nothing you already logged was lost,
  and reopening the page at the same spot picks the session back up right
  where it left off ("Reconnected - picked this session back up..."). This app
  still needs a live connection to do anything - it can't work with zero
  signal - but a dropped-and-restored connection won't cost you your place.
- **Trip History (punch-list #55 redesign)** - one record per fishing *session*,
  not one per lure. A Spot Session run (▶ Start Session through ⏹ End Session,
  including any lure added mid-session) writes one trip-log row per lure fished, all
  sharing a real `session_id`; this page groups those rows back into a single
  session card so a multi-lure outing shows up once, not scattered across several
  rows. Trips logged before this redesign existed were retroactively grouped
  (matched by date + time-of-day window + angler, with a same-day time-gap check
  so two genuinely separate outings don't get merged - see SESSION_NOTES.md
  entry 118 for why); a handful of genuinely solo, one-lure
  trips still show as their own single-lure session. A **"🔄 Refresh from GitHub"**
  button at the top pulls the latest saved data on demand - this server only syncs
  automatically once, when it starts up, so if a trip you know was saved isn't
  showing up yet, press this before assuming something's wrong (see
  SESSION_NOTES.md entry 119). The page opens to
  just six filters - date range (pick a single date, a range, or today even before
  today's session is logged), time of day,
  location, angler, lure type, and specific lure, each defaulting to "all" - and
  stays empty until you press **"🔍 See Trips"**; after that, changing a filter
  updates the results immediately without pressing it again. Matching sessions show
  as a stack of collapsed cards (date · time of day · location · angler · fish
  count) - open one to see everything about it: date, time window, angler,
  structure type, every observed condition (water temp, clarity/stain/stirred-up,
  wind, sky, precipitation, forage seen, fish/forage activity, fish depth), and per
  lure - lure, color, technique, trailer, notes, and the full per-fish catch list.
  It opens read-only - nothing here is an editable field until you press
  **"✏️ Edit"** at the top, so just browsing a session can never accidentally
  change something in it. Edit swaps in the actual form (add/edit/remove fish,
  same fields as Spot Session's own "Log a fish" popup); a single
  **"💾 Save changes"** button saves every lure in the session at once (editing a
  shared condition like water temp applies it to every lure in that session, not
  just one), or **"Cancel"** discards whatever you typed and goes back to read-only
  without saving anything. **"🗑️ Delete this session"** stays available either way
  (it has its own two-step confirmation, so it doesn't need Edit first) - confirm
  it, then it removes every
  lure row (and every fish logged on them) for good. A few things stay read-only by
  design: location (remapping a spot isn't part of this), and predicted score /
  cloud-cover / wind-mph / pressure-trend / moon-phase, which stay exactly as
  originally computed rather than being silently re-scored from an edit. Fish
  weight displays as lb-oz (e.g. "3 lb 8 oz") everywhere on this page; type it that
  way or as a plain decimal ("3.5") when editing. The old wide `st.data_editor`
  grid, the "Edit this trip" handoff back to Spot Session, and this page's own
  summary metrics/calibration-status section are gone - rankings/totals live on the
  **Leaderboard** page instead.
- **Tackle Box (lure inventory)** - your tackle box, tracked: brand, full description,
  a category (matching it to one of the forecast engine's lure types), a photo, the
  last price paid, and how many you have on hand. Seeded from a Cabela's order history
  import; add more any time by typing them in or by uploading/taking a photo. See
  "Tackle Box (lure inventory)" below for details.
- **Inventory-aware lure suggestions** - every page that recommends lures (7-Day
  Forecast, Spot Session) checks each recommended lure against your tackle inventory:
  lures you already own are flagged (✅ "In your tackle box", with the specific
  brand/description/quantity **and a photo thumbnail** of the owned item(s)) and
  sorted to the top of each choice tier, while ones you don't have yet stay in the
  list underneath as pick-up suggestions (🛒). Nothing is added or hidden based on
  ownership - the season/structure/pressure/forage logic still decides what's
  recommended; ownership only decides what's flagged and what floats to the top.
- **Color-match filtering on owned lures** - within a lure block, owned items are
  further checked against that block's suggested color for today's water clarity, and
  only the ones whose description shares color/pattern words with the suggestion
  (e.g. "shad" in both "Green shad" and "Tennessee Shad") are shown as ✅ "Color
  match." An owned item in the same lure category but a different color (e.g. a
  green-pumpkin crankbait next to a chartreuse suggestion) isn't shown as a photo
  "match" for that block - but per punch-list #48 below, it's also not treated as
  if you don't own it: if you own the category but not today's color, the block
  shows an honest 🎣 "already in your tackle box, just not today's suggested
  color" note instead of the misleading 🛒 pick-up-suggestion treatment. Only when
  you own *nothing at all* in that category does the block fall back to the real
  🛒 pick-up-suggestion treatment.
- **Honest "wrong color" messaging, not "you don't own this" (punch-list #48).**
  A user reported the 7-Day Forecast showing Top-Water Walking Bait as recommended
  with a "not in your inventory yet" note, despite owning a Heddon Super Spook Jr.
  tagged exactly as that category. Investigation confirmed the categorization and
  color-match logic were both working as designed (Entries 25/26): the Spook's
  description is "Blue Chrome," and "Chrome/blue" is only a suggested color for
  Walking Topwater under "Clear" water - Nolin's default/typical conditions
  (Green/Brown stained, Muddy) suggest other colors instead, so the item correctly
  didn't show as a color-matched pick. The real bug was the *message*: owning zero
  of a lure type and owning one in the wrong color both collapsed into the same
  "not in your inventory yet" wording, which reads as "you don't have this bait"
  when the truth is "you have it, just not in this color today." Fixed by adding
  a new `LureBlock.owned_off_color_items` field (populated by
  `core.lures._split_owned_by_color()`) and a new UI branch that shows a distinct,
  accurate message for the "own it, wrong color" case - text-only, no photo
  thumbnail, keeping the anti-clutter design from Entry 26 intact for the true
  zero-ownership case.
- **Top-2-per-category capping, and real Cabela's buy suggestions when you own
  nothing that matches** - within a lure block, at most the top 2 color-matched
  owned items are shown (ranked #1/#2 by quantity on hand), not every match, so a
  category with a dozen color-matched items on hand doesn't dominate the card. When
  a lure block has *nothing* color-matched on hand, up to 2 real products from
  Cabela's (brand, name, price, photo, and a link to search for it on Cabela's own
  site) are suggested instead of the plain "not in your inventory" note, using the
  same `core/cabelas_lookup.py` integration the Tackle Box page's "Scan a lure"
  flow already uses (see "How the Cabela's lookup works" below) - cached for a day
  per lure name so the 7-Day Forecast page's ~28 recommendation calls (one per
  segment per day) don't each trigger a live lookup for the same handful of repeating
  lure names. Falls back to the plain pick-up note if Cabela's has no match or can't
  be reached, same fail-soft behavior as everywhere else this integration is used -
  that fallback note always includes a "Search Cabela's" link for the lure category
  even when the live product lookup itself fails (punch-list #21), since that link is
  just a URL (no network call needed) and Cabela's/Coveo's search API has been
  observed to work from a real browser while failing from this app's own
  server-side requests (the same kind of server-side-only network restriction seen
  with the USACE water-quality integration). Punch-list #22 added a second layer on
  top of that link: a small curated cache of 2 real product picks per lure category
  (`data/cabelas_picks_cache.csv`, captured via a real browser the same way the
  live lookup itself was confirmed still working) that the suggestion cards fall
  back to showing - with a note that they're saved picks, not a live check - whenever
  the live lookup comes back empty, so the block still shows real photos/brand/price
  instead of just a link. See "How the Cabela's lookup works" below.

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

**Pressure trend is computed per time-of-day segment, not once for the whole day.**
Each segment's 24h pressure trend is anchored at that segment's own midpoint (Dawn at
its own hour, Afternoon at its own hour, Night at its own hour, etc.) rather than
sharing one value computed at noon - so a front moving through overnight or in the
afternoon shows up as a falling-pressure bonus for the segments it actually affects,
instead of only counting if it happened to be falling right at noon. The 24-hour,
same-hour-of-day lookback window itself is unchanged (and deliberately not shortened) -
real Open-Meteo pressure data for Nolin Lake confirmed a genuine ~12-hour semidiurnal
atmospheric "pressure tide" is layered under the real frontal signal, and comparing
each hour against the same hour 24h earlier is what cancels that tide out. The
single day-level "24h pressure trend" number shown at a glance on Home/7-Day
Forecast's summary line is still the noon-anchored snapshot, unchanged - it's each
segment's own score and lure recommendation underneath that now reflect that
segment's own trend.

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
  blended from a trailing average of recent daily HIGH air temps and a seasonal baseline
  curve tuned against real logged Nolin readings. Always shown as an estimate in the UI.
- Lake level (pool elevation): a genuine live measurement, not an estimate - [USGS Water
  Services](https://waterservices.usgs.gov/) gauge 03310900 ("Nolin Lake near Kyrock, KY"),
  the one on the lake pool itself rather than the separate downstream river gauges. Shown
  on the Home page alongside how far above/below USACE's normal summer pool (515 ft) the
  lake currently sits.
- Surface water temperature + dissolved oxygen (real reading, secondary to the daily
  estimate above): [USACE Louisville District's periodic water-quality
  survey](https://www.lrl-wc.usace.army.mil/reports/wq/NRR.html) for Nolin Lake
  (`core/lake_water_quality.py`). This is a genuine measured reading at the "Dam Site"
  station's surface (0 ft), but only republished roughly every 1-2 weeks via a manual
  USACE survey, so it's shown on the Home page as a clearly-dated secondary caption
  ("measured 8/06"), not folded into the live/daily metrics. Dissolved oxygen is shown
  both as raw mg/l and as a computed saturation percentage (standard APHA/Elmore-Hayes
  polynomial + barometric correction for the lake's elevation).

  Other sources considered and ruled out for surface water temperature: lake-ready.com
  (a beta site that turned out not to actually publish water temperature anywhere on
  it, despite the name), USACE's modern CWMS Data API (Nolin Lake is registered, but no
  working/documented timeseries query was found), USGS's Water Quality Portal for the
  lake gauge (discontinued since 2017), and USGS site 03311000 (a live feed, but it's
  the tailwater/river gauge below the dam - cooler released water, not the lake's own
  surface).
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
- On-the-water condition bands (`core/onwater.py`), used by the Spot Session page: sky
  conditions/cloud cover (Clear/Sunny, Mostly Clear, Partly Cloudy, Mostly Cloudy,
  Overcast - the one band here that *does* follow a published public standard, the
  [National Weather Service's own oktas-based sky-condition terminology]
  (https://forecast.weather.gov/glossary.php?word=sky+condition), rather than a
  hand-picked scale), wind (mph - Glassy, Light Ripple, Moderate Chop/Action Trigger,
  Heavy/Turbulent), water visibility (Secchi depth - Clear, Stained, Dirty/Muddy), and
  water temperature (metabolic state - Cold/Lethargic, Pre-Spawn Transition, Peak
  Optimal Prime, Summer Stratified, Extreme Thermal Load) - everything except sky
  conditions is supplied by the angler from general bass-biology reference bands, not
  derived from a Nolin-specific source. Sky conditions replaced an earlier lux-based
  "Light conditions" scale (Night/Crepuscular/Overcast-Diffuse-Day/Direct-High-Sun) that
  conflated time-of-day light level (already captured separately by the "Time window"
  field) with actual cloud cover (this field's only real downstream use - it drives the
  same `avg_cloud_pct` input a real forecast's cloud-cover reading would) - see
  `core/onwater.py` for the full rationale. As of punch-list #49, the water-visibility
  band (`resolve_water_clarity()`/`visibility_band()`) is shared with the 7-Day
  Forecast page's own "Lake Setup Options" sidebar too - see "Water clarity as a real
  visibility reading" below.

## Trip logging & calibration

Logged trips are stored in `data/trip_log.csv`, inside the repo itself - no external
database required. When a `GITHUB_TOKEN` secret is configured (see below), each new log
entry is also committed and pushed back to this repo, so it survives Streamlit Cloud app
restarts/redeploys. Without a token, entries still work but only persist for that
session.

Every push (trip log, inventory, saved spots, punch-list, water-quality log, angler
roster) goes through `core.storage.commit_and_push()`, which retries a failed push
instead of giving up on the first try: a rejected/non-fast-forward push (another device
saved in the moment between this one's own last fetch and its push) fetches, rebases
onto the latest remote commit, and tries again; a plain transient network failure
(dropped connection, DNS hiccup, GitHub's edge returning a 5xx - all expected sometimes
when this app is used standing at the lake on spotty cell signal, punch-list #58) gets
the same kind of automatic retry with a short backoff between attempts, no fetch/rebase
needed since nothing about the remote actually changed. Either way it's a few attempts
before giving up and telling you to retry yourself. `.gitattributes` marks every
`data/*.csv` file `merge=union`, so two independent appends to the same file (the common
case - two people logging separate trips) rebase cleanly without a real conflict; a
genuine same-row edit from two devices at once isn't caught by that rule and will
silently produce two rows rather than blocking, so if that ever happens, check Trip
History for a duplicate rather than assuming one save quietly overwrote the other.

**Autosave, and what happens when a save can't reach GitHub (punch-list #58).** Every
fish you log, lure you add, and lure you retire already writes to `data/trip_log.csv`
and pushes immediately - not batched until the end of the session - so nothing you've
already logged depends on this page staying open or your connection staying up.
What used to be a real gap: if a push failed for any reason OTHER than a rejected
push (a dropped connection, GitHub having a bad moment), nothing ever tried it again -
the save just sat committed on this device only, invisible and harmless right up until
the app process itself restarted (a real code deploy, or a resource-limit restart with
no code change involved at all - suspected cause of a real incident: an hour-long Spot
Session lost every fish it had logged, because none of it had ever actually reached
GitHub, and reconnecting found nothing to pick back up from). Two things close that
gap now: every push attempt itself retries harder (see above), and while a session is
in progress, Spot Session runs a quiet background check every 30 seconds
(`st.fragment(run_every=30)`) that retries any push still stuck locally-only - no tap
required. If a save is currently stuck, a persistent (not a toast - easy to miss
mid-cast) warning banner appears at the top of the session with a "🔁 Retry save now"
button, so you always know when something hasn't backed up yet instead of assuming
silence means success. This can't do anything about data that was only ever local to a
process that's already gone by the time it's retried - the fix for that is making the
push itself as resilient as reasonably possible before that can happen, which is what
this actually does. A genuinely dropped connection at the exact moment you're mid-form
(typing a fish's weight, not yet tapped "✅ Record") is still a real gap - see "Known
limitations" below and entry 90 in `SESSION_NOTES.md` - this app has no offline queue,
by Streamlit's own live-round-trip architecture.

**Who's fishing.** The Spot Session page opens with a "🎣 Who's fishing" picker -
John, Matthew, Alex, or "Other" (type in a name, which is then remembered as a real
dropdown choice from then on - see `data/anglers.csv`/`core/anglers.py`). This is a
lightweight name tag, not a login - no password, nothing prevents picking someone else's
name - and it's remembered for the rest of your browser session so you don't have to
re-pick it every time you log something. Every trip you log is tagged with whoever was
picked, and Trip History has an **Angler** filter/column so you can see your own trips,
someone else's, or everyone's combined - all trips still land in the same shared log for
calibration and analytics either way.

**Independent sessions per angler (punch-list #47).** If more than one of you is
fishing the same spot at the same time (each on your own phone), each name picked in
"Who's fishing" gets its own completely independent session: its own Start Session,
its own lure buttons/fish logging, its own "⏹ End Session" and "❌ Cancel Session." One
angler ending or canceling their session never touches anyone else's still-in-progress
one at that same spot - if someone else has one open, a caption says so right on the
page. This also fixed a real bug: reconnecting after a dropped connection or a locked
phone used to reload "the" one active session for a spot regardless of whose it was
(picking up whichever one had started more recently), so one angler's own reconnect
could land them on a different angler's session, and ending it from there really did end
the wrong one. Reconnecting now always restores *your own* named session specifically.

**"Who's fishing" survives a reconnect too (punch-list #51).** Punch-list #47 above
fixed which *data* a reconnect picks up; it didn't fix what could feed it the wrong
angler in the first place. The "Who's fishing" picker used to live only in
`st.session_state`, which is wiped by anything that resets your browser's connection to
the app - most notably, Streamlit Community Cloud auto-redeploying (see "Deploying on
Streamlit Community Cloud" below). At the time, every save in this app - anyone's, not
just yours - pushed to `main` (the branch that triggers a redeploy); punch-list #52
right below changed that. When a reset hit, the picker silently fell back to
`angler_options[0]`, which is always "John" (the first row in `data/anglers.csv`) - so a
reconnecting angler could briefly *be* John as far as the app was concerned, and see
John's active session/lures instead of their own, until they noticed and re-picked their
own name. The picker now also carries its value in the page's URL (the same pattern the
spot picker and "edit this trip" already used), so a reconnect restores *you*,
automatically, regardless of what reset the connection.

**A fresh visit no longer silently becomes someone else's session, and anyone can
"just watch" instead (punch-list #59).** Punch-list #51 fixed the picker's fallback for
*your own* reconnect; it didn't cover a genuinely fresh visit with no identity attached at
all - a bare or bookmarked link, someone else's phone, a family member checking in. That
case used to fall back to `angler_options[0]` too (always "John"), landing that visitor
directly on the real angler's live session as if they *were* that angler - one tap on
"⏹ End Session" (which has no confirmation step) or "❌ Cancel Session" could end or
delete a session that wasn't theirs, with no warning to either person. Now, a fresh visit
with no established name or watch link shows an explicit landing choice instead of ever
guessing: pick your own name to start fishing (anyone who already has a session going
here right now is left off this list entirely, so you can't pick your way into someone
else's session by accident), or choose **"👀 Just watching"** to follow someone else's
live session read-only - no login, no buttons that change anything, and it auto-refreshes
every 20 seconds so new catches show up on their own. If more than one angler has a
session open here at once, watching asks which one. Typing an already-active name into
"Other" (the one path this can't outright hide, since it's free text) warns you and
requires an explicit confirmation click rather than silently granting access - the
deliberate-click still lets the real angler reclaim their own session by name if they've
somehow lost their URL-based identity, without letting anyone else in by accident. Once
you've picked a name, everything works exactly as before (punch-list #47/#51 above).

**Sessions dropping less often (punch-list #52).** The other half of the fix above: every
data save now pushes to a separate `data` branch instead of `main`, so a routine save
(logging a fish, adding a lure) no longer restarts the app for every connected angler -
see "Deploying on Streamlit Community Cloud" below for how that's wired up. A real code
deploy (or a platform-level restart outside this app's control) can still reset
connected sessions, same as before - punch-list #47/#51 mean an already-started session
recovers correctly when that happens.

**Setting up a session survives a reset too (punch-list #53).** Punch-list #52 made
restarts rarer; this closes the remaining gap for the case that's left - a session you
were still *setting up* (hadn't hit "Start Session" yet) used to be lost completely if a
reset hit while you were mid-conditions-form or mid-lure-picking, with nothing on disk
yet to recover from. The conditions form and whatever lures you've queued so far are now
also carried in the page's URL (the same trick as "Who's fishing"), kept in sync as you
go, so a reconnect at any point - even before picking a single lure - restores exactly
where you left off instead of a blank form. Clears itself automatically once you actually
hit "Start Session," since the session is durably saved from that point on anyway.

**Conditions can change mid-session (punch-list #49).** Fish/forage activity and wind
can shift fast once you're actually out there, so an active session now has its own
"🔄 Conditions changed? Get updated suggestions" panel (right below the lure list,
above "➕ Add a lure to this session") - a live preview, not a form you submit: adjust
fish activity, forage activity, wind, or sky conditions and the score plus lure cards
(with the same per-lure "why" from above) refresh immediately, no page reload needed.
Tapping "🔄 Update conditions" is a separate, deliberate step: only then do the shown
values get baked into the session's own conditions, so any *new* lure you add from that
point on - from this panel or from "➕ Add a lure to this session" below it - carries
them forward; lures you already added keep exactly what was true when you added them,
untouched. Water clarity, water temp, and fish depth are deliberately left out of this
panel and stay whatever they were at Start Session - those don't swing session-to-
session the way activity and wind do, and changing them mid-session would call the
whole session's premise into question in a way this panel isn't meant to. The updated
lure recommendation cards live in their own **"🎣 See updated lure suggestions"**
sub-section, collapsed by default (punch-list #56) - the score updates live without
opening it, and "🔄 Update conditions" sits right below the score rather than inside
that sub-section, so a quick "just log this new reading, keep fishing what I've got"
update never requires scrolling past a full lure list you didn't ask to see.

`core/calibration.py` compares catch outcomes between trips where a given factor (e.g.
"falling pressure") was present vs. absent, and nudges that factor's weight - capped at
+/-35% of its default - once you've logged at least 4 trips on each side. See the **Trip
History** page in the app for calibration status.

**Every reader of a trip's saved conditions is hardened against a malformed row now
(punch-list #60).** `conditions_json` is free-text JSON, not schema-validated - a
hand-edited CSV, a legacy row, or a future bug elsewhere could in principle leave
something in that column that's valid JSON but not an object (a bare number, string,
list, or null). Several places (the personal-history lure track record, calibration,
Trip History, Leaderboard, and Spot Session's own "does someone already have a session
open here" check) each used to parse that column with a try/except that only caught a
genuine JSON parse *error*, then called `.get(...)` on whatever came back with no check -
a row shaped like that would raise an uncaught error rather than just being skipped like
any other unusable row. All of them now go through one shared `core.storage.
parse_conditions()`, which always hands back a dict. Found while investigating a
"briefly flashed an error, didn't stop anything" report from a real session - current
data has no rows shaped that way, so it couldn't be reproduced end-to-end against real
data, but the defect itself was real and is fixed regardless.

## Leaderboard (punch-list #54)

Ranks your logged trip history (same source as Trip History) a bunch of different ways -
pick a category, optionally filter to one angler and/or species, pick a sort direction and
how many rows to show, and see the ranked list plus a quick bar chart. Fourteen categories
across five groups:

- **Fish:** biggest fish (by weight), longest fish (by length), biggest fish by species
  (one row per species, not a top-N ranking - a quick "what's the best of each kind"
  summary).
- **By lure:** most fish caught, best fish-per-use rate (total fish ÷ times that lure's been
  used - the "Uses" column is right there so a rate from one lucky use doesn't read as
  reliable as one from twenty), biggest single fish caught.
- **By spot:** the same three, by location instead of lure.
- **By angler:** the same three, by "Who's fishing."
- **By day / by trip:** most fish caught in a single day (with who caught them, when more
  than one angler contributed), and most fish caught on a single lure use (one trip_log
  row).

The Angler filter is hidden (not just left at "All") on the three "by angler" categories,
since filtering to one angler while ranking by angler would be a redundant no-op. The
Species filter only applies to the three fish-level categories above - trips logged before
the Spot Session redesign have no per-fish species detail at all, only a flat fish-count
column, so filtering the lure/spot/angler/day aggregates by species would silently make
older trips disappear from those rankings with nothing to explain why. Read entirely from
`data/trip_log.csv` (via the same cached `get_trip_history()` every other page uses) -
this page never writes anything.

## Tackle Box (lure inventory)

The **Tackle Box** page (`pages/5_Lure_Inventory.py`) is a tackle inventory tracker
that also feeds the forecast/recommendation engine (`core/lures.py`) - the two stay
loosely coupled through a single `category` field rather than sharing internals. For each lure
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
- **Manual entry** - add a lure any time with brand, description, price, quantity,
  category, and package qty (see below), and optionally attach a photo you upload or
  take right there with your camera. These photos are yours, so they're stored under
  `data/lure_images/` and committed to the repo like any other user data.
- **Scan a lure (photo -> Cabela's lookup)** - take or upload a photo of a lure's
  package in the "📷 Scan a lure" section at the top of the page. The webcam only
  turns on when you explicitly click "📷 Turn on camera" after choosing "Take a
  photo" - it never activates just from opening this page or expanding this
  section, and it turns itself back off the instant you capture a shot, click
  "Turn off camera," or collapse the section. Claude's vision (`core/lure_vision.py`)
  reads the brand/product name off the label, that guess becomes a search query
  against Cabela's own product catalog (`core/cabelas_lookup.py`),
  and you're shown the real matching product(s) - photo, brand, description, SKU,
  price - to pick from. Picking one shows an editable confirm form (category
  pre-guessed the same way the import batches above are, everything else editable)
  before anything is saved - nothing is added automatically. If the SKU already
  matches something in your inventory, confirming bumps that row's quantity instead
  of creating a duplicate, same rule as the order-history/cart imports above. This
  needs an `ANTHROPIC_API_KEY` in Streamlit secrets (see `secrets.toml.example`) -
  without one, this section just explains that and stays otherwise out of the way;
  manual entry above still works regardless. See "How the Cabela's lookup works"
  below for how the product search itself works and its limitations.
- **Search Cabela's by description (punch-list #41)** - no photo needed: the
  "🔍 Search Cabela's by description" section (between "Scan a lure" and "Add a
  lure") takes a typed description - brand, name, color, size, whatever you know -
  and searches Cabela's own catalog directly with it (`core/cabelas_lookup.py`,
  the same lookup the photo-scan flow uses), then shows the same pick-a-match ->
  confirm-details flow as scanning a photo does. Since there's no photo or
  Claude-vision step involved, this works even without an `ANTHROPIC_API_KEY`
  configured. Items added this way are tagged `source="Cabela's search"` in your
  inventory, distinct from `"Scanned photo -> Cabela's lookup"` and `"Manual"`, so
  it's still clear later how each lure was actually added.
- **In-app camera photo quality (punch-list #39)** - both "Take a photo" camera
  widgets on this page (the "Scan a lure" flow above, and manual entry's own photo
  field) now explicitly request `resolution="1080p"` from the browser. Streamlit's
  in-browser camera is a live-video-stream widget (`getUserMedia`), not your
  phone's native camera app, and without a requested resolution the browser picks
  one on its own - often lower/less sharp on mobile Safari than what a phone's own
  camera app would capture, which is why a photo that looked crisp when it was
  taken could still come out too blurry for label-text recognition. Requesting
  `"1080p"` is best-effort, not a guarantee (the browser uses the closest
  resolution it actually supports) - if a capture still looks soft, try "Upload a
  photo" instead and use your phone's own "Take Photo" option, which does use the
  native camera/sensor.
- **Manual entry's photo picker lives outside its form (punch-list #40)** - the
  Photo radio and the upload/camera widgets it controls sit above the
  `st.form(...)` in the "➕ Add a lure" section, not inside it. Streamlit forms
  only rerun the page when their submit button is clicked, so a radio button
  changed inside a form doesn't redraw anything until submit - selecting "Take a
  photo" there used to silently do nothing visible. Moving those widgets outside
  the form (same pattern as "Scan a lure" above) makes the camera appear the
  instant you select "Take a photo," the same way it does everywhere else in the
  app.
- **Fixed a manual-add submit crash (punch-list #42)** - the punch-list #40 fix
  above tried to reset the Photo radio back to "Upload a photo" after a
  successful add by directly assigning to its `session_state` key, which
  Streamlit forbids once that widget has already rendered in the current run
  - every manual add crashed with `StreamlitAPIException` as a result. Fixed by
  popping (deleting) that key instead of assigning to it, so the radio falls
  back to its own default on the next render with no forbidden assignment.
- **Package qty (punch-list #43)** - every way a lure gets added (manual entry,
  "Scan a lure," "Search Cabela's by description") and each card's Edit expander
  now has a "Package qty (lures per package)" field, defaulting to 1. It's
  purely a note of how many individual lures came in one retail package (e.g. 8
  for an "8-pack") - it's never multiplied into **Quantity**, which still means
  exactly what it always has (how many units of this row you have on hand).
  Cards show a "(N-pack)" note next to Qty whenever `package_qty > 1`. The 51
  rows that already existed in `data/lure_inventory.csv` before this field was
  added were automatically migrated to `package_qty=1` the first time the app
  ran after this update (same one-time-rewrite approach used when the
  **Category** column was added) - nothing else about those rows changed.
- **In-app camera default is the front (selfie) camera (punch-list #45)** - after
  a report that photo quality was still poor even with `resolution="1080p"`
  requested (punch-list #39), digging into Streamlit's own bundled front-end code
  (`streamlit/static/static/js/CameraInput.*.js`) turned up the real cause:
  `st.camera_input()` opens with `facingMode: "user"` (the front/selfie camera)
  by default, and there's no parameter in this Streamlit version's Python API to
  change that default - the only way to get the back camera is the small
  flip/switch-camera icon inside the widget itself, which is easy to miss. A
  phone's front camera is meaningfully lower-resolution and has weaker
  autofocus than its back camera on virtually every phone, which fully explains
  why requesting a higher capture resolution alone didn't fix soft/blurry
  photos - a higher-resolution capture from the *wrong, lower-quality* camera
  is still a low-quality photo. (Confirmed the resolution request itself is
  working as intended: the same front-end code forces the screenshot to use
  the camera's full native capture size, rather than the widget's on-page
  display size, whenever a `resolution` is set - so this needed a UX fix, not
  a resolution fix.) Since there's no way to default the widget to the back
  camera from Python, both "Take a photo" camera widgets (the "Scan a lure"
  flow and manual entry's own photo field) now carry an explicit caption
  telling you to tap the flip/switch-camera icon before shooting, and the
  existing "still looks soft? try Upload a photo" guidance now also explains
  *why* - not just that it can happen.

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

### Fill your tackle gaps

The "🎯 Fill your tackle gaps" expander (above the inventory grid) checks every lure
type this app knows how to suggest for Nolin Lake - all of `core/lures.py`'s
`LURE_PROFILES` categories - against what's actually in your inventory, and lists the
ones you own nothing of (`core.lures.find_inventory_gaps`). Trailer styles aren't a
separate list here: craw/creature (Texas-rig creature) and paddle-tail (weightless soft
plastic) trailers are themselves entries in `LURE_PROFILES`, same as any crankbait or
jig, so this single gap check already covers "lure types and trailers" together. A
category with quantity 0 in every matching row still counts as a gap, same as owning
none at all.

Each gap shows up to two real Cabela's products worth considering (via the same
`core.appstate.get_cabelas_suggestions` lookup and card layout the forecast page's "not
in your inventory yet" suggestions use), with a "Search Cabela's" link that opens that
product's live search results in a new tab. There's no way for this app to add
something to your cart directly - Cabela's product search doesn't expose a stable
per-product URL to link to (see "How the Cabela's lookup works" below), and a
server-side app has no access to your own logged-in Cabela's session to place items in
a cart on your behalf - so the honest version of "shop this gap" is one click to their
search results, with the actual add-to-cart click staying on their site. If you own at
least one of every suggested lure type, this section just shows a "nothing to fill"
success message instead.

### How the Cabela's lookup works (and its limits)

Cabela's search results are rendered client-side by JavaScript, so there's no plain
HTML page to fetch/parse for product data. Instead, `core/cabelas_lookup.py` calls the
same two JSON endpoints the site's own search box calls: it fetches a short-lived,
anonymous, read-only search token from a first-party Cabela's endpoint (no login
involved - it's the same token any visitor's browser gets), then POSTs that token to
Coveo's public search REST API (the third-party search platform Cabela's site search
runs on) with a plain text query, and gets back real product data - brand, name,
price, SKU, category, photo - as JSON. This was confirmed by inspecting Cabela's own
site's network traffic while searching, not from any published/documented API, so
there's no guarantee it keeps working: if Cabela's changes how their search works or
starts blocking non-browser traffic, these calls will start failing. Every function in
that module fails soft (returns `[]`, never raises) specifically so a lookup failure
just falls back to "no matches found" in the UI and the manual "Add a lure" form still
works - it never breaks the page. If scanning stops finding matches, that module is
the first place to check.

**Punch-list #38:** `search_lures()` also dedupes its results by SKU now - confirmed
live that Coveo can genuinely return the same product twice for one query (a real
crash report: the Tackle Box page's "Scan a lure" results grid keys each "Use this"
button by SKU, so a duplicate SKU crashed the whole page with `StreamlitDuplicate
ElementKey`). Fixed once at the source so every caller is covered, with the affected
page's own key also made index-safe as cheap defense-in-depth.

**Punch-list #21 finding:** confirmed by calling both endpoints directly from a real
browser that Cabela's/Coveo's search API itself still works exactly as this module
expects (same token shape, same request/response shape, real product data back) - but
the live 7-Day Forecast and Spot Session pages were showing no suggestions at all in
this app's actual deployment. That means the *lookup* is fine but this app's own
server-side requests to it (from Streamlit Community Cloud) are apparently being
blocked or filtered somewhere between the two - the exact same "works from a browser,
fails from this app's own server" pattern already seen with the USACE water-quality
site. `_BROWSER_HEADERS` now also sends `Accept`/`Accept-Language`/`Referer`/`Origin`
headers a real browser tab would send (previously only `User-Agent`) as a best-effort
improvement, but if the real cause is TLS/network-level fingerprinting of the
underlying HTTP client rather than header content, no header change fixes it - which
is why the "not in your inventory" fallback (see above) now always shows a working
"Search Cabela's" link regardless of whether the live product lookup succeeds, so
there's always something useful there even if this integration stays blocked
indefinitely.

**Punch-list #22 follow-up:** with the link-only fallback in place, essentially every
lure block was hitting it - the live lookup was failing 100% of the time in
production, not intermittently. Two changes: (1) `core/cabelas_lookup.py` switched
from the plain `requests` library to `curl_cffi` (`impersonate="chrome124"` on both
calls), which can spoof a real Chrome browser's actual TLS/JA3 handshake, not just its
headers - a plausible explanation for why a browser-like User-Agent alone wasn't
enough, since bot-mitigation systems commonly fingerprint the TLS layer itself. This
is still not guaranteed to fix it (if Cabela's/Coveo is blocking by IP/network
reputation instead, no amount of header or TLS spoofing helps), so (2) a safety net:
`data/cabelas_picks_cache.csv` holds 2 real, curated Cabela's picks (SKU, brand,
description, price, photo) for each of the 20 fixed lure category names
`core.lures.LURE_PROFILES` can ever produce - captured via the same real-browser
method that confirmed the live lookup itself works, since this app only ever
recommends from that fixed vocabulary (not arbitrary free text, unlike the Lure
Inventory page's "Scan a lure" flow below, which doesn't get this fallback).
`core.appstate.get_cabelas_suggestions()` now tries the live lookup first and falls
back to `core.cabelas_picks_cache.get_cached_picks()` when it comes back empty,
returning `(suggestions, is_live)` so `core.ui.render_cabelas_suggestions()` can add
an honest "showing picks saved from a previous lookup" note whenever the fallback -
not a live check - is what's actually on screen. This cache isn't auto-refreshing;
updating it means re-running the same browser-based capture and overwriting the CSV
in a future session.

The photo-identify step (`core/lure_vision.py`) is deliberately kept separate from the
product lookup - it only reads whatever's legible on the package well enough to build
a search query (e.g. "Strike King Thunder Cricket Swimjig"), and the Cabela's lookup
above finds the real product data for that query. A vision model's read of a small,
possibly glare-y label is a good search query, but isn't trustworthy enough to source
exact price/SKU from directly - hence showing you the actual matched Cabela's products
to confirm, rather than saving whatever the photo step guessed.

The same `search_lures()` function also powers the lure-block "worth considering from
Cabela's" suggestions described above (queried by lure name, e.g. "Squarebill
Crankbait", via `core.appstate.get_cabelas_suggestions()`, which adds a 24h cache on
top so the 7-Day Forecast page's many recommendation calls don't each trigger a live
lookup). The mapped product data doesn't include a stable per-product page URL (Coveo's
`raw` fields don't have one that's been found), so each suggestion links to Cabela's own
live site search for that product's brand + name instead of a direct product page
(`core.cabelas_lookup.search_page_url()`). That link points at Cabela's real search
route, `https://www.cabelas.com/SearchDisplay#q=<query>` (a URL fragment, since their
search is a single-page-app view, not a separate page) with spaces percent-encoded as
`%20` - confirmed by actually driving Cabela's own search box and watching where it
navigated to, after a plausible-looking `/search?q=...` guess with `+`-for-space
encoding turned out to 404 unconditionally (even for a single bare word), and to leak
literal `+` characters into Cabela's own search box once there, since a URL fragment
isn't form-urlencoded the way a query string is - only `%20` reliably means space in
one.

### How inventory feeds the forecast

`core.lures.recommend()` takes an optional `inventory` argument (the same rows this page
reads/writes) and, for each lure it would otherwise recommend, checks whether any
in-hand item (quantity > 0) shares that lure's category and matches today's suggested
color. If so, the block is flagged ✅ **"In your tackle box"** with the top 2
color-matched items (ranked #1/#2 by quantity on hand, not every match) - specific
brand/description/quantity, plus a photo thumbnail per owned item, using
`core.lure_inventory.resolve_image_source()`, the same local-photo-wins-over-vendor-link
rule the Tackle Box page itself uses - and that block is stable-sorted to the front
of its choice tier (first choice or second choice) - so the best options you actually
own surface first. Lures you don't have anything color-matched for instead show up to 2
real Cabela's product suggestions worth buying (see "Top-2-per-category capping..."
above and "How the Cabela's lookup works" below). This only reorders and annotates; it
never adds, removes, or changes *which* lures a given day/segment/structure/forage
combination recommends - that's still entirely the season/structure/pressure/forage
logic described above.

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
water clarity (`core.lures._color_tokens()` / `_split_owned_by_color()` - a
simple, explainable keyword match, same philosophy as the rest of the engine, not a
real color model). Only items that share a color/pattern word with the suggestion
(e.g. "shad" in both "Green shad" and "Tennessee Shad") are shown as ✅ **"Color
match"** - an owned item in the same category but a different color is left out of
the photo-match list. As of punch-list #48, though, that off-color item isn't
treated as unowned either: `_split_owned_by_color()` returns it separately as
`owned_off_color_items`, and `core.ui.render_lure_block()` shows a 🎣 "already in
your tackle box, just not today's suggested color" note for it (text only, no
thumbnail) instead of the old, misleading "not in your inventory" note. Only when
nothing at all is owned in that category does the block fall back to the real 🛒
"not in your inventory yet" / Cabela's-suggestion treatment. Because the color
check is keyword-based against free text rather than a structured color field, it
can occasionally miss a real match (different wording) or flag a coincidental one -
it's meant as a helpful signal, not a guarantee.

### Where the lure recommendations actually come from

Punch-list #37: the angler asked directly how a suggested lure gets picked, especially
one not already in the tackle box, and said general bass-fishing knowledge alone
"is really not all the helpful" - the recommendation needed to be grounded in real
Nolin Lake experience and, where possible, the angler's own results. Three sources now
feed `core.lures.recommend()`'s season/structure lure picks, on top of the general bass
biology (upward strike bias, etc.) that was already there:

1. **Documented real Nolin Lake fishing patterns.** Each season's first/second-choice
   lure list (`recommend()`'s season branches) is now sourced from real, Nolin-specific
   season-by-season structure/lure/color/depth data (Omnia Fishing's published Nolin
   Lake fishing patterns), plus two corroborating real reports: a first-hand Nolin
   angler forum post (bluff walls, ~45 ft dam points fished on drop shot, dawn/dusk
   topwater "the jumps" with poppers and soft flukes) and KDFWR's own official 2026
   Fishing Forecast, which calls out Nolin by name - "During late spring through summer,
   best results are often at night" - surfaced as an explicit rationale note on the
   Night segment in summer rather than silently folded into the lure list. Two lure
   categories new to this app's taxonomy, **Drop Shot** and **Soft Swimbait (paddle
   tail)**, were added specifically because this research surfaced them as real,
   documented Nolin patterns with no existing home in the lure list. Every source is
   cited inline in `core/lures.py`'s season-branch comments and in the rationale text
   itself, not just in this README - previously-first-choice generic picks that aren't
   contradicted by any of this stay on as second choices rather than being dropped, so
   proven techniques aren't lost just because a given source didn't happen to mention them.

2. **Your own catch history, in similar situations.** `core.lure_history.
   lure_track_records()` (called from `recommend()` via a new `trip_history`/`spot_id`
   argument) looks at your own logged trips (`data/trip_log.csv`) for ones that share
   real **location** with the current situation - the same spot, or at least the same
   structure type when no specific spot is known (the 7-Day Forecast page's "structure
   type" is a general Lake Setup selection, not a spot) - and, only once at least 2 such
   situation-matched trips exist for a lure category (deliberately cautious, mirroring
   `core.calibration.py`'s "wait for a minimum sample before touching anything"
   philosophy for the score weights), surfaces the real numbers: trips landed vs. tried,
   biggest fish. This can (a) annotate an already-recommended lure with your own
   real track record on it, or (b) surface up to 2 *additional* lures you've genuinely
   caught fish on before in a similar spot/situation - even ones not part of the
   season's default pattern, and even ones not currently in your tackle box - which is
   exactly the "before I decide to go out and buy that lure" case the angler described.
   This only ever adds a signal on top of the season/structure/pressure picks above; it
   never removes or overrides them, and a lure you've tried without ever catching
   anything on it in a similar spot never gets promoted just because it's been tried
   enough times to clear the minimum-sample gate. The note shows up right on the lure's
   own card (⬤ "Your own history: N of M similar trips landed fish...") rather than
   being buried, so you can judge the strength of the signal yourself before trusting it.

3. **Live fish/forage activity and wind, on Spot Session only (punch-list #49).** Spot
   Session's own condition form already asked for "Fish activity" and "Forage activity"
   (five-point sliders, both running least active to most active - Inactive/Sluggish/
   Moderate/Active/Very active, and None seen/Sparse/Moderate/Active-schooling/Frenzied-
   busting-bait) and a wind reading - these used to be recorded to the trip log and
   otherwise ignored. They now feed
   `recommend()` directly: "Very active"/"Active" fish, "Active / schooling"/"Frenzied
   (busting bait)" forage, or wind at/above ~10 mph (`core.onwater.WIND_BANDS`' own
   "Moderate Chop / Action Trigger" cutoff) promote a reaction/moving bait (walking
   topwater, buzzbait, chatterbait, swim jig, lipless crankbait, or spinnerbait -
   whichever's already closest to being picked, or a season-appropriate default if
   none of them are anywhere in the plan) to the very front of first choice.
   "Sluggish"/"Inactive / shut down" fish or "None seen" forage nudge the other way,
   toward a slower finesse presentation (finesse shaky head, drop shot, wacky rig
   senko, or football jig) - the same style of nudge the existing pressure-trend
   rationale already used, just driven by what you actually observe on the water
   instead of a barometer reading. This is Spot-Session-only on purpose - the 7-Day
   Forecast page is a genuine forecast, and has no way to know whether fish will be
   schooling three days from now, so these three inputs default to unused there and
   change nothing about its picks.

### Why this lure and this color (punch-list #49)

Every lure block now shows a short "💡 Why:" line explaining why THAT specific lure -
and its suggested color - made the card, instead of leaving that only in the one
shared caption below the whole recommendation (which explains the overall situation -
season, structure, pressure - but was never attributed to any one lure). Each reason
sentence traces back to whichever rule actually put that lure in the plan: the season
pattern (every pick's first reason), plus whichever nudges specifically touched it -
added for the structure type, added for the water clarity/temp, added to match
reported forage, swapped in for your sonar depth reading, or moved up front for
reported fish/forage activity or wind (see above). A final sentence always names the
water clarity behind the suggested colors shown ("Colors shown are Nolin's documented
picks for green stained water."). This is separate from - and shown alongside - the
lure's own personal-catch-history note (punch-list #37) and the shared situational
caption at the bottom of the whole recommendation, which still covers context that
doesn't belong to any single lure (the season's overall pattern description, the
structure-specific casting tip, etc.). Built in `core.lures.recommend()` (a `key_why`
dict, tagged as each lure key enters or moves within first/second choice) and
`_build_block()` (which appends the color reason last, since it's the one place that
actually knows which colors got picked for today's water clarity) - see
`LureBlock.why` for the full field-level rationale.

## Development punch list

The **Development** page is a running list of things to adjust or fix in the app
itself - not a fishing feature, a place to jot down anything you notice while using
the app so it's not forgotten by the next session. Add an item with a description and
the page it's mainly about; each one gets a small auto-assigned number (`#1`, `#2`,
...) that's never reused, even if that item is later edited or deleted, so you can
reference it later just by number ("let's do #7 next") instead of re-describing it,
and so a future Claude session can read this list and ask which number to work on.
Check the "Done" box next to an item to mark it finished (or uncheck to reopen it) -
saves immediately, no extra button. Each item also has its own "✏️ Edit or delete"
section: edit its description/page and save, or delete it outright (a two-step
confirm, since it's permanent - same pattern as deleting a trip in Trip History).
Deleting an item never reuses its number for anything added later - see
`core/dev_tasks.py`'s module docstring for how the numbering is kept stable. Toggle
"Show completed items" to see finished ones again. Stored in `data/dev_tasks.csv`
(plus a small `data/dev_tasks_counter.txt` sidecar tracking the next number to hand
out) and committed back to GitHub like every other data file when a `GITHUB_TOKEN`
is configured.

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

**Data lives on a separate `data` branch (punch-list #52).** Every real data save
the app makes (trip logs, tackle inventory, lure spots, anglers, the punch list,
forecast freezes) pushes to a `data` branch, not `main` - Streamlit Cloud only
watches `main` for auto-redeploy, so a routine save no longer restarts the app for
everyone connected (that used to be the leading cause of "my session dropped" -
see SESSION_NOTES.md punch-list #51/#52). `app.py` pulls the latest `data/`
content from that branch once per boot, so a real redeploy (from an actual code
push) still shows current data. Nothing to configure for this in the Streamlit
Cloud dashboard - it's entirely handled by `core/storage.py`.

## Project layout

```
app.py                  Entry point (streamlit run app.py) - wires up the sidebar
                         navigation (st.navigation/st.Page) with a title/icon per
                         page; holds no page content of its own
home.py                  Landing page content - today at a glance ("Today" in the
                         sidebar)
pages/ (sidebar order set by app.py's st.navigation list, not these numeric
        filename prefixes - the prefixes are left over from the old file-based
        pages/ auto-discovery this app no longer uses, see app.py's own
        docstring)
  1_7_Day_Forecast.py   Full week, drill into any day
  2_Lake_Map.py          Fish attractors + your own saved spots (click to add/edit)
  6_Spot_Session.py       Per-spot on-the-water conditions -> suggestions -> log activity
  4_Trip_History.py      Filterable log of every trip (Spot Session is now the only
                         way to log one) + per-trip details + calibration status
  8_Leaderboard.py        Ranks trip history different ways - biggest/longest fish,
                         most fish by lure/spot/angler/day, best fish-per-use rates
  5_Lure_Inventory.py    Tackle inventory (brand/description/category/photo/price/qty)
  7_Development.py        Punch list of app adjustments/fixes to track between sessions
core/
  astro.py               Moon phase + solunar rise/transit/set
  weather.py              Open-Meteo integration + water-temp estimate
  lake_level.py            USGS Water Services integration - real, live pool elevation
                           (not an estimate, unlike everything else weather-derived)
  lake_water_quality.py     USACE periodic water-quality survey - real (but not live)
                           surface temp + dissolved oxygen % saturation
  water_quality_log.py      Local git-committed archive of USACE readings (data/
                           water_quality_log.csv) - the live report has no history
                           of its own, so this app records one going forward, for
                           the Home page's "🌡️ USACE surface reading history" chart
  scoring.py              1-10 activity scoring engine (shared by the forecast and
                           Spot Session pages via manual_segment_score())
  forecast_freeze.py       Locks in a 7-Day Forecast time segment's score once its
                           window has passed + git commit-back, so it stops drifting
                           with later weather refreshes (data/segment_score_freeze.csv)
  onwater.py               On-the-water condition bands (sky/wind/visibility/water
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
  lure_vision.py           Photo -> brand/product-name read via Claude's vision API,
                           for the Tackle Box page's "Scan a lure" flow
  cabelas_lookup.py        Text query -> real Cabela's product data (SKU/price/photo),
                           via the same JSON endpoints Cabela's own site search calls
  cabelas_picks_cache.py   Curated fallback picks (data/cabelas_picks_cache.csv) for
                           when the live Cabela's lookup above fails - punch-list #22
  bathymetry.py            Modeled depth grid + historic-topo + real-data blending
                           (not currently rendered on the Lake Map page - see "Data sources")
  historic_bathymetry.py   Loads depth points read from pre-dam USGS historical topo maps
  survey_points.py         Loads the angler's own Quickdraw CSV exports
  shoreline.py              Real digitized lake shoreline + point-in-polygon clip mask
  cover.py                  Pre-dam bottom-cover classification (wooded/cleared/channel)
  fish_attractors.py        Loads real KY Fish & Wildlife fish attractor GPS data
  dev_tasks.py              Development punch-list read/write/edit/delete (auto-
                           numbered, numbers never reused) + git commit-back, for
                           the Development page
  anglers.py                "Who's fishing" roster read/add + git commit-back
                           (data/anglers.csv) - punch-list #26's lightweight
                           multi-user support, used by the Spot Session picker
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
  dev_tasks.csv            Development punch-list items (grows over time; auto-numbered)
  dev_tasks_counter.txt    Next punch-list number to hand out (survives item deletes)
  water_quality_log.csv    Locally-recorded USACE survey history (grows ~every 1-2
                           weeks; starts empty, see core/water_quality_log.py)
  anglers.csv               "Who's fishing" roster (seeded John/Matthew/Alex; grows
                           any time someone picks "Other" and types a new name)
tests/                    pytest unit tests for astro/scoring/lures/inventory/lake_spots/onwater/activity_log/dev_tasks
```

## Disclaimers

Forecast scores are a fishing-planning aid based on general bass-behavior heuristics,
not a guarantee. Water temperature is estimated, not measured. Map locations are
approximate. Always check current weather/lightning conditions before heading out.
