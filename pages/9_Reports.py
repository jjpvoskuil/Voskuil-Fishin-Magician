"""
Reports - punch-list #92, first pass, plus a first stab at its predictive
half.

UI on top of core/reports.py (see that module's own docstring for the full
design rationale). Pick a factor (session parameter / weather / moon /
location / lure / etc.) and a success metric, optionally narrow it down by
date range / angler / time segment / species, and get a chart + data table
+ an Excel export of both the aggregated report and the underlying filtered
rows - then, below that, a "Predict a future day" section: a first,
deliberately-scoped-to-one-variable pass at the OTHER half of the angler's
original ask ("predict success in future days given forecasted parameter
and/or known moon illumination"). See core.reports.predict_by_moon_
illumination()'s own docstring for the full "why moon illumination first,
and why a historical lookup instead of a fitted model" reasoning - short
version: moon phase for a future date is exact (no forecast uncertainty),
and the real live data (~126 trustworthy trips) is thin for fitting
anything more sophisticated across this page's many candidate factors.
A second predictor - barometric pressure trend, from a real weather
forecast this time - lives right below it, at the angler's own explicit
direction ("lets try weather but lets focus only on barometric pressure
forecast first"); see core.reports.predict_by_pressure_trend()'s own
docstring for how it stays honest about the bounded forecast window that
one genuinely depends on.
"""
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st

from core.activity_log import format_weight_lb_oz
from core.appstate import get_trip_history, get_anglers, get_weather_bundle, github_token, repo_slug
from core.reports import (
    build_reports_dataframe, compute_report, species_options,
    predict_by_moon_illumination, predict_by_pressure_trend,
    FACTOR_OPTIONS, METRIC_OPTIONS, SPECIES_FILTERABLE_METRICS, DATE_FACTOR_COLUMNS,
    WATER_TEMP_BUCKET_FACTOR, DEFAULT_WATER_TEMP_BUCKET_WIDTH_F, MIN_PREDICTION_SAMPLES,
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
    "🔮 A first, deliberately narrow stab at predicting a future day lives at the bottom of "
    "this page - moon illumination (zero forecast uncertainty) and now barometric pressure "
    "trend (a real weather forecast, so it carries real forecast-accuracy uncertainty)."
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

# Punch-list #92 follow-up: "Water Temp Band" (the 5 fixed biological
# stages) is too coarse while a whole season's worth of trips hasn't been
# logged yet - the angler's own report was that the real observed range so
# far is only ~10-15°F wide, so nearly every trip lands in one or two of
# those five bands. This lets the bucket width be tuned instead of fixed -
# tight while the season's range is narrow, wider once it isn't. Only
# shown for that one factor; every other factor ignores this control.
water_temp_bucket_width = DEFAULT_WATER_TEMP_BUCKET_WIDTH_F
if factor_col == WATER_TEMP_BUCKET_FACTOR:
    water_temp_bucket_width = st.number_input(
        "Bucket width (°F)", min_value=0.5, max_value=20.0, value=DEFAULT_WATER_TEMP_BUCKET_WIDTH_F, step=0.5,
        key="rpt_water_temp_bucket_width",
        help="How wide each water-temp bucket should be. Narrower gives more buckets over "
             "your current logged range; widen it back out once a fuller season's worth of "
             "temperature spread makes fewer, bigger buckets more useful.",
    )

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
    water_temp_bucket_width_f=water_temp_bucket_width,
)

st.divider()

if report.empty:
    st.caption("No data matches these filters yet - try widening the date range or clearing a filter.")
else:
    display_col = factor_col
    report_display = report.copy()
    if factor_col in DATE_FACTOR_COLUMNS:
        report_display[display_col] = report_display[display_col].apply(
            lambda d: d.strftime("%m/%d/%Y") if pd.notna(d) else "-"
        )

    # --- Chart --------------------------------------------------------------------
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

    # --- Table --------------------------------------------------------------------
    table = report_display.rename(columns={display_col: factor_label, "value": metric_label, "n": "Sample size (n)"})
    st.dataframe(table, width='stretch', hide_index=True)
    st.caption(
        f"{len(report_display)} row(s) shown. \"Sample size (n)\" is how many trips/catches back "
        "each row - a striking value from a very small n isn't necessarily reliable."
    )

    # --- Excel export ---------------------------------------------------------------
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

# --- Predict a future day (punch-list #92's predictive half, first pass) -------------
# Deliberately independent of the "Factor" picker above (always moon
# illumination, for this first pass - see core.reports.predict_by_moon_
# illumination()'s own docstring for why) but reuses the Metric/Species/
# date-range/Angler/Segment filters already chosen above, so this stays a
# "the same lens I'm already using above, pointed at a future date" tool
# rather than a wholly separate control panel to keep in sync by hand.
st.divider()
st.subheader("🔮 Predict a future day")
st.caption(
    "First pass at punch-list #92's other ask, one variable at a time - both predictors below "
    "share the same target date and the same Species/date-range/Angler/Segment filters set "
    "above, and both are historical-bucket LOOKUPS (not fitted statistical models): each one "
    "figures out which bucket the target date falls into, then reports back that bucket's real "
    "historical average from your logged trips - \"here's what happened historically under "
    "this same condition,\" not a forecast in the statistical sense."
)

predict_date = st.date_input(
    "Predict for date", value=date.today() + timedelta(days=1), key="rpt_predict_date",
    help="Any date works, including a past one - useful for sanity-checking a prediction "
         "against a day that's already been fished and logged. The pressure-trend predictor "
         "below is further limited to whatever window the fetched weather forecast actually "
         "covers.",
)

prediction = predict_by_moon_illumination(
    trips_df, fish_df, predict_date, metric_key=metric_key,
    species=species_choice, date_start=date_start, date_end=date_end,
    anglers=anglers_choice or None, segments=segments_choice or None,
)


def _format_metric_value(key: str, value) -> str:
    if value is None:
        return "—"
    if key == "biggest_fish":
        return format_weight_lb_oz(value) or "—"
    if key == "fish_per_hour":
        return f"{value:.2f} fish/hr"
    if key == "trip_count":
        return f"{value:.0f} trip(s)"
    return f"{value:.0f} fish"  # total_fish


st.markdown("**🌙 Moon illumination (night before)**")
pred_col1, pred_col2 = st.columns([1, 2])
pred_col1.metric(
    f"Predicted {metric_label}",
    _format_metric_value(metric_key, prediction["predicted_value"]),
)
moon_pct = prediction["moon_illumination_pct"]
moon_bucket = prediction["moon_illumination_bucket"]
n = prediction["n"]
if n == 0:
    pred_col2.caption(
        f"🌙 {moon_pct:.0f}% illuminated the night before ({moon_bucket} bucket) - no trips logged "
        "under this moon-illumination bucket yet (with the filters above), so there's nothing to "
        "predict from."
    )
elif prediction["low_sample"]:
    pred_col2.caption(
        f"🌙 {moon_pct:.0f}% illuminated the night before ({moon_bucket} bucket) - based on only "
        f"{n} logged trip(s) under this bucket, fewer than the {MIN_PREDICTION_SAMPLES} this app's "
        "own weight-calibration engine requires before trusting a pattern elsewhere - treat this "
        "one with real skepticism."
    )
else:
    pred_col2.caption(
        f"🌙 {moon_pct:.0f}% illuminated the night before ({moon_bucket} bucket) - based on {n} "
        "logged trips under this same bucket."
    )

# --- Predict a future day: barometric pressure trend (forecasted) -------------------
# Second predictor, at the angler's own explicit direction ("lets try
# weather but lets focus only on barometric pressure forecast first").
# Requests 16 days (Open-Meteo's real forecast_days cap - see
# core.weather.fetch_forecast()) rather than this app's usual 7, to
# maximize how far out `predict_date` above can actually be covered - a
# separate st.cache_data entry from the 7-day bundle other pages use
# (get_weather_bundle() caches per its own `days` argument), same
# fail-soft "no live weather, no crash" convention pages/6_Spot_Session.py
# already uses elsewhere on this app.
try:
    _pressure_bundle = get_weather_bundle(16)
except Exception:
    _pressure_bundle = None

pressure_prediction = predict_by_pressure_trend(
    trips_df, fish_df, predict_date, _pressure_bundle, metric_key=metric_key,
    species=species_choice, date_start=date_start, date_end=date_end,
    anglers=anglers_choice or None, segments=segments_choice or None,
)

st.markdown("**📉 Barometric pressure trend (forecasted)**")
if not pressure_prediction["forecast_available"]:
    if _pressure_bundle is None:
        st.caption(
            "📉 No live weather forecast available right now, so there's nothing to predict "
            "pressure trend from for this date - moon illumination above still works."
        )
    else:
        _times = _pressure_bundle.hourly.get("time") or []
        if _times:
            _lo = min(_times)[:10]
            _hi = max(_times)[:10]
            _window_note = f"the fetched forecast only covers {_lo} through {_hi}"
        else:
            _window_note = "the fetched forecast has no usable hourly data right now"
        st.caption(
            f"📉 {predict_date.isoformat()} is outside the fetched weather forecast's window - "
            f"{_window_note}. Pick a date in that range for a pressure-based prediction (moon "
            "illumination above still works for any date)."
        )
else:
    pcol1, pcol2 = st.columns([1, 2])
    pcol1.metric(
        f"Predicted {metric_label}",
        _format_metric_value(metric_key, pressure_prediction["predicted_value"]),
    )
    p_trend = pressure_prediction["pressure_trend_24h"]
    p_band = pressure_prediction["pressure_trend_band"]
    p_n = pressure_prediction["n"]
    if p_n == 0:
        pcol2.caption(
            f"📉 Forecast: {p_trend:+.1f} hPa/24h ({p_band}) - no trips logged under this "
            "pressure-trend bucket yet (with the filters above), so there's nothing to predict "
            "from."
        )
    elif pressure_prediction["low_sample"]:
        pcol2.caption(
            f"📉 Forecast: {p_trend:+.1f} hPa/24h ({p_band}) - based on only {p_n} logged "
            f"trip(s) under this bucket, fewer than the {MIN_PREDICTION_SAMPLES} this app's own "
            "weight-calibration engine requires before trusting a pattern elsewhere - treat this "
            "one with real skepticism. This also carries real weather-forecast uncertainty on "
            "top of that, unlike the moon-illumination prediction above."
        )
    else:
        pcol2.caption(
            f"📉 Forecast: {p_trend:+.1f} hPa/24h ({p_band}) - based on {p_n} logged trips under "
            "this same bucket. Still a real weather forecast, not a certainty - accuracy degrades "
            "the further out `predict_date` is, unlike the moon-illumination prediction above."
        )
