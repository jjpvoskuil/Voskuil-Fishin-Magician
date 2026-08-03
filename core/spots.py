"""
Nolin River Lake named reference spots.

Spots are loaded from data/nolin_spots.json. Coordinates are anchored to
verified public sources where possible (USACE gauge, KY State Parks GNIS
record, U.S. Census TIGER geocoding) with nearby fishing-relevant
sub-spots offset a short distance from those anchors. See each spot's
"source" field. This is a planning aid, not survey-grade navigation data.

The interactive map itself (with modeled depth contours) is built in
core/lake_map.py.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

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
