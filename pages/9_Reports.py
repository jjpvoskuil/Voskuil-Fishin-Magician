"""
Reports - punch-list #92, first pass.

UI on top of core/reports.py (see that module's own docstring for the full
design rationale). Pick a factor (session parameter / weather / moon /
location / lure / etc.) and a success metric, optionally narrow it down by
date range / angler / time segment / species, and get a chart + data table
+ an Excel export of both the aggregated report and the underlying filtered
rows.

Deliberately out of scope for this pass (see the caption right below the
title, and core/reports.py's module docstring): predicting future success
from a forecast. This page is the descriptive/correlational half only -
"what's worked" not "what will work" - per the angler's own framing that
this first pass is a basic framework expected to iterate a lot.
"""
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st

from core.appstate import get_trip_history, get_anglers, github_token, repo_slug
from core.reports import (
    build_reports_dataframe, compute_report, species_options,
    FACTOR_OPTIONS, METRIC_OPTIONS, SPECIES_FILTERABLE_METRICS, DATE_FACTOR_COLUMNS,
)
from core.scoring import SEGMENTS
from core.storage import sync_data_from_data_branch
from core.ui import inject_mobile_css

st.set_page_config(page_title="Reports - Nolin Lake", page_icon="📈", layout="wide")
inject_mobile_css()
st.title("📈 Reports")

st.caption(
    "Slice your logged trip history by any session parameter, weather condition, moon "
    "illumination, location, lure, or technique, and see how it lines up with fishing "
    "success. Pick a factor and a metric below, narrow it down with the filters if you "
    "want, then read the chart/table or export both to Excel."
)
st.caption(
    "🔮 Not in this first pass: predicting future success from a forecast (punch-list #92's "
    "own \"predict success in future days\" ask). This page is the descriptive/correlational "
    "half only for now - that's the planned next iteration."
)

# Mirrors pages/8_Leaderboard.py's own "🔄 Refresh from GitHub" button -
# same 5-minute get_trip_history() cache, same reason a manual refresh can
# matter here (see that page's own comment for the full "why").
_refresh_col, _ = st.columns([1, 3])
if _refresh_col.button(
    "🔄 Refresh from GitHub", help=(
        "Pulls the latest trip_log.csv (and the rest of data/) from GitHub right now, and "
        "clears this page's own cache of it - use this if you know a trip was saved but this "
        "page still looks out of date."
    ),
):
    _token = github_token()
    if _token:
        _ok, _msg = sync_data_from_data_branch(_token, repo_slug())
        get_trip_history.clear()
        (st.success if _ok else st.warning)(_msg)
    else:
        st.info("No GitHub token configured here - nothing to refresh.")

rows = get_trip_history()

if not rows:
    st.info(
        "No trips logged yet - reports fill in as you log sessions on the **Spot Session** page."
    )
    st.stop()

trips_df, fish_df = build_reports_dataframe(rows)

# --- Controls -------------------------------------------------------------------
FACTOR_LABELS = list(FACTOR_OPTIONS.keys())
METRIC_LABELS = list(METRIC_OPTIONS.keys())

c1, c2 = st.columns([1, 1])
factor_label = c1.selectbox("Factor (x-axis)", FACTOR_LABELS, index=FACTOR_LABELS.index("Lure Category"), key="rpt_factor")
metric_label = c2.selectbox("Success metric", METRIC_LABELS, index=0, key="rpt_metric")
factor_col = FACTOR_OPTIONS[factor_label]
metric_key = METRIC_OPTIONS[metric_label]

species_supported = metric_key in SPECIES_FILTERABLE_METRICS
c3, c4 = st.columns([1, 1])
if species_supported:
    species_choice = c3.selectbox("Species", ["All species"] + species_options(fish_df), key="rpt_species")
else:
    c3.selectbox("Species", ["All species"], disabled=True, key="rpt_species_disabled",
                 help="This metric is inherently per-trip, not per-catch, so a species filter "
                      "wouldn't change anything - and would silently drop trips logged before "
                      "per-fish detail existed.")
    species_choice = "All species"

angler_roster = get_anglers()
anglers_present = sorted(set(trips_df["angler"]) - set(angler_roster)) if not trips_df.empty else []
ANGLER_OPTIONS = angler_roster + [a for a in anglers_present if a != "Unspecified"] + (
    ["Unspecified"] if (not trips_df.empty and "Unspecified" in set(trips_df["angler"])) else []
)
anglers_choice = c4.multiselect("Anglers (blank = all)", ANGLER_OPTIONS, key="rpt_anglers")

c5, c6, c7 = st.columns([1, 1, 1])
# Not just "trips_df.empty" - a non-empty trips_df whose "date" column is
# entirely unparseable (e.g. every row has a malformed trip_date) leaves
# dropna() empty too, and an empty Series' .min() is float NaN, not None -
# st.date_input() rejects a float outright, so both cases need the same
# "fall back to a 30-day window" treatment.
_valid_dates = trips_df["date"].dropna() if not trips_df.empty else pd.Series(dtype=object)
earliest = _valid_dates.min() if not _valid_dates.empty else None
default_start = earliest if earliest else (date.today() - timedelta(days=29))
date_start = c5.date_input("From", value=default_start, key="rpt_date_start")
date_end = c6.date_input("To", value=date.today(), key="rpt_date_end")
segments_choice = c7.multiselect("Time segments (blank = all)", SEGMENTS, key="rpt_segments")

if date_start > date_end:
    st.warning("From date is after To date - swapping them.")
    date_start, date_end = date_end, date_start

report = compute_report(
    trips_df, fish_df, factor_col, metric_key,
    species=species_choice, date_start=date_start, date_end=date_end,
    anglers=anglers_choice or None, segments=segments_choice or None,
)

st.divider()

if report.empty:
    st.caption("No data matches these filters yet - try widening the date range or clearing a filter.")
    st.stop()

display_col = factor_col
report_display = report.copy()
if factor_col in DATE_FACTOR_COLUMNS:
    report_display[display_col] = report_display[display_col].apply(
        lambda d: d.strftime("%m/%d/%Y") if pd.notna(d) else "-"
    )

# --- Chart ------------------------------------------------------------------------
# Date-based factors read naturally as a line over time; everything else
# (categorical factors) reads naturally as a bar per category - matching
# how the rest of this app already draws these two shapes
# (core.ui.render_line_chart() for time series, Leaderboard's st.bar_chart
# for categorical rankings).
is_date_factor = factor_col in DATE_FACTOR_COLUMNS
chart_series = pd.Series(
    report_display["value"].values, index=report_display[display_col].astype(str).values, name=metric_label,
)
if is_date_factor:
    st.line_chart(chart_series)
else:
    st.bar_chart(chart_series, horizontal=(len(report_display) > 8))

# --- Table ------------------------------------------------------------------------
table = report_display.rename(columns={display_col: factor_label, "value": metric_label, "n": "Sample size (n)"})
st.dataframe(table, width='stretch', hide_index=True)
st.caption(
    f"{len(report_display)} row(s) shown. \"Sample size (n)\" is how many trips/catches back "
    "each row - a striking value from a very small n isn't necessarily reliable."
)

# --- Excel export -------------------------------------------------------------------
# Two sheets: the aggregated report actually being looked at, plus the
# underlying filtered raw trip rows, so the export is useful for further
# analysis outside the app, not just a screenshot of the chart.
filtered_trips_export = trips_df
if not filtered_trips_export.empty:
    if date_start is not None:
        filtered_trips_export = filtered_trips_export[
            filtered_trips_export["date"].notna() & (filtered_trips_export["date"] >= date_start)
        ]
    if date_end is not None:
        filtered_trips_export = filtered_trips_export[
            filtered_trips_export["date"].notna() & (filtered_trips_export["date"] <= date_end)
        ]
    if anglers_choice:
        filtered_trips_export = filtered_trips_export[filtered_trips_export["angler"].isin(anglers_choice)]
    if segments_choice:
        filtered_trips_export = filtered_trips_export[filtered_trips_export["segment"].isin(segments_choice)]

buffer = BytesIO()
with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
    table.to_excel(writer, sheet_name="Report", index=False)
    filtered_trips_export.drop(columns=["fish_per_hour"], errors="ignore").to_excel(
        writer, sheet_name="Underlying trips", index=False
    )
buffer.seek(0)

st.download_button(
    "⬇️ Export to Excel",
    data=buffer,
    file_name=f"nolin_lake_report_{date.today().isoformat()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Downloads the report above (as shown) plus the filtered raw trip rows behind it, "
         "as a two-sheet Excel workbook.",
)
