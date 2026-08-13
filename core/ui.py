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
from .appstate import get_lake_spots

MAX_OWNED_THUMBNAILS = 4  # cap per lure block so a big category doesn't dominate the card
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


def render_lure_block(block: LureBlock):
    with st.container(border=True):
        st.markdown(f"**{block.name}**")
        if block.owned_items:
            # block.owned_items only ever contains items that both match this lure's
            # category AND match today's suggested color (core.lures._color_matched_
            # owned_items) - an owned item in the wrong color for today's water
            # clarity isn't shown here at all, so what's shown is always ready to go.
            owned_desc = "; ".join(
                f"{it['brand']} – {it['description']} (qty {it['quantity']})"
                for it in block.owned_items
            )
            st.success(f"✅ Color match in your tackle box: {owned_desc}")

            photos = [it for it in block.owned_items if resolve_image_source(it)]
            if photos:
                shown, extra = photos[:MAX_OWNED_THUMBNAILS], photos[MAX_OWNED_THUMBNAILS:]
                cols = st.columns(len(shown))
                for col, it in zip(cols, shown):
                    with col:
                        render_square_thumbnail(it, size_px=OWNED_THUMBNAIL_PX)
                        st.caption(f"{it['brand']} – {it['description']}"[:60])
                if extra:
                    st.caption(f"+ {len(extra)} more color-matched item(s) in this category (see Lure Inventory for photos).")
        else:
            st.caption("🛒 Not in your inventory yet - worth picking one up for this presentation.")
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
    default_water_temp_f: float = 75.0,
    default_fish_depth_ft: float = 10.0,
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
            index=BASE_STAIN_OPTIONS.index(DEFAULT_BASE_STAIN), key="lso_base_stain",
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
