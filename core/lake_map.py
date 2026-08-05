"""
Folium-based interactive map for Nolin River Lake: named reference spots,
a real-shoreline-restricted pre-dam bottom-cover layer, and support for
capturing an arbitrary click location anywhere on the lake (not just on a
marker) - handled by streamlit-folium in the page that renders this map.

No numeric depth contour lines are rendered here (see core/bathymetry.py's
module docstring) - two attempts at deriving smooth depth isolines from
public data both produced results that didn't hold up, and continuing to
render them implied a precision the underlying data can't support. What IS
shown, and IS defensible from the same public USGS sources, is bottom
cover: core/cover.py classifies each cell of the real lake footprint
(data/nolin_shoreline.geojson) by what it looked like on the pre-dam
topo sheets - wooded (likely standing timber), cleared (likely open
bottom), or the original stream channel. Land-cover classification only
needs the color/symbol on the scan, not precise elevation, so it tolerates
the same registration slop that broke the depth work.

Two more toggleable layers show provenance: channel-model anchor points
colored by how their depth_ft was sourced (data/nolin_channel.json's
"depth_source" field), and the real digitized shoreline itself
(data/nolin_shoreline.geojson) as a thin reference outline.
"""
from __future__ import annotations
import folium

from .bathymetry import lake_center, load_channel, METERS_PER_DEG_LAT, _meters_per_deg_lon
from .cover import load_cover_cells, get_cover_at
from .historic_bathymetry import load_historic_points
from .shoreline import shoreline_polygons

COVER_STYLE = {
    "wooded":  {"color": "#2d7a2d", "label": "Wooded before flooding - likely standing timber"},
    "cleared": {"color": "#d9a441", "label": "Cleared/open before flooding - likely open bottom"},
    "water":   {"color": "#3d8bcc", "label": "Original stream channel"},
}


def build_folium_map(spots: list, clicked=None, zoom_start: int = 13) -> folium.Map:
    center_lat, center_lon = lake_center()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles="OpenStreetMap",
                    control_scale=True, max_zoom=19)

    cover_cells = load_cover_cells()
    if cover_cells:
        cover_group = folium.FeatureGroup(
            name=f"Pre-dam bottom cover ({len(cover_cells)} cells, USGS topo)", show=True
        )
        lat0 = sum(c["lat"] for c in cover_cells) / len(cover_cells)
        m_per_lon = _meters_per_deg_lon(lat0)
        half_m = 27.4  # half the ~55m aggregation cell used to build data/nolin_cover.csv
        half_lat = half_m / METERS_PER_DEG_LAT
        half_lon = half_m / m_per_lon
        for c in cover_cells:
            style = COVER_STYLE.get(c["dominant_class"], COVER_STYLE["cleared"])
            bounds = [
                [c["lat"] - half_lat, c["lon"] - half_lon],
                [c["lat"] + half_lat, c["lon"] + half_lon],
            ]
            popup = (
                f"<b>{c['dominant_class'].title()}</b><br>"
                f"{style['label']}<br>"
                f"wooded {c['wooded_frac']*100:.0f}% / cleared {c['cleared_frac']*100:.0f}% / "
                f"stream {c['water_frac']*100:.0f}%<br>"
                f"<i>from {c['n_px']} classified source pixels</i>"
            )
            folium.Rectangle(
                bounds=bounds,
                color=style["color"],
                weight=0,
                fill=True,
                fill_color=style["color"],
                fill_opacity=0.55,
                tooltip=f"{c['dominant_class']} ({style['label']})",
                popup=folium.Popup(popup, max_width=260),
            ).add_to(cover_group)
        cover_group.add_to(m)

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

    shoreline_group = folium.FeatureGroup(name="Real digitized shoreline (reference)", show=False)
    for poly in shoreline_polygons():
        folium.PolyLine(
            locations=[(lat, lon) for lon, lat in poly],
            color="#000000",
            weight=1,
            opacity=0.5,
        ).add_to(shoreline_group)
    shoreline_group.add_to(m)

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
        cover_hit = get_cover_at(clicked["lat"], clicked["lon"])
        if cover_hit:
            style = COVER_STYLE.get(cover_hit["dominant_class"], COVER_STYLE["cleared"])
            cover_txt = f"{cover_hit['dominant_class'].title()} pre-flooding - {style['label']}"
        else:
            cover_txt = "no pre-dam cover data at this point"
        folium.Marker(
            location=[clicked["lat"], clicked["lon"]],
            tooltip="Selected location",
            popup=f"Selected location<br>Bottom cover: {cover_txt}",
            icon=folium.Icon(color="red", icon="crosshairs", prefix="fa"),
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
