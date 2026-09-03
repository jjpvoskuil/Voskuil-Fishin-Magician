"""Shared Streamlit rendering helpers so the lure-block layout is
identical on the 7-Day Forecast page and the Spot Session page."""
from __future__ import annotations
from dataclasses import dataclass, field
import streamlit as st

from .lures import LureBlock, STRUCTURE_TYPES, FORAGE_OPTIONS, MAX_OWNED_ITEMS_PER_BLOCK
from .lure_inventory import resolve_image_source, image_data_uri_or_url
from .lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE
from .appstate import get_lake_spots, get_cabelas_suggestions
from .cabelas_lookup import search_page_url
from .onwater import resolve_water_clarity, visibility_band, STAIN_COLOR_OPTIONS

# Punch-list #8: cap how many real Cabela's products get suggested per lure
# block when nothing color-matched is in the tackle-box inventory - "only
# show a max of 2 best options from cabelas."
MAX_CABELAS_SUGGESTIONS = 2

# A lure block's owned-item thumbnails are naturally capped at 2 now (see
# core.lures.MAX_OWNED_ITEMS_PER_BLOCK), so no separate thumbnail cap is
# needed here anymore - only the shared display size remains.
OWNED_THUMBNAIL_PX = 64   # small on purpose - these are ownership flags, not the card's focus

# Below this viewport width, wide multi-column rows (4+ columns) reflow
# instead of squishing - see inject_mobile_css() below for why this needed
# real measurement against the live app rather than just reasoning about
# Streamlit's CSS from the outside.
MOBILE_BREAKPOINT_PX = 700
MOBILE_COLUMN_MIN_WIDTH_PX = 120


def inject_mobile_css():
    """Site-wide phone-usability CSS - call once near the top of every page,
    right after st.set_page_config(). Two independent fixes:

    1. **Bigger, higher-contrast collapsed-sidebar toggle.** Streamlit's own
       collapsed-sidebar expand arrow (`stExpandSidebarButton`, the
       "keyboard_double_arrow_right" icon button that appears top-left once
       the sidebar is collapsed) is a small, low-contrast 28x28px hit target
       by default - a widely-reported Streamlit usability complaint, worse on
       a phone where it's also the only way back to Lake Setup Options/nav
       and has to survive a thumb tap instead of a precise mouse click.
       Enlarged and given a solid background so it reads as a button, not a
       stray mark in the corner. Applied unconditionally (not just under the
       mobile media query below) since a clearer toggle only helps on desktop
       too.
    2. **Reflow wide column rows below a phone-width breakpoint**, instead of
       letting them squish unreadably. Verified directly against the live
       deployed app (not just reasoned about): Streamlit's own
       `stHorizontalBlock` already sets `flex-wrap: wrap`, but `st.metric`'s
       label/value text has its own `white-space: nowrap` + ellipsis CSS, so
       a column's min-content width collapses to almost nothing and the row
       never actually triggers a wrap - each column just truncates in place
       (e.g. the 7-Day Forecast's day-by-day score row and its 6-column
       time-of-day breakdown becoming a strip of "Thu ...", "6..." slivers).
       Giving each column a real minimum width forces the existing wrap to
       actually fire once a row can't fit at that minimum. Scoped to rows of
       3+ columns via `:has(> ... :nth-child(3))` so intentional 2-column
       master/detail layouts (e.g. the Lake Map's map + detail panel, or a
       page's own info + best-window pair) keep their original proportions
       instead of being forced to an even split - only the wide metric/card
       rows this was actually reported about are affected.
    3. **Keep selectbox/multiselect dropdown popovers scrollable and on
       screen** (punch-list #33). Streamlit's own dropdown already sets
       `max-height`/`overflow-y: auto` on the option list (confirmed by
       inspecting the live app's DOM directly, not just reasoning about
       Streamlit's CSS from the outside - `[data-testid="stSelectboxVirtualDropdown"]`
       for a selectbox, `[data-testid="stMultiSelectDropdown"]` for a
       multiselect, both wrapping a `[role="listbox"]`), but the angler
       still reported a multiselect's last option getting cut off with no
       way to scroll to it on a phone - most likely the classic mobile-web
       gap between the *layout* viewport a `position: fixed` popover is
       placed against and the smaller *visual* viewport actually on screen
       once the browser's own chrome/keyboard eats into it, which no
       server-rendered pixel height can account for. `100dvh` (dynamic
       viewport height) is the CSS unit built specifically to track the
       real, current visual viewport, so capping the popover to a `dvh`-
       based height is a safety net that keeps the whole thing (and a
       working scrollbar to its last option) inside whatever's actually
       visible, on top of `overscroll-behavior: contain` so a touch-drag
       inside the list can't get grabbed by a page scroll instead. The
       *specific* dropdown reported cut off - the "Type of hit" field in
       "Log a fish" - was separately switched from `st.multiselect` to
       `st.pills` (see pages/6_Spot_Session.py), which has no popover to
       cut off at all; this CSS is general hardening for every other
       selectbox/multiselect in the app, not a substitute for that fix.
    4. **A selectbox's own CLOSED value text no longer gets hard-clipped
       with no ellipsis** (punch-list #75) - a different spot from #3
       above, which is about the OPEN dropdown *list* of options; this is
       about the *already-picked* value shown on the closed widget itself.
       Reported live: picking a long inventory item as a trailer (e.g.
       "Strike King - Rage Tail Craw Soft Bait - Fire Craw, 4\", 7-pack")
       showed fine on a full-width desktop browser but was abruptly cut off
       mid-word on a phone, with no visual indication more text existed.
       Confirmed by inspecting the live rendered DOM directly (not just
       reasoning about it): every `st.selectbox` in this Streamlit version
       renders its current value into a real `<input role="combobox">`
       (a React Aria ComboBox, not the older BaseWeb `<select>`-style div
       punch-list #33 above was written against), and that input's
       computed style was `overflow: clip; text-overflow: clip` - a hard
       cut with no `...`, at a fixed 14px regardless of viewport. Fixed two
       ways: `text-overflow: ellipsis` (with the `overflow: hidden` it
       requires to actually render) so a truncated value at least *looks*
       intentionally truncated instead of broken; and, only below the
       mobile breakpoint, a smaller font-size for just these inputs so
       more of a long value fits before the ellipsis kicks in. This is
       scoped to `st.selectbox`'s own `input[role="combobox"]` specifically
       (not every text input on the page) via `[data-testid="stSelectbox"]`.
    """
    st.markdown(
        f"""
        <style>
        button[data-testid="stExpandSidebarButton"] {{
            width: 44px !important;
            height: 44px !important;
            background-color: #0e4f66 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.35) !important;
        }}
        button[data-testid="stExpandSidebarButton"] span[data-testid="stIconMaterial"] {{
            color: #ffffff !important;
            font-size: 26px !important;
        }}

        [data-testid="stSelectboxVirtualDropdown"],
        [data-testid="stMultiSelectDropdown"] {{
            max-height: min(324px, 90dvh) !important;
        }}
        [data-testid="stSelectboxVirtualDropdown"] [role="listbox"],
        [data-testid="stMultiSelectDropdown"] [role="listbox"] {{
            max-height: min(300px, 80dvh) !important;
            overflow-y: auto !important;
            -webkit-overflow-scrolling: touch !important;
            overscroll-behavior: contain !important;
        }}

        /* Punch-list #75: a selectbox's own CLOSED value text - not the
           open dropdown list above - used to hard-clip with no ellipsis
           (confirmed via the live DOM: overflow/text-overflow both
           "clip"). Ellipsis applies everywhere, since it's a strict
           improvement (an honest "..." beats an abrupt cut) with no
           downside on a wide screen where it rarely if ever triggers.
           `white-space: nowrap` is required too - without it the browser
           never considers the single-line value to be "overflowing" in
           the way text-overflow needs, so ellipsis silently does nothing
           and the text still hard-clips (confirmed the same way: adding
           text-overflow/overflow alone was NOT enough in a live re-test
           after the first attempt at this fix - the value still cut off
           with no "..." until nowrap was added too). */
        [data-testid="stSelectbox"] input[role="combobox"] {{
            text-overflow: ellipsis !important;
            overflow: hidden !important;
            white-space: nowrap !important;
        }}

        @media (max-width: {MOBILE_BREAKPOINT_PX}px) {{
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)) {{
                flex-wrap: wrap !important;
            }}
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
                > div[data-testid="stColumn"] {{
                min-width: {MOBILE_COLUMN_MIN_WIDTH_PX}px !important;
                flex: 1 1 {MOBILE_COLUMN_MIN_WIDTH_PX}px !important;
            }}
            /* Punch-list #75: a bit smaller than the normal 14px, only on
               a narrow screen, so more of a long selected value (a lure/
               trailer's full brand + description + size) fits before the
               ellipsis above has to kick in at all. */
            [data-testid="stSelectbox"] input[role="combobox"] {{
                font-size: 12.5px !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_compact_metric_css(container_key: str, value_rem: float = 1.15, label_rem: float = 0.72):
    """Punch-list #16: shrink `st.metric()`'s label/value/delta font size,
    scoped to one `st.container(key=container_key)` rather than site-wide -
    for a row that's grown past the 4-5 columns Streamlit's default metric
    sizing comfortably fits on one line (home.py's "Today at a glance" row,
    now up to 6 tiles wide after adding the USACE reading), the default
    ~2.25rem value / ~0.875rem label wraps or gets cramped well before a
    normal desktop width runs out. `st.container(key=...)` renders a
    `st-key-<container_key>` wrapper class (see Streamlit's own
    `elements/layouts.py`), which is what this targets - unlike the
    `:nth-child(3)` column-count selector `inject_mobile_css()` uses above
    (deliberately wide-reaching, for any multi-column row on any page),
    this only ever affects the one caller-chosen row, so it's safe to call
    from just the one page that needs it without touching metric sizing
    anywhere else in the app."""
    st.markdown(
        f"""
        <style>
        .st-key-{container_key} [data-testid="stMetricValue"] {{
            font-size: {value_rem}rem !important;
        }}
        .st-key-{container_key} [data-testid="stMetricLabel"] {{
            font-size: {label_rem}rem !important;
        }}
        .st-key-{container_key} [data-testid="stMetricDelta"] {{
            font-size: {label_rem}rem !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_line_chart(col, series, y_domain: tuple | None = None):
    """Renders one `pd.Series` as a line chart in `col` (an `st.columns()`
    slot, container, or the page itself). Punch-list #20: plain
    `st.line_chart()` always auto-scales its Y axis to whatever the data's
    own min/max happen to be, with no built-in way to pin it - for a
    temperature series that reads as misleadingly volatile (a real swing
    of a degree or two fills the whole chart height) when the angler wants
    to see it against a fixed, meaningful band instead (e.g. 45-95°F, the
    real range Nolin Lake's surface actually sees across a season).

    `y_domain=None` (the default) is just `st.line_chart(series)`,
    unchanged from before this existed - every other trend chart on the
    page (activity score, pressure trend, lake level, dissolved oxygen)
    keeps auto-scaling, since a fixed range only makes sense for a metric
    with a known real-world band. Passing `y_domain=(lo, hi)` drops down
    to a raw `st.altair_chart()` instead, the documented escape hatch for
    anything `st.line_chart()` doesn't expose a parameter for - built from
    the same Series' values/index (renamed to plain "x"/"value" columns
    since Altair encodes off column names, not a Series' own name/index
    labels), with an explicit `alt.Scale(domain=[lo, hi])` on the Y
    encoding. `sort=None` on the X encoding keeps the data's own point
    order instead of Altair's default alphabetical-by-value sort for
    string axis labels (this app's non-USACE trend charts use formatted
    day strings like "Mon 8/10", not dates, as their X labels)."""
    if y_domain is None:
        col.line_chart(series)
        return
    import altair as alt

    df = series.rename("value").rename_axis("x").reset_index()
    chart = (
        alt.Chart(df)
        .mark_line()
        .encode(
            x=alt.X("x", sort=None, title=None),
            y=alt.Y("value", scale=alt.Scale(domain=list(y_domain)), title=None),
        )
    )
    col.altair_chart(chart, width="stretch")


def render_square_thumbnail(item: dict, size_px: int = 96) -> bool:
    """Render one inventory item's photo (if it has one) as a center-cropped
    square, capped at `size_px` but shrinking to fit a narrower container,
    via inline HTML/CSS (object-fit: cover). Returns False (renders nothing)
    if the item has no usable photo, so callers can fall back to a "no
    photo" caption.

    st.image(..., width='stretch') - the original approach - stretched every
    photo to fill its full column width, which (a) blurs any photo whose
    native resolution is smaller than that column (upscaling), and (b) left
    each thumbnail a different height, since it just scales width and lets
    height follow the source photo's own aspect ratio. Cropping to a square
    here fixes both: every thumbnail is the same shape, and the on-screen
    size no longer depends on the source photo's own aspect ratio.

    Punch-list #74: that fix's own first version pinned both `width` and
    `height` to a bare `{size_px}px`, which - unlike everything else in a
    Streamlit column - does not shrink when its actual container gets
    narrower than that. Every card grid this renders into (the Tackle Box
    inventory grid, the Scan-a-lure/Search-Cabela's candidate grid, Spot
    Session's lure picker) sits inside `st.columns(...)`, and
    `inject_mobile_css()` above reflows those into narrower columns below
    `MOBILE_BREAKPOINT_PX` - down to `MOBILE_COLUMN_MIN_WIDTH_PX` (120px),
    well under every real `size_px` this function is ever called with (96,
    120, 160). A fixed-pixel thumbnail wider than its own column spills out
    of its card's border and overlaps the next card - confirmed live via a
    real screenshot (a 160px Tackle Box thumbnail overlapping the "No photo
    yet" card next to it). Fixed by making the box `width:100%` (so it
    shrinks with its real container, exactly like every other Streamlit
    element already does) capped at `max-width:{size_px}px` (so it still
    never exceeds the intended size on a wide screen), with `aspect-ratio:1`
    keeping it square at whatever width it actually ends up - since height
    is no longer pinned to a fixed px value once width can shrink.
    """
    src = image_data_uri_or_url(resolve_image_source(item))
    if not src:
        return False
    st.markdown(
        f'<div style="width:100%;max-width:{size_px}px;aspect-ratio:1;overflow:hidden;'
        f'border-radius:6px;margin:0 auto;background:#eee;">'
        f'<img src="{src}" style="width:100%;height:100%;object-fit:cover;display:block;" />'
        f'</div>',
        unsafe_allow_html=True,
    )
    return True


def render_cabelas_suggestions(
    query: str, found_caption: str, empty_caption: str, num_results: int = MAX_CABELAS_SUGGESTIONS,
):
    """Looks up up to `num_results` real Cabela's products for `query` (via
    the cached core.appstate.get_cabelas_suggestions) and renders them as
    small cards - thumbnail, brand/description/price, and a "Search
    Cabela's" link to that same query's live search results. There's no
    stable link to a specific product page (see core.cabelas_lookup.
    search_page_url's own docstring for why) - the search-results link is
    the real, honest thing this app can offer; a genuine one-click "add to
    cart" isn't possible from a server-side app with no access to the
    angler's own logged-in Cabela's session (punch-list #14).

    Falls back to `empty_caption` (no product cards) if the lookup finds
    nothing or fails - search_lures() fails soft (returns []) on any
    problem, same "degrade quietly" contract every external source in this
    app follows. Callers own both caption strings since the same "nothing
    found"/"found something" moment reads differently in different
    contexts (a specific lure recommendation vs. a general inventory gap) -
    shared here (punch-list #8's original block, and #14's gap-filling
    section) purely to avoid duplicating the card-rendering markup itself.

    Punch-list #21: even in the fallback case, still show a "Search
    Cabela's" link for `query` - confirmed live that Cabela's/Coveo's
    search API (which needs a server-side lookup to work at all) can fail
    from Streamlit Community Cloud's own servers while working fine from a
    real browser on the same network (the same kind of server-side-only
    network restriction already seen with the USACE water-quality site) -
    search_page_url() is a pure link-building function with no network
    call, so it's always safe to show regardless of whether the live
    product lookup itself succeeded.

    Punch-list #22: core.appstate.get_cabelas_suggestions now returns
    `(suggestions, is_live)` - when the live lookup fails, it falls back to
    a small curated cache (core.cabelas_picks_cache) instead of coming back
    empty outright, so `suggestions` can be non-empty with `is_live=False`.
    In that case this still renders real product cards (same shape either
    way), but adds a caption making clear these are saved picks, not a
    live price/availability check, so the angler isn't misled."""
    suggestions, is_live = get_cabelas_suggestions(query, num_results=num_results)
    if not suggestions:
        st.caption(empty_caption)
        st.markdown(f"[Search Cabela's]({search_page_url(query)})")
        return
    st.caption(found_caption)
    if not is_live:
        st.caption(
            "🛈 Cabela's live search couldn't be reached just now - showing picks saved "
            "from a previous lookup (prices/availability may be out of date)."
        )
    cols = st.columns(len(suggestions))
    for i, (col, item) in enumerate(zip(cols, suggestions), start=1):
        with col:
            if resolve_image_source(item):
                render_square_thumbnail(item, size_px=OWNED_THUMBNAIL_PX)
            price_txt = f" – ${item['price']:.2f}" if item.get("price") else ""
            st.caption(f"**#{i}** {item['brand']} – {item['description']}{price_txt}"[:100])
            product_query = f"{item['brand']} {item['description']}"
            st.markdown(f"[Search Cabela's]({search_page_url(product_query)})")


def render_lure_block(block: LureBlock):
    with st.container(border=True):
        st.markdown(f"**{block.name}**")
        if block.why:
            # Punch-list #49: "why this lure and color combination was
            # chosen" - core.lures.recommend()'s per-key reason(s) (season
            # pattern, plus whichever nudges actually touched this lure -
            # structure, pressure, forage, depth, activity/wind) followed by
            # a color reason _build_block() always appends. Distinct from
            # block.note below (personal catch-history track record) and
            # from LureRecommendation.rationale (one shared caption for the
            # whole situation, not attributed to any one lure) - this is the
            # one place both "why this lure" and "why this color" live
            # together, right on the card they're about.
            st.caption("💡 Why: " + " ".join(block.why))
        if block.note:
            # Punch-list #37: block.note carries the "why this pick, and how
            # much to trust it" signal - core.lures.recommend()'s personal-
            # history track record (core.lure_history.track_record_note())
            # when your own trip log has enough situation-matched trips on
            # this lure. Surfaced as its own line, not buried in a caption,
            # since the angler specifically asked to see sourcing/confidence
            # before deciding whether to buy something new.
            st.info(block.note)
        if block.owned_items:
            # block.owned_items only ever contains items that both match this lure's
            # category AND match today's suggested color (core.lures._split_owned_by_
            # color), already capped to the top MAX_OWNED_ITEMS_PER_BLOCK (#1/#2)
            # by quantity on hand - so what's shown here is always ready to go, and
            # never more than 2 items (punch-list #8).
            st.success("✅ In your tackle box:")
            for i, it in enumerate(block.owned_items, start=1):
                st.write(f"**#{i}** {it['brand']} – {it['description']} (qty {it['quantity']})")

            photos = [it for it in block.owned_items if resolve_image_source(it)]
            if photos:
                cols = st.columns(len(photos))
                for col, it in zip(cols, photos):
                    with col:
                        render_square_thumbnail(it, size_px=OWNED_THUMBNAIL_PX)
        elif block.owned_off_color_items:
            # Punch-list #48: you own this lure TYPE, just not in today's
            # suggested color (e.g. a Blue Chrome Spook when today calls for
            # Bone/white) - the user-reported bug this fixes was this exact
            # case rendering the plain "Not in your inventory yet" message
            # below, which is simply false: you do own one. No photos here
            # (deliberately - showing photo cards for a color that doesn't
            # match today's suggestion is exactly the confusing clutter
            # punch-list #26 removed), just an honest text note plus the
            # normal right-color shopping suggestions underneath.
            owned_bit = "; ".join(
                f"{it['brand']} – {it['description']}" for it in block.owned_off_color_items[:MAX_OWNED_ITEMS_PER_BLOCK]
            )
            st.info(f"🎣 Already in your tackle box, just not today's suggested color: {owned_bit}")
            render_cabelas_suggestions(
                block.name,
                found_caption="🛒 In today's suggested color:",
                empty_caption="🛒 Nothing found in today's suggested color right now - what you already have is still worth a try.",
            )
        else:
            # Nothing on hand in this category at all - suggest up to
            # MAX_CABELAS_SUGGESTIONS real products worth buying instead
            # (punch-list #8). Cached (see core.appstate.get_cabelas_
            # suggestions) so repeated blocks for the same lure name across
            # a page (e.g. the same crankbait recommended for several
            # days/segments at once) don't each trigger a live lookup.
            render_cabelas_suggestions(
                block.name,
                found_caption="🛒 Not in your inventory yet - worth considering from Cabela's:",
                empty_caption="🛒 Not in your inventory yet - worth picking one up for this presentation.",
            )
        st.write(f"Colors: {', '.join(block.colors)}")
        if block.trailer:
            st.write(f"Trailer: {block.trailer.type} - {', '.join(block.trailer.colors)}")
        st.write(f"Depth to run: {block.depth}")
        st.write(f"Presentation: {block.presentation}")
        video_links = " · ".join(f"[{v['title']}]({v['url']})" for v in block.videos)
        st.caption(f"📺 {video_links}")


def render_lure_recommendation(rec, first_label: str = "First choice", second_label: str = "Second choice"):
    st.markdown(f"**{first_label}**")
    for block in rec.first_choice:
        render_lure_block(block)
    if rec.second_choice:
        st.markdown(f"**{second_label}**")
        for block in rec.second_choice:
            render_lure_block(block)
    if rec.rationale:
        st.caption(" · ".join(rec.rationale))


# Shown in the Location dropdown when the angler isn't fishing (or planning
# around) one specific saved spot - falls through to a manual structure-type
# pick instead of a saved spot's own structure type.
OTHER_LOCATION_LABEL = "Other (pick structure manually)"


@dataclass
class LakeSetupOptions:
    water_clarity: str          # resolved: Clear / Green stained / Brown stained / Muddy
    secchi_ft: float             # raw visibility reading the angler entered
    stirred_up: bool
    structure_type: str
    water_temp_override_f: float
    fish_depth_ft: float
    forage: list = field(default_factory=list)


def render_lake_setup_sidebar(
    include_structure: bool = True,
    default_structure_index: int = 0,
    default_water_temp_f: float = 85.0,
    default_fish_depth_ft: float = 8.0,
    default_secchi_ft: float = 2.5,
) -> LakeSetupOptions:
    """
    Shared "Lake Setup Options" sidebar (currently only used by the 7-Day
    Forecast page - Lake Map dropped its own use of this when Spot Session
    took over on-the-water recommendations). Every value returned here is a
    direct input the angler controls, feeding straight into recommend() so
    the guidance stays consistent with the rest of the app's rules.

    Water clarity (punch-list #49): mirrors the Secchi-depth model Spot
    Session's own condition form has always used (core.onwater.
    resolve_water_clarity()/visibility_band()) instead of the plain Clear/
    Green/Brown dropdown this sidebar used before - a real visibility
    reading in feet (default 2.5', Nolin's typical "Stained" band) is a more
    accurate, and more consistent-with-the-rest-of-the-app, way to get to
    the same four color-table keys. A reading only asks for a stain color
    (Green vs Brown) when it lands in the genuinely ambiguous "Stained"
    band (1.5-4 ft) - a Clear or Muddy reading resolves on its own. The
    "stirred up" flag still always overrides straight to Muddy, exactly as
    before, since a Secchi estimate taken a bit before (or after) a wind/
    rain event may not reflect it yet.

    Location: picking one of the angler's own saved spots (data/lake_spots.csv,
    same catalog as the Lake Map page) auto-resolves that spot's structure
    type via core.lake_spots.LOCATION_TYPE_TO_STRUCTURE_TYPE, the same lookup
    Spot Session uses - one less thing to enter by hand, and it stays correct
    if the spot's type is edited later. Picking "Other" instead reveals a
    second, plain structure-type dropdown for a spot that isn't saved (or
    isn't a specific spot at all).

    Water surface temp and the depth you're marking fish at on your own
    electronics are both required, direct inputs (Nolin has no live feed for
    either) - they always drive lure/season selection, depth-to-run guidance,
    and retrieval notes; there's no "estimate" fallback.

    Forage: which baitfish/prey are actually available right now, out of
    Nolin's documented forage base plus a few optional add-ons. Nothing is
    pre-checked - an empty selection just means "unknown/not specified" to
    the lure engine, rather than asserting a specific forage base the angler
    didn't actually confirm. Selections nudge lure color/pattern choice and
    make sure at least one forage-matched lure shows up in the recommendation.
    """
    with st.sidebar:
        st.header("Lake Setup Options")

        st.session_state.setdefault("lso_secchi", default_secchi_ft)
        secchi_ft = st.number_input(
            "Water visibility / Secchi depth (ft)", min_value=0.0, max_value=20.0, step=0.5,
            help="How far down you can see a light-colored object/lure. Estimate visually if you don't carry a Secchi disk.",
            key="lso_secchi",
        )
        vis_band = visibility_band(secchi_ft)
        st.caption(f"Visibility band: **{vis_band['label']}** ({vis_band['detail']})")

        stain_color = None
        if vis_band["label"] == "Stained":
            st.session_state.setdefault("lso_stain_color", STAIN_COLOR_OPTIONS[0])
            stain_color = st.selectbox(
                "Stain color (Nolin normally runs greenish-brown, leaning brown)", STAIN_COLOR_OPTIONS,
                key="lso_stain_color",
            )
        stirred_up = st.checkbox(
            "Stirred up / muddy right now (recent wind or rain)", key="lso_stirred_up",
            help="Overrides the reading above straight to Muddy, regardless of Secchi depth or stain color.",
        )
        clarity = resolve_water_clarity(secchi_ft, stain_color, stirred_up)

        structure = None
        if include_structure:
            saved_spots = get_lake_spots()
            location_options = [s["name"] for s in saved_spots] + [OTHER_LOCATION_LABEL]
            location_choice = st.selectbox(
                "Location", location_options, index=len(location_options) - 1, key="lso_location",
                help="Pick a saved spot to use its own structure type automatically, or Other to set one yourself.",
            )
            if location_choice == OTHER_LOCATION_LABEL:
                structure = st.selectbox(
                    "Structure type", STRUCTURE_TYPES, index=default_structure_index, key="lso_structure",
                )
            else:
                spot = next((s for s in saved_spots if s["name"] == location_choice), None)
                structure = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(
                    (spot or {}).get("location_type"), STRUCTURE_TYPES[default_structure_index]
                )
                st.caption(f"Structure: **{structure}** (from this spot's saved type)")

        c3, c4 = st.columns(2)
        water_temp_override = c3.number_input(
            "Water temp (°F)", min_value=32.0, max_value=100.0,
            value=default_water_temp_f, step=0.5, key="lso_water_temp",
            help="Nolin has no live temperature feed - enter your own reading.",
        )
        fish_depth = c4.number_input(
            "Fish depth (ft)", min_value=0.0, max_value=100.0,
            value=default_fish_depth_ft, step=1.0, key="lso_fish_depth",
            help="Depth fish are showing up on your electronics.",
        )

        forage = st.multiselect(
            "Forage available / being eaten",
            FORAGE_OPTIONS, default=[], key="lso_forage",
            help="Gizzard shad and bluegill are Nolin's documented forage base; add others you're actually seeing.",
        )

    return LakeSetupOptions(
        water_clarity=clarity,
        secchi_ft=secchi_ft,
        stirred_up=stirred_up,
        structure_type=structure,
        water_temp_override_f=water_temp_override,
        fish_depth_ft=fish_depth,
        forage=forage,
    )
