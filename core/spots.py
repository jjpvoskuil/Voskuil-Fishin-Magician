"""
Nolin River Lake named spot map.

Spots are loaded from data/nolin_spots.json. Coordinates are anchored to
verified public sources where possible (USACE gauge, KY State Parks GNIS
record, U.S. Census TIGER geocoding) with nearby fishing-relevant
sub-spots offset a short distance from those anchors. See each spot's
"source" field. This is a planning aid, not survey-grade navigation data.

The map is rendered with Plotly's scattermapbox using the free
"open-street-map" style, which needs no API token - keeping the app
zero-config to deploy.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import plotly.graph_objects as go

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "nolin_spots.json"

STRUCTURE_COLORS = {
    "Main-lake point": "#1f77b4",
    "Creek channel / ledge": "#9467bd",
    "Cove / pocket (shallow cover)": "#2ca02c",
    "Flat": "#bcbd22",
    "Standing timber": "#8c564b",
    "Riprap / dam face": "#7f7f7f",
    "Bridge piling": "#e377c2",
    "Boat dock": "#ff7f0e",
}


def load_spots() -> dict:
    with open(DATA_PATH) as f:
        return json.load(f)


def nearest_spot(lat: float, lon: float, spots: list) -> dict:
    def dist(s):
        return math.hypot(s["lat"] - lat, s["lon"] - lon)
    return min(spots, key=dist)


def build_map_figure(spots: list, selected_id: str = None) -> go.Figure:
    lats = [s["lat"] for s in spots]
    lons = [s["lon"] for s in spots]
    colors = [STRUCTURE_COLORS.get(s["structure_type"], "#1f77b4") for s in spots]
    sizes = [22 if s["id"] == selected_id else 14 for s in spots]
    text = [s["name"] for s in spots]
    hover = [
        f"{s['name']}<br>{s['structure_type']}<br>Depth: {s['depth_range_ft'][0]}-{s['depth_range_ft'][1]} ft"
        for s in spots
    ]

    fig = go.Figure(
        go.Scattermapbox(
            lat=lats,
            lon=lons,
            mode="markers+text",
            marker=dict(size=sizes, color=colors),
            text=text,
            textposition="top center",
            hovertext=hover,
            hoverinfo="text",
            customdata=[s["id"] for s in spots],
        )
    )
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=11.5),
        margin=dict(l=0, r=0, t=0, b=0),
        height=560,
        showlegend=False,
    )
    return fig
