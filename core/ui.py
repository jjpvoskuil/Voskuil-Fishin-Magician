"""Shared Streamlit rendering helpers so the lure-block layout is
identical on the 7-Day Forecast page and the Lake Map page."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
import streamlit as st

from .lures import (
    LureBlock, BASE_STAIN_OPTIONS, DEFAULT_BASE_STAIN, STRUCTURE_TYPES,
    resolve_water_clarity, FORAGE_OPTIONS, DEFAULT_FORAGE,
)
from .thermocline import estimate_thermocline_ft, default_thermocline_input_ft


def render_lure_block(block: LureBlock):
    with st.container(border=True):
        st.markdown(f"**{block.name}**")
        if block.owned_items:
            owned_desc = "; ".join(
                f"{it['brand']} – {it['description']} (qty {it['quantity']})"
                for it in block.owned_items
            )
            st.success(f"✅ In your tackle box: {owned_desc}")
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


@dataclass
class LakeSetupOptions:
    water_clarity: str          # resolved: Clear / Green stained / Brown stained / Muddy
    base_stain: str              # what the angler picked before the stirred-up flag was applied
    stirred_up: bool
    structure_type: str
    water_temp_override_f: float
    fish_depth_ft: float
    thermocline_ft: float
    forage: list = field(default_factory=list)


def render_lake_setup_sidebar(
    include_structure: bool = True,
    default_structure_index: int = 0,
    default_water_temp_f: float = 75.0,
    default_fish_depth_ft: float = 10.0,
) -> LakeSetupOptions:
    """
    Shared "Lake Setup Options" sidebar. Every value returned here is a
    direct input the angler controls, and every page that shows a lure
    recommendation (7-Day Forecast, Lake Map) feeds ALL of them - water
    clarity, structure, water temp, fish depth, thermocline depth, and
    forage - straight into recommend() so the guidance stays consistent
    everywhere it's shown.

    Water color: Nolin normally runs a greenish-brown stain (leaning brown),
    but wind/rain can stir it up to muddy regardless of the usual color -
    so this is two independent inputs (base stain color, and a stirred-up
    flag) resolved into one effective clarity key for the lure engine.

    Water surface temp and the depth you're marking fish at on your own
    electronics are both required, direct inputs (Nolin has no live feed
    for either) - they always drive lure/season selection, depth-to-run
    guidance, and retrieval notes; there's no "estimate" fallback.

    Thermocline depth is also a direct input - pre-filled with a seasonal
    model estimate (Nolin is normally well-mixed outside roughly May-
    September; KDFWR has confirmed ~15 ft here in mid/late summer), but
    your own electronics/temp-probe reading always wins if you have one.
    Used to flag when a marked fish depth is likely below the oxygen-
    depleted zone.

    Forage: which baitfish/prey are actually available right now. Gizzard
    shad and bluegill are pre-checked since both are documented forage for
    Nolin bass; crawfish and shiners/minnows are optional add-ons. Selections
    nudge lure color/pattern choice and make sure at least one forage-matched
    lure shows up in the recommendation.
    """
    with st.sidebar:
        st.header("Lake Setup Options")

        base_stain = st.selectbox(
            "Water stain color (normal conditions)", BASE_STAIN_OPTIONS,
            index=BASE_STAIN_OPTIONS.index(DEFAULT_BASE_STAIN), key="lso_base_stain",
        )
        stirred_up = st.checkbox(
            "Stirred up / muddy right now (recent wind or rain)", key="lso_stirred_up"
        )
        clarity = resolve_water_clarity(base_stain, stirred_up)

        structure = None
        if include_structure:
            structure = st.selectbox("Structure type", STRUCTURE_TYPES, index=default_structure_index, key="lso_structure")

        st.divider()
        st.caption("Enter your own readings - Nolin has no live feed for either.")

        water_temp_override = st.number_input(
            "Water surface temp (°F)", min_value=32.0, max_value=100.0,
            value=default_water_temp_f, step=0.5, key="lso_water_temp",
        )

        fish_depth = st.number_input(
            "Depth fish are showing up on your electronics (ft)",
            min_value=0.0, max_value=100.0, value=default_fish_depth_ft, step=1.0, key="lso_fish_depth",
        )

        modeled_estimate = estimate_thermocline_ft(date.today())
        thermocline_ft = st.number_input(
            "Thermocline depth (ft)",
            min_value=0.0, max_value=100.0, value=default_thermocline_input_ft(date.today()),
            step=1.0, key="lso_thermocline",
            help="Where warm, oxygenated water gives way to cold, low-oxygen water below - read it off a "
                 "temp/DO probe if you have one. Pre-filled with a seasonal estimate otherwise.",
        )
        st.caption(
            f"Today's seasonal estimate: ~{modeled_estimate:.0f} ft"
            if modeled_estimate is not None
            else "Today's seasonal estimate: no thermocline expected (lake normally well-mixed this time of year)"
        )

        st.divider()
        forage = st.multiselect(
            "Forage available / being eaten",
            FORAGE_OPTIONS, default=DEFAULT_FORAGE, key="lso_forage",
        )

        st.caption("These carry over to the other pages too.")

    return LakeSetupOptions(
        water_clarity=clarity,
        base_stain=base_stain,
        stirred_up=stirred_up,
        structure_type=structure,
        water_temp_override_f=water_temp_override,
        fish_depth_ft=fish_depth,
        thermocline_ft=thermocline_ft,
        forage=forage,
    )
