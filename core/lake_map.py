"""
Folium-based interactive map for Nolin River Lake: real, GPS-tagged fish
attractors placed by Kentucky Fish & Wildlife (data/nolin_fish_attractors.csv,
core/fish_attractors.py) plus the angler's own saved spots
(data/lake_spots.csv, core/lake_spots.py). Both are on by default and each
can be toggled independently via a small folium.LayerControl.

Earlier versions of this map also drew a pre-dam bottom-cover layer, a
modeled-depth channel-point layer, a historic-topo depth-point layer, and
the real digitized shoreline outline, all behind a much busier
folium.LayerControl, plus an explanatory dialog on the page about where
that data came from. Per user feedback, all of that was removed in favor
of a simpler map: the one thing that's unambiguously real, GPS-placed data
(fish attractors) plus the spots the angler records themselves - no
modeled/derived layers, no disclaimer needed. A follow-up request asked
for the layer toggle back for just these two remaining layers, so there's
still a (much smaller) LayerControl here. Support for clicking anywhere on
the lake (not just on a marker) to drop a new pin is handled by
streamlit-folium in the page that renders this map (pages/2_Lake_Map.py).
"""
from __future__ import annotations
import folium

from .bathymetry import lake_center
from .fish_attractors import load_fish_attractors
from .lake_spots import split_bottom_structure

ATTRACTOR_STYLE = {
    "Brush":           "#6b3e26",
    "Christmas Trees": "#1a7a3c",
    "Pallet Stack":    "#8a5a2b",
    "Plastic":         "#c0392b",
    "Spider Hump":     "#7a5299",
    "Reef Ball":       "#555555",
    "Rock":            "#777777",
}
ATTRACTOR_DEFAULT_COLOR = "#333333"


def _spot_popup_html(spot: dict) -> str:
    lines = [f"<b>{spot['name']}</b>"]
    if spot.get("location_type"):
        lines.append(spot["location_type"])
    bottom = split_bottom_structure(spot.get("bottom_structure", ""))
    if bottom:
        lines.append(", ".join(bottom))
    if spot.get("main_depth_ft"):
        lines.append(f"Main area: {spot['main_depth_ft']} ft")
    if spot.get("transition_depth_ft"):
        grade = spot.get("transition_grade", "")
        lines.append(f"Transition: {spot['transition_depth_ft']} ft" + (f" ({grade})" if grade else ""))
    if spot.get("notes"):
        lines.append(f"<i>{spot['notes']}</i>")
    return "<br>".join(lines)


def build_folium_map(user_spots: list, clicked: dict = None, selected_spot_id: str = None,
                      zoom_start: int = 13) -> folium.Map:
    center_lat, center_lon = lake_center()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles="OpenStreetMap",
                    control_scale=True, max_zoom=19, prefer_canvas=True)

    attractors = load_fish_attractors()
    attractor_group = folium.FeatureGroup(name=f"Fish attractors ({len(attractors)})", show=True)
    for a in attractors:
        color = ATTRACTOR_STYLE.get(a["structure_type"], ATTRACTOR_DEFAULT_COLOR)
        folium.CircleMarker(
            location=[a["lat"], a["lon"]],
            radius=4,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            weight=1,
            tooltip=f"{a['structure_type']} ({a['ident']})",
            popup=(
                f"<b>{a['structure_type']}</b><br>ID: {a['ident']}<br>"
                f"<i>Kentucky Fish &amp; Wildlife fish attractor</i>"
            ),
        ).add_to(attractor_group)
    attractor_group.add_to(m)

    spot_group = folium.FeatureGroup(name=f"My saved spots ({len(user_spots)})", show=True)
    for s in user_spots:
        is_selected = selected_spot_id is not None and s["spot_id"] == selected_spot_id
        folium.Marker(
            location=[float(s["lat"]), float(s["lon"])],
            tooltip=s["name"],
            popup=folium.Popup(_spot_popup_html(s), max_width=260),
            icon=folium.Icon(color="red" if is_selected else "blue", icon="map-pin", prefix="fa"),
        ).add_to(spot_group)
    spot_group.add_to(m)

    # Deliberately outside both toggleable groups: this marks where a click
    # currently sits before it's saved, so hiding "My saved spots" (a
    # different layer) shouldn't also hide the thing you're actively adding.
    if clicked and not selected_spot_id:
        folium.Marker(
            location=[clicked["lat"], clicked["lon"]],
            tooltip="New spot - not saved yet",
            popup="Fill in the form on the right and save to keep this spot.",
            icon=folium.Icon(color="orange", icon="crosshairs", prefix="fa"),
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
