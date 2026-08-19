from datetime import timedelta

import pandas as pd
import streamlit as st

from core.appstate import (
    get_weather_bundle, get_calibrated_weights, get_lake_level, get_lake_level_history,
    get_surface_water_quality, get_water_quality_log, github_token, repo_slug,
)
from core.scoring import score_day
from core.weather import lake_today, HOME_TREND_CHART_PAST_DAYS
from core.lake_level import NORMAL_SUMMER_POOL_FT
from core.storage import commit_and_push
from core.water_quality_log import append_if_new, WATER_QUALITY_LOG_PATH
from core.lake_water_quality import SurfaceWaterQuality
from core.ui import inject_mobile_css, inject_compact_metric_css, render_line_chart

# Punch-list #20: fixed Y-axis range (°F) for this page's temperature trend
# charts (est. water temp, USACE surface water temp) - the real range
# Nolin Lake's surface plausibly sees across a season, so a real but small
# swing doesn't fill the whole chart height and read as more dramatic than
# it is. See core.ui.render_line_chart() for how this is actually applied.
TEMP_CHART_Y_DOMAIN = (45, 95)

st.set_page_config(page_title="Voskuil Fishin' Magician", page_icon="🎣", layout="wide")
inject_mobile_css()

st.title("🎣 Voskuil Fishin' Magician")
st.caption("Largemouth bass fishing forecasts for Nolin River Lake, KY")

st.markdown(
    """
This app blends weather, moon phase, and solunar theory into a 1-10 daily
activity forecast for largemouth bass on Nolin River Lake, then recommends
where to fish and what to throw. Use the sidebar to navigate:

- **7 Day Forecast** - the full week, drill into any day for best times, lures, colors, and technique.
- **Lake Map** - click any spot on the lake, then **Spot Session** to get a live, on-the-water
  recommendation and log what actually happened so the model can learn from it.
- **Trip History** - filter and review your logged trips, and see how the model is calibrating.
"""
)

bundle = None
weights, n_trips = {}, 0
try:
    weights, n_trips = get_calibrated_weights()
    bundle = get_weather_bundle(7)
except Exception as e:
    st.error(f"Couldn't fetch live weather data right now: {e}")
    st.caption("This can happen if Open-Meteo is briefly unreachable - try refreshing in a minute.")

# Independent of the weather bundle above - a USGS outage shouldn't block
# the weather-derived metrics, and vice versa. Unlike everything else on
# this page (all weather-derived estimates), lake level is a genuine live
# measurement - USGS gauge 03310900 ("Nolin Lake near Kyrock, KY") reports
# the reservoir's actual real-time pool elevation. See core/lake_level.py.
lake_level = None
try:
    lake_level = get_lake_level()
except Exception:
    pass  # Shown as a footer caption fallback below rather than an st.error -
    # a missing "nice to have" live reading shouldn't read as alarming as a
    # failed weather fetch, which blocks the whole scored forecast above.

# Also independent - a stale/unreachable USACE report shouldn't block either
# of the sources above. This one is a genuine measured reading (not live -
# see core/lake_water_quality.py), so it's shown separately below as a
# clearly-dated secondary data point, not folded into "Today at a glance".
water_quality = None
try:
    water_quality = get_surface_water_quality()
except Exception:
    pass

# Punch-list #13: record this reading into the local historical log (see
# core/water_quality_log.py) so a real trend chart can accumulate over
# time - the live USACE page itself only ever has the CURRENT reading,
# nothing to chart a history from otherwise. append_if_new() is a cheap
# no-op except on the rare rerun where USACE has actually published a new
# survey since the last one logged (roughly every 1-2 weeks); only that
# case writes anything or reaches the git commit below. Same "nice to
# have, don't block the page" treatment as everything else on this page -
# a failure here (e.g. no write access, a git push conflict) just means
# this particular rerun's reading doesn't get archived, not an error shown
# to the angler.
if water_quality is not None:
    try:
        if append_if_new(water_quality):
            token = github_token()
            if token:
                commit_and_push(
                    [WATER_QUALITY_LOG_PATH], token, repo_slug(),
                    f"Log USACE water-quality reading {water_quality.observed_at.date().isoformat()}",
                )
    except Exception:
        pass

# Punch-list #16 (revised): the live USACE fetch above has been failing on
# the deployed app the same way it fails from this dev sandbox (no network
# path to lrl-wc.usace.army.mil at all - see core/lake_water_quality.py's
# docstring), so `water_quality` is None on effectively every real page
# load even though a real reading (from Aug 6) is already sitting in
# data/water_quality_log.csv. Rather than require a fresh successful fetch
# on THIS run just to show a periodic, dated survey - which USACE only
# republishes every 1-2 weeks anyway, so "fresh this run" was never really
# the point - fall back to the most recent logged reading whenever the
# live fetch didn't come back with anything. The tile's own help text
# always shows the real survey date either way, so this never claims to be
# more current than it is; `is_live_reading` just lets the tile say
# clearly when it's showing a cached fallback vs. a fetch that succeeded
# just now.
water_quality_display = water_quality
is_live_reading = water_quality is not None
if water_quality_display is None:
    try:
        logged = get_water_quality_log()
        if logged:
            water_quality_display = SurfaceWaterQuality(**logged[-1])
    except Exception:
        pass

# Punch-list #16: today's weather-derived score (activity score/est. water
# temp/moon phase/pressure trend) genuinely does need `bundle` - but lake
# level and the USACE reading are each fetched independently above and
# shouldn't disappear just because Open-Meteo happened to be rate-limited
# or briefly unreachable at the same moment. Computing `today` here, and
# rendering the metrics row below keyed off whichever of the three sources
# actually came back, means a weather-only outage (e.g. the 429s Open-Meteo
# free tier gives when its shared-IP rate limit is hit) still leaves lake
# level and the USACE reading visible instead of hiding all six behind one
# gate.
today = None
if bundle is not None:
    try:
        today = score_day(bundle, lake_today(), weights=weights)
    except ValueError as e:
        # Weather fetched fine, but today's date fell outside the returned window -
        # e.g. a briefly stale cached bundle right at the lake's local day rollover.
        st.warning(f"Today's forecast isn't available yet: {e}. Try refreshing in a moment.")

if today or lake_level or water_quality_display:
    st.subheader("Today at a glance")
    # Punch-list #16: put the current USACE reading on this same metrics
    # line (it used to be a separate caption below, cut off entirely
    # whenever `today` wasn't available even though it's an independent
    # fetch) and shrink this row's font so up to 6 tiles still fit across
    # a normal page width instead of wrapping/cramping - see
    # inject_compact_metric_css()'s own docstring for how the scoping works.
    with st.container(key="today_at_a_glance_metrics"):
        inject_compact_metric_css("today_at_a_glance_metrics")
        n_cols = (4 if today else 0) + (1 if lake_level else 0) + (2 if water_quality_display else 0)
        cols = st.columns(n_cols)
        i = 0
        if today:
            cols[i].metric("Activity score", f"{today.overall_score} / 10"); i += 1
            cols[i].metric("Est. water temp", f"{today.water_temp_f}°F"); i += 1
            cols[i].metric("Moon phase", today.moon.name); i += 1
            cols[i].metric("Pressure trend (24h)", f"{today.pressure_trend_24h:+.1f} hPa"); i += 1
        if lake_level:
            cols[i].metric(
                "Lake level",
                f"{lake_level.elevation_ft:g} ft",
                delta=f"{lake_level.elevation_ft - NORMAL_SUMMER_POOL_FT:+.1f} ft vs. normal pool",
                delta_color="off",
                help=f"Live reading from USGS site 03310900 ({lake_level.site_name}), "
                     f"as of {lake_level.observed_at.strftime('%-I:%M %p %m/%d')}.",
            )
            i += 1
        if water_quality_display:
            # Punch-list #19: dropped the "USACE water temp" tile here (the
            # "Est. water temp" tile already covers water temp on this row;
            # USACE's own real surface temp is still charted below in "14-
            # day trends") in favor of two dissolved-oxygen tiles - mg/l and
            # saturation % - since that's the reading the angler actually
            # wanted visible on this line. Both share the same underlying
            # reading and the same "is this fresh or a fallback" framing,
            # so build that shared help text once.
            live_note = (
                "USACE's own site couldn't be reached just now, so this is the last reading logged locally - "
                if not is_live_reading else ""
            )
            survey_note = (
                f"Most recent real surface reading (USACE Dam Site survey, "
                f"{water_quality_display.observed_at.strftime('%-m/%d')}). {live_note}"
                "This is a periodic manual survey, not a live/daily feed."
            )
            cols[i].metric(
                "USACE dissolved oxygen",
                f"{water_quality_display.do_mg_l:g} mg/l",
                help=f"{survey_note} Surface water temp {water_quality_display.water_temp_f}°F, "
                     f"{water_quality_display.do_saturation_pct:.0f}% of full DO saturation - see the "
                     "\"USACE DO saturation\" tile.",
            )
            i += 1
            cols[i].metric(
                "USACE DO saturation",
                f"{water_quality_display.do_saturation_pct:.0f}%",
                help=f"{survey_note} Dissolved oxygen {water_quality_display.do_mg_l:g} mg/l, "
                     f"{water_quality_display.do_saturation_pct:.0f}% of full saturation at this "
                     "temperature/elevation - a summer reservoir often runs well over 100% during the "
                     "day from photosynthetic supersaturation.",
            )
            i += 1

if today:
    best_segment = max(today.segments, key=lambda s: s.score)
    st.info(f"Best window today: **{best_segment.name}** ({best_segment.start.strftime('%-I:%M %p')} - "
            f"{best_segment.end.strftime('%-I:%M %p')}), score {best_segment.score}/10")

    if today.warnings:
        for w in today.warnings:
            st.warning(w)

    if n_trips > 0:
        st.caption(f"Model calibration: using {n_trips} logged trip(s) to nudge the default weights.")
    else:
        st.caption("Model calibration: no trips logged yet - using default weights. Log a trip to start improving it!")

# Punch-list #13/#15: trend charts for "Today at a glance"'s own metrics,
# now going back HOME_TREND_CHART_PAST_DAYS (14) days rather than 3.
# score_day() works for any date the bundle covers, and fetch_forecast()
# requests max(WATER_TEMP_TREND_PAST_DAYS, HOME_TREND_CHART_PAST_DAYS) days
# of real past weather alongside the forecast - so the last 14 days
# (today included) are already sitting in `bundle` with no extra fetch
# needed for the first three charts below. Lake level's trend is a
# separate live USGS request (fetch_lake_level_history()) since that's
# real telemetry, not something derivable from the weather bundle.
trend_forecasts = []
if bundle is not None:
    trend_days = [lake_today() - timedelta(days=i) for i in range(HOME_TREND_CHART_PAST_DAYS - 1, -1, -1)]
    for d in trend_days:
        try:
            trend_forecasts.append(score_day(bundle, d, weights=weights))
        except ValueError:
            pass  # date fell outside the bundle's window - shouldn't normally
            # happen given fetch_forecast()'s past_days request, but a chart
            # with fewer points is a much better failure mode here than
            # blowing up the whole page.

lake_level_history = None
try:
    lake_level_history = get_lake_level_history(days=HOME_TREND_CHART_PAST_DAYS)
except Exception:
    pass

# Punch-list #13: "for the data from the corp of engineers, let's do a
# longer trend since that is update[d] less frequently." Unlike the charts
# above, this can't just be computed from data already on hand - the live
# USACE page has no history (see core/water_quality_log.py's docstring), so
# this series is only ever as long as what's been locally recorded so far,
# starting from whenever this feature first shipped and growing by roughly
# one point every 1-2 weeks. Fetched independently of `bundle`/weather
# status above - a weather-fetch failure shouldn't hide a USACE trend
# that's otherwise available.
wq_log = []
try:
    wq_log = get_water_quality_log()
except Exception:
    pass

# Punch-list #19: USACE's charts used to live in their own separate
# expander below this one, and only showed as metric tiles (not an actual
# chart) until a second real survey was logged. Folded into this same
# "N-day trends" expander instead - one place for every trend on this page
# - and now charted starting from the very first point: `st.line_chart()`
# on a single-value Series just renders one dot, which reads fine sitting
# alongside the fuller weather/lake-level charts rather than needing its
# own "not enough data yet" special case. Each entry here is (caption,
# pd.Series, y_domain) - USACE's own index is however many real surveys
# have been logged (not the same 14-day window as the weather-derived
# charts, and deliberately not forced onto it - see the note above).
# y_domain is None for most charts (auto-scaled, as before) except the two
# °F series - punch-list #20 pins those to TEMP_CHART_Y_DOMAIN so a real
# but small swing (a degree or two) doesn't fill the whole chart height
# and read as more dramatic than it is; see core.ui.render_line_chart()
# for how the fixed scale is actually drawn.
trend_items = []
if len(trend_forecasts) >= 2:
    trend_idx = [df.the_date.strftime("%a %-m/%d") for df in trend_forecasts]
    trend_items.append(("Activity score", pd.Series([df.overall_score for df in trend_forecasts], index=trend_idx), None))
    trend_items.append(("Est. water temp (°F)", pd.Series([df.water_temp_f for df in trend_forecasts], index=trend_idx), TEMP_CHART_Y_DOMAIN))
    trend_items.append(("Pressure trend (24h, hPa)", pd.Series([df.pressure_trend_24h for df in trend_forecasts], index=trend_idx), None))
if lake_level_history:
    trend_items.append(("Lake level (ft)", pd.Series(
        [lv.elevation_ft for lv in lake_level_history],
        index=[lv.observed_at for lv in lake_level_history],
    ), None))
if wq_log:
    wq_idx = [r["observed_at"].strftime("%-m/%d/%y") for r in wq_log]
    trend_items.append(("USACE dissolved oxygen (mg/l)", pd.Series([r["do_mg_l"] for r in wq_log], index=wq_idx), None))
    trend_items.append(("USACE DO saturation (%)", pd.Series([r["do_saturation_pct"] for r in wq_log], index=wq_idx), None))
    trend_items.append(("USACE surface water temp (°F)", pd.Series([r["water_temp_f"] for r in wq_log], index=wq_idx), TEMP_CHART_Y_DOMAIN))

if trend_items:
    with st.expander(f"📈 {HOME_TREND_CHART_PAST_DAYS}-day trends", expanded=True):
        for row_start in range(0, len(trend_items), 3):
            row_items = trend_items[row_start:row_start + 3]
            row_cols = st.columns(len(row_items))
            for col, (caption, series, y_domain) in zip(row_cols, row_items):
                col.caption(caption)
                render_line_chart(col, series, y_domain)
        caption_bits = []
        if len(trend_forecasts) >= 2:
            caption_bits.append(
                f"Activity score, water temp, and pressure trend are recomputed from the same weather data "
                f"as \"Today at a glance\" above, for the last {HOME_TREND_CHART_PAST_DAYS} days."
            )
        if lake_level_history:
            caption_bits.append("Lake level is real USGS telemetry (readings every 15-60 min) for the same window.")
        if wq_log:
            caption_bits.append(
                f"USACE readings ({len(wq_log)} logged so far, starting {wq_log[0]['observed_at'].strftime('%-m/%d/%Y')}) "
                "are real periodic surveys, roughly every 1-2 weeks - not the same 14-day window as the "
                "charts above, and never backfilled with guessed past readings, so this series just grows "
                "one real point at a time."
            )
        st.caption(" ".join(caption_bits))

st.divider()
if lake_level is None:
    st.caption(
        "Couldn't fetch the live lake level just now (USGS site 03310900 may be briefly unreachable) - "
        "try refreshing in a minute."
    )
st.caption(
    f"Nolin River Lake summer/normal pool: {NORMAL_SUMMER_POOL_FT:g} ft elevation, ~5,795 surface acres. "
    "Lake map locations are planning approximations - verify with your own GPS/chartplotter on the water."
)
