"""Shared Streamlit rendering helpers so the lure-block layout is
identical on the 7-Day Forecast page and the Lake Map page."""
from __future__ import annotations
from dataclasses import dataclass, field
import streamlit as st

from .lures import (
    LureBlock, BASE_STAIN_OPTIONS, DEFAULT_BASE_STAIN, STRUCTURE_TYPES,
    resolve_water_clarity, FORAGE_OPTIONS, DEFAULT_FORAGE,
)


def render_lure_block(block: LureBlock):
    with st.container(border=True):
        st.markdown(f"**{block.name}**")
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


def render_thermocline_caption(band):
    """Small shared caption for the modeled thermocline band, or the fact
    that the lake is expected to be well-mixed (no thermocline) right now."""
    if band is None:
        st.caption(
            "🌡️ Modeled thermocline: none expected this time of year - Nolin is "
            "typically well-mixed top to bottom outside of late spring-early fall."
        )
    else:
        lo, hi = band
        st.caption(
            f"🌡️ Modeled thermocline: ~{lo:.0f}-{hi:.0f} ft (KDFWR reports Nolin at "
            f"~15 ft in mid/late summer; not a live reading - Nolin has no public "
            f"real-time DO/temperature profile buoy)."
        )


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
    Shared "Lake Setup Options" sidebar.

    Water color: Nolin normally runs a greenish-brown stain (leaning brown),
    but wind/rain can stir it up to muddy regardless of the usual color -
    so this is two independent inputs (base stain color, and a stirred-up
    flag) resolved into one effective clarity key for the lure engine.

    Water surface temp and the depth you're marking fish at on your own
    electronics are both required, direct inputs (Nolin has no live feed
    for either) - they always drive lure/season selection, depth-to-run
    guidance, and retrieval notes; there's no "estimate" fallback.

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
        forage=forage,
    )
