"""
Folium-based interactive map for Nolin River Lake: modeled depth contour
lines you can zoom into, named reference spots, and support for capturing
an arbitrary click location anywhere on the lake (not just on a marker) -
handled by streamlit-folium in the page that renders this map.

Two extra toggleable layers show where the depth model's data actually
comes from (see core/bathymetry.py's module docstring for the full
picture): channel-model anchor points colored by how their depth_ft was
sourced (data/nolin_channel.json's "depth_source" field - surveyed
benchmark, read off historic contour lines, or extrapolated along the
gradient), and the small set of real digitized points from pre-dam USGS
topo sheets (data/historic_bathymetry.csv). Both are off the beaten path
of "just draw contours" but make it obvious at a glance which parts of
the lake are backed by something more than the Gaussian channel guess.
"""
from __future__ import annotations
import folium

from .bathymetry import contour_lines, lake_center, get_depth_at_ft, load_channel
from .historic_bathymetry import load_historic_points

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

    SOURCE_STYLE = {
        "benchmark":    {"color": "#1a9850", "label": "USGS surveyed benchmark (highest confidence)"},
        "contour_read": {"color": "#fdae61", "label": "Read off 1953/54 topo contour lines (medium confidence)"},
        "extrapolated": {"color": "#999999", "label": "Extrapolated along the gradient (lower confidence)"},
    }
    channel_group = folium.FeatureGroup(name="Channel depth points (data source)", show=True)
    seen_channel_pts = set()
    channel_data = load_channel()
    for branch in channel_data["branches"].values():
        for pt in branch["points"]:
            key = (pt["lat"], pt["lon"])
            if key in seen_channel_pts:
                continue
            seen_channel_pts.add(key)
            source = pt.get("depth_source", "extrapolated")
            style = SOURCE_STYLE.get(source, SOURCE_STYLE["extrapolated"])
            label = pt.get("label", "")
            popup = (
                f"<b>{label or 'Channel point'}</b><br>"
                f"Modeled depth: {pt['depth_ft']} ft<br>"
                f"<i>{style['label']}</i>"
            )
            folium.CircleMarker(
                location=[pt["lat"], pt["lon"]],
                radius=7 if source == "benchmark" else 5,
                color=style["color"],
                fill=True,
                fill_color=style["color"],
                fill_opacity=0.9,
                weight=2,
                tooltip=f"{label or 'Channel point'}: {pt['depth_ft']} ft ({source.replace('_', ' ')})",
                popup=folium.Popup(popup, max_width=260),
            ).add_to(channel_group)
    channel_group.add_to(m)

    hist_lat, hist_lon, hist_depth = load_historic_points()
    if len(hist_lat):
        historic_group = folium.FeatureGroup(
            name=f"Historic-topo depth points ({len(hist_lat)} pts, pre-dam USGS)", show=True
        )
        for lat, lon, depth in zip(hist_lat, hist_lon, hist_depth):
            folium.CircleMarker(
                location=[lat, lon],
                radius=4,
                color="#3d8bcc",
                fill=True,
                fill_color="#3d8bcc",
                fill_opacity=0.85,
                weight=1,
                tooltip=f"~{depth:g} ft (1953 USGS topo)",
                popup=f"Depth: ~{depth:g} ft<br><i>Read from the 1953 Bee Spring pre-dam USGS topo sheet</i>",
            ).add_to(historic_group)
        historic_group.add_to(m)

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
