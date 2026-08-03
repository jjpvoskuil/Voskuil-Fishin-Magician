"""Shared Streamlit rendering helpers so the lure-block layout is
identical on the 7-Day Forecast page and the Lake Map page."""
from __future__ import annotations
from dataclasses import dataclass
import streamlit as st

from .lures import LureBlock, WATER_CLARITY_OPTIONS, STRUCTURE_TYPES


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


@dataclass
class LakeSetupOptions:
    water_clarity: str
    structure_type: str
    water_temp_override_f: float = None
    fish_depth_ft: float = None


def render_lake_setup_sidebar(include_structure: bool = True, default_structure_index: int = 0) -> LakeSetupOptions:
    """
    Shared "Lake Setup Options" sidebar. Water clarity/structure are basic
    context; the water temp and fish-depth readings are optional overrides
    from the angler's own electronics (Nolin has no live feed for either) -
    when provided, they take priority over the app's estimates and get
    threaded into lure/season selection, depth-to-run guidance, and
    retrieval notes.
    """
    with st.sidebar:
        st.header("Lake Setup Options")
        clarity = st.selectbox("Water clarity", WATER_CLARITY_OPTIONS, index=1, key="lso_clarity")
        structure = None
        if include_structure:
            structure = st.selectbox("Structure type", STRUCTURE_TYPES, index=default_structure_index, key="lso_structure")

        st.divider()
        st.caption("Optional - readings from your own electronics beat our estimates when provided. "
                   "Leave at 0 to skip.")

        water_temp_input = st.number_input(
            "Water surface temp (°F)", min_value=0.0, max_value=100.0, value=0.0, step=0.5, key="lso_water_temp"
        )
        water_temp_override = water_temp_input if water_temp_input > 0 else None

        fish_depth_input = st.number_input(
            "Depth fish are showing up on your electronics (ft)",
            min_value=0.0, max_value=100.0, value=0.0, step=1.0, key="lso_fish_depth",
        )
        fish_depth = fish_depth_input if fish_depth_input > 0 else None

        if water_temp_override or fish_depth:
            st.caption("These carry over to the other pages too.")

    return LakeSetupOptions(
        water_clarity=clarity,
        structure_type=structure,
        water_temp_override_f=water_temp_override,
        fish_depth_ft=fish_depth,
    )
