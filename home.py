import pandas as pd
import streamlit as st

from core.appstate import (
    get_weather_bundle, get_calibrated_weights, get_lake_level,
    get_surface_water_quality, get_water_quality_log, get_trip_history, github_token, repo_slug,
)
from core.scoring import score_day
from core.weather import lake_today
from core.lake_level import NORMAL_SUMMER_POOL_FT
from core.storage import commit_and_push_data
from core.water_quality_log import append_if_new, WATER_QUALITY_LOG_PATH
from core.lake_water_quality import SurfaceWaterQuality
from core.daily_leaderboard import (
    build_daily_activity, build_weekly_activity, daily_awards, leaderboard_table_rows, week_bounds,
)
from core.activity_log import format_weight_lb_oz
from core.ui import inject_mobile_css, inject_compact_metric_css

st.set_page_config(page_title="Voskuil Fishin' Magician", page_icon="🎣", layout="wide")
inject_mobile_css()

st.title("🎣 Voskuil Fishin' Magician")
st.caption("Largemouth bass fishing forecasts for Nolin River Lake, KY")

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
                commit_and_push_data(
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

# Punch-list #91: "show fishing activity for any or all anglers that are
# currently logged in and/or posted a session" - a combined roster (open
# Spot Session anywhere on the lake, OR at least one row logged in the
# period), three "award" tiles for the period's biggest fish/top angler by
# weight/top angler by fish count, and a detailed per-angler, per-species
# leaderboard table with subtotals and a grand total. Originally just
# "today"; extended (same punch-list item, angler follow-up) to offer the
# identical set of categories for "this week" (Sunday-start, per the
# angler's own framing) too - _render_activity_section() below renders
# either period from the same core.daily_leaderboard functions, which
# don't care which period built their input. All the real logic lives in
# core/daily_leaderboard.py (kept Streamlit-free and unit tested on its
# own) - this block is just rendering. Independent of the weather/bundle
# status above (this is trip-log data, not weather), so a weather outage
# shouldn't hide it.
st.subheader("🎣 Fishing Activity")
try:
    _activity_rows = get_trip_history()
except Exception:
    _activity_rows = []
_lake_today = lake_today()


def _render_activity_section(period_stats: list, period_word: str, period_key: str, reset_note: str):
    """Renders one period's roster + award tiles + leaderboard table.
    period_word is used in the roster/table captions ("today"/"this
    week"); period_key is a short slug ("today"/"week") used only to give
    this period's award-tile container its own unique CSS scope. Otherwise
    identical for both periods, since core.daily_leaderboard's functions
    don't know or care which period built the stats they're handed.

    Punch-list #91 follow-up: tightened up for phones - confirmed live
    that the original labels (with "of the Day"/"of the Week" appended)
    and the roster's per-angler "(N fish today)" wording both got cut off
    with "..." once inject_mobile_css()'s generic reflow packed 2 tiles
    per row on a normal phone width. The period is already named by the
    tab itself now, so it's dropped from both the tile labels and the
    roster bullets; the roster legend also moved from an every-time text
    prefix into a one-time `help=` tooltip. inject_compact_metric_css(...,
    stack_on_mobile=True) forces one tile per row on a phone besides
    shrinking the font, which is what actually stops the label
    truncation - see that function's own docstring for why the shrink
    alone wasn't enough."""
    if not period_stats:
        st.caption(f"Nobody's logged a Spot Session yet {period_word} - be the first one out there!")
        return

    roster_bits = [
        f"{'🟢' if s.active else '⚪'} **{s.angler}** ({s.fish_count} fish)"
        for s in period_stats
    ]
    st.caption(
        " · ".join(roster_bits),
        help="🟢 = has an open Spot Session right now. ⚪ = posted but not currently active.",
    )

    awards = daily_awards(period_stats)
    award_container_key = f"activity_awards_{period_key}"
    with st.container(key=award_container_key):
        inject_compact_metric_css(award_container_key, stack_on_mobile=True)
        award_cols = st.columns(3)

        biggest = awards["biggest_fish"]
        award_cols[0].metric(
            "🎣 Berkley - Biggest Fish",
            f"{biggest['angler']} ({format_weight_lb_oz(biggest['weight_lb'])})" if biggest else "None yet",
            help=f"{biggest['species']}" if biggest else f"No fish logged yet {period_word}.",
        )
        top_weight = awards["top_angler_weight"]
        award_cols[1].metric(
            "🎣 String King - Top Angler",
            f"{top_weight.angler} ({format_weight_lb_oz(top_weight.total_weight_lb)})" if top_weight else "None yet",
            help=f"Highest total weight caught {period_word}, across every species." if top_weight
                 else f"No fish logged yet {period_word}.",
        )
        top_count = awards["top_bag_count"]
        award_cols[2].metric(
            "🎣 Z-Man - Bag Limit Buster",
            f"{top_count.angler} ({top_count.fish_count} fish)" if top_count else "None yet",
            help=f"Most total fish caught {period_word}, across every species." if top_count
                 else f"No fish logged yet {period_word}.",
        )

    table_rows = leaderboard_table_rows(period_stats)
    if table_rows:
        st.caption(f"Leaderboard - {period_word}'s catch by angler")
        st.dataframe(pd.DataFrame(table_rows), width='stretch', hide_index=True)
    st.caption(reset_note)


_today_tab, _week_tab = st.tabs(["📅 Today", "🗓️ This Week"])
with _today_tab:
    day_stats = build_daily_activity(_activity_rows, _lake_today.isoformat())
    _render_activity_section(
        day_stats, "today", "today",
        "Resets at the lake's own local midnight (America/Chicago) - see the full, filterable, "
        "all-time rankings on the **Leaderboard** page.",
    )
with _week_tab:
    week_start, week_end = week_bounds(_lake_today)
    week_stats = build_weekly_activity(_activity_rows, _lake_today)
    _render_activity_section(
        week_stats, "this week", "week",
        f"Week of {week_start.strftime('%-m/%d')} - {week_end.strftime('%-m/%d')} (Sun-Sat, lake-local) - "
        "see the full, filterable, all-time rankings on the **Leaderboard** page.",
    )

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
