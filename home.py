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
from core.ui import inject_mobile_css, inject_compact_metric_css, render_score_breakdown
from core.nav import render_bottom_nav

st.set_page_config(page_title="Voskuil Fishin' Magician", page_icon="🎣", layout="wide")
inject_mobile_css()
render_bottom_nav("home.py")

# Computed early (cheap - a local timezone lookup, no network) so both the
# brand header's date chip below AND the "Fishing Activity" section further
# down share this one call, instead of the header needing its own separate
# lake_today() just to show today's date.
_lake_today = lake_today()

# --- Design-language CSS + fonts (punch-list #98 Phase 3: Today/Home) --------
# Same visual language as The Stringer (pages/8_Leaderboard.py, punch-list
# #97) - Plus Jakarta Sans + IBM Plex Mono, one muted teal accent, flat
# cards, no gradients/illustrated icons - this is the second page in that
# rollout (README's own "Phase 3+ (punch-list #98), one page at a time").
# Reuses the exact same --stringer-* variable names (not --home-*) on
# purpose: these are purely additive on :root (harmless on every other
# page, which simply never references them - see that page's own comment),
# and keeping one shared name per token now is one less rename later once
# enough pages share this look to promote it into a single site-wide
# stylesheet.
#
# Font <link> tags are deliberately their OWN st.markdown call, never
# combined with the <style> block below into one string: SESSION_NOTES.md
# entries 174/177 both trace back to the same failure mode - a <style> (or
# other raw-text) tag that ISN'T the very first content in an
# unsafe_allow_html string can have its raw-HTML passthrough silently
# broken by a blank line anywhere inside it, truncating everything after
# that point before it ever reaches the browser. Splitting the two calls
# means <style> is always first in ITS string, closing off that whole bug
# class here rather than relying on remembering "no blank lines" on every
# future edit to this block.
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <style>
    :root {
      --stringer-surface:#FFFFFF; --stringer-surface-sunk:#EEF0EA;
      --stringer-ink:#0F1410; --stringer-ink-soft:#3C443E; --stringer-muted:#6E766F;
      --stringer-border:#E7E9E2; --stringer-accent:#2C7C6E; --stringer-accent-strong:#1F5F54;
      --stringer-accent-track:#D8EAE5; --stringer-warn:#8A5A1E; --stringer-warn-track:#F3E6D2;
      /* Card "depth" treatment (punch-list #98 follow-up, angler's own ask
         after seeing the first flat-card pass: "kind of a boring look...
         3D depth shaded boxes"). A glossy-gradient card - a soft top-light
         sheen top-to-bottom, plus a layered shadow and a hairline border -
         picked over a plain flat fill (the original Stringer look), a
         heavier drop-shadow-only "elevated" card, and a neumorphic
         soft-embossed treatment, from a set of options previewed for and
         chosen by the angler directly. One shared set of tokens so every
         card shell below (and pages/8_Leaderboard.py's own, kept in sync
         by hand) pulls from the same three values instead of repeating
         the gradient/shadow/border literals at each card. */
      --stringer-card-from:#FFFFFF; --stringer-card-to:#F5F7F1;
      --stringer-card-shadow:0 1px 2px rgba(15,20,16,0.05), 0 6px 16px rgba(15,20,16,0.08);
      --stringer-card-border:1px solid rgba(15,20,16,0.05);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --stringer-surface:#131A16; --stringer-surface-sunk:#0F1512;
        --stringer-ink:#F1F3EF; --stringer-ink-soft:#C4CCC5; --stringer-muted:#8A948C;
        --stringer-border:#212A24; --stringer-accent:#4FAE9C; --stringer-accent-strong:#6FC2B2;
        --stringer-accent-track:#173630; --stringer-warn:#E8B370; --stringer-warn-track:#2E2413;
        /* Dark mode needs its own values, not just a lighter/darker pair of
           the same two colors - a black box-shadow is nearly invisible
           against an already-dark page, so the "lift" here leans more on
           the gradient itself (a lighter top fading to a darker bottom)
           and a faint light-colored hairline border than on the shadow. */
        --stringer-card-from:#1A231D; --stringer-card-to:#10150F;
        --stringer-card-shadow:0 1px 2px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.45);
        --stringer-card-border:1px solid rgba(255,255,255,0.05);
      }
    }
    .home-topbar, .home-card-head, .st-key-home_glance_card, .st-key-home_bestwindow_card,
    .st-key-home_activity_card {
        font-family: "Plus Jakarta Sans", system-ui, sans-serif;
    }
    /* Brand row - same shape as The Stringer's own .stringer-topbar (brand
       wordmark + a rolling chip on the right), replacing the plain
       st.title()/st.caption() pair this page used before. */
    .home-topbar {
        display:flex; align-items:center; justify-content:space-between;
        gap:12px; flex-wrap:wrap; margin-bottom:2px;
    }
    .home-brand { font-weight:800; font-size:1.05rem; letter-spacing:.04em; color:var(--stringer-ink); }
    .home-tagline { font-size:.78rem; color:var(--stringer-muted); margin-top:2px; }
    .home-date-chip {
        font-family:"IBM Plex Mono", monospace; font-size:.72rem; color:var(--stringer-muted);
        background:var(--stringer-surface-sunk); padding:5px 10px; border-radius:100px; white-space:nowrap;
    }
    /* Card shells - each of the three sections below (glance metrics, best
       window, fishing activity) becomes one st.container(key=...) card,
       the same "whole container becomes one visual card" pattern The
       Stringer uses for its own ring hero. */
    .st-key-home_glance_card, .st-key-home_bestwindow_card, .st-key-home_activity_card {
        background:linear-gradient(180deg, var(--stringer-card-from) 0%, var(--stringer-card-to) 100%);
        box-shadow:var(--stringer-card-shadow); border:var(--stringer-card-border);
        border-radius:16px; padding:14px 18px 18px; margin-bottom:14px;
    }
    .home-card-head { display:flex; align-items:baseline; gap:8px; margin-bottom:6px; }
    .home-card-head h3 { font-size:.95rem; font-weight:700; margin:0; color:var(--stringer-ink); }
    /* "Today at a Glance" metric tiles - IBM Plex Mono values, muted
       Jakarta Sans labels, same pairing as every other number on The
       Stringer. inject_compact_metric_css() (called right below, unchanged)
       still owns the actual font SIZE / mobile-stacking behavior - this
       only adds family/color on top of it. */
    .st-key-today_at_a_glance_metrics [data-testid="stMetricValue"] {
        font-family:"IBM Plex Mono", monospace; color:var(--stringer-ink);
    }
    .st-key-today_at_a_glance_metrics [data-testid="stMetricLabel"] {
        font-family:"Plus Jakarta Sans", system-ui, sans-serif; color:var(--stringer-muted); font-weight:600;
    }
    /* st.info/st.warning inside the "Best Window" card - Streamlit's own
       blue/yellow alert boxes read jarring next to this page's muted
       palette, so both are re-skinned as flat, near-white cards with a
       colored left rule instead (teal for info, warm amber for warning -
       kept distinct so a real warning still reads as one at a glance,
       just without Streamlit's default saturated yellow). Confirmed live
       (a standalone scratch st.info()/st.warning() render, DOM-inspected)
       that the actual tinted background lives on the MIDDLE of three
       nested wrapper divs - `[data-testid="stAlertContainer"]`, not the
       outer `[data-testid="stAlert"]` this rule targeted on the first
       pass, which has no background of its own to override at all. */
    .st-key-home_bestwindow_card [data-testid="stAlertContainer"] {
        background:var(--stringer-surface-sunk) !important; border-radius:10px !important;
        border:none !important;
    }
    .st-key-home_bestwindow_card [data-testid="stAlertContentInfo"] {
        border-left:3px solid var(--stringer-accent) !important;
    }
    .st-key-home_bestwindow_card [data-testid="stAlertContentWarning"] {
        border-left:3px solid var(--stringer-warn) !important;
    }
    .st-key-home_bestwindow_card [data-testid="stMarkdownContainer"] p {
        color:var(--stringer-ink-soft) !important;
    }
    /* Fishing Activity tabs - identical underline treatment to The
       Stringer's own six-tab ranked-list bar. */
    .st-key-home_activity_tabs [data-baseweb="tab-list"] {
        gap:20px; border-bottom:1px solid var(--stringer-border); background:transparent;
    }
    .st-key-home_activity_tabs [data-baseweb="tab"] {
        font-weight:600; font-size:.84rem; color:var(--stringer-muted); background:transparent;
        padding:8px 2px 10px;
    }
    .st-key-home_activity_tabs [data-baseweb="tab"][aria-selected="true"] { color:var(--stringer-ink) !important; }
    .st-key-home_activity_tabs [data-baseweb="tab-highlight"] { background-color:var(--stringer-accent) !important; }
    .st-key-home_activity_tabs [data-baseweb="tab-border"] { background-color:transparent !important; }
    /* Award tiles (Biggest Fish / Top Angler / Bag Limit Buster) - both
       tabs' container keys start with "activity_awards_", so a substring
       selector covers today's and this week's tiles from one rule instead
       of duplicating it per period. */
    [class*="st-key-activity_awards_"] [data-testid="stMetricValue"] {
        font-family:"IBM Plex Mono", monospace; color:var(--stringer-ink);
    }
    [class*="st-key-activity_awards_"] [data-testid="stMetricLabel"] {
        font-family:"Plus Jakarta Sans", system-ui, sans-serif; color:var(--stringer-muted); font-weight:600;
    }
    /* Leaderboard table - same substring-selector trick, one rule for both
       the today/week dataframes. Rounds and borders just the outer frame;
       deliberately leaves the grid's own internal rendering untouched. */
    [class*="st-key-home_leaderboard_table_"] [data-testid="stDataFrame"] {
        border-radius:10px !important; overflow:hidden !important;
        border:1px solid var(--stringer-border) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="home-topbar">
        <div>
            <div class="home-brand">🎣 VOSKUIL FISHIN' MAGICIAN</div>
            <div class="home-tagline">Largemouth bass fishing forecasts for Nolin River Lake, KY</div>
        </div>
        <div class="home-date-chip">{_lake_today.strftime('%a, %b %-d')}</div>
    </div>
    """,
    unsafe_allow_html=True,
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
    with st.container(key="home_glance_card"):
        st.markdown('<div class="home-card-head"><h3>📊 Today at a Glance</h3></div>', unsafe_allow_html=True)
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
                with cols[i]:
                    st.metric("Activity score", f"{today.overall_score} / 10")
                    # Punch-list #94 (follow-up: averages each factor's own
                    # delta across the day's 6 segments instead of averaging
                    # the segments' own scores - see core.scoring.
                    # aggregate_day_overall()'s docstring for why).
                    render_score_breakdown(today.overall_breakdown, today.overall_score, key="home_activity_score_breakdown")
                i += 1
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
    with st.container(key="home_bestwindow_card"):
        st.markdown('<div class="home-card-head"><h3>🌤️ Best Window Today</h3></div>', unsafe_allow_html=True)
        best_segment = max(today.segments, key=lambda s: s.score)
        st.info(f"Best window today: **{best_segment.name}** ({best_segment.start.strftime('%-I:%M %p')} - "
                f"{best_segment.end.strftime('%-I:%M %p')}), score {best_segment.score}/10")
        # Punch-list #94: this segment's own factor breakdown (pressure trend,
        # moon, wind, season, etc.) - the SAME breakdown the 7-Day Forecast
        # page shows for this identical segment, since both are built by the
        # same core.scoring.score_day().
        render_score_breakdown(best_segment.breakdown, best_segment.score, key="home_best_window_score_breakdown")

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
try:
    _activity_rows = get_trip_history()
except Exception:
    _activity_rows = []


def _render_activity_section(period_stats: list, period_word: str, period_key: str, reset_note: str):
    """Renders one period's roster + award tiles + leaderboard table.
    period_word is used in the roster/table captions ("today"/"this
    week"); period_key is a short slug ("today"/"week") used only to give
    this period's award-tile container (and, punch-list #98, its
    leaderboard-table container) its own unique CSS scope. Otherwise
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
        with st.container(key=f"home_leaderboard_table_{period_key}"):
            st.dataframe(pd.DataFrame(table_rows), width='stretch', hide_index=True)
    st.caption(reset_note)


with st.container(key="home_activity_card"):
    st.markdown('<div class="home-card-head"><h3>🎣 Fishing Activity</h3></div>', unsafe_allow_html=True)
    with st.container(key="home_activity_tabs"):
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
