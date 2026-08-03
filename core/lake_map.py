"""
Folium-based interactive map for Nolin River Lake: modeled depth contour
lines you can zoom into, named reference spots, and support for capturing
an arbitrary click location anywhere on the lake (not just on a marker) -
handled by streamlit-folium in the page that renders this map.
"""
from __future__ import annotations
import folium

from .bathymetry import contour_lines, lake_center, get_depth_at_ft

# Light (shallow) to dark navy (deep) - a look reminiscent of real chart plotters.
DEPTH_COLOR_STOPS = [
    (0, "#cfe8ff"),
    (10, "#8fc4f0"),
    (20, "#5aa0e0"),
    (30, "#2f78c8"),
    (45, "#1c56a5"),
    (60, "#123a78"),
    (85, "#0a2450"),
]


def _color_for_depth(depth_ft: float) -> str:
    for (d0, c0), (d1, c1) in zip(DEPTH_COLOR_STOPS, DEPTH_COLOR_STOPS[1:]):
        if d0 <= depth_ft <= d1:
            return c1
    return DEPTH_COLOR_STOPS[-1][1] if depth_ft > DEPTH_COLOR_STOPS[-1][0] else DEPTH_COLOR_STOPS[0][1]


def build_folium_map(spots: list, clicked=None, zoom_start: int = 13) -> folium.Map:
    center_lat, center_lon = lake_center()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles="OpenStreetMap",
                    control_scale=True, max_zoom=19)

    contour_group = folium.FeatureGroup(name="Modeled depth contours (ft)", show=True)
    for level in contour_lines():
        color = _color_for_depth(level["depth_ft"])
        weight = 1 + level["depth_ft"] / 20
        for path in level["paths"]:
            folium.PolyLine(
                locations=path,
                color=color,
                weight=weight,
                opacity=0.85,
                tooltip=f"~{level['depth_ft']} ft",
            ).add_to(contour_group)
    contour_group.add_to(m)

    spot_group = folium.FeatureGroup(name="Named reference spots", show=True)
    for s in spots:
        folium.Marker(
            location=[s["lat"], s["lon"]],
            tooltip=s["name"],
            popup=folium.Popup(
                f"<b>{s['name']}</b><br>{s['structure_type']}<br>"
                f"Depth: {s['depth_range_ft'][0]}-{s['depth_range_ft'][1]} ft<br>"
                f"<i>{s['source']}</i>",
                max_width=250,
            ),
            icon=folium.Icon(color="orange", icon="anchor", prefix="fa"),
        ).add_to(spot_group)
    spot_group.add_to(m)

    if clicked:
        depth = get_depth_at_ft(clicked["lat"], clicked["lon"])
        depth_txt = f"~{depth} ft (modeled)" if depth is not None else "no data at this point"
        folium.Marker(
            location=[clicked["lat"], clicked["lon"]],
            tooltip="Selected location",
            popup=f"Selected location<br>Depth: {depth_txt}",
            icon=folium.Icon(color="red", icon="crosshairs", prefix="fa"),
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
