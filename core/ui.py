"""Shared Streamlit rendering helpers so the lure-block layout is
identical on the 7-Day Forecast page and the Spot Session page."""
from __future__ import annotations
from dataclasses import dataclass, field
import streamlit as st

from .lures import (
    LureBlock, BASE_STAIN_OPTIONS, DEFAULT_BASE_STAIN, STRUCTURE_TYPES,
    resolve_water_clarity, FORAGE_OPTIONS,
)
from .lure_inventory import resolve_image_source, image_data_uri_or_url
from .lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE
from .appstate import get_lake_spots, get_cabelas_suggestions
from .cabelas_lookup import search_page_url

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

        @media (max-width: {MOBILE_BREAKPOINT_PX}px) {{
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)) {{
                flex-wrap: wrap !important;
            }}
            [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
                > div[data-testid="stColumn"] {{
                min-width: {MOBILE_COLUMN_MIN_WIDTH_PX}px !important;
                flex: 1 1 {MOBILE_COLUMN_MIN_WIDTH_PX}px !important;
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
    """Render one inventory item's photo (if it has one) as a fixed-size,
    center-cropped square via inline HTML/CSS (object-fit: cover). Returns
    False (renders nothing) if the item has no usable photo, so callers can
    fall back to a "no photo" caption.

    st.image(..., width='stretch') - the previous approach - stretched every
    photo to fill its full column width, which (a) blurs any photo whose
    native resolution is smaller than that column (upscaling), and (b) left
    each thumbnail a different height, since it just scales width and lets
    height follow the source photo's own aspect ratio. Cropping to a fixed
    square here fixes both: every thumbnail is the same size, and the
    on-screen size no longer depends on the surrounding layout, so a modest,
    consistently-sized image never gets stretched past its real resolution.
    """
    src = image_data_uri_or_url(resolve_image_source(item))
    if not src:
        return False
    st.markdown(
        f'<div style="width:{size_px}px;height:{size_px}px;overflow:hidden;'
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
        if block.owned_items:
            # block.owned_items only ever contains items that both match this lure's
            # category AND match today's suggested color (core.lures._color_matched_
            # owned_items), already capped to the top MAX_OWNED_ITEMS_PER_BLOCK (#1/#2)
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
        else:
            # Nothing color-matched on hand - suggest up to MAX_CABELAS_SUGGESTIONS
            # real products worth buying instead (punch-list #8). Cached (see
            # core.appstate.get_cabelas_suggestions) so repeated blocks for the same
            # lure name across a page (e.g. the same crankbait recommended for
            # several days/segments at once) don't each trigger a live lookup.
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
    base_stain: str              # what the angler picked before the stirred-up flag was applied
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
    default_base_stain: str = DEFAULT_BASE_STAIN,
) -> LakeSetupOptions:
    """
    Shared "Lake Setup Options" sidebar (currently only used by the 7-Day
    Forecast page - Lake Map dropped its own use of this when Spot Session
    took over on-the-water recommendations, and Spot Session has always had
    its own, separate condition inputs). Every value returned here is a
    direct input the angler controls, feeding straight into recommend() so
    the guidance stays consistent with the rest of the app's rules.

    Water color: Nolin normally runs a greenish-brown stain (leaning brown),
    but wind/rain can stir it up to muddy regardless of the usual color -
    so this is two independent inputs (base stain color, and a stirred-up
    flag) resolved into one effective clarity key for the lure engine.

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

        c1, c2 = st.columns(2)
        base_stain = c1.selectbox(
            "Water stain", BASE_STAIN_OPTIONS,
            index=(
                BASE_STAIN_OPTIONS.index(default_base_stain)
                if default_base_stain in BASE_STAIN_OPTIONS
                else BASE_STAIN_OPTIONS.index(DEFAULT_BASE_STAIN)
            ),
            key="lso_base_stain",
            help="Nolin's normal color under typical conditions.",
        )
        stirred_up = c2.checkbox(
            "Stirred up / muddy", key="lso_stirred_up",
            help="Recent wind or rain - overrides the stain color to Muddy regardless of what's picked above.",
        )
        clarity = resolve_water_clarity(base_stain, stirred_up)

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
        base_stain=base_stain,
        stirred_up=stirred_up,
        structure_type=structure,
        water_temp_override_f=water_temp_override,
        fish_depth_ft=fish_depth,
        forage=forage,
    )
