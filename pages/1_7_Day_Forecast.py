import streamlit as st

from core.appstate import (
    get_weather_bundle, get_calibrated_weights, get_spots, get_inventory, get_trip_history, github_token, repo_slug,
)
from core.scoring import score_week, effective_season_and_temp
from core.lures import recommend
from core.ui import (
    render_lure_recommendation, render_lake_setup_sidebar, inject_mobile_css,
    render_score_breakdown,
)
from core.weather import lake_today
from core.storage import commit_and_push_data
from core.forecast_freeze import apply_freeze, FREEZE_PATH
from core.nav import render_bottom_nav

st.set_page_config(page_title="7 Day Forecast - Nolin Lake", page_icon="📅", layout="wide")
inject_mobile_css()
render_bottom_nav("pages/1_7_Day_Forecast.py")

today = lake_today()

# --- Design-language CSS + fonts (punch-list #98 Phase 4: 7-Day Forecast) ----
# Same visual language as Home/The Stringer (punch-list #97/#98) - Plus
# Jakarta Sans headers, one muted teal accent, glossy-gradient cards - the
# third page in the site-wide rollout (README's own "Phase 3+, one page at
# a time"). Reuses the exact same --stringer-* variable names as those two
# pages (kept in sync by hand - no shared stylesheet exists yet, see their
# own comments on why).
#
# One deliberate departure from the two earlier pages: NO IBM Plex Mono
# import here at all. The angler's own most recent ask (SESSION_NOTES.md
# entry 180) was "change the font... too telegraph type looking" about
# that exact typeface - reintroducing it on a brand-new page now, only to
# probably swap it out again later, would be working against that
# feedback rather than with it. Every number on this page (the metric
# tiles below) uses Space Grotesk from the start instead, matching what
# Home's own numbers already moved to.
#
# Font <link> tags are their own st.markdown call, never combined with
# <style> into one string - see home.py's own comment on entries 174/177
# for why a stray blank line in a combined call can silently truncate
# everything after it.
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
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
      --stringer-good:#2C7C6E;
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
        --stringer-good:#4FAE9C;
        --stringer-card-from:#1A231D; --stringer-card-to:#10150F;
        --stringer-card-shadow:0 1px 2px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.45);
        --stringer-card-border:1px solid rgba(255,255,255,0.05);
      }
    }
    .forecast-topbar, .st-key-forecast_week_card, .st-key-forecast_days_list {
        font-family: "Plus Jakarta Sans", system-ui, sans-serif;
    }
    /* Brand row - same shape as Home's/The Stringer's own topbar. */
    .forecast-topbar {
        display:flex; align-items:center; justify-content:space-between;
        gap:12px; flex-wrap:wrap; margin-bottom:2px;
    }
    .forecast-brand { font-weight:800; font-size:1.05rem; letter-spacing:.04em; color:var(--stringer-ink); }
    .forecast-tagline { font-size:.78rem; color:var(--stringer-muted); margin-top:2px; }
    .forecast-date-chip {
        font-family:"Space Grotesk", system-ui, sans-serif; font-size:.72rem; color:var(--stringer-muted);
        background:var(--stringer-surface-sunk); padding:5px 10px; border-radius:100px; white-space:nowrap;
    }
    /* Week-at-a-glance card - the 7 day-score tiles + their breakdown
       popovers, same card shell as Home's three cards. */
    .st-key-forecast_week_card {
        background:linear-gradient(180deg, var(--stringer-card-from) 0%, var(--stringer-card-to) 100%);
        box-shadow:var(--stringer-card-shadow); border:var(--stringer-card-border);
        border-radius:16px; padding:14px 18px 18px; margin-bottom:14px;
    }
    .st-key-forecast_week_card [data-testid="stMetricValue"],
    .st-key-forecast_days_list [data-testid="stMetricValue"] {
        font-family:"Space Grotesk", system-ui, sans-serif; font-variant-numeric:tabular-nums;
        color:var(--stringer-ink);
    }
    .st-key-forecast_week_card [data-testid="stMetricLabel"],
    .st-key-forecast_days_list [data-testid="stMetricLabel"] {
        font-family:"Plus Jakarta Sans", system-ui, sans-serif; color:var(--stringer-muted); font-weight:600;
    }
    /* Each day's own st.expander becomes a card (gradient/shadow/border,
       same treatment as every other card on this site) - `details` (not
       the outer [data-testid="stExpander"] wrapper) is what actually
       carries Streamlit's own border/radius/background, confirmed live
       via getComputedStyle() before writing this rule, same discipline as
       every other widget reskin on this site (see entry 178's alert-box
       lesson). `!important` throughout since these are overriding
       Streamlit's own emotion-generated classes, not just the theme
       defaults inject_mobile_css() already touches. */
    .st-key-forecast_days_list [data-testid="stExpander"] > details {
        background:linear-gradient(180deg, var(--stringer-card-from) 0%, var(--stringer-card-to) 100%) !important;
        box-shadow:var(--stringer-card-shadow) !important; border:var(--stringer-card-border) !important;
        border-radius:16px !important;
    }
    .st-key-forecast_days_list [data-testid="stExpander"] > details > summary {
        background:transparent !important; border-radius:16px 16px 0 0 !important;
        padding:14px 18px !important; font-weight:700 !important; color:var(--stringer-ink) !important;
    }
    .st-key-forecast_days_list [data-testid="stExpander"] > details > [data-testid="stExpanderDetails"] {
        padding:4px 18px 18px !important;
    }
    /* A lure-setup expander (or, one level deeper, its own "tackle box
       gaps" expander from core.ui.render_lure_recommendation) nested
       inside a day's expander gets a flatter, sunk look instead of the
       same gradient/shadow card again - stacking identical heavy cards
       inside each other reads as visual noise, not depth. This descendant
       selector catches any expander-inside-an-expander regardless of how
       many levels deep, so it doesn't need to know about
       render_lure_recommendation's own internal structure. */
    .st-key-forecast_days_list [data-testid="stExpander"] [data-testid="stExpander"] > details {
        background:var(--stringer-surface-sunk) !important; box-shadow:none !important;
        border:1px solid var(--stringer-border) !important; border-radius:10px !important;
    }
    .st-key-forecast_days_list [data-testid="stExpander"] [data-testid="stExpander"] > details > summary {
        background:transparent !important; border-radius:10px 10px 0 0 !important;
        font-weight:600 !important;
    }
    /* st.info/st.warning/st.success inside a day's expander - same
       re-skin as Home's "Best Window" card (entry 178): the real tinted
       background lives on the middle `stAlertContainer` layer, not the
       outer `stAlert` wrapper, which has none of its own to override. */
    .st-key-forecast_days_list [data-testid="stAlertContainer"] {
        background:var(--stringer-surface-sunk) !important; border-radius:10px !important;
        border:none !important;
    }
    .st-key-forecast_days_list [data-testid="stAlertContentInfo"] {
        border-left:3px solid var(--stringer-accent) !important;
    }
    .st-key-forecast_days_list [data-testid="stAlertContentWarning"] {
        border-left:3px solid var(--stringer-warn) !important;
    }
    .st-key-forecast_days_list [data-testid="stAlertContentSuccess"] {
        border-left:3px solid var(--stringer-good) !important;
    }
    /* Body text color, inside a day's card (and, since this selector
       doesn't care how deep, inside a nested lure-setup/gaps expander
       too) - live-checked in dark mode and found NOT automatically
       legible without this: this app's .streamlit/config.toml pins a
       fixed LIGHT theme (textColor #262730), so Streamlit's own native
       widget text never itself follows the OS/browser's prefers-color-
       scheme the way these --stringer-* tokens do - only an explicit
       override here keeps plain st.write()/st.caption()/alert text
       readable once a card's own background flips dark under that same
       media query. Same fix, same reason, as home.py's own bestwindow-
       card markdown override (entry 178) - scoped to stExpanderDetails
       specifically (a sibling of summary, not an ancestor of it) so it
       doesn't also mute the bold ink-colored day/segment titles above. */
    .st-key-forecast_days_list [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p {
        color:var(--stringer-ink-soft) !important;
    }
    .st-key-forecast_days_list [data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"] p {
        color:var(--stringer-muted) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="forecast-topbar">
        <div>
            <div class="forecast-brand">📅 7-DAY LARGEMOUTH BASS FORECAST</div>
            <div class="forecast-tagline">Day-by-day activity scores and lure setups for Nolin River Lake, KY</div>
        </div>
        <div class="forecast-date-chip">{today.strftime('%a, %b %-d')}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
weights, n_trips = get_calibrated_weights()
bundle = get_weather_bundle(7)
week = score_week(bundle, today, 7, weights=weights)
inventory = get_inventory()
trip_history = get_trip_history()

# Once a time-of-day window's end time has passed, its score/notes/solunar
# overlap are locked in at whatever they were the moment it was first
# observed as past, rather than continuing to drift every time the hourly
# weather refresh (get_weather_bundle above) changes what score_day()
# would otherwise compute for it - a forecast score that keeps changing
# after its window has already closed isn't a forecast anymore. Only
# today's entry in `week` can ever have a mix of past/future segments
# (every later day is still entirely in the future), but this is called
# for every day rather than special-casing that, since it's a no-op for a
# day with nothing past yet. Only pushes to GitHub when a segment is newly
# frozen this run (the common case is nothing new, especially since the
# weather bundle itself only refreshes hourly) - see core/forecast_freeze.py.
newly_frozen = []
for day in week:
    newly_frozen += apply_freeze(day, path=FREEZE_PATH)
if newly_frozen:
    token = github_token()
    if token:
        commit_and_push_data(
            [FREEZE_PATH], token, repo_slug(),
            f"Freeze forecast score(s) for {', '.join(newly_frozen)}",
        )

if not week:
    st.error(
        "No forecast days are available right now - the weather data may not have refreshed yet. "
        "Try refreshing this page in a moment."
    )
    st.stop()
if len(week) < 7:
    st.warning(
        f"Only {len(week)} of 7 days had weather data available just now (usually a brief gap right "
        "at the forecast window's edge) - showing what's available. Refresh in a bit for the full week."
    )

st.caption(
    "Scores are 1 (least active) to 10 (most active), built from pressure trend, moon phase, "
    "solunar windows, cloud cover, wind, and season. " +
    (f"Calibrated using {n_trips} logged trips." if n_trips else "Using default weights - log trips to calibrate.")
)
if inventory:
    st.caption(
        "🧰 Lure setups below show your top 3 best-fit owned lures for each window, checked against "
        "your Tackle Box - anything else well-suited but not in your tackle box shows up in a separate "
        "'gaps' section instead of being mixed in."
    )

with st.container(key="forecast_week_card"):
    cols = st.columns(len(week))
    for col, day in zip(cols, week):
        with col:
            st.metric(day.the_date.strftime("%a %m/%d"), f"{day.overall_score}/10")
            # Punch-list #94 (follow-up: each factor's own delta averaged
            # across the day's 6 segments, not the segments' own scores - see
            # core.scoring.aggregate_day_overall()'s docstring for why).
            render_score_breakdown(day.overall_breakdown, day.overall_score, key=f"week_day_score_breakdown_{day.the_date.isoformat()}")

st.divider()

lake_setup = render_lake_setup_sidebar(
    include_structure=True, default_water_temp_f=week[0].water_temp_f,
)
clarity = lake_setup.water_clarity
structure = lake_setup.structure_type

with st.container(key="forecast_days_list"):
    for day in week:
        with st.expander(f"{day.the_date.strftime('%A, %B %d')} - overall {day.overall_score}/10 | "
                          f"{day.season.replace('_', ' ').title()} | {day.moon.name}", expanded=(day.the_date == today)):

            c1, c2 = st.columns([2, 1])
            with c1:
                eff_season, eff_water_temp = effective_season_and_temp(day, lake_setup.water_temp_override_f)
                st.write(f"**Water temp (Lake Setup Options):** {eff_water_temp}°F  |  "
                         f"**24h pressure trend:** {day.pressure_trend_24h:+.1f} hPa  |  "
                         f"**Moon illumination:** {day.moon.illumination_pct:.0f}%")
                if eff_season != day.season:
                    st.caption(f"Your water temp puts this day in the {eff_season.replace('_', ' ').title()} pattern for "
                               f"lure selection (the weather-only estimate would be {day.season.replace('_', ' ').title()}).")
                st.write(f"**Sunrise:** {day.sunrise.strftime('%-I:%M %p')}  |  "
                         f"**Sunset:** {day.sunset.strftime('%-I:%M %p')}")
                ws = day.weather_summary
                st.write(f"Avg cloud cover {ws['avg_cloud_pct']:.0f}%, avg wind {ws['avg_wind_mph']:.0f} mph, "
                         f"high/low {ws['temp_hi_f']}°/{ws['temp_lo_f']}°F, "
                         f"precip chance {ws['max_precip_prob_pct']:.0f}%")
                for w in day.warnings:
                    st.warning(w)

            with c2:
                best = max(day.segments, key=lambda s: s.score)
                st.success(f"Best window: **{best.name}**\n\n{best.start.strftime('%-I:%M %p')} - {best.end.strftime('%-I:%M %p')}")

            st.write("**Time-of-day breakdown:**")
            seg_cols = st.columns(len(day.segments))
            for sc, seg in zip(seg_cols, day.segments):
                with sc:
                    st.metric(seg.name, f"{seg.score}/10", help="\n".join(seg.notes) if seg.notes else None)
                    if seg.solunar_overlap:
                        st.caption(f"☾ solunar {seg.solunar_overlap}")
                    # Punch-list #94: full factor breakdown, one click away -
                    # a popover (not st.expander) since this is already nested
                    # inside this day's own expander.
                    render_score_breakdown(
                        seg.breakdown, seg.score,
                        key=f"week_segment_score_breakdown_{day.the_date.isoformat()}_{seg.name}",
                    )

            st.write("**Lure setup by time of day** (expand a window for full lure blocks):")
            best_name = max(day.segments, key=lambda s: s.score).name
            for seg in day.segments:
                # Punch-list #35: this segment's OWN pressure trend (anchored at its
                # own time of day), not the day's single noon-anchored value - see
                # core.scoring.score_day()'s comment on SegmentForecast.pressure_trend_24h.
                # Punch-list #37: trip_history lets recommend() nudge/inject picks
                # backed by your own logged catches in a similar structure/water-
                # clarity/light/temp situation - no spot_id here, since this page's
                # "structure type" is a general Lake Setup selection, not a specific
                # spot (Spot Session's own call to recommend() passes spot_id too,
                # for the strongest possible match).
                # Punch-list #82: pass this day's real average wind (score_day()
                # itself already uses the same day-level average for every
                # segment's score - see core.scoring.score_day()'s own avg_wind
                # comment - so this is exactly consistent, not a finer-grained
                # value than the score already reflects) so recommend()'s
                # wind-driven reaction-bait promotion can actually fire here.
                # Before this fix it never could - this page never passed
                # wind_mph at all, so a genuinely windy forecast day never
                # changed the lure pick the way a windy Spot Session already did.
                rec = recommend(eff_season, eff_water_temp, seg.name, seg.pressure_trend_24h, structure, clarity,
                                 fish_depth_ft=lake_setup.fish_depth_ft, forage=lake_setup.forage,
                                 inventory=inventory, trip_history=trip_history, wind_mph=ws["avg_wind_mph"])
                with st.expander(
                    f"{seg.name} ({seg.start.strftime('%-I:%M %p')}-{seg.end.strftime('%-I:%M %p')}) - score {seg.score}/10",
                    expanded=(seg.name == best_name),
                ):
                    render_lure_recommendation(rec, inventory=inventory)
