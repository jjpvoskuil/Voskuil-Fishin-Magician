import json
import re
import uuid
from datetime import datetime, time as dtime

import streamlit as st

from core.appstate import (
    get_lake_spots, get_inventory, get_weather_bundle, get_anglers, get_trip_history,
    get_calibrated_weights, get_location_adjustments, github_token, repo_slug, github_connection_status,
)
from core.anglers import add_angler, ANGLERS_PATH, OTHER_LABEL as ANGLER_OTHER_LABEL
from core.lake_spots import LOCATION_TYPE_TO_STRUCTURE_TYPE, split_bottom_structure
from core.onwater import (
    LIGHT_CONDITIONS, LIGHT_CONDITION_INFO, cloud_proxy_for_light_condition, light_condition_for_cloud_pct,
    WIND_BANDS, WIND_BAND_LABELS, WIND_DIRECTIONS, wind_band, wind_mph_for_band, wind_direction_for_degrees,
    resolve_water_clarity, STAIN_COLOR_OPTIONS, water_temp_band, visibility_band,
    PRECIPITATION_OPTIONS, precipitation_proxy, precipitation_option_for_forecast,
)
from core.scoring import (
    SEGMENTS, season_stage, manual_segment_score, realtime_context_from_bundle,
    segment_time_ranges, lake_now_naive,
)
from core.activity_log import (
    inventory_item_label, lure_can_take_trailer,
    FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS, RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
    FISH_SPECIES_OPTIONS, HIT_TYPE_OPTIONS, format_weight_lb_oz,
    WEIGHT_LB_OPTIONS, WEIGHT_OZ_OPTIONS, LENGTH_OPTIONS,
    weight_lb_for_dropdown, length_in_for_dropdown,
)
from core.lures import recommend, FORAGE_OPTIONS, is_trailer_eligible, curate_recommendation
from core.ui import (
    render_lure_block, render_lure_recommendation, render_square_thumbnail, inject_mobile_css,
    render_score_breakdown,
)
from core.storage import (
    TripEntry, TRIP_LOG_PATH, append_trip, commit_and_push_data, push_pending_data,
    read_all_trips, update_trip, delete_trip, parse_conditions,
)
from core.weather import lake_today, hourly_rows_for_date, estimate_water_temp_f
from core.nav import render_bottom_nav

st.set_page_config(page_title="Spot Session - Nolin Lake", page_icon="🎯", layout="wide")
inject_mobile_css()
render_bottom_nav("pages/6_Spot_Session.py")

# --- Design-language CSS + fonts (punch-list #98 Phase 5: Spot Session) -----
# Same visual language as Home/The Stringer/7-Day Forecast (punch-list
# #97/#98) - Plus Jakarta Sans, Space Grotesk numbers, one muted teal
# accent, glossy-gradient cards - the fourth and by far the biggest/most
# interactive page in the rollout (the angler's own framing: "this one
# needs to be the best and crispest" - it's the page actually used
# standing at the water, not just reviewed afterward). Reuses the exact
# same --stringer-* variable names as the other three pages (kept in sync
# by hand - no shared stylesheet exists yet, see their own comments on
# why). No IBM Plex Mono import, same reasoning as 7-Day Forecast (entry
# 181): the angler's own prior ask (entry 180) was to move OFF that exact
# monospace look, so every number here (session/segment scores, fish
# counts) uses Space Grotesk from the start instead.
#
# This page's own content - unlike Home, which mixes styled cards with a
# native Streamlit sidebar it deliberately leaves alone - has nothing on
# it that should stay unstyled, so most rules below are page-wide
# (`[data-testid="stExpander"]`, not `.st-key-<container> [data-testid=
# "stExpander"]`): every expander, alert, and metric on THIS page should
# look the same way, and a page-local <style> block only ever applies
# while this page itself is being viewed (Streamlit's multi-page nav
# fully remounts the DOM per page - see app.py's own docstring), so this
# can't leak onto any other page. Three specific always-visible sections
# (Conditions, the active-session lure list, "Lures for this session")
# get their own named `st.container(key=...)` card treatment, matching
# Home's own always-visible cards; every `st.expander` on this page (there
# are many - Suggestions, Conditions changed/Relocate, Add a lure, Fish
# caught, Retired lures, Tackle box gaps, Add from tackle box) gets the
# same two-tier treatment 7-Day Forecast already established (entry 181):
# the outermost expander in any nesting chain gets the full glossy-
# gradient card; anything nested inside it gets a flatter, sunk look
# instead, so identical heavy cards don't stack visual noise. This page's
# three `st.dialog` popups (`_trailer_dialog`, `_fish_entry_dialog`,
# `_lure_added_dialog`) render into a browser-level portal, confirmed live
# via `.closest()` NOT to be a descendant of `[data-testid="stMain"]` -
# page-container CSS can't reach them, so they get their own explicit
# `[data-testid="stDialog"]` font rule instead of inheriting one.
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
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20,500,0,0&display=swap" rel="stylesheet">
    """,
    unsafe_allow_html=True,
)
# Punch-list #98 follow-up entry 185: the Conditions sub-card headers below
# use this webfont directly (a raw <span class="ss-msym">) rather than
# st.subheader(..., icon=":material/...:") - confirmed live (post-deploy,
# via the browser tools) that Streamlit's own heading-icon path creates a
# real stHeadingIconWrapper element but never actually applies the Material
# Symbols font to it in this version/context (computed font-family stayed
# Streamlit's own default "Source Sans", not a bug in this app's CSS - the
# icon text itself never got the right font at all). AppTest confirmed the
# icon WAS reaching the proto correctly, so this is a frontend-only quirk,
# not a mistake in how the icon was passed. Sidestepping it entirely with a
# real, independently-loaded webfont (same technique already proven in the
# approved mockup) was faster and more reliable than chasing a Streamlit
# internal rendering bug further.
st.markdown(
    """
    <style>
    :root {
      --stringer-surface:#FFFFFF; --stringer-surface-sunk:#EEF0EA;
      --stringer-ink:#0F1410; --stringer-ink-soft:#3C443E; --stringer-muted:#6E766F;
      --stringer-border:#E7E9E2; --stringer-accent:#2C7C6E; --stringer-accent-strong:#1F5F54;
      --stringer-accent-track:#D8EAE5; --stringer-warn:#8A5A1E; --stringer-warn-track:#F3E6D2;
      --stringer-good:#2C7C6E; --stringer-error:#B3261E;
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
        --stringer-good:#4FAE9C; --stringer-error:#E5847E;
        --stringer-card-from:#1A231D; --stringer-card-to:#10150F;
        --stringer-card-shadow:0 1px 2px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.45);
        --stringer-card-border:1px solid rgba(255,255,255,0.05);
      }
    }
    [data-testid="stMainBlockContainer"], [data-testid="stDialog"] {
        font-family: "Plus Jakarta Sans", system-ui, sans-serif;
    }
    /* Brand row - same shape as Home's/The Stringer's/7-Day Forecast's own
       topbar. Deliberately FIXED (non-flipping) text colors here, not
       var(--stringer-ink)/var(--stringer-muted) - caught live via a dark-
       mode Playwright check while verifying this page: the brand/tagline
       sit directly on Streamlit's own native page background, which
       .streamlit/config.toml pins to a fixed LIGHT theme that never
       itself responds to prefers-color-scheme (same root cause as the
       widget-text contrast fix below), unlike the date-chip next to them,
       which is safe because BOTH its own background and its text use the
       flipping tokens together. Using the flipping ink token here made
       the brand line render near-white-on-white (unreadable) in dark
       mode - this bug is latent on Home's and 7-Day Forecast's own
       identical topbar markup too (not yet fixed there as of this entry). */
    .spotsession-topbar {
        display:flex; align-items:center; justify-content:space-between;
        gap:12px; flex-wrap:wrap; margin-bottom:2px;
    }
    .spotsession-brand { font-weight:800; font-size:1.05rem; letter-spacing:.04em; color:#0F1410; }
    .spotsession-tagline { font-size:.78rem; color:#6E766F; margin-top:2px; }
    .spotsession-date-chip {
        font-family:"Space Grotesk", system-ui, sans-serif; font-size:.72rem; color:var(--stringer-muted);
        background:var(--stringer-surface-sunk); padding:5px 10px; border-radius:100px; white-space:nowrap;
    }
    /* The three always-visible "big" sections (Conditions, the active
       session's own lure list, and the pending build's "Lures for this
       session" list) - the same glossy-gradient card shell as Home's
       always-visible cards, not an expander (nothing about these should
       be collapsible). */
    .st-key-spotsession_active_card,
    .st-key-spotsession_pending_lures_card {
        background:linear-gradient(180deg, var(--stringer-card-from) 0%, var(--stringer-card-to) 100%);
        box-shadow:var(--stringer-card-shadow); border:var(--stringer-card-border);
        border-radius:16px; padding:14px 18px 18px; margin-bottom:14px;
    }
    /* Punch-list #98 follow-up: the "Conditions" section's own sub-groups
       (Water conditions / Environmental stain / Wind & atmosphere / Fish
       & forage activity) - the angler's own reference image (a phone
       mockup screenshot) asked for denser, clearly-separated field
       groups with their own header band, rather than one long list
       inside a single big card. Approved first as a standalone HTML
       mockup before any of this landed here (see SESSION_NOTES.md), then
       every selector below was read off the REAL live DOM (the deployed
       app's own iframe) before writing it - not guessed. Deliberately
       flatter than the two "hero" cards above (no gradient/shadow) - the
       same "nested content gets a flatter treatment, not another stacked
       heavy card" principle already used for a nested expander (see
       below). Because these sub-cards carry their own --stringer-
       surface/-sunk backgrounds, spotsession_conditions_card is
       deliberately DROPPED from the hero-card selector above - it's now
       a plain, unstyled layout wrapper (the "Conditions" heading/caption
       sit directly on the native page background, same as any other
       page-level heading), and these four keys take over its old spot in
       the dark-mode stWidgetLabel override further below instead. */
    .st-key-spotsession_cond_water_card,
    .st-key-spotsession_cond_stain_card,
    .st-key-spotsession_cond_wind_card,
    .st-key-spotsession_cond_activity_card {
        background:var(--stringer-surface) !important; border:1px solid var(--stringer-border) !important;
        border-radius:14px !important; padding:0 18px 16px !important; margin-bottom:14px !important;
        overflow:hidden;
    }
    /* Header band - a raw markdown div (`.ss-card-head`), not
       st.subheader (entry 185: st.subheader's own icon= path creates a
       real stHeadingIconWrapper element live, confirmed via the browser
       tools, but never actually applies the Material Symbols font to it
       in this version/context - a frontend-only quirk, confirmed NOT a
       mistake in how the icon was passed via a matching AppTest proto
       check). Bled edge-to-edge via a negative margin matching the
       container's own side padding above. `.ss-msym` uses the
       Material+Symbols+Outlined webfont loaded alongside this page's
       other two fonts above - same real, independently-loaded-webfont
       technique already proven in the approved mockup, sidestepping
       Streamlit's own icon path entirely. */
    .ss-card-head {
        display:flex; align-items:center; gap:8px;
        background:var(--stringer-surface-sunk); margin:0 -18px 14px -18px;
        padding:10px 18px; border-bottom:1px solid var(--stringer-border);
        font-family:"Plus Jakarta Sans", system-ui, sans-serif; font-size:.92rem; font-weight:700;
        color:var(--stringer-ink);
    }
    .ss-msym {
        font-family:'Material Symbols Outlined'; font-variation-settings:'opsz' 20,'wght' 500,'FILL' 0,'GRAD' 0;
        font-size:19px; line-height:1; color:var(--stringer-accent);
    }
    /* Numeric steppers (water temp / secchi / fish depth) - real
       st.number_input, just reskinned. Confirmed live that
       stNumberInputContainer is the actual flex-row box (input + a
       grouped stepDown/stepUp pair on the right) - the two buttons are
       NOT split to either side of the value, so this works with that
       real layout rather than fighting it into the angler's reference
       image's split layout. */
    .st-key-spotsession_cond_water_card [data-testid="stNumberInputContainer"],
    .st-key-spotsession_cond_activity_card [data-testid="stNumberInputContainer"] {
        background:var(--stringer-surface) !important; border:1px solid var(--stringer-border) !important;
        border-radius:10px !important; height:46px !important;
    }
    .st-key-spotsession_cond_water_card [data-testid="stNumberInputField"],
    .st-key-spotsession_cond_activity_card [data-testid="stNumberInputField"] {
        font-family:"Space Grotesk", system-ui, sans-serif !important; font-weight:600 !important;
        font-size:1rem !important; color:var(--stringer-ink) !important;
    }
    .st-key-spotsession_cond_water_card [data-testid="stNumberInputContainer"] > div:last-child,
    .st-key-spotsession_cond_activity_card [data-testid="stNumberInputContainer"] > div:last-child {
        border-left:1px solid var(--stringer-border) !important;
    }
    .st-key-spotsession_cond_water_card [data-testid="stNumberInputStepUp"],
    .st-key-spotsession_cond_water_card [data-testid="stNumberInputStepDown"],
    .st-key-spotsession_cond_activity_card [data-testid="stNumberInputStepUp"],
    .st-key-spotsession_cond_activity_card [data-testid="stNumberInputStepDown"] {
        background:var(--stringer-surface-sunk) !important; width:34px !important; height:44px !important;
    }
    /* Data badges (Metabolic state / Visibility band) - custom markup,
       not a restyled native widget: a real colored pill needs exact
       control a restyled st.caption can't reliably give. */
    .ss-badge-label {
        font-family:"Plus Jakarta Sans", system-ui, sans-serif; font-size:.68rem; font-weight:700;
        letter-spacing:.03em; color:var(--stringer-muted); text-transform:uppercase; margin:10px 0 5px;
    }
    .ss-badge {
        background:var(--stringer-accent); color:#EAF6F2; font-size:.85rem; font-weight:600;
        border-radius:9px; padding:8px 11px; line-height:1.35;
    }
    .ss-badge b { color:#FFFFFF; }
    /* Selectbox (Stain color / Wind / Wind direction / Sky / Precipitation)
       - confirmed live: the real bordered box is the div[role="group"]
       wrapping input[role="combobox"] + the chevron button, not the
       outer stSelectbox testid (that just wraps the label + this group). */
    .st-key-spotsession_cond_stain_card [data-testid="stSelectbox"] div[role="group"],
    .st-key-spotsession_cond_wind_card [data-testid="stSelectbox"] div[role="group"] {
        background:var(--stringer-surface) !important; border:1px solid var(--stringer-border) !important;
        border-radius:10px !important;
    }
    .st-key-spotsession_cond_stain_card [data-testid="stSelectbox"] input[role="combobox"],
    .st-key-spotsession_cond_wind_card [data-testid="stSelectbox"] input[role="combobox"] {
        color:var(--stringer-ink) !important;
    }
    /* "Stirred up / muddy" checkbox - sunk pill, matching the reference
       image's treatment, via stCheckbox's own <label> (confirmed live:
       the checkbox input, label text, and tooltip icon are all children
       of one <label>, so this is the one element that can carry the pill
       background without breaking the native click target). */
    .st-key-spotsession_cond_stain_card [data-testid="stCheckbox"] label {
        background:var(--stringer-surface-sunk) !important; border-radius:10px !important;
        padding:10px 12px !important;
    }
    /* Every expander on this page becomes a card - `details` (not the
       outer [data-testid="stExpander"] wrapper) is what actually carries
       Streamlit's own border/radius/background, confirmed live via
       getComputedStyle() before writing this rule, same discipline as
       every other widget reskin on this site (entry 178's alert-box
       lesson). Page-wide, not container-scoped - see the block comment
       above this whole style block for why that's safe here. */
    [data-testid="stExpander"] > details {
        background:linear-gradient(180deg, var(--stringer-card-from) 0%, var(--stringer-card-to) 100%) !important;
        box-shadow:var(--stringer-card-shadow) !important; border:var(--stringer-card-border) !important;
        border-radius:16px !important;
    }
    [data-testid="stExpander"] > details > summary {
        background:transparent !important; border-radius:16px 16px 0 0 !important;
        padding:14px 18px !important; font-weight:700 !important; color:var(--stringer-ink) !important;
    }
    [data-testid="stExpander"] > details > [data-testid="stExpanderDetails"] {
        padding:4px 18px 18px !important;
    }
    /* An expander nested inside another one (Tackle box gaps inside
       Suggestions; See updated lure suggestions inside Conditions
       changed?) gets a flatter, sunk look instead of the same gradient/
       shadow card stacked inside itself - identical heavy cards nested
       reads as visual noise, not depth. One descendant selector covers
       any nesting depth, same as 7-Day Forecast's own version of this
       rule (entry 181). */
    [data-testid="stExpander"] [data-testid="stExpander"] > details {
        background:var(--stringer-surface-sunk) !important; box-shadow:none !important;
        border:1px solid var(--stringer-border) !important; border-radius:10px !important;
    }
    [data-testid="stExpander"] [data-testid="stExpander"] > details > summary {
        background:transparent !important; border-radius:10px 10px 0 0 !important; font-weight:600 !important;
    }
    /* st.info/st.warning/st.success/st.error anywhere on this page - same
       re-skin as every other page (entry 178): the real tinted background
       lives on the middle `stAlertContainer` layer, not the outer
       `stAlert` wrapper, which has none of its own to override. */
    [data-testid="stAlertContainer"] {
        background:var(--stringer-surface-sunk) !important; border-radius:10px !important;
        border:none !important;
    }
    [data-testid="stAlertContentInfo"] { border-left:3px solid var(--stringer-accent) !important; }
    [data-testid="stAlertContentWarning"] { border-left:3px solid var(--stringer-warn) !important; }
    [data-testid="stAlertContentSuccess"] { border-left:3px solid var(--stringer-good) !important; }
    [data-testid="stAlertContentError"] { border-left:3px solid var(--stringer-error) !important; }
    /* Every number on this page (session/segment activity scores, fish
       counts) - Space Grotesk, not IBM Plex Mono, matching where Home's
       own numbers already moved to (entry 180) and 7-Day Forecast started
       from day one (entry 181). */
    [data-testid="stMetricValue"] {
        font-family:"Space Grotesk", system-ui, sans-serif; font-variant-numeric:tabular-nums;
        color:var(--stringer-ink);
    }
    [data-testid="stMetricLabel"] {
        font-family:"Plus Jakarta Sans", system-ui, sans-serif; color:var(--stringer-muted); font-weight:600;
    }
    /* Body text color, inside any expander (any nesting depth) or one of
       the three named cards above - this app's .streamlit/config.toml
       pins a fixed LIGHT theme (textColor #262730), so Streamlit's own
       native widget text never itself follows the OS/browser's prefers-
       color-scheme the way these --stringer-* tokens do - only an
       explicit override here keeps plain text, captions, widget labels,
       and headings readable once a card's own background flips dark
       under that same media query. Same fix, same reason, as Home's own
       bestwindow-card override (entry 178) and 7-Day Forecast's page-wide
       version of it (entry 181) - this page just has far more of these
       (a dozen-plus expanders, three big cards, and this is the one page
       in the app where every field is a live on-the-water input, not
       read-only display, so widget LABELS need the same fix too, not
       just markdown/caption text). */
    [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p,
    .st-key-spotsession_conditions_card [data-testid="stMarkdownContainer"] p,
    .st-key-spotsession_active_card [data-testid="stMarkdownContainer"] p,
    .st-key-spotsession_pending_lures_card [data-testid="stMarkdownContainer"] p {
        color:var(--stringer-ink-soft) !important;
    }
    [data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"] p,
    .st-key-spotsession_conditions_card [data-testid="stCaptionContainer"] p,
    .st-key-spotsession_active_card [data-testid="stCaptionContainer"] p,
    .st-key-spotsession_pending_lures_card [data-testid="stCaptionContainer"] p {
        color:var(--stringer-muted) !important;
    }
    [data-testid="stExpanderDetails"] [data-testid="stWidgetLabel"] p,
    .st-key-spotsession_cond_water_card [data-testid="stWidgetLabel"] p,
    .st-key-spotsession_cond_stain_card [data-testid="stWidgetLabel"] p,
    .st-key-spotsession_cond_wind_card [data-testid="stWidgetLabel"] p,
    .st-key-spotsession_cond_activity_card [data-testid="stWidgetLabel"] p,
    .st-key-spotsession_active_card [data-testid="stWidgetLabel"] p,
    .st-key-spotsession_pending_lures_card [data-testid="stWidgetLabel"] p {
        color:var(--stringer-ink-soft) !important;
    }
    [data-testid="stExpanderDetails"] [data-testid="stHeading"] h1,
    [data-testid="stExpanderDetails"] [data-testid="stHeading"] h2,
    [data-testid="stExpanderDetails"] [data-testid="stHeading"] h3,
    [data-testid="stExpanderDetails"] [data-testid="stHeading"] h4,
    .st-key-spotsession_conditions_card [data-testid="stHeading"] h1,
    .st-key-spotsession_conditions_card [data-testid="stHeading"] h2,
    .st-key-spotsession_conditions_card [data-testid="stHeading"] h3,
    .st-key-spotsession_conditions_card [data-testid="stHeading"] h4,
    .st-key-spotsession_active_card [data-testid="stHeading"] h1,
    .st-key-spotsession_active_card [data-testid="stHeading"] h2,
    .st-key-spotsession_active_card [data-testid="stHeading"] h3,
    .st-key-spotsession_active_card [data-testid="stHeading"] h4,
    .st-key-spotsession_pending_lures_card [data-testid="stHeading"] h1,
    .st-key-spotsession_pending_lures_card [data-testid="stHeading"] h2,
    .st-key-spotsession_pending_lures_card [data-testid="stHeading"] h3,
    .st-key-spotsession_pending_lures_card [data-testid="stHeading"] h4 {
        color:var(--stringer-ink) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
_top_today = lake_today()
st.markdown(
    f"""
    <div class="spotsession-topbar">
        <div>
            <div class="spotsession-brand">🎯 SPOT SESSION</div>
            <div class="spotsession-tagline">Live on-the-water conditions, lure calls, and catch logging</div>
        </div>
        <div class="spotsession-date-chip">{_top_today.strftime('%a, %b %-d')}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Punch-list #62: a persistent (not a toast, so it can't be missed/scrolled
# past on a phone) line saying whether this running process can actually
# see a GITHUB_TOKEN right now - every save on this page silently keeps
# working locally either way, with only a toast to say whether it also
# reached GitHub, and that toast is easy to miss. Shown once, right up
# top, before anything else - so "is this actually saving to GitHub right
# now" never depends on catching a toast at the right moment.
_gh_configured, _gh_preview = github_connection_status()
if _gh_configured:
    st.caption(f"🔌 GitHub sync: connected ({_gh_preview})")
else:
    st.warning(
        "🔌 **GitHub sync: not connected.** No GITHUB_TOKEN configured here (or Streamlit "
        "couldn't read it) - everything you log this session will stay on this device only, "
        "and won't survive an app restart or reboot. Check the app's Secrets in Streamlit "
        "Cloud settings."
    )

# Punch-list #65: what End/Cancel Session just did, shown here - before ANY
# spot/angler resolution below - rather than as three separate per-spot-
# keyed checks further down the page (session_closed_banner_{spot_id}/
# session_canceled_banner_{spot_id}/session_cancel_failed_banner_{spot_id},
# the pre-#65 approach). That approach broke the moment a real Cancel
# Session started also clearing the picked location (_reset_builder_to_
# scratch() below, added for this same punch-list item): with no spot_id
# left to key off of, the page hits the "no spot selected yet" screen's
# own st.stop() further up and the per-spot banner check code - which
# lived AFTER that point - would never even run. One page-wide dict
# instead, popped and shown immediately, that carries the spot's name as
# plain text rather than needing a live `spot` object to describe it.
_action_banner = st.session_state.pop("session_action_banner", None)
if _action_banner:
    _banner_spot = _action_banner.get("spot_name") or "that spot"
    _banner_kind = _action_banner.get("kind")
    if _banner_kind == "closed":
        st.success(f"✅ Session closed at {_banner_spot} - pick a spot below whenever you're ready to start a new one.")
    elif _banner_kind == "canceled":
        st.info(f"❌ Session at {_banner_spot} canceled - nothing from that session was saved. Starting fresh below.")
    elif _banner_kind == "cancel_failed":
        # Punch-list #64: see _cancel_session()'s docstring - this
        # session's own data went missing from session_state right when
        # "Yes, cancel it" was tapped, so nothing was deleted and nothing
        # was changed. Tapping "❌ Cancel Session" again has reliably
        # worked on the very next try in every reproduction so far.
        st.warning(
            f"❌ Cancel didn't go through at {_banner_spot} - this session's data wasn't found where "
            "expected just now (a dropped connection can do this). Nothing was changed or lost. "
            "Scroll down and tap \"❌ Cancel Session\" again."
        )

# --- Spot picker (unchanged from before the redesign) ------------------------
# session_state is the reliable channel from the "Fish this spot now" button on the
# Lake Map page (st.switch_page doesn't consistently carry query params set in that
# same run over to this page's initial load); query_params is kept as a fallback so a
# manual page refresh or a bookmarked/shared link with ?spot_id=... still works.
spot_id = st.session_state.get("spot_session_target_id") or st.query_params.get("spot_id")
spots = get_lake_spots()
spot = next((s for s in spots if s["spot_id"] == spot_id), None) if spot_id else None

if spot is not None:
    st.session_state["spot_session_target_id"] = spot_id
    st.query_params["spot_id"] = spot_id

if not spots:
    st.info(
        "No spot selected yet. Pick one of your saved spots below to start a session here directly, "
        "or go to the Lake Map page to click (or jump to) one instead."
    )
    st.caption("You don't have any saved spots yet - drop a pin on the Lake Map page first.")
    if st.button("Go to Lake Map"):
        st.switch_page("pages/2_Lake_Map.py")
    st.stop()

sorted_spots = sorted(spots, key=lambda s: s["name"])

if spot is not None:
    current_spot_idx = next(i for i, s in enumerate(sorted_spots) if s["spot_id"] == spot["spot_id"])
    picked_idx = st.selectbox(
        "📍 Location", options=range(len(sorted_spots)), format_func=lambda i: sorted_spots[i]["name"],
        index=current_spot_idx, key=f"spot_picker_{spot['spot_id']}",
    )
    picked_spot = sorted_spots[picked_idx]
    if picked_spot["spot_id"] != spot["spot_id"]:
        st.session_state["spot_session_target_id"] = picked_spot["spot_id"]
        st.query_params["spot_id"] = picked_spot["spot_id"]
        st.rerun()
else:
    st.info(
        "No spot selected yet. Pick one of your saved spots below to start a session here directly, "
        "or go to the Lake Map page to click (or jump to) one instead."
    )
    NO_SPOT_PROMPT = "— choose a saved spot —"
    picked_idx = st.selectbox(
        "📍 Location", options=range(len(sorted_spots) + 1),
        format_func=lambda i: NO_SPOT_PROMPT if i == 0 else sorted_spots[i - 1]["name"],
        key="spot_picker_none",
    )
    if picked_idx != 0:
        picked_spot = sorted_spots[picked_idx - 1]
        st.session_state["spot_session_target_id"] = picked_spot["spot_id"]
        st.query_params["spot_id"] = picked_spot["spot_id"]
        st.rerun()

    if st.button("Go to Lake Map"):
        st.switch_page("pages/2_Lake_Map.py")
    st.stop()

def _guess_segment(hour: int, now: datetime = None) -> str:
    """Best-effort guess at the time-of-day segment for a given moment
    (`now`). Prefers the real thing - `seg_ranges` (module-level, computed a
    little below from segment_time_ranges() for this session's date, the
    same real sunrise/sunset-derived windows the 7-Day Forecast page's own
    labels use) checked against `now`. One extra case those windows alone
    don't cover: `now` in the early hours after midnight but before *today's*
    Dawn actually belongs to the tail end of *last night's* Night window.
    Falls back to fixed clock-hour cutoffs when no weather bundle is
    available or `now` isn't given."""
    if seg_ranges and now is not None:
        for name in SEGMENTS:
            window = seg_ranges.get(name)
            if window and window[0] <= now < window[1]:
                return name
        dawn = seg_ranges.get("Dawn")
        if dawn and now < dawn[0]:
            return "Night"
    if hour < 7:
        return "Dawn"
    if hour < 11:
        return "Morning"
    if hour < 14:
        return "Midday"
    if hour < 18:
        return "Afternoon"
    if hour < 20:
        return "Dusk"
    return "Night"


st.subheader(f"📍 {spot['name']}")
bottom = split_bottom_structure(spot.get("bottom_structure", ""))
meta_bits = []
if spot.get("location_type"):
    meta_bits.append(spot["location_type"])
if bottom:
    meta_bits.append(", ".join(bottom))
if spot.get("main_depth_ft"):
    meta_bits.append(f"main area {spot['main_depth_ft']} ft")
if spot.get("transition_depth_ft"):
    meta_bits.append(f"transition {spot['transition_depth_ft']} ft ({spot.get('transition_grade', '')})")
st.caption(" · ".join(meta_bits) if meta_bits else "No saved details for this spot yet - add some from the Lake Map page.")

if st.button("← Back to Lake Map"):
    st.switch_page("pages/2_Lake_Map.py")

# --- Structure type + session-lookup helpers, needed before the angler
# picker below can warn about (and exclude) anglers who already have a
# session going here right now (punch-list #59) - moved up from where they
# used to live, right next to where "NORMAL MODE" further down uses them
# for the real session-in-progress view. Nothing about their behavior
# changed by moving them.
structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(spot.get("location_type"), "Main-lake point")


def _angler_session_slug(angler: str) -> str:
    """Stable, session_state-key-safe token for an angler name, so it can
    be embedded in _active_session_key() below. Falls back to a fixed
    sentinel for a blank/unset angler rather than "" - keeps the key
    readable in a stale session_state dump and avoids a blank name and a
    literally-blank-string name colliding by coincidence."""
    name = (angler or "").strip()
    if not name:
        return "unassigned"
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "unassigned"


def _active_session_key(spot_id: str, angler: str) -> str:
    return f"active_session_{spot_id}_{_angler_session_slug(angler)}"


# Punch-list #29: every lure/fish already lands in data/trip_log.csv the
# instant it happens (see _record_fish()/_add_lure_to_active_session()/the
# Start Session handler below - each calls append_trip()/update_trip() and
# pushes immediately, not batched until End Session), but which lures were
# still "active" and tappable to log a fish lived ONLY in st.session_state -
# in-memory on the server, tied to one browser session. Spotty cell coverage
# (a dropped WebSocket), a phone locking mid-session, or the server itself
# restarting all wipe st.session_state, and the angler's own report was that
# reconnecting after one of these made an in-progress session look like it
# had never started - conditions/spot still there (those ride along via
# query_params, entry 34), but the lure buttons were gone and it dropped
# back to the pre-session builder. Nothing was actually lost on disk; the
# fix is to rebuild the "session in progress" view from what's already
# there instead of losing track of it. True offline operation isn't
# achievable here - every interaction in this app is a live round trip to
# the Python server, there's no offline-capable client code - so this is
# the practical fix within that constraint: reconnecting picks up exactly
# where the last successful save left off, rather than losing the session.
#
# Punch-list #69: this reconstruction (and the "is this angler already
# mid-session here" check the picker uses) used to only look at rows whose
# trip_date matched one specific date - "today" for the picker-exclusion
# check, or whatever the "Session date" widget happened to show for the
# actual reconnect. That's fine the moment a session starts, but an angler
# who closes the app (loses their session_state AND the ?angler= query
# param - e.g. relaunching from an iPhone home-screen icon, which opens the
# bare URL) and comes back on a LATER calendar day found their own name no
# longer flagged as "already active" (good), but reconnecting silently
# failed anyway, because the reconstruction lookup was still only checking
# TODAY's rows and their real open session was dated yesterday (or
# earlier) - it simply vanished from every code path that could find it,
# with no error shown. A real angler hit exactly this: their session
# couldn't be reopened, and in the meantime (still the same day) their name
# was excluded from the main picker with no obvious way back in besides the
# little-used "Other" reclaim flow. Fixed by dropping the trip_date
# equality check everywhere below - "does this angler have an open session
# at this spot" and "reconnect to it" now both mean "is there ANY row here
# without a lure_end_time yet," regardless of which day it was logged
# under. A still-open session now stays reachable (and keeps blocking a
# same-named fresh start, forcing a deliberate resume-then-End/Cancel
# instead of silently orphaning it) no matter how many days pass before
# someone gets back to a browser that remembers who they are.
_PER_LURE_CONDITION_KEYS = {
    "lure_category", "trailer_used", "trailer_name", "trailer_color",
    "trailer_category", "lure_start_time", "lure_end_time", "fish", "source",
}


def _session_group_key(t: dict, cond: dict):
    """The key _open_session_rows()/_anglers_with_open_session() group rows
    by. Prefers the real session_id (punch-list #55 - a fresh uuid stamped
    once at Start Session, so it can never collide between two genuinely
    different sessions). Falls back to trip_date + start_time + angler for
    legacy rows logged before session_id existed (blank string there).

    Punch-list #69: this fallback used to be JUST conditions["start_time"] -
    a bare wall-clock time-of-day string with no date attached. Investigating
    the reported stuck-session bug surfaced a real, separate corruption risk
    that created: an angler who fishes the same spot at a habitual time (e.g.
    "06:00:00" for a dawn start) ends up with MULTIPLE, completely unrelated
    real sessions on different real dates sharing that exact string - grouping
    on it alone silently merged three of one real angler's real past sessions
    at one real spot into a single "session" here, purely because they all
    started at the same clock time on different days. Reconnecting to
    whichever one of those was still open would then have pulled in the
    OTHER, already-properly-closed sessions' rows too, and hitting "⏹ End
    Session" would have overwritten their real, already-correct end times.
    Returns None (never groups) for a row with no start_time at all - same
    as the original "not a real session row" skip."""
    session_id = cond.get("session_id")
    if session_id:
        return session_id
    start_time = cond.get("start_time")
    if not start_time:
        return None
    return f"{t.get('trip_date')}|{start_time}|{cond.get('angler')}"


def _open_session_rows(spot_id: str, trips_at_spot: list, angler: str) -> list:
    """Groups this spot's spot_session-sourced rows (any trip_date - see
    punch-list #69 note above) by _session_group_key() (real session_id
    when present, else trip_date+start_time+angler - see that function's
    own docstring for why a bare start_time alone isn't safe to group on),
    then returns the rows for whichever group still has at least one lure
    without a lure_end_time yet (i.e. genuinely still in progress - a
    properly "⏹ End Session"-ed group has every row's lure_end_time
    stamped, retired or not) AND whose own conditions["angler"] matches
    `angler` (punch-list #47) - so reconnecting always picks back up THIS
    angler's own open session, never someone else's still-in-progress one,
    even if theirs started more recently. Returns [] if nothing's open for
    this angler - either nothing's ever been logged here under this name,
    or their own session(s) logged here have already all been ended.
    If, unusually, this angler has more than one group open at once (this
    page has no flow that starts a second session before ending the first
    under the same name, but a hand-edited CSV or an old bug could produce
    one), the most recently started of THEIR groups wins - the others are
    simply left alone rather than merged or discarded."""
    groups = {}
    for t in trips_at_spot:
        if t.get("spot_id") != spot_id:
            continue
        cond = parse_conditions(t)
        if cond.get("source") != "spot_session":
            continue
        key = _session_group_key(t, cond)
        if not key:
            continue
        groups.setdefault(key, []).append((t, cond))
    my_slug = _angler_session_slug(angler)
    open_groups = {
        k: rows for k, rows in groups.items()
        if any(not c.get("lure_end_time") for _, c in rows)
        and _angler_session_slug(rows[0][1].get("angler")) == my_slug
    }
    if not open_groups:
        return []
    latest_key = max(open_groups, key=lambda k: min(t.get("logged_at") or "" for t, _ in open_groups[k]))
    return sorted(open_groups[latest_key], key=lambda tc: tc[0].get("logged_at") or "")


def _anglers_with_open_session(spot_id: str, trips_at_spot: list) -> list:
    """Distinct angler names (first-seen order) who have their own still-
    open spot_session at this spot - ANY date (punch-list #69 - see the
    block comment above), not just today. Punch-list #59: the angler
    picker below uses this directly to keep anyone from silently picking
    (or defaulting to) a name that's already mid-session here, and to offer
    a choice of whose session to watch when more than one is live.
    _other_anglers_with_open_session() just below is a thin wrapper that
    excludes one name from this same list, for the in-session "so-and-so
    also has a session going" caption. Grouped by _session_group_key() -
    see that function's docstring for why a bare start_time alone isn't a
    safe grouping key (punch-list #69)."""
    groups = {}
    for t in trips_at_spot:
        if t.get("spot_id") != spot_id:
            continue
        cond = parse_conditions(t)
        if cond.get("source") != "spot_session":
            continue
        key = _session_group_key(t, cond)
        if not key:
            continue
        groups.setdefault(key, []).append(cond)
    seen_slugs = set()
    anglers = []
    for conds in groups.values():
        if not any(not c.get("lure_end_time") for c in conds):
            continue
        angler_name = (conds[0].get("angler") or "").strip()
        slug = _angler_session_slug(angler_name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        anglers.append(angler_name or "an unnamed angler")
    return anglers


def _other_anglers_with_open_session(spot_id: str, trips_at_spot: list, my_angler: str) -> list:
    """_anglers_with_open_session() above, minus my_angler - punch-list #47,
    used purely to reassure whoever's looking at this page that starting/
    ending/canceling their own session never touches anyone else's (each
    angler's session is independently tracked - see
    _active_session_key()/_open_session_rows() above)."""
    my_slug = _angler_session_slug(my_angler)
    return [
        a for a in _anglers_with_open_session(spot_id, trips_at_spot)
        if _angler_session_slug(a) != my_slug
    ]


def _reconstruct_active_session(spot: dict, structure_type: str, trips_at_spot: list, angler: str):
    """Rebuilds this angler's own active_session_{spot_id}_{angler} dict
    (see _active_session_key(), punch-list #47 - the same shape Start
    Session/_add_lure_to_active_session build live) from already-saved
    trip_log.csv rows, for the reconnect-after-a-session_state-loss case -
    see the block comment above. Returns None if there's no still-open
    session for THIS angler logged here, on ANY date (punch-list #69 - a
    different angler's own still-open session at this same spot is left
    completely alone either way - see _open_session_rows()). One thing a
    persisted row can't give back:
    `item_id` (which inventory item this lure is) was never itself written
    to disk, only the lure's display label - so a reconstructed lure's
    item_id is always None, which just means the "already added" dedup
    check in _add_lure_to_active_session() won't catch re-adding the exact
    same inventory item after a reconnect (picking it again would show up
    as a second, separate row for the same lure - harmless, just tidy up
    manually via Trip History if it happens, not silent data loss).
    Also reused read-only by _render_watch_view() below (punch-list #59) to
    build a "just watching" display of someone else's session - that call
    site never stores the result in st.session_state and never calls
    anything that writes to disk.

    Punch-list #93: session-level fields (spot/structure/water clarity/
    base_conditions/predicted_score/segment_name) used to always be taken
    from `rows[0]` - the FIRST lure ever added, chronologically. That was
    harmless when nothing about a session could change after Start Session,
    but now that location AND conditions can both change mid-session (see
    _relocate_active_session() below - and, retroactively, this was already
    subtly true for the punch-list #49 "🔄 Conditions changed?" panel, which
    updates active["base_conditions"] in memory but never rewrote any
    on-disk row with it), reconstructing from the FIRST row would silently
    revert a reconnect to the ORIGINAL session-start conditions/location,
    losing whatever the most recent mid-session update actually said. Fixed
    by reconstructing those fields from the latest still-OPEN row instead -
    `_open_session_rows()` only ever returns this group because at least
    one row lacks lure_end_time, so there's always at least one to use, and
    every currently-open lure always shares the same current location/
    conditions (every relocation carries ALL of them over together - see
    that function). `session_date`/`start_time` still come from the very
    FIRST row - those describe when the SESSION itself began, which a
    mid-session relocation or conditions update never changes."""
    rows = _open_session_rows(spot["spot_id"], trips_at_spot, angler)
    if not rows:
        return None
    lures = []
    for t, cond in rows:
        entry_kwargs = dict(
            trip_date=t.get("trip_date"),
            segment=t.get("segment"),
            spot_id=t.get("spot_id"),
            spot_name=t.get("spot_name"),
            structure_type=t.get("structure_type"),
            water_clarity=t.get("water_clarity"),
            lure_used=t.get("lure_used"),
            color_used=t.get("color_used") or "",
            technique_used=t.get("technique_used") or "",
            fish_caught=int(t["fish_caught"]) if t.get("fish_caught") not in (None, "") else 0,
            biggest_fish_lb=float(t["biggest_fish_lb"]) if t.get("biggest_fish_lb") not in (None, "") else None,
            predicted_score=float(t["predicted_score"]) if t.get("predicted_score") not in (None, "") else None,
            conditions=cond,
            notes=t.get("notes") or "",
            # Punch-list #55: preserve whatever session_id this row already
            # has (blank for a row logged before that field existed) so a
            # reconnect's subsequent update_trip() calls (record/remove a
            # fish, retire a lure, end the session) don't silently drop it.
            session_id=t.get("session_id") or "",
        )
        lures.append({
            "trip_id": t.get("trip_id"), "logged_at": t.get("logged_at"), "label": t.get("lure_used"),
            "item_id": None,
            "entry_kwargs": entry_kwargs, "fish": cond.get("fish") or [],
            "retired": bool(cond.get("lure_end_time")),
        })
    open_rows = [(t, cond) for t, cond in rows if not cond.get("lure_end_time")]
    current_t, current_cond = open_rows[-1] if open_rows else rows[-1]
    # Every lure's own conditions dict is this same shared snapshot plus the
    # per-lure keys layered on top (see the Start Session handler /
    # _add_lure_to_active_session() below) - strip those back off to
    # recover the shared snapshot, so a lure added after reconnecting still
    # reuses the real current session conditions instead of nothing.
    base_conditions = {k: v for k, v in current_cond.items() if k not in _PER_LURE_CONDITION_KEYS}
    first_cond = rows[0][1]
    return {
        "spot_id": current_t.get("spot_id") or spot["spot_id"],
        "spot_name": current_t.get("spot_name") or spot["name"],
        "session_date": rows[0][0].get("trip_date") or lake_today().isoformat(),
        "start_time": first_cond.get("start_time") or lake_now_naive().time().isoformat(),
        "segment_name": current_t.get("segment"),
        "session_id": current_t.get("session_id") or "",
        "structure_type": current_t.get("structure_type") or structure_type,
        "water_clarity": current_t.get("water_clarity"),
        "predicted_score": (
            float(current_t["predicted_score"]) if current_t.get("predicted_score") not in (None, "") else None
        ),
        "base_conditions": base_conditions,
        "lures": lures,
        "reconstructed": True,
    }


@st.fragment(run_every=20)
def _render_watch_view(spot: dict, structure_type: str, watched_angler: str):
    """Punch-list #59: read-only, no-login 'just watching' view. Rebuilds
    the watched angler's session purely for DISPLAY via the same
    _reconstruct_active_session() the real angler's own reconnect flow
    uses (punch-list #69: any date, not just today - see that function's
    own docstring). This function never writes to st.session_state's
    active_session_* key, never calls append_trip()/update_trip()/
    delete_trip(), and renders no button that could touch the real session -
    a watcher can look, but there is nothing here to tap that changes
    anything. Wrapped in a 20-second auto-refreshing fragment (same
    mechanism as the autosave heartbeat below) so a new catch shows up
    without the watcher needing to manually reload."""
    trips_at_spot = [t for t in read_all_trips() if t.get("spot_id") == spot["spot_id"]]
    active = _reconstruct_active_session(spot, structure_type, trips_at_spot, watched_angler)
    if active is None:
        st.info(f"👀 {watched_angler}'s session here has ended (or hasn't started). Nothing to watch right now.")
        return
    st.header(f"👀 Watching {watched_angler}'s session")
    score_bit = f" · predicted score {active['predicted_score']}/10" if active.get("predicted_score") is not None else ""
    st.caption(
        f"Started {active['start_time']} · {active['segment_name']} · {active['water_clarity']} water{score_bit}"
    )
    # No "ℹ️ How this score was derived" popover here (punch-list #94) -
    # this view always goes through _reconstruct_active_session(), which
    # (like every reconnect) never has the factor breakdown to show;
    # recomputing it fresh here would silently describe a DIFFERENT
    # score than the frozen predicted_score above (pressure trend, moon
    # window etc. keep moving), which would be actively misleading rather
    # than just unavailable.
    st.caption("Read-only - refreshes automatically every 20 seconds, no login and nothing you can accidentally change.")
    total_fish = 0
    for lure in active["lures"]:
        fish_count = sum((f.get("count") or 1) for f in lure["fish"])
        total_fish += fish_count
        status = " (retired)" if lure.get("retired") else ""
        st.write(f"🎣 {lure['label']}{status} - {fish_count} caught")
    if not active["lures"]:
        st.caption("No lures logged yet.")
    else:
        st.caption(f"{total_fish} fish total so far this session.")


# Anglers with a session open at this spot RIGHT NOW - ANY date, not just
# today (punch-list #69: a still-open session used to stop being findable
# the moment its own start date wasn't "today" anymore, which both stranded
# it unreachable and, while it WAS still today, excluded its angler's name
# from the picker with no obvious way back in - see the block comment above
# _open_session_rows() for the full story). Read once here, before the
# picker, so it can both keep anyone from picking a name that's already
# mid-session and offer a "just watching" option for it instead
# (punch-list #59).
_open_check_entries = [t for t in read_all_trips() if t.get("spot_id") == spot["spot_id"]]
anglers_with_open_session_here = _anglers_with_open_session(spot["spot_id"], _open_check_entries)


# --- Angler picker (punch-list #26: lightweight multi-user support) --------
# A plain "who's fishing" name picker, not real accounts/passwords - see
# core/anglers.py's module docstring for why. Every trip this page logs
# gets tagged with whichever name is picked here (baked into every lure's
# conditions dict by _build_base_conditions() below), so Trip History can
# filter by angler while every trip still lands in the same one shared log.
# The picker's own widget key ("active_angler") is deliberately NOT scoped
# by spot_id/trip_id - it's a page-wide "who's at the keyboard right now"
# setting for this browser session, not something tied to any one trip or
# spot, so it should keep whatever was last picked as the angler moves
# between spots/sessions.
angler_roster = get_anglers()
angler_key = "active_angler"
angler_other_key = "active_angler_other_name"
angler_query_key = "angler"
watch_key = "spot_session_watch_angler"
watch_query_key = "watch"
WATCH_LABEL = "👀 Just watching (read-only, no login)"
LANDING_PROMPT = "— pick one —"

_identity_established = angler_key in st.session_state
_watching_established = watch_key in st.session_state

if not _identity_established and not _watching_established:
    # Punch-list #51/#59: session_state alone doesn't survive a full app
    # restart (Streamlit Cloud auto-redeploying after ANY user's save, or
    # just a plain reconnect). Restore an already-established identity (or
    # watch target) from the URL first - the same pattern already used for
    # spot_id - so a reconnecting angler (or a still-watching watcher) lands
    # back on themselves automatically, before anything below ever has to
    # guess who this is.
    _qp_watch = (st.query_params.get(watch_query_key) or "").strip()
    _qp_angler = (st.query_params.get(angler_query_key) or "").strip()
    if _qp_watch:
        st.session_state[watch_key] = _qp_angler if _qp_angler in anglers_with_open_session_here else ""
        _watching_established = True
    elif _qp_angler:
        if _qp_angler in angler_roster:
            st.session_state[angler_key] = _qp_angler
        else:
            st.session_state[angler_key] = ANGLER_OTHER_LABEL
            st.session_state[angler_other_key] = _qp_angler
        _identity_established = True

if not _identity_established and not _watching_established:
    # Punch-list #59: no established identity AND no restorable watch link -
    # a genuinely fresh visit (a bare/bookmarked link, someone else's
    # phone). This used to silently default to angler_options[0] -
    # deterministically the first roster name - landing whoever this is
    # directly on that person's real session as if they WERE them. Now it
    # asks first: anglers who don't already have a session going here right
    # now can pick their own name and start fishing; anyone else (including
    # someone who'd type an already-active name into "Other") gets steered
    # to "Just watching" instead - read-only, no way to touch the real
    # session, with a picker of whose session to watch if more than one is
    # live right now.
    _eligible_to_fish = [a for a in angler_roster if a not in anglers_with_open_session_here]
    _landing_options = [LANDING_PROMPT] + _eligible_to_fish + [ANGLER_OTHER_LABEL, WATCH_LABEL]
    st.info(
        "👋 New here, or a fresh link with no name attached. Pick your own name to start fishing, "
        "or choose \"Just watching\" to follow someone else's live session with no risk of changing it."
    )
    _landing_choice = st.selectbox("🎣 Who's this?", _landing_options, key="spot_session_landing_choice")

    def _stop_with_scroll_room() -> None:
        """A real angler report from a phone: this landing screen is often
        the SHORTEST state this page ever renders (a brand-new visit has
        nothing above it but one st.info banner and this selectbox), so
        whatever renders last here - the "Name" field, the watch-target
        picker, the reclaim-session button - can end up sitting right at
        the edge of how far a phone's on-screen keyboard/momentum-scroll
        will actually let a real user scroll, underneath core.nav's fixed
        bottom bar. This dev sandbox has no real phone/keyboard to nail the
        exact mechanism against (see SESSION_NOTES), so rather than guess
        at the precise pixel math, add a big invisible spacer right before
        every st.stop() in this block - cheap, safe insurance that there's
        always genuine extra scroll room past the real content, regardless
        of which branch above fired."""
        st.markdown('<div style="height:240px"></div>', unsafe_allow_html=True)
        st.stop()

    if _landing_choice == WATCH_LABEL:
        if not anglers_with_open_session_here:
            st.caption("No one has a session in progress at this spot right now - nothing to watch yet.")
            _stop_with_scroll_room()
        if len(anglers_with_open_session_here) > 1:
            _watch_target = st.selectbox(
                "Whose session?", anglers_with_open_session_here, key="spot_session_landing_watch_pick",
            )
        else:
            _watch_target = anglers_with_open_session_here[0]
        st.session_state[watch_key] = _watch_target
        st.query_params[watch_query_key] = "1"
        st.query_params[angler_query_key] = _watch_target
        st.rerun()

    elif _landing_choice == ANGLER_OTHER_LABEL:
        _typed = (st.text_input("Name", key="spot_session_landing_other_name") or "").strip()
        if _typed and _typed in anglers_with_open_session_here:
            st.warning(
                f"⚠️ \"{_typed}\" already has a session in progress here right now. If that's you "
                "reconnecting (a dropped connection, a locked phone), confirm below to pick it back up. "
                "If it's someone else fishing under that name, use a different name, or just watch instead."
            )
            if st.button(f"Yes, that's me - resume {_typed}'s session", key="spot_session_reclaim_confirm"):
                st.session_state[angler_key] = ANGLER_OTHER_LABEL
                st.session_state[angler_other_key] = _typed
                st.query_params[angler_query_key] = _typed
                st.rerun()
        elif _typed:
            st.session_state[angler_key] = ANGLER_OTHER_LABEL
            st.session_state[angler_other_key] = _typed
            st.query_params[angler_query_key] = _typed
            st.rerun()
        _stop_with_scroll_room()

    elif _landing_choice == LANDING_PROMPT:
        _stop_with_scroll_room()

    else:
        st.session_state[angler_key] = _landing_choice
        st.query_params[angler_query_key] = _landing_choice
        st.rerun()

if _watching_established:
    _watched = st.session_state.get(watch_key) or ""
    if not _watched or _watched not in anglers_with_open_session_here:
        if anglers_with_open_session_here:
            if len(anglers_with_open_session_here) > 1:
                _watched = st.selectbox(
                    "Whose session?", anglers_with_open_session_here, key="spot_session_watch_pick_active",
                )
            else:
                _watched = anglers_with_open_session_here[0]
            st.session_state[watch_key] = _watched
            st.query_params[angler_query_key] = _watched
        else:
            st.info("👀 No one has a session in progress at this spot right now.")
            if st.button("Stop watching", key="spot_session_stop_watching_empty"):
                st.session_state.pop(watch_key, None)
                st.query_params.pop(watch_query_key, None)
                st.query_params.pop(angler_query_key, None)
                st.rerun()
            st.stop()
    _render_watch_view(spot, structure_type, _watched)
    if st.button("Not watching anymore - let me pick a name and fish", key="spot_session_stop_watching"):
        st.session_state.pop(watch_key, None)
        st.query_params.pop(watch_query_key, None)
        st.query_params.pop(angler_query_key, None)
        st.rerun()
    st.stop()

# From here on, an identity is established (either just now, or already
# from before) - unchanged from before, except the option list now leaves
# out anyone else's already-active session (their own name stays selectable
# even while their own session is active, so ending/reconnecting to their
# own session still works normally).
angler_options = [
    a for a in angler_roster
    if a not in anglers_with_open_session_here or a == st.session_state.get(angler_key)
] + [ANGLER_OTHER_LABEL]
if st.session_state.get(angler_key) not in angler_options:
    # The previously-picked name now collides with someone else's session
    # that started since (rare - two browsers racing to pick the same
    # fresh name at the same spot within moments of each other) - fall back
    # to "Other" rather than crash the widget on a stored value that's no
    # longer a valid option.
    st.session_state[angler_key] = ANGLER_OTHER_LABEL
    st.session_state.setdefault(angler_other_key, "")
angler_choice = st.selectbox(
    "🎣 Who's fishing", angler_options, key=angler_key,
    help='Tags every trip you log with your name - Trip History can filter by angler, but '
         'everyone\'s trips stay combined in one shared log. Remembered for this browser '
         'session (and carried in the page link) so a reconnect brings you back as '
         'yourself; pick "Other" to add a new name to the list.',
)
angler_other_name = ""
if angler_choice == ANGLER_OTHER_LABEL:
    st.session_state.setdefault(angler_other_key, "")
    angler_other_name = st.text_input(
        "Name", key=angler_other_key,
        help="Saved as a new dropdown choice the next time you log a trip.",
    )
resolved_angler = angler_other_name.strip() if angler_choice == ANGLER_OTHER_LABEL else angler_choice

# Keep the URL in sync so a reconnect (a redeploy-triggered restart, a
# locked phone, a spotty-signal drop) restores this angler instead of
# ever falling back to a default - see the restore block above.
if resolved_angler:
    st.query_params[angler_query_key] = resolved_angler
elif angler_query_key in st.query_params:
    st.query_params.pop(angler_query_key, None)


def _save_new_angler_if_needed() -> bool:
    """Called right before a trip actually gets saved (Start Session / Save
    changes) - not at picker-render time - so idly typing into "Other"
    without ever logging anything doesn't itself trigger a git commit.
    Returns True if a genuinely new name was just added to the roster, so
    the caller knows to include data/anglers.csv in that same push."""
    if angler_choice == ANGLER_OTHER_LABEL and resolved_angler:
        return add_angler(resolved_angler)
    return False


# structure_type, _angler_session_slug() and _active_session_key() now live
# above, next to the angler picker (punch-list #59 needed them earlier than
# this point) - see the comment block up there for the full "why" behind
# per-angler session scoping.


st.session_state.setdefault(f"session_date_{spot['spot_id']}", lake_today())

session_date = st.date_input(
    "Session date",
    max_value=lake_today(),
    help="Defaults to today - pick an earlier date to log a past session at this spot. Pressure trend and "
         "solunar timing may fall back to their no-data defaults for dates outside the current forecast window.",
    key=f"session_date_{spot['spot_id']}",
)

try:
    bundle = get_weather_bundle(7)
except Exception:
    bundle = None
seg_ranges = segment_time_ranges(bundle, session_date)


def _segment_option_label(name: str) -> str:
    if seg_ranges and name in seg_ranges:
        s, e = seg_ranges[name]
        return f"{name} ({s.strftime('%-I:%M %p')}-{e.strftime('%-I:%M %p')})"
    return name


_wind_help = "\n".join(
    f"{label} ({lo:g}-{hi:g} mph): {detail}" if hi != float("inf") else f"{label} ({lo:g}+ mph): {detail}"
    for lo, hi, label, detail in WIND_BANDS
)

# All logged rows at this spot, any date - the base list for punch-list
# #69's date-independent "is there still an open session under this
# angler's name" reconnect check just below. todays_entries (the "already
# logged for this spot on <date>" caption right here, and the trip_date
# every NEW row gets stamped with) stays scoped to whatever the "Session
# date" widget shows, same as always - only the open-session lookup itself
# needed to stop caring which date a row landed on.
entries_at_spot = [t for t in read_all_trips() if t.get("spot_id") == spot["spot_id"]]
todays_entries = [t for t in entries_at_spot if t.get("trip_date") == session_date.isoformat()]
if todays_entries:
    summary_bits = [f"{t.get('lure_used') or 'unknown lure'} ({t.get('fish_caught') or 0} fish)" for t in todays_entries]
    st.caption(f"📋 Already logged for this spot on {session_date.isoformat()}: {', '.join(summary_bits)}")


# --- Weather-driven defaults for the consolidated conditions block ----------
def _weather_defaults(bundle, d, now) -> dict:
    """Best-effort live-forecast-driven defaults for the conditions block
    below, computed fresh every run (cheap - a plain list scan over one
    day's ~24 hourly rows). Any field it can't compute (no bundle, no
    hourly coverage for this date) is simply left out, so the conditions
    block falls back to its own hardcoded default for that one field via
    st.session_state.setdefault()."""
    defaults = {}
    if bundle is None:
        return defaults
    try:
        water_temp = estimate_water_temp_f(bundle, d, d.timetuple().tm_yday)
        if water_temp:
            defaults["water_temp_f"] = round(water_temp, 1)
    except Exception:
        pass
    rows = hourly_rows_for_date(bundle, d)
    if rows:
        nearest = min(rows, key=lambda r: abs((r["time"] - now).total_seconds()))
        if nearest.get("windspeed_10m") is not None:
            defaults["wind_band"] = wind_band(nearest["windspeed_10m"])["label"]
        if nearest.get("winddirection_10m") is not None:
            defaults["wind_direction"] = wind_direction_for_degrees(nearest["winddirection_10m"])
        if nearest.get("cloudcover") is not None:
            defaults["light_condition"] = light_condition_for_cloud_pct(nearest["cloudcover"])
        defaults["precipitation"] = precipitation_option_for_forecast(
            nearest.get("precipitation"), nearest.get("precipitation_probability"),
        )
    return defaults


def render_conditions_block(key_ns: str, weather_defaults: dict, prefill: dict = None):
    """The single consolidated "conditions" block - merges what used to be
    two separate sections ("Conditions right now" and "Conditions during
    this lure use") into one, per the angler's own redesign ask, with
    redundant fields (there used to be two separate Wind fields, and two
    separate forage-seen fields) shown just once each. Every
    weather-related field defaults from the live forecast
    (`weather_defaults`, see _weather_defaults() above) rather than a fixed
    literal, with the angler always free to override.

    `key_ns` namespaces every widget key so this same function can render a
    brand-new blank block (new session) or an edit-mode block seeded from
    an already-logged trip's data (`prefill`) without the two colliding.
    Each field is seeded via st.session_state.setdefault() - which only
    ever applies the FIRST time this exact key exists - so `prefill`/
    `weather_defaults` only ever set the initial value, never fight a
    manual override on a later rerun, the same pattern every other keyed
    widget on this page follows.

    Punch-list #98 follow-up: rebuilt as four flatter sub-cards (Water
    conditions / Environmental stain / Wind & atmosphere / Fish & forage
    activity) instead of one long list, per the angler's own reference-
    image ask - approved first as a standalone HTML mockup (see
    SESSION_NOTES.md) before any of this landed here. The four container
    keys are safe to reuse across this function's two call sites (a
    brand-new session vs. the mid-session "Conditions changed? Relocate"
    expander) because they only ever render from mutually exclusive
    if/else branches - never both in the same page load."""
    prefill = prefill or {}

    def _default(field, fallback):
        if field in prefill and prefill[field] not in (None, ""):
            return prefill[field]
        return weather_defaults.get(field, fallback)

    def _badge(label, value_html):
        st.markdown(
            f'<div class="ss-badge-label">{label}</div><div class="ss-badge">{value_html}</div>',
            unsafe_allow_html=True,
        )

    with st.container(key="spotsession_cond_water_card"):
        st.markdown('<div class="ss-card-head"><span class="ss-msym">water_drop</span>Water conditions</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        wt_key = f"{key_ns}_water_temp"
        st.session_state.setdefault(wt_key, _default("water_temp_f", 85.0))
        water_temp_f = c1.number_input(
            "Water temperature (°F)", min_value=32.0, max_value=100.0, step=0.5, key=wt_key,
        )
        sec_key = f"{key_ns}_secchi"
        st.session_state.setdefault(sec_key, _default("secchi_ft", 2.5))
        secchi_ft = c2.number_input(
            "Water visibility / Secchi depth (ft)", min_value=0.0, max_value=20.0, step=0.5,
            help="How far down you can see a light-colored object/lure. Estimate visually if you don't carry a Secchi disk.",
            key=sec_key,
        )
        temp_band = water_temp_band(water_temp_f)
        _badge("Metabolic state", f"<b>{temp_band['label']}</b> — {temp_band['detail']}")
        vis_band = visibility_band(secchi_ft)
        _badge("Visibility band", f"<b>{vis_band['label']}</b> — {vis_band['detail']}")

    with st.container(key="spotsession_cond_stain_card"):
        st.markdown('<div class="ss-card-head"><span class="ss-msym">invert_colors</span>Environmental stain</div>', unsafe_allow_html=True)
        stain_color = None
        if vis_band["label"] == "Stained":
            stain_key = f"{key_ns}_stain_color"
            st.session_state.setdefault(stain_key, _default("stain_color", STAIN_COLOR_OPTIONS[0]))
            stain_color = st.selectbox(
                "Stain color (Nolin normally runs greenish-brown, leaning brown)", STAIN_COLOR_OPTIONS,
                key=stain_key,
            )
        stirred_key = f"{key_ns}_stirred_up"
        st.session_state.setdefault(stirred_key, _default("stirred_up", False))
        stirred_up = st.checkbox(
            "Stirred up / muddy right now (recent wind or rain)",
            help="Overrides the reading above straight to Muddy, regardless of Secchi depth or stain color.",
            key=stirred_key,
        )

    with st.container(key="spotsession_cond_wind_card"):
        st.markdown('<div class="ss-card-head"><span class="ss-msym">air</span>Wind &amp; atmosphere</div>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        wind_key = f"{key_ns}_wind_band"
        st.session_state.setdefault(wind_key, _default("wind_band", WIND_BAND_LABELS[1]))
        wind_band_choice = c3.selectbox("Wind", WIND_BAND_LABELS, help=_wind_help, key=wind_key)
        wind_dir_key = f"{key_ns}_wind_dir"
        st.session_state.setdefault(wind_dir_key, _default("wind_direction", "SW"))
        wind_direction = c4.selectbox("Wind direction", WIND_DIRECTIONS, key=wind_dir_key)

        c5, c6 = st.columns(2)
        light_key = f"{key_ns}_light_condition"
        st.session_state.setdefault(light_key, _default("light_condition", LIGHT_CONDITIONS[2]))
        light_condition = c5.selectbox(
            "Sky conditions", LIGHT_CONDITIONS,
            help="\n".join(f"{k} ({v['range']}): {v['detail']}" for k, v in LIGHT_CONDITION_INFO.items()),
            key=light_key,
        )
        precip_key = f"{key_ns}_precipitation"
        st.session_state.setdefault(precip_key, _default("precipitation", PRECIPITATION_OPTIONS[0]))
        precipitation = c6.selectbox("Precipitation", PRECIPITATION_OPTIONS, key=precip_key)

    with st.container(key="spotsession_cond_activity_card"):
        st.markdown('<div class="ss-card-head"><span class="ss-msym">set_meal</span>Fish &amp; forage activity</div>', unsafe_allow_html=True)
        forage_key = f"{key_ns}_forage_seen"
        st.session_state.setdefault(forage_key, _default("forage_seen", []) or [])
        forage_seen = st.multiselect("Forage seen (optional)", FORAGE_OPTIONS, key=forage_key)

        c7, c8 = st.columns(2)
        fish_act_key = f"{key_ns}_fish_activity"
        st.session_state.setdefault(fish_act_key, _default("fish_activity", "Moderate"))
        fish_activity = c7.select_slider("Fish activity", options=FISH_ACTIVITY_OPTIONS, key=fish_act_key)
        forage_act_key = f"{key_ns}_forage_activity"
        st.session_state.setdefault(forage_act_key, _default("forage_activity", "Moderate"))
        forage_activity = c8.select_slider("Forage activity", options=FORAGE_ACTIVITY_OPTIONS, key=forage_act_key)

        depth_key = f"{key_ns}_fish_depth"
        st.session_state.setdefault(depth_key, _default("fish_depth_ft", 8.0))
        fish_depth_ft = st.number_input(
            "Depth fish are showing up on electronics (ft, optional)", min_value=0.0, max_value=100.0, step=1.0,
            key=depth_key,
        )

    return {
        "water_temp_f": water_temp_f, "secchi_ft": secchi_ft, "stain_color": stain_color,
        "stirred_up": stirred_up, "wind_band": wind_band_choice, "wind_direction": wind_direction,
        "light_condition": light_condition, "precipitation": precipitation,
        "forage_seen": forage_seen, "fish_activity": fish_activity, "forage_activity": forage_activity,
        "fish_depth_ft": fish_depth_ft or None,
    }


def _compute_scoring(cond_values: dict, session_date, bundle, at_time: datetime, segment_name: str, spot_id: str = None):
    """Shared scoring path for both a live setup preview (using "right now"
    as at_time/segment) and edit mode (using that trip's own logged time/
    segment) - one formula, one place, instead of the old page's separate
    "cond may or may not exist yet" branches.

    Every field is read with .get() + the same fallback this page's own
    Conditions form widgets default to elsewhere, rather than assuming
    cond_values is always fully populated. Punch-list #69: this is also now
    called (via the "🔄 Conditions changed?" mid-session panel) against a
    RECONSTRUCTED session's base_conditions - which, since that panel only
    ever asks about fish/forage activity, wind, and sky (punch-list #49),
    relies entirely on whatever the original Start Session actually saved
    for secchi_ft/water_temp_f/precipitation. A legacy row or one logged
    via "Log this session" without ever filling in Conditions (punch-list
    #42) can genuinely lack these - direct dict indexing here used to raise
    a bare KeyError and crash the whole page the moment such a session
    became reconnectable, instead of falling back the same way the live
    form's own widgets already do.

    Punch-list #81: `spot_id`, when given, looks up this spot's own
    (spot_id, segment_name) entry from core.appstate.get_location_
    adjustments() - how much this specific spot has historically over/
    under-performed at this specific time of day, relative to that same
    time of day everywhere else. Optional (defaults to None/no adjustment)
    since not every caller necessarily has a resolved spot yet."""
    secchi_ft = cond_values.get("secchi_ft", 2.5)
    water_temp_f = cond_values.get("water_temp_f", 85.0)
    light_condition = cond_values.get("light_condition") or LIGHT_CONDITIONS[2]
    wind_band_choice = cond_values.get("wind_band") or WIND_BAND_LABELS[1]
    precipitation = cond_values.get("precipitation") or PRECIPITATION_OPTIONS[0]
    water_clarity = resolve_water_clarity(
        secchi_ft, cond_values.get("stain_color"), cond_values.get("stirred_up", False),
    )
    season = season_stage(session_date.timetuple().tm_yday, water_temp_f)
    avg_cloud_pct = cloud_proxy_for_light_condition(light_condition)
    avg_wind_mph = wind_mph_for_band(wind_band_choice)
    total_precip_in, max_precip_prob_pct = precipitation_proxy(precipitation)
    rt = realtime_context_from_bundle(bundle, segment_name, session_date, at_time=at_time)
    loc_entry = get_location_adjustments().get((spot_id, segment_name)) if spot_id else None
    score_result = manual_segment_score(
        segment_name, season, avg_cloud_pct, avg_wind_mph, total_precip_in, max_precip_prob_pct,
        pressure_trend_24h=rt["pressure_trend_24h"], solunar_overlap=rt["solunar_overlap"], at_time=at_time,
        water_temp_f=water_temp_f, water_clarity=water_clarity,
        forage_present=bool(cond_values.get("forage_seen")),
        location_adjustment=loc_entry["adjustment"] if loc_entry else 0.0,
        location_adjustment_n=loc_entry["n"] if loc_entry else None,
    )
    return water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result


def _build_base_conditions(cond_values: dict, avg_cloud_pct, avg_wind_mph, rt, score_result, start_time, segment_name, angler: str = None):
    """Everything about the SESSION as a whole (not any one lure) that gets
    saved into every lure's TripEntry.conditions this session produces."""
    d = dict(cond_values)
    d.update({
        "avg_cloud_pct": avg_cloud_pct,
        "avg_wind_mph": avg_wind_mph,
        "pressure_trend_24h": rt["pressure_trend_24h"] if rt else None,
        "moon_near_new_full": score_result.moon.is_new_or_full_window if score_result else None,
        "moon_phase": score_result.moon.name if score_result else None,
        "start_time": start_time.isoformat() if start_time else None,
        "segment_name": segment_name,
        # Trip History's FIELD_SPECS still reads a separate "Wind (logged)"
        # column under its old name - both that and "Wind" above now just
        # show this same single reading, since the redesign merged what
        # used to be two separate Wind fields into one.
        "wind_band_logged": cond_values.get("wind_band"),
        # Punch-list #26: whichever name the "Who's fishing" picker was set
        # to when this session/edit was saved (core/anglers.py) - blank/None
        # for anything logged before that feature existed, same as every
        # other optional key in this dict.
        "angler": angler or None,
    })
    return d


LURE_PICKER_COLS = 4
LURE_PICKER_THUMBNAIL_PX = 90


def _visual_lure_picker(inventory_items: list, key_prefix: str, empty_message: str = None):
    """Searchable, single-select image-card picker over the tackle
    inventory (edit mode's "Lure used"/"Trailer" pickers). Returns the
    selected inventory row, or None if nothing's picked."""
    selected_key = f"{key_prefix}_selected_id"
    if not inventory_items:
        st.caption(
            empty_message or
            "No lures in your tackle box yet - add some on the Tackle Box page, "
            "or just type this one in below."
        )
        return None

    search = st.text_input(
        "Search", key=f"{key_prefix}_search",
        placeholder="Search your tackle box by brand or description...",
        label_visibility="collapsed",
    )
    filtered = inventory_items
    if search:
        s = search.lower()
        filtered = [
            it for it in filtered
            if s in (it.get("description") or "").lower() or s in (it.get("brand") or "").lower()
        ]

    if not filtered:
        st.caption("No matches for that search.")
    else:
        for row_start in range(0, len(filtered), LURE_PICKER_COLS):
            row_items = filtered[row_start:row_start + LURE_PICKER_COLS]
            cols = st.columns(LURE_PICKER_COLS)
            for col, item in zip(cols, row_items):
                with col:
                    with st.container(border=True):
                        if not render_square_thumbnail(item, size_px=LURE_PICKER_THUMBNAIL_PX):
                            st.caption("No photo")
                        st.caption(f"**{item.get('brand', '')}**  \n{item.get('description', '')}"[:90])
                        is_selected = item.get("item_id") == st.session_state.get(selected_key)
                        if st.button(
                            "✅ Selected" if is_selected else "Select",
                            key=f"{key_prefix}_pick_{item['item_id']}",
                            disabled=is_selected, width='stretch',
                        ):
                            st.session_state[selected_key] = item["item_id"]
                            st.rerun()

    current_id = st.session_state.get(selected_key)
    selected_item = next((it for it in inventory_items if it.get("item_id") == current_id), None)
    if selected_item is not None:
        cc1, cc2 = st.columns([5, 1])
        cc1.caption(f"Selected: **{inventory_item_label(selected_item)}**")
        if cc2.button("Clear", key=f"{key_prefix}_clear"):
            st.session_state[selected_key] = None
            st.rerun()
    return selected_item


# --- Pending-session draft persistence (punch-list #53) ---------------------
# Everything below Start Session (conditions form + picked lures, not yet
# saved anywhere) lived only in st.session_state, so it was the one thing
# punch-list #47/#51/#52 didn't already make durable - an ALREADY-STARTED
# session recovers from disk on reconnect (#47), and #52 made a reconnect a
# lot less frequent, but a session still being set up had nothing to
# recover FROM. Mirrors the exact "carry it in the URL" pattern already
# used for spot_id/edit_trip/angler above (see those for precedent) - one
# JSON blob under a single "draft" query param, since there's real
# structure here (a dozen-odd condition fields plus a list of picked
# lures/trailers) rather than one scalar value.
PENDING_DRAFT_QUERY_KEY = "draft"


def _load_pending_draft(spot_id: str) -> dict:
    """Parses ?draft=... back into {"spot_id", "seq", "cond", "lures"}.
    Returns {} on anything that doesn't check out - no param, invalid JSON,
    missing keys, or (most importantly) a draft that belongs to a
    DIFFERENT spot than the one this URL/page is currently on, e.g. after
    switching spots without ever hitting Start Session at the old one -
    never raises, since this is untrusted input coming from a URL."""
    raw = st.query_params.get(PENDING_DRAFT_QUERY_KEY)
    if not raw:
        return {}
    try:
        draft = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(draft, dict) or draft.get("spot_id") != spot_id:
        return {}
    if not {"seq", "cond", "lures"} <= draft.keys():
        return {}
    return draft


def _save_pending_draft(spot_id: str, seq: int, cond_values: dict, pending_lures: list):
    """Keeps ?draft=... in sync with the current pending build on every
    render, so a reconnect at ANY point - mid-conditions-form, with lures
    already picked, or both - restores exactly where things were left off
    instead of starting over blank."""
    blob = {"spot_id": spot_id, "seq": seq, "cond": cond_values, "lures": pending_lures}
    st.query_params[PENDING_DRAFT_QUERY_KEY] = json.dumps(blob, separators=(",", ":"))


def _clear_pending_draft():
    st.query_params.pop(PENDING_DRAFT_QUERY_KEY, None)


# --- Multi-lure selection for a NEW session ----------------------------------
def _pending_lures_key(spot_id: str, seq: int) -> str:
    return f"pending_session_lures_{spot_id}_{seq}"


def _tackle_box_expander_open_key(spot_id: str, seq: int) -> str:
    """Punch-list #87 follow-up #2: the angler watched a live reproduction
    of the add-3-lures sequence and pointed out the actual remaining
    annoyance - the popup itself DOES reopen correctly for every add (the
    len(pending_lures)-keyed widget fix from the first follow-up works),
    but "Add more lures" dumps you back onto a page where the "Add from
    tackle box" expander has silently collapsed back shut, so every single
    add after the first needs an extra manual click just to reopen it
    before you can even see the picker again - exactly backwards from the
    "add lure after lure with no extra navigation" the popup was built for.
    Root cause: st.expander's `expanded=` argument only sets its INITIAL
    state - a manual open/close toggle lives purely in the frontend and
    does not survive a script rerun (st.rerun(), which every add and every
    popup button here triggers), so without something re-asserting
    `expanded=True` on the next render, it snaps back to its default
    (False) every single time. This session_state flag is that something:
    set True the moment a lure actually lands in the pending list (see
    _handle_lure_add_click() and _trailer_dialog()'s own "Add lure"
    confirm, both of which cover the tackle-box picker, the manual-entry
    field, and quick-add - anything that can add a lure while building a
    NEW session), so the expander stays visibly open for the rest of this
    session build once the angler has used it at all. Scoped to
    (spot_id, seq), same as everything else here, so a fresh session_build_seq
    (a new build, after Start Session or Cancel) starts collapsed again."""
    return f"tackle_box_expander_open_{spot_id}_{seq}"


def _add_lure_to_pending(spot_id: str, seq: int, lure: dict):
    key = _pending_lures_key(spot_id, seq)
    pending = st.session_state.setdefault(key, [])
    if lure.get("item_id") is not None:
        if any(p.get("item_id") == lure["item_id"] for p in pending):
            return
    else:
        # Manual (not-in-inventory) entries have no item_id - dedupe by
        # label instead, so typing the exact same name twice doesn't add it
        # twice.
        if any(p.get("item_id") is None and p.get("label") == lure.get("label") for p in pending):
            return
    pending.append(lure)
    st.session_state[key] = pending


def _remove_lure_from_pending(spot_id: str, seq: int, index: int):
    key = _pending_lures_key(spot_id, seq)
    pending = st.session_state.get(key, [])
    if 0 <= index < len(pending):
        pending.pop(index)
        st.session_state[key] = pending


def _added_lure_item_ids(spot_id: str, seq: int, mode: str, angler: str = "") -> set:
    """Item ids already queued for this session - the pre-session "pending"
    list before Start Session, or the active session's currently-in-use
    (not yet retired) lures once one's running. Used to disable/relabel a
    picker card that's already been added. `angler` only matters for the
    "active" branch - the active session it looks up is scoped per angler
    (see _active_session_key() above)."""
    if mode == "pending":
        return {p.get("item_id") for p in st.session_state.get(_pending_lures_key(spot_id, seq), [])}
    active = st.session_state.get(_active_session_key(spot_id, angler))
    if not active:
        return set()
    return {l.get("item_id") for l in active["lures"] if not l.get("retired")}


def _trailer_dialog_lure_key(lure_stub: dict) -> str:
    """Stable id for a lure_stub's trailer-dialog widget keys - the same
    inventory item (or the same typed manual name) always maps to the same
    keys, so the dialog's checkbox/selection reflects what's actually been
    picked so far no matter how many times this exact "+ Add" click
    re-renders it while it's open (each click re-runs the whole script,
    and Streamlit only keeps a dialog open by re-satisfying the same
    opening condition every run - a monotonically-incrementing id here
    would hand the dialog a brand new, blank set of keys on every single
    one of those re-renders instead of remembering what was just entered)."""
    if lure_stub.get("item_id"):
        return lure_stub["item_id"]
    return f"manual_{abs(hash(lure_stub.get('label', '')))}"


def _handle_lure_add_click(spot_id: str, seq: int, lure_stub: dict, item_for_trailer_check, mode: str, angler: str = ""):
    """Common "+ Add" handler for a lure card, wherever it's clicked from
    (a recommendation's quick-add, the tackle-box grid, or a manual
    entry) - if that lure's category can take a trailer (or it's a manual
    entry, whose category is unknown), a popup asks about a trailer before
    it's actually added; otherwise it's added immediately, same as before.
    `mode` ("pending" before a session starts, "active" to add a lure
    mid-session) decides which list the lure - and its trailer pick, if
    any - eventually lands in. `angler` is only actually used for "active"
    mode (see _add_lure_to_active_session's own angler-scoping)."""
    if lure_can_take_trailer(item_for_trailer_check):
        _trailer_dialog(spot_id, seq, lure_stub, mode, angler)
    else:
        if mode == "pending":
            _add_lure_to_pending(spot_id, seq, lure_stub)
            # Punch-list #87: flag a one-shot "lure added" confirmation
            # popup for the very next render - see _lure_added_popup_key()/
            # _lure_added_dialog() and the trigger check right after
            # pending_lures is computed below. Only for "pending" mode -
            # there's no "start the session" action to offer once one's
            # already running.
            st.session_state[_lure_added_popup_key(spot_id, seq)] = True
            # Punch-list #87 follow-up #2: also keep the "Add from tackle
            # box" expander open from here on for this session build - see
            # _tackle_box_expander_open_key()'s own docstring for why this
            # is needed at all (st.expander forgets a manual open/close
            # toggle across every st.rerun()).
            st.session_state[_tackle_box_expander_open_key(spot_id, seq)] = True
        else:
            _add_lure_to_active_session(spot_id, lure_stub, angler)
        st.rerun()


@st.dialog("Add a trailer?")
def _trailer_dialog(spot_id: str, seq: int, lure_stub: dict, mode: str, angler: str = ""):
    dkey = _trailer_dialog_lure_key(lure_stub)
    if st.session_state.pop(f"trailer_dialog_reset_pending_{spot_id}_{dkey}", False):
        for k in (
            f"trailer_dialog_use_{spot_id}_{dkey}", f"trailer_dialog_pick_{spot_id}_{dkey}",
            f"trailer_dialog_manual_{spot_id}_{dkey}",
        ):
            st.session_state.pop(k, None)
    st.markdown(f"**{lure_stub['label']}**")
    use_trailer = st.checkbox("Used a trailer with this lure", key=f"trailer_dialog_use_{spot_id}_{dkey}")
    trailer = None
    if use_trailer:
        trailer_items = [it for it in get_inventory() if is_trailer_eligible(it)]
        options = ["Type it in manually"] + [inventory_item_label(it) for it in trailer_items]
        idx = st.selectbox(
            "Trailer", options=list(range(len(options))), format_func=lambda i: options[i],
            key=f"trailer_dialog_pick_{spot_id}_{dkey}",
        )
        if idx == 0:
            manual_trailer_name = st.text_input("Trailer name", key=f"trailer_dialog_manual_{spot_id}_{dkey}")
            if manual_trailer_name.strip():
                trailer = {"item_id": None, "label": manual_trailer_name.strip(), "category": None, "color": None}
        else:
            picked = trailer_items[idx - 1]
            trailer = {
                "item_id": picked.get("item_id"), "label": inventory_item_label(picked),
                "category": picked.get("category"), "color": picked.get("description", ""),
            }

    fc1, fc2 = st.columns(2)
    if fc1.button("Add lure", type="primary", width='stretch', key=f"trailer_dialog_confirm_{spot_id}_{dkey}"):
        final_lure = dict(lure_stub)
        final_lure["trailer"] = trailer
        if mode == "pending":
            _add_lure_to_pending(spot_id, seq, final_lure)
            # Punch-list #87 - see the matching comment in
            # _handle_lure_add_click()'s non-trailer branch above.
            st.session_state[_lure_added_popup_key(spot_id, seq)] = True
            # Punch-list #87 follow-up #2 - see the matching comment in
            # _handle_lure_add_click()'s non-trailer branch above.
            st.session_state[_tackle_box_expander_open_key(spot_id, seq)] = True
        else:
            _add_lure_to_active_session(spot_id, final_lure, angler)
        # Clears the checkbox/selection back to blank for the NEXT time this
        # exact lure's dialog is opened (e.g. re-adding it later in a future
        # session) - can't just pop the keys here, since they're already
        # instantiated widgets this run; deferred the same way every other
        # "reset before re-instantiation" case on this page is (see
        # session_build_seq_key's own comment for the general pattern).
        st.session_state[f"trailer_dialog_reset_pending_{spot_id}_{dkey}"] = True
        st.rerun()
    if fc2.button("Cancel", width='stretch', key=f"trailer_dialog_cancel_{spot_id}_{dkey}"):
        st.rerun()


def _multi_lure_picker(inventory_items: list, key_prefix: str, spot_id: str, seq: int, mode: str = "pending", angler: str = ""):
    """Multi-select sibling of _visual_lure_picker - same searchable card
    grid, but each card adds to the running "lures for this session" list
    (see _pending_lures_key, or the active session once one's started)
    instead of picking exactly one. Shows the whole tackle box, including
    trailer-eligible baits (craw/creature, paddle-tail swimbait-style; see
    core.lures.is_trailer_eligible) - punch-list #46: those baits are often
    fished on their own too (e.g. a Texas-rigged creature bait or a
    weightless soft plastic), not just attached to another lure via the
    trailer popup below, so they belong here as regular pickable lures.
    The trailer popup's own picker (_trailer_dialog) stays filtered to
    is_trailer_eligible() only - that's the "attach this to another lure"
    list, a separate concern from "what can I fish on its own"."""
    if not inventory_items:
        st.caption("No lures in your tackle box yet - add some on the Tackle Box page.")
        return
    search = st.text_input(
        "Search", key=f"{key_prefix}_search",
        placeholder="Search your tackle box by brand or description...",
        label_visibility="collapsed",
    )
    filtered = inventory_items
    if search:
        s = search.lower()
        filtered = [
            it for it in filtered
            if s in (it.get("description") or "").lower() or s in (it.get("brand") or "").lower()
        ]
    if not filtered:
        st.caption("No matches for that search.")
        return
    added_ids = _added_lure_item_ids(spot_id, seq, mode, angler)
    for row_start in range(0, len(filtered), LURE_PICKER_COLS):
        row_items = filtered[row_start:row_start + LURE_PICKER_COLS]
        cols = st.columns(LURE_PICKER_COLS)
        for col, item in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    if not render_square_thumbnail(item, size_px=LURE_PICKER_THUMBNAIL_PX):
                        st.caption("No photo")
                    st.caption(f"**{item.get('brand', '')}**  \n{item.get('description', '')}"[:90])
                    is_added = item.get("item_id") in added_ids
                    if st.button(
                        "✓ Added" if is_added else "+ Add", key=f"{key_prefix}_toggle_{item['item_id']}",
                        disabled=is_added, width='stretch',
                    ):
                        _handle_lure_add_click(spot_id, seq, {
                            "item_id": item["item_id"], "label": inventory_item_label(item),
                            "category": item.get("category"),
                        }, item, mode, angler)


def _render_recommendation_with_quick_add(
    rec, spot_id: str, seq: int, key_prefix: str, inventory: list = None, mode: str = "pending", angler: str = "",
):
    """Displays the CURATED lure recommendation (punch-list #82 -
    core.lures.curate_recommendation: top 3 owned lures ranked for today's
    situation, plus a separate "gaps" section for well-ranked lures not in
    the tackle box) with a "+ Add to session" button under each
    color-matched owned item, so a suggested lure can be added to this
    session with one click instead of having to go find it again in the
    tackle-box picker below. Gap lures never have owned_items (that's what
    makes them gaps), so they get no quick-add button - they're shown for
    awareness/shopping, not one-click session logging. Punch-list #46:
    blocks for a trailer-eligible category (see
    core.lures.TRAILER_ELIGIBLE_CATEGORIES) get a quick-add button too, same
    as any other category - those baits can be fished standalone, matching
    _multi_lure_picker below no longer excluding them either."""
    added_ids = _added_lure_item_ids(spot_id, seq, mode, angler)
    curated = curate_recommendation(rec, inventory)

    def _render_block_with_quick_add(block):
        render_lure_block(block)
        for item in block.owned_items:
            item_id = item.get("item_id")
            if not item_id:
                continue
            is_added = item_id in added_ids
            btn_label = "✓ Added to session" if is_added else f"+ Add {item.get('brand', '')} - {item.get('description', '')}"[:60]
            if st.button(btn_label, key=f"{key_prefix}_{block.key}_{item_id}", disabled=is_added):
                _handle_lure_add_click(spot_id, seq, {
                    "item_id": item_id, "label": inventory_item_label(item), "category": block.key,
                }, {"category": block.key}, mode, angler)

    if curated.recommended:
        st.markdown("**🎣 Top picks from your tackle box**")
        for block in curated.recommended:
            _render_block_with_quick_add(block)
    else:
        st.info(
            "Nothing in your tackle box is a strong fit for this exact situation yet - "
            "see the tackle box gaps below for what would rank well."
        )
    if curated.gaps:
        with st.expander(f"🧰 Tackle box gaps worth a look ({len(curated.gaps)})", expanded=False):
            st.caption(
                "Not in your tackle box today, but ranked among the best-fit lures for this exact "
                "situation - real alternatives worth considering, not a generic shopping list."
            )
            for block in curated.gaps:
                render_lure_block(block)
    if rec.rationale:
        st.caption(" · ".join(rec.rationale))


# --- Per-fish entry (used by both the active-session dialog and edit mode) --
def _weight_input(key_prefix: str) -> float:
    """Punch-list #86: plain lb/oz dropdowns (core.activity_log.
    WEIGHT_LB_OPTIONS/WEIGHT_OZ_OPTIONS) replacing the old 1-oz-increment
    select_slider (+ manual text fields) from punch-list #31 - angler
    feedback was that the slider was too sensitive to drag precisely on a
    phone. A selectbox opens a native OS picker wheel instead (tap once,
    scroll, tap again), which is both faster and far less fiddly to aim
    than dragging a slider handle. Defaults to 0 lb 8 oz (0.5 lb) - the
    same starting point the old slider's own default position
    represented, so a fish left untouched here still gets a sane
    placeholder rather than truly zero.

    Punch-list #90: `filter_mode=None` on both dropdowns - a plain
    `st.selectbox` always renders a "type to search" text box at the top
    of its option list (its default `filter_mode="fuzzy"`), and on a
    phone, tapping that box to open the dropdown focuses that hidden text
    field too, popping the on-screen keyboard - which then covers the
    option list right below it, exactly the reported "keyboard blocks the
    dropdown, can't get to it to pick" symptom. `filter_mode=None`
    disables that search box entirely (per Streamlit's own docs: "typing
    is disabled and the options are not filtered"), leaving a pure
    tap-to-open/tap-to-pick list with no text input to steal focus - a
    real fix, not a workaround, and it's exactly the "not a manual key-in
    field" the angler asked for. Needs Streamlit's `filter_mode` selectbox
    parameter (confirmed present in 1.63.0, the version this sandbox
    installs from this repo's own `streamlit>=1.36` pin - not otherwise
    version-gated here, since this app has never pinned an exact upper
    version and Streamlit Cloud installs whatever's current at deploy
    time)."""
    lb_key = f"{key_prefix}_lb"
    oz_key = f"{key_prefix}_oz"
    lcol, ocol = st.columns(2)
    lb_choice = lcol.selectbox(
        "Weight - lb", WEIGHT_LB_OPTIONS, index=0, key=lb_key,
        format_func=lambda v: f"{v} lb",
        filter_mode=None,
    )
    oz_choice = ocol.selectbox(
        "oz", WEIGHT_OZ_OPTIONS, index=8, key=oz_key,
        format_func=lambda v: f"{v} oz",
        filter_mode=None,
    )
    return weight_lb_for_dropdown(lb_choice, oz_choice)


def _length_input(key_prefix: str) -> float:
    """Punch-list #86: a single length dropdown (core.activity_log.
    LENGTH_OPTIONS) replacing the old whole-inch select_slider (+ manual
    field) from punch-list #31. Since every new fish gets a fresh widget
    key (a blank form for the next catch), the old slider's own default
    position - its lowest bucket, "<13 in" (12.0 in) - meant every single
    fish had to be manually re-adjusted from a 12"-equivalent starting
    point every time, reported as "the length always reverts to 12.""
    Defaults to 12 in here too (an angler's own explicit preference, and
    the single most common size range at this lake) - the difference is
    that changing it is now one dropdown tap instead of a fiddly drag.

    Punch-list #90: `filter_mode=None` here too - see `_weight_input()`'s
    docstring above for why (disables the hidden "type to search" text
    box that was popping a phone's on-screen keyboard over the option
    list)."""
    length_key = f"{key_prefix}_len"
    choice = st.selectbox(
        "Length (in)", LENGTH_OPTIONS, index=LENGTH_OPTIONS.index(12), key=length_key,
        format_func=lambda v: "Under 12 in" if v == "<12" else ("26+ in" if v == "26+" else f"{v} in"),
        filter_mode=None,
    )
    return length_in_for_dropdown(choice)


def _new_fish_from_form(species_label, species_other, weight_lb, length_in, hit_types, retrieve_style, retrieve_speed) -> dict:
    species_final = (
        species_other.strip() if (species_label == "Other (type in species)" and species_other.strip())
        else species_label
    )
    return {
        "species": species_final,
        "species_other": species_other or None,
        "count": 1,
        "weight_lb": weight_lb or None,
        "length_in": length_in or None,
        "hit_types": hit_types,
        "retrieve_speed": retrieve_speed,
        "retrieve_style": retrieve_style,
        # Punch-list #32: the real moment this catch record was saved (same
        # lake_now_naive().time().isoformat() convention as
        # lure_start_time/lure_end_time above), so Trip History's per-fish
        # detail can show when each fish in a session was actually caught,
        # not just the session's own overall start/end time. Older rows
        # logged before this existed simply have no "caught_at" key -
        # display code below treats that the same as every other optional
        # per-fish field.
        "caught_at": lake_now_naive().time().isoformat(),
    }


def _format_fish_time(iso_time_str) -> str:
    """"08:15:32.123456" -> "8:15 AM" - same %-I:%M %p convention this page
    already uses for time-window ranges (_segment_option_label). Returns
    None (not shown) for a blank/unparseable value, e.g. a fish record
    logged before punch-list #32 added "caught_at"."""
    try:
        return dtime.fromisoformat(iso_time_str).strftime("%-I:%M %p")
    except (TypeError, ValueError):
        return None


def _fish_summary_bits(fish: dict) -> list:
    count = fish.get("count") or 1
    bits = [f"{count} x {fish['species']}" if count > 1 else (fish.get("species") or "Unknown species")]
    caught_at_label = _format_fish_time(fish.get("caught_at"))
    if caught_at_label:
        bits.append(caught_at_label)
    if fish.get("weight_lb"):
        bits.append(format_weight_lb_oz(fish["weight_lb"]))
    if fish.get("length_in"):
        bits.append(f"{fish['length_in']:g} in")
    if fish.get("hit_types"):
        bits.append(", ".join(fish["hit_types"]))
    presentation = " / ".join(x for x in [fish.get("retrieve_speed"), fish.get("retrieve_style")] if x)
    if presentation:
        bits.append(presentation)
    return bits


# --- Push-health tracking + autosave retry (punch-list #58) -----------------
# The angler's own report: a save happens (every fish/lure/etc. already
# writes to data/trip_log.csv and pushes immediately - see each handler
# below), but if that push doesn't land on GitHub for any reason, the row
# only exists on THIS process's local disk. That's invisible and harmless
# right up until the process itself restarts (a real code deploy, or - the
# suspected cause of the actual incident this was built for - a resource-
# limit restart on Streamlit Community Cloud with no code push involved at
# all) - at which point the fresh process's data/ is whatever the "data"
# branch last had, silently dropping anything that was only ever
# committed-not-pushed in the now-dead process. core.storage's retry/backoff
# (punch-list #58) makes any ONE push attempt considerably more resilient to
# a flaky connection, but that alone still leaves a gap: a push that fails
# even after those retries (GITHUB_TOKEN briefly bad, a longer outage) just
# sits there unpushed with nothing else ever trying again - until the very
# next real save happens to succeed and carries it along for free (a `git
# push` always sends everything HEAD is ahead by, not just the newest
# commit). If a while passes with no new save (thinking, watching a bobber,
# between spots) and the process dies in that window, it's gone regardless
# of how good the retry-per-attempt logic is.
#
# _PUSH_HEALTH_KEY tracks whether the LAST push attempt actually succeeded,
# independent of which action triggered it. Whenever it's failing, the
# "session in progress" view below shows a persistent (not a toast that can
# be missed) warning with a manual retry button, AND a background
# st.fragment(run_every=...) heartbeat (see _autosave_heartbeat() below)
# keeps quietly retrying on its own every 30s the tab stays open and
# connected - belt (visible + actionable) and suspenders (automatic),
# exactly what was asked for. This closes the gap for as long as the
# process itself survives; it can't do anything about data that was only
# ever local to a process that's already gone - the real fix for that is
# making each individual push attempt (and the retries around it) as
# resilient as reasonably possible, which is what core.storage's own
# punch-list #58 changes are for.
_PUSH_HEALTH_KEY = "_push_health"


def _push_health() -> dict:
    return st.session_state.setdefault(
        _PUSH_HEALTH_KEY, {"ok": True, "message": "", "consecutive_failures": 0},
    )


def _record_push_result(ok: bool, message: str):
    health = _push_health()
    if ok:
        health["ok"] = True
        health["consecutive_failures"] = 0
        health["message"] = ""
    else:
        health["ok"] = False
        health["consecutive_failures"] = health.get("consecutive_failures", 0) + 1
        health["message"] = message
    st.session_state[_PUSH_HEALTH_KEY] = health


def _push_or_toast(paths, commit_message, local_message):
    if TRIP_LOG_PATH in paths:
        # Punch-list #61: get_trip_history()/get_calibrated_weights() are a
        # separate 5-minute st.cache_data cache (core/appstate.py) that
        # Leaderboard, 7-Day Forecast, and this page's own two
        # lure-recommendation panels all read through - unlike every OTHER
        # cached getter in this app (get_lake_spots, get_inventory,
        # get_dev_tasks), it was never cleared after a write, so a catch
        # logged just now wouldn't show up anywhere that reads through
        # those for up to 5 more minutes. Cleared unconditionally here -
        # regardless of whether the push itself below succeeds - since the
        # write to local disk (append_trip()/update_trip(), already done by
        # the caller before this runs) is what actually changed, not the
        # push. One choke point for every trip-log write this page makes,
        # rather than a clear() call repeated at each of the 7 call sites.
        get_trip_history.clear()
        get_calibrated_weights.clear()
        get_location_adjustments.clear()
    token = github_token()
    if token:
        ok, msg = commit_and_push_data(paths, token, repo_slug(), commit_message)
        _record_push_result(ok, msg)
        st.toast(msg, icon="✅" if ok else "⚠️")
    else:
        # No token at all isn't a "failing push" in the retry-worthy sense -
        # there's nothing to retry until one's configured - so this
        # deliberately doesn't touch push health/trigger the warning banner.
        st.toast(local_message, icon="ℹ️")


def _retry_pending_push(show_toast: bool = True) -> bool:
    """Manual/heartbeat retry of whatever's already committed locally but
    hasn't reached GitHub yet - see the block comment above. Safe to call
    any time, including when nothing's actually pending (push_pending_data
    is a harmless no-op then) - so both the manual "🔁 Retry save now"
    button and the automatic heartbeat can call this unconditionally
    without first checking whether there's really something to retry."""
    token = github_token()
    if not token:
        return False
    ok, msg = push_pending_data(token, repo_slug())
    _record_push_result(ok, msg)
    if show_toast:
        st.toast(msg, icon="✅" if ok else "⚠️")
    return ok


def _render_push_health_banner():
    """Persistent (not a toast - those can be missed, especially mid-cast)
    warning shown right at the top of an in-progress session whenever the
    last push attempt failed, with a manual retry button. Silent/renders
    nothing when the last push succeeded or none has happened yet."""
    health = _push_health()
    if health.get("ok", True):
        return
    n = health.get("consecutive_failures", 1)
    st.warning(
        f"⚠️ The last {n} save{'s' if n != 1 else ''} couldn't reach GitHub yet "
        f"(saved on this device, just not backed up there) - {health.get('message', '')}. "
        "Everything you log keeps working normally, and this keeps retrying automatically "
        "every 30 seconds while this page stays open - tap below to retry right now instead."
    )
    if st.button("🔁 Retry save now", key="retry_pending_push_btn"):
        if _retry_pending_push():
            st.rerun()


@st.fragment(run_every=30)
def _autosave_heartbeat():
    """Punch-list #58: a periodic, no-interaction-required retry of any
    currently-unpushed save, running independently of whatever the angler
    is doing on the rest of the page - the "even if I don't touch anything
    for a while" half of the autosave ask. st.fragment(run_every=30) means
    this one small block re-executes on its own every 30 seconds the
    browser tab stays open and connected, without rerunning (or blocking)
    the rest of the page. Only actually does anything when the last known
    push attempt failed - otherwise push_pending_data() is a cheap no-op
    ("Everything up-to-date"), so this doesn't hammer GitHub every 30
    seconds during a session where every save has been landing fine."""
    if not _push_health().get("ok", True):
        _retry_pending_push(show_toast=False)


def _record_fish(spot_id: str, lure_index: int, fish_record: dict, angler: str = ""):
    """Appends one fish to the given lure's running catch list, immediately
    saving that lure's TripEntry (via update_trip) and pushing - per the
    angler's own ask, each catch is saved right away rather than batched
    until the session ends."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None or lure_index >= len(active["lures"]):
        return
    lure = active["lures"][lure_index]
    lure["fish"].append(fish_record)
    entry_kwargs = dict(lure["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["fish"] = lure["fish"]
    entry_kwargs["conditions"] = conditions
    fish_weights = [f["weight_lb"] for f in lure["fish"] if f.get("weight_lb")]
    entry_kwargs["fish_caught"] = sum((f.get("count") or 1) for f in lure["fish"])
    entry_kwargs["biggest_fish_lb"] = max(fish_weights) if fish_weights else None
    entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
    update_trip(entry)
    lure["entry_kwargs"] = entry_kwargs
    active["lures"][lure_index] = lure
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Log a fish on {lure['label']} ({active.get('spot_name', spot_id)})",
        "Fish logged locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


def _remove_fish(spot_id: str, lure_index: int, fish_index: int, angler: str = ""):
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None or lure_index >= len(active["lures"]):
        return
    lure = active["lures"][lure_index]
    if not (0 <= fish_index < len(lure["fish"])):
        return
    lure["fish"].pop(fish_index)
    entry_kwargs = dict(lure["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["fish"] = lure["fish"]
    entry_kwargs["conditions"] = conditions
    fish_weights = [f["weight_lb"] for f in lure["fish"] if f.get("weight_lb")]
    entry_kwargs["fish_caught"] = sum((f.get("count") or 1) for f in lure["fish"])
    entry_kwargs["biggest_fish_lb"] = max(fish_weights) if fish_weights else None
    entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
    update_trip(entry)
    lure["entry_kwargs"] = entry_kwargs
    active["lures"][lure_index] = lure
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Remove a fish from {lure['label']} ({active.get('spot_name', spot_id)})",
        "Removed locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


def _add_lure_to_active_session(spot_id: str, lure_stub: dict, angler: str = ""):
    """Adds one more lure to an already-running session - the same "switch
    rods any time" ability as picking lures before Start Session, just
    writing a brand-new TripEntry row (its own lure_start_time = right
    now) instead of queuing into the pre-session pending list, using this
    session's own conditions snapshot (active["base_conditions"]) for
    everything about the SESSION as a whole. That snapshot is captured once
    at Start Session and normally reused unchanged for every lure added
    after - EXCEPT fish activity/forage activity/wind/sky, which the
    "🔄 Conditions changed? Get updated suggestions" panel (punch-list #49,
    extended by #93 to also allow relocating mid-session) can update
    mid-session; if the angler has tapped "Update conditions" there, this
    picks up whatever was most recently saved, not necessarily what was
    true at Start Session. Water clarity/temp/depth are never touched
    mid-session except by that same panel, so absent a mid-session update
    those always stay what they were at the start.

    `spot_id` here is ONLY used to look up `_active_session_key()` (the
    session_state key stays anchored to wherever Start Session happened,
    per punch-list #93's design) - it is NOT necessarily where this lure
    is actually being fished right now. The row this function writes uses
    `active["spot_id"]` (the session's CURRENT location, which
    `_relocate_active_session()` updates on a mid-session location change),
    falling back to the passed-in `spot_id` only for older reconstructed
    sessions that predate that field."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return
    if lure_stub.get("item_id") is not None:
        # Dedupe against currently-ACTIVE (not retired) lures only - picking
        # the same lure back up after retiring it earlier in this same
        # session is allowed and expected (an angler genuinely does switch
        # back and forth), so a past retirement shouldn't block re-adding it.
        if any(not l.get("retired") and l.get("item_id") == lure_stub["item_id"] for l in active["lures"]):
            return
    start_time = lake_now_naive().time()
    trailer = lure_stub.get("trailer")
    lure_conditions = dict(active["base_conditions"])
    lure_conditions.update({
        "lure_category": lure_stub.get("category"),
        "trailer_used": trailer is not None,
        "trailer_name": trailer.get("label") if trailer else None,
        "trailer_color": trailer.get("color") if trailer else None,
        "trailer_category": trailer.get("category") if trailer else None,
        "lure_start_time": start_time.isoformat(),
        "lure_end_time": None,
        "fish": [],
        "source": "spot_session",
    })
    entry_kwargs = dict(
        trip_date=active["session_date"],
        segment=active["segment_name"],
        spot_id=active.get("spot_id") or spot_id,
        spot_name=active["spot_name"],
        structure_type=active["structure_type"],
        water_clarity=active["water_clarity"],
        lure_used=lure_stub["label"],
        color_used="",
        technique_used="",
        fish_caught=0,
        biggest_fish_lb=None,
        predicted_score=active.get("predicted_score"),
        conditions=lure_conditions,
        notes="",
        session_id=active.get("session_id", ""),
    )
    entry = TripEntry(**entry_kwargs)
    append_trip(entry)
    active["lures"].append({
        "trip_id": entry.trip_id, "logged_at": entry.logged_at, "label": lure_stub["label"],
        "item_id": lure_stub.get("item_id"), "entry_kwargs": entry_kwargs, "fish": [], "retired": False,
    })
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Add {lure_stub['label']} to active session ({active.get('spot_name', spot_id)})",
        "Lure added locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


def _retire_lure(spot_id: str, lure_index: int, angler: str = ""):
    """"🔄 Change" - stops active use of one lure mid-session without
    ending the whole session: stamps its own lure_end_time right now
    (same field Start Session leaves blank and End Session would otherwise
    fill in later) and marks it retired so it drops out of the active
    button list, while the rest of the session (and any other lure still
    in play) keeps going."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None or lure_index >= len(active["lures"]):
        return
    lure = active["lures"][lure_index]
    if lure.get("retired"):
        return
    end_time = lake_now_naive().time()
    entry_kwargs = dict(lure["entry_kwargs"])
    conditions = dict(entry_kwargs["conditions"])
    conditions["lure_end_time"] = end_time.isoformat()
    entry_kwargs["conditions"] = conditions
    entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
    update_trip(entry)
    lure["entry_kwargs"] = entry_kwargs
    lure["retired"] = True
    active["lures"][lure_index] = lure
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH], f"Retire {lure['label']} from active session ({active.get('spot_name', spot_id)})",
        "Retired locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )


def _relocate_active_session(
    spot_id: str, angler: str, new_spot: dict, new_cond_values: dict, session_date, bundle,
):
    """Punch-list #93, the angler's own explicit ask: change BOTH the
    conditions AND the fishing location mid-session, without ending the
    session or having to re-add any lure already in play. `spot_id` is the
    page-level spot used only to look up `_active_session_key()` (that key
    stays anchored to wherever Start Session happened for the rest of this
    browser session - see that function's own docstring); `new_spot` is
    the spot row the angler picked in the mid-session panel, which may or
    may not be the same spot this page itself is showing.

    Rather than overwriting active["base_conditions"] in place (which is
    all the original punch-list #49 panel did, and which would silently
    retro-apply the new location/conditions to fish already caught under
    the old ones), every currently-active (non-retired) lure is "split":
    its existing TripEntry row is end-stamped and closed out exactly like
    _retire_lure() does, and a brand-new continuation row is appended
    carrying the same lure/trailer identity forward, under the new
    spot_id/conditions and a fresh lure_start_time. Fish already logged
    stay on the OLD (now-closed, now-retired) row exactly as they were;
    any fish landed on that same lure from this point on land on the NEW
    row instead. Both rows - and every other row this session ever
    writes - share the one session_id, so this is still a single session
    to Trip History, just one that has now touched more than one location
    and/or condition set. Retired lures from before this call are left
    completely alone - there's nothing to split for a lure that's already
    out of play.

    Returns the list of lure labels that were carried forward (empty list
    if nothing was active to move), or None if there's no active session
    to relocate."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return None
    now = lake_now_naive()
    segment_name = _guess_segment(now.hour, now)
    new_structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(new_spot.get("location_type"), "Main-lake point")
    water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
        new_cond_values, session_date, bundle, now, segment_name, spot_id=new_spot["spot_id"],
    )
    # Preserve the session's ORIGINAL start_time (Start Session's own clock
    # reading, or whatever an earlier relocation already carried forward) -
    # a relocation changes location/conditions, not when the session itself
    # began.
    original_start_time = None
    _start_iso = (active.get("base_conditions") or {}).get("start_time")
    if _start_iso:
        try:
            original_start_time = dtime.fromisoformat(_start_iso)
        except ValueError:
            original_start_time = None
    new_base_conditions = _build_base_conditions(
        new_cond_values, avg_cloud_pct, avg_wind_mph, rt, score_result,
        original_start_time, segment_name, angler=angler,
    )
    end_time = now.time()
    moved_labels = []
    for lure in list(active["lures"]):
        if lure.get("retired"):
            continue
        # Close out the OLD row - same fields _retire_lure() stamps, just
        # inlined here so the close-out and its continuation row land in
        # the same pass. Any fish already logged on lure["fish"] are never
        # touched - they stay associated with this now-closed row's
        # location/conditions, per the angler's own ask.
        old_entry_kwargs = dict(lure["entry_kwargs"])
        old_conditions = dict(old_entry_kwargs["conditions"])
        old_conditions["lure_end_time"] = end_time.isoformat()
        old_entry_kwargs["conditions"] = old_conditions
        old_entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **old_entry_kwargs)
        update_trip(old_entry)
        lure["entry_kwargs"] = old_entry_kwargs
        lure["retired"] = True

        # New continuation row - same lure/trailer identity carried
        # forward untouched, fresh lure_start_time, empty fish list, under
        # the new spot + conditions.
        new_lure_conditions = dict(new_base_conditions)
        new_lure_conditions.update({
            "lure_category": old_conditions.get("lure_category"),
            "trailer_used": old_conditions.get("trailer_used", False),
            "trailer_name": old_conditions.get("trailer_name"),
            "trailer_color": old_conditions.get("trailer_color"),
            "trailer_category": old_conditions.get("trailer_category"),
            "lure_start_time": end_time.isoformat(),
            "lure_end_time": None,
            "fish": [],
            "source": "spot_session",
        })
        new_entry_kwargs = dict(
            trip_date=active["session_date"],
            segment=segment_name,
            spot_id=new_spot["spot_id"],
            spot_name=new_spot["name"],
            structure_type=new_structure_type,
            water_clarity=water_clarity,
            lure_used=old_entry_kwargs["lure_used"],
            color_used=old_entry_kwargs.get("color_used", ""),
            technique_used=old_entry_kwargs.get("technique_used", ""),
            fish_caught=0,
            biggest_fish_lb=None,
            predicted_score=score_result.score if score_result else None,
            conditions=new_lure_conditions,
            notes="",
            session_id=active.get("session_id", ""),
        )
        new_entry = TripEntry(**new_entry_kwargs)
        append_trip(new_entry)
        active["lures"].append({
            "trip_id": new_entry.trip_id, "logged_at": new_entry.logged_at, "label": lure["label"],
            "item_id": lure.get("item_id"), "entry_kwargs": new_entry_kwargs, "fish": [], "retired": False,
        })
        moved_labels.append(lure["label"])

    active["spot_id"] = new_spot["spot_id"]
    active["spot_name"] = new_spot["name"]
    active["structure_type"] = new_structure_type
    active["water_clarity"] = water_clarity
    active["base_conditions"] = new_base_conditions
    active["predicted_score"] = score_result.score if score_result else None
    # Punch-list #94: kept in session_state only (never written to
    # trip_log.csv - predicted_score itself is the only piece of this
    # that's ever persisted there) purely so the "Session in progress"
    # caption's own "ℹ️ How this score was derived" popover has something
    # to show without recomputing anything. Lost on a reconnect the same
    # way every other in-memory-only `active` field is - see
    # _reconstruct_active_session()'s own docstring - which just means
    # that popover quietly won't appear until the next relocate/update;
    # no worse than before this existed.
    active["predicted_score_breakdown"] = score_result.breakdown if score_result else []
    active["segment_name"] = segment_name
    st.session_state[active_key] = active
    _push_or_toast(
        [TRIP_LOG_PATH],
        f"Update conditions/location for active session ({new_spot['name']}, {len(moved_labels)} lure(s) carried over)",
        "Saved locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )
    return moved_labels


@st.dialog("Log a fish")
def _fish_entry_dialog(spot_id: str, lure_index: int, angler: str = ""):
    active = st.session_state.get(_active_session_key(spot_id, angler))
    if active is None or lure_index >= len(active["lures"]):
        st.error("This session has ended.")
        return
    lure = active["lures"][lure_index]
    st.markdown(f"**{lure['label']}**")

    dseq_key = f"fish_dialog_seq_{spot_id}_{lure_index}"
    st.session_state.setdefault(dseq_key, 0)
    dseq = st.session_state[dseq_key]

    species_idx = st.selectbox(
        "Species", options=list(range(len(FISH_SPECIES_OPTIONS))), format_func=lambda j: FISH_SPECIES_OPTIONS[j],
        key=f"fish_species_{spot_id}_{lure_index}_{dseq}",
    )
    species_label = FISH_SPECIES_OPTIONS[species_idx]
    species_other = ""
    if species_label == "Other (type in species)":
        species_other = st.text_input("Species (type it in)", key=f"fish_species_other_{spot_id}_{lure_index}_{dseq}")

    weight_lb_value = _weight_input(f"fish_weight_{spot_id}_{lure_index}_{dseq}")
    length_in_value = _length_input(f"fish_length_{spot_id}_{lure_index}_{dseq}")
    # Punch-list #33: st.pills instead of st.multiselect - a multiselect's
    # option list opens in a floating dropdown that, on a phone, was
    # reported to cut off the last option ("Surface hit") with no way to
    # scroll down to it. Pills render all options as always-visible,
    # directly tappable chips (wrapping onto a second line on a narrow
    # screen instead of hiding anything behind a popover), which sidesteps
    # that failure mode entirely rather than trying to patch the dropdown's
    # scroll behavior. selection_mode="multi" keeps the same "pick any
    # number of these" behavior and still returns a plain list, so nothing
    # downstream (_new_fish_from_form, the ", ".join(...) display bit)
    # needed to change.
    hit_types = st.pills(
        "Type of hit", HIT_TYPE_OPTIONS, selection_mode="multi",
        key=f"fish_hit_types_{spot_id}_{lure_index}_{dseq}",
    )

    rc1, rc2 = st.columns(2)
    retrieve_style = rc1.selectbox("Retrieve style", RETRIEVE_STYLE_OPTIONS, key=f"fish_retrieve_style_{spot_id}_{lure_index}_{dseq}")
    retrieve_speed = rc2.selectbox("Retrieve speed", RETRIEVE_SPEED_OPTIONS, index=1, key=f"fish_retrieve_speed_{spot_id}_{lure_index}_{dseq}")

    fc1, fc2 = st.columns(2)
    if fc1.button("✅ Record", type="primary", width='stretch', key=f"fish_record_{spot_id}_{lure_index}_{dseq}"):
        fish_record = _new_fish_from_form(
            species_label, species_other, weight_lb_value, length_in_value, hit_types, retrieve_style, retrieve_speed,
        )
        _record_fish(spot_id, lure_index, fish_record, angler)
        st.session_state[dseq_key] = dseq + 1
        st.rerun()
    if fc2.button("Cancel", width='stretch', key=f"fish_cancel_{spot_id}_{lure_index}_{dseq}"):
        st.rerun()


def _end_session(spot_id: str, angler: str = ""):
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return
    end_time = lake_now_naive().time()
    for lure in active["lures"]:
        entry_kwargs = dict(lure["entry_kwargs"])
        conditions = dict(entry_kwargs["conditions"])
        # Punch-list #34: "session_end_time" is stamped on EVERY lure in the
        # session (retired or not) - the one moment "⏹ End Session" was
        # actually clicked, so Trip History can show a real session-level
        # end time no matter which lure a trip row belongs to. This is
        # deliberately separate from "lure_end_time", which stays whatever
        # it already was for a retired lure (see below) - a lure retired
        # early via "🔄 Change" mid-session has its own, earlier, real
        # lure_end_time, while every lure's session_end_time is this same
        # single "the whole session closed at X" value.
        conditions["session_end_time"] = end_time.isoformat()
        if not lure.get("retired"):
            # Already stamped its own (earlier, real) lure_end_time when it
            # was retired via "🔄 Change" - don't overwrite that with the
            # session's own end time now.
            conditions["lure_end_time"] = end_time.isoformat()
        entry_kwargs["conditions"] = conditions
        entry = TripEntry(trip_id=lure["trip_id"], logged_at=lure["logged_at"], **entry_kwargs)
        update_trip(entry)
    _push_or_toast(
        [TRIP_LOG_PATH], f"End spot session ({active.get('spot_name', spot_id)})",
        "Session ended locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )
    st.session_state.pop(active_key, None)
    st.session_state["session_action_banner"] = {"kind": "closed", "spot_name": active.get("spot_name", spot_id)}


def _reset_builder_to_scratch(spot_id: str):
    """Punch-list #65: after a REAL cancel (called only from the success
    path of _cancel_session() below, never the silent-failure one), wipe
    every trace of the canceled session's own setup - not just its
    active_session_* record - so the page genuinely looks like a fresh
    visit, per the angler's own ask: "It really should completely reset
    the page like I am starting from scratch." Deliberately different from
    "⏹ End Session" (which keeps angler/location on purpose - you're still
    you, still standing at the same spot, about to log another real
    session there right after) - "❌ Cancel Session" exists specifically
    for "that was a mistake or a test, let me start over," so this clears:
    - the picked angler identity, back to the "who's fishing" landing
      picker (and the "Other" name text box under it),
    - the picked location, back to "— choose a saved spot —",
    - the pending builder's picked lure(s) and conditions inputs, by
      retiring this spot's session_build_seq - the same mechanism
      ▶ Start Session already uses to make ITS next builder blank (see
      session_build_seq_key's own comment) - so the next render's
      pending-lures/conditions widget keys are brand new and unseeded
      rather than reusing whatever was mid-build when Cancel was tapped.
    Query params are popped too, not just session_state - they're what
    survives a reconnect/page reload, so leaving them would silently
    re-establish the very identity/location this is trying to clear."""
    st.session_state.pop(angler_key, None)
    st.session_state.pop(angler_other_key, None)
    st.session_state.pop("spot_session_target_id", None)
    st.query_params.pop(angler_query_key, None)
    st.query_params.pop("spot_id", None)
    seq_key = f"session_build_seq_{spot_id}"
    st.session_state[seq_key] = st.session_state.get(seq_key, 0) + 1
    _clear_pending_draft()


def _cancel_session(spot_id: str, angler: str = "") -> bool:
    """"❌ Cancel Session" (punch-list #32) - discards an in-progress session
    entirely, rather than finalizing it like "⏹ End Session" does: deletes
    every trip_log.csv row this session created (delete_trip(), the same
    row-removal primitive Trip History's own "🗑️ Delete this trip" uses)
    and drops this angler's own active session key (see
    _active_session_key(), punch-list #47) from session_state, leaving no
    trace of the session behind. For testing sessions, or wanting a clean
    restart at this spot without keeping anything logged so far. Every row
    to delete comes from active["lures"] (in-memory, not a fresh disk
    read), so this only ever touches rows THIS session itself created -
    it can't reach into some other, unrelated angler's session data.

    Punch-list #64: returns True/False now (used to return None always) -
    live testing on the deployed app found "Yes, cancel it" reproducibly
    needing TWO clicks to actually take effect: the first click quietly
    landed on this `if active is None: return` early-out (session_state's
    active_key had gone missing by the time this ran, even though the
    confirm dialog for it was on screen a moment earlier) and reset the UI
    straight back to the un-confirmed "❌ Cancel Session" button with no
    error and no trace anything had gone wrong - indistinguishable from a
    successful cancel unless you happened to notice the lure was still
    there. The exact cause of active_key going missing between rendering
    the confirm dialog and handling its own button click is still open
    (see SESSION_NOTES.md punch-list #64) - this doesn't fix that root
    cause, but it stops the failure from being silent, which is what
    actually made it look like a mystery."""
    active_key = _active_session_key(spot_id, angler)
    active = st.session_state.get(active_key)
    if active is None:
        return False
    trip_ids = [lure["trip_id"] for lure in active["lures"]]
    for trip_id in trip_ids:
        delete_trip(trip_id)
    _push_or_toast(
        [TRIP_LOG_PATH],
        f"Cancel spot session ({active.get('spot_name', spot_id)}) - discard {len(trip_ids)} row(s)",
        "Session canceled locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )
    st.session_state.pop(active_key, None)
    # Punch-list #65: a page-wide banner key now (see the block right after
    # the GitHub connection status near the top of this file), not one
    # keyed by spot_id and checked only after a spot is re-established -
    # _reset_builder_to_scratch() below clears the picked location too, so
    # a per-spot-keyed check further down the page would never be reached
    # (the "no spot selected yet" screen calls st.stop() first).
    st.session_state["session_action_banner"] = {"kind": "canceled", "spot_name": active.get("spot_name", spot_id)}
    _reset_builder_to_scratch(spot_id)
    return True


def _confirm_cancel_session(spot: dict, cancel_pending_key: str, angler: str):
    """on_click callback for the Cancel Session confirm dialog's "Yes,
    cancel it" button (punch-list #66, third pass). Both earlier attempts at
    this confirm dialog - a plain st.button() (first pass) and
    st.form()/st.form_submit_button() (second pass) - reproducibly needed
    TWO taps to register the very first click: the button's return value,
    checked inline in the script run that (might) follow the click, came
    back False on that first tap even though the click visibly registered
    (the button showed its pressed state) - live-reproduced again this
    round on a completely fresh session (Northwest Channel Point/Alex),
    disproving the form fix. `on_click=` is Streamlit's own documented
    mechanism for exactly this class of bug: the callback runs as part of
    handling the click event itself, before the next script rerun even
    starts, rather than something the page has to notice by re-reading a
    widget's value afterward. No st.rerun() here - Streamlit already
    reruns the script once automatically after any widget callback."""
    st.session_state.pop(cancel_pending_key, None)
    # Punch-list #64: _cancel_session() returns True/False so a genuine
    # no-op (e.g. active_key already gone from session_state) is visible
    # via the "cancel_failed" banner instead of looking identical to a
    # real cancel.
    if not _cancel_session(spot["spot_id"], angler):
        st.session_state["session_action_banner"] = {"kind": "cancel_failed", "spot_name": spot["name"]}


def _keep_session(cancel_pending_key: str):
    """on_click callback for the Cancel Session confirm dialog's "Keep
    session" button - see _confirm_cancel_session()'s docstring for why
    this uses on_click instead of an inline return-value check."""
    st.session_state.pop(cancel_pending_key, None)


def _start_pending_session(
    spot: dict, cond_values: dict, session_date, bundle, structure_type: str, resolved_angler: str,
    pending_lures: list, session_build_seq: int, session_build_seq_key: str, active_session_key: str,
):
    """The actual "▶ Start Session" flow - locks in the exact time/score/
    conditions snapshot, writes one trip_log row per queued lure, and
    stashes the new active-session dict in session_state. Extracted out of
    the inline button handler it used to be (punch-list #87) so both the
    real "▶ Start Session" button below AND the new post-add confirmation
    popup's own "Start Session" option (_lure_added_dialog()) can trigger
    the exact same flow instead of duplicating it."""
    start_time = lake_now_naive().time()
    at_time = datetime.combine(session_date, start_time)
    segment_name = _guess_segment(at_time.hour, at_time)
    water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
        cond_values, session_date, bundle, at_time, segment_name, spot_id=spot["spot_id"],
    )
    base_conditions = _build_base_conditions(cond_values, avg_cloud_pct, avg_wind_mph, rt, score_result, start_time, segment_name, angler=resolved_angler)
    # Punch-list #55: a real session_id, stamped once here and reused by
    # every lure this session ever writes (including ones added later
    # via _add_lure_to_active_session()) - lets Trip History group every
    # lure/fish from one outing into a single record. Rows written
    # before this existed have no session_id; Trip History treats those
    # as their own single-lure "session" rather than guessing at
    # grouping from date/spot/timestamp proximity (see that page's own
    # docstring for why).
    session_id = str(uuid.uuid4())[:8]

    active_lures = []
    for lure in pending_lures:
        trailer = lure.get("trailer")
        lure_conditions = dict(base_conditions)
        lure_conditions.update({
            "lure_category": lure.get("category"),
            "trailer_used": trailer is not None,
            "trailer_name": trailer.get("label") if trailer else None,
            "trailer_color": trailer.get("color") if trailer else None,
            "trailer_category": trailer.get("category") if trailer else None,
            "lure_start_time": start_time.isoformat(),
            "lure_end_time": None,
            "fish": [],
            "source": "spot_session",
        })
        entry_kwargs = dict(
            trip_date=session_date.isoformat(),
            segment=segment_name,
            spot_id=spot["spot_id"],
            spot_name=spot["name"],
            structure_type=structure_type,
            water_clarity=water_clarity,
            lure_used=lure["label"],
            color_used="",
            technique_used="",
            fish_caught=0,
            biggest_fish_lb=None,
            predicted_score=score_result.score,
            conditions=lure_conditions,
            notes="",
            session_id=session_id,
        )
        entry = TripEntry(**entry_kwargs)
        append_trip(entry)
        active_lures.append({
            "trip_id": entry.trip_id, "logged_at": entry.logged_at, "label": lure["label"],
            "item_id": lure.get("item_id"), "entry_kwargs": entry_kwargs, "fish": [], "retired": False,
        })

    st.session_state[active_session_key] = {
        # Punch-list #93: the session's own CURRENT location - starts equal
        # to the page you started it on, but can move to a different
        # spot_id via _relocate_active_session() below without touching
        # this active_session_{spot_id}_{angler} session_state KEY itself
        # (which stays anchored to wherever Start Session happened for the
        # rest of this browser session - see that function's own docstring).
        "spot_id": spot["spot_id"],
        "spot_name": spot["name"],
        "session_date": session_date.isoformat(),
        "start_time": start_time.isoformat(),
        "segment_name": segment_name,
        "structure_type": structure_type,
        "water_clarity": water_clarity,
        "predicted_score": score_result.score,
        # Punch-list #94: session_state-only, feeds the "Session in
        # progress" caption's "ℹ️ How this score was derived" popover -
        # see _relocate_active_session()'s own comment on this same field
        # for why it's never written to trip_log.csv.
        "predicted_score_breakdown": score_result.breakdown,
        # Reused unchanged by _add_lure_to_active_session() for every lure
        # added after Start Session - UNLESS the angler applies a
        # mid-session location/conditions update (punch-list #93,
        # _relocate_active_session() below), which replaces these in place.
        "base_conditions": base_conditions,
        "lures": active_lures,
        "session_id": session_id,
    }
    st.session_state[session_build_seq_key] = session_build_seq + 1
    # Punch-list #53: this build is no longer "pending" - it's active
    # and durably saved to disk/data branch below, so the draft that
    # was only ever a stand-in for that isn't needed anymore. Leaving
    # it would also risk a stale seq lingering in the URL indefinitely.
    _clear_pending_draft()
    _push_paths = [TRIP_LOG_PATH]
    if _save_new_angler_if_needed():
        _push_paths.append(ANGLERS_PATH)
    _push_or_toast(
        _push_paths, f"Start spot session ({spot['name']}, {len(active_lures)} lure(s))",
        "Session started locally. No GITHUB_TOKEN configured in Streamlit secrets, so this won't survive an app restart.",
    )
    st.rerun()


def _lure_added_popup_key(spot_id: str, seq: int) -> str:
    return f"show_lure_added_popup_{spot_id}_{seq}"


@st.dialog("Lure added")
def _lure_added_dialog(
    spot: dict, cond_values: dict, session_date, bundle, structure_type: str, resolved_angler: str,
    pending_lures: list, session_build_seq: int, session_build_seq_key: str, active_session_key: str,
):
    """Punch-list #87, the angler's own direct ask: "each lure I add to the
    session should be followed by a pop up that shows what lure have been
    added so far and an option to either add more lures or start the
    session." Opened once per add (see _lure_added_popup_key() - set right
    after a lure actually lands in the pending list, whether that happened
    through the plain "+ Add" path or the trailer dialog's own "Add lure"
    button) rather than leaving the angler to scroll down to the
    always-visible "Lures for this session" list to confirm the add
    actually took. Only ever shown while building a NEW session (mode ==
    "pending") - there's no "start the session" action once one's already
    running, so adding a lure mid-session (_add_lure_to_active_session)
    deliberately does not trigger this."""
    st.success(f"Added! {len(pending_lures)} lure{'s' if len(pending_lures) != 1 else ''} queued for this session so far:")
    for lure in pending_lures:
        trailer = lure.get("trailer")
        trailer_bit = f" + {trailer['label']} trailer" if trailer else ""
        st.write(f"🎣 {lure['label']}{trailer_bit}")
    # Punch-list #87 follow-up: the widget keys below include len(pending_lures)
    # - real, live-app feedback was that after adding 2 lures, tapping "Add
    # more lures" a second time stopped working ("doesn't toggle to let me
    # add more"). Every earlier build of this popup keyed these two buttons
    # only by (spot_id, session_build_seq) - constant across every reopening
    # of this same dialog within one session build, so the SECOND (and every
    # later) time this exact popup opens, its buttons carry the exact same
    # key as the FIRST time. That reuse worked fine under this app's own
    # AppTest harness (which doesn't model real Streamlit's dialog-widget
    # bookkeeping closely enough to catch this), but apparently doesn't
    # survive a real browser session reopening the same st.dialog with
    # identical keys more than once. len(pending_lures) increases by
    # exactly 1 every time this popup opens (it only ever opens right after
    # an add), so folding it into the key gives every single occurrence of
    # this popup - the 1st, 2nd, 3rd, ... - a genuinely fresh, never-before-
    # seen widget key, which is the standard fix for this class of Streamlit
    # dialog quirk.
    _popup_key_suffix = f"{spot['spot_id']}_{session_build_seq}_{len(pending_lures)}"
    dc1, dc2 = st.columns(2)
    if dc1.button("➕ Add more lures", width='stretch', key=f"lure_added_popup_more_{_popup_key_suffix}"):
        # Explicitly closes the popup - see the trigger check's own comment
        # for why this can't just rely on the flag having already been
        # "consumed": the flag is deliberately NOT popped there (a plain
        # pop-on-render would close this dialog the instant IT renders,
        # before either of its own buttons ever gets a chance to be
        # clicked - the dialog function has to be reachable again on every
        # rerun ITS OWN widgets trigger, same as _trailer_dialog above).
        st.session_state.pop(_lure_added_popup_key(spot["spot_id"], session_build_seq), None)
        st.rerun()
    if dc2.button(
        "▶ Start Session", type="primary", width='stretch',
        key=f"lure_added_popup_start_{_popup_key_suffix}",
    ):
        _start_pending_session(
            spot, cond_values, session_date, bundle, structure_type, resolved_angler,
            pending_lures, session_build_seq, session_build_seq_key, active_session_key,
        )


# _PER_LURE_CONDITION_KEYS, _open_session_rows(), _other_anglers_with_open_
# session() and _reconstruct_active_session() now live up near the angler
# picker (punch-list #59 needed them earlier than this point, to check for
# already-active sessions before the picker renders) - see the comment
# block up there for the full "why" behind reconstruct-on-reconnect
# (originally punch-list #29).

# ==============================================================================
# NORMAL MODE - either a session is already in progress at this spot, or the
# angler is setting one up (conditions -> lure selection -> Start Session).
# ==============================================================================
active_session_key = _active_session_key(spot["spot_id"], resolved_angler)
active = st.session_state.get(active_session_key)

if active is None:
    # Punch-list #29 - see the block comment above _reconstruct_active_session()
    # for the full story. Reuses entries_at_spot (already read above for the
    # "Already logged for this spot" caption's own todays_entries) rather
    # than a second read_all_trips() call. Punch-list #47: scoped to
    # resolved_angler, so this only ever reconnects THIS angler's own
    # still-open session at this spot, never someone else's - see
    # _open_session_rows()'s own docstring. Punch-list #69: deliberately
    # NOT scoped to session_date.isoformat() (the "Session date" widget,
    # which defaults to today) - an open session from an earlier date needs
    # to be found here too, or it becomes permanently unreachable the
    # moment that widget isn't pointed at the exact day it started.
    active = _reconstruct_active_session(spot, structure_type, entries_at_spot, resolved_angler)
    if active is not None:
        st.session_state[active_session_key] = active

# Punch-list #47: surfaced whether building a new session or already inside
# one, so it's never a surprise that someone else is independently fishing
# this same spot right now - each angler's own session (start/add-lure/log
# fish/end/cancel) is fully independent of everyone else's.
_other_open_anglers = _other_anglers_with_open_session(
    spot["spot_id"], entries_at_spot, resolved_angler,
)
if _other_open_anglers:
    st.caption(
        f"🎣 {', '.join(_other_open_anglers)} also "
        f"{'has' if len(_other_open_anglers) == 1 else 'have'} an active session here - "
        "starting, ending, or canceling your own session never affects theirs."
    )

if active is not None:
    st.divider()
    # Punch-list #66: computed up here (used below by the autosave-heartbeat
    # guard) instead of down by "❌ Cancel Session" itself, so both places
    # reference the exact same key without recomputing the f-string twice.
    cancel_pending_key = f"cancel_session_confirm_{spot['spot_id']}"
    _session_angler = (active.get("base_conditions") or {}).get("angler") or resolved_angler
    with st.container(key="spotsession_active_card"):
        st.header(f"🎣 Session in progress{f' - {_session_angler}' if _session_angler else ''}")
        if active.pop("reconstructed", False):
            st.info(
                "Reconnected - picked this session back up from what was already saved "
                "(nothing was lost, but double-check the fish list below matches what you've logged)."
            )
            st.session_state[active_session_key] = active
        score_bit = f" · predicted score {active['predicted_score']}/10" if active.get("predicted_score") is not None else ""
        # Punch-list #93: a session can now be relocated mid-session (see the
        # "🔄 Conditions changed?" panel below), so its CURRENT location can
        # differ from spot["name"] (the page this session happens to be viewed
        # from) - surfaced here explicitly rather than leaving the angler to
        # infer it only from the page header above.
        _current_spot_name = active.get("spot_name") or spot["name"]
        st.caption(
            f"Started {active['start_time']} · currently at 📍 {_current_spot_name} · {active['segment_name']} · "
            f"{active['water_clarity']} water{score_bit}"
        )
        # Punch-list #94: only present for a session that hasn't needed
        # _reconstruct_active_session() to rebuild it from disk since its
        # score was last set (Start Session, or a #93 relocate/conditions
        # update) - see "predicted_score_breakdown"'s own comment above.
        render_score_breakdown(
            active.get("predicted_score_breakdown") or [], active.get("predicted_score"),
            key=f"active_session_score_breakdown_{spot['spot_id']}",
        )
        st.caption("Tap a lure below every time you land a fish on it. \"🔄 Change\" retires a lure without ending the session.")

        # Punch-list #58: persistent save-health warning + silent 30s background
        # retry heartbeat - see the block comment above _push_or_toast() for the
        # full "why". Rendered/started once here, right under the session
        # header, so it's visible no matter how far down the angler has
        # scrolled to tap a lure or open "Add a lure to this session."
        #
        # Punch-list #66: skipped entirely while this spot's Cancel Session
        # confirm ("Yes, cancel it" / "Keep session") is on screen. Live
        # reproduction of punch-list #64's still-open "first click on 'Yes,
        # cancel it' silently does nothing" bug found that the failure was
        # NOT _cancel_session() returning False (that path sets a visible
        # "cancel_failed" banner - punch-list #64/#65 - and the banner never
        # appeared in any failing repro). The button's own `if ccol1.button(...)`
        # block wasn't running at all on the failing click - nothing it does
        # (delete_trip, the push, either banner) ever started. This page is
        # the ONLY one in the app using st.fragment(run_every=...) (this one,
        # plus _render_watch_view()'s 20s tick for spectators) - every other
        # page's identical two-step confirm (e.g. Trip History's "🗑️ Delete
        # this trip") has never had this reported. A background fragment's own
        # periodic rerun landing at the same moment as a click on an unrelated
        # button is a known source of that click being silently dropped rather
        # than processed on the next full script run - plausible here given
        # the timing (tap "❌ Cancel Session", read the warning, tap "Yes,
        # cancel it" a few seconds later lines up with this heartbeat's 30s
        # cadence) and given no other page pairs a fragment with a confirm-
        # click flow. Not calling the fragment at all while the confirm buttons
        # are the only thing the angler can act on removes that window - it
        # already skips its own work most ticks anyway (see its docstring), so
        # pausing it for the few seconds a "are you sure" prompt is up costs
        # nothing. Unproven as THE root cause (see SESSION_NOTES.md punch-list
        # #66), but a real candidate worth eliminating rather than another
        # diagnostic-only pass.
        _render_push_health_banner()
        if not st.session_state.get(cancel_pending_key):
            _autosave_heartbeat()

        retired_lures = []
        for i, lure in enumerate(active["lures"]):
            if lure.get("retired"):
                retired_lures.append((i, lure))
                continue
            fish_count = sum((f.get("count") or 1) for f in lure["fish"])
            label = f"🎣 {lure['label']}" + (f" ({fish_count} caught)" if fish_count else "")
            lcol1, lcol2 = st.columns([4, 1])
            if lcol1.button(label, key=f"open_fish_dialog_{spot['spot_id']}_{i}", width='stretch'):
                _fish_entry_dialog(spot["spot_id"], i, resolved_angler)
            if lcol2.button("🔄 Change", key=f"retire_lure_{spot['spot_id']}_{i}", width='stretch'):
                _retire_lure(spot["spot_id"], i, resolved_angler)
                st.rerun()
            if lure["fish"]:
                with st.expander(f"Fish caught on {lure['label']} ({fish_count})", expanded=False):
                    for fi, fish in enumerate(lure["fish"]):
                        frow1, frow2 = st.columns([5, 1])
                        frow1.write(f"- {', '.join(str(b) for b in _fish_summary_bits(fish))}")
                        if frow2.button("Remove", key=f"remove_active_fish_{spot['spot_id']}_{i}_{fi}"):
                            _remove_fish(spot["spot_id"], i, fi, resolved_angler)
                            st.rerun()

        if retired_lures:
            with st.expander(f"Retired lures ({len(retired_lures)})", expanded=False):
                for i, lure in retired_lures:
                    fish_count = sum((f.get("count") or 1) for f in lure["fish"])
                    start = lure["entry_kwargs"]["conditions"].get("lure_start_time") or "?"
                    end = lure["entry_kwargs"]["conditions"].get("lure_end_time") or "?"
                    # Punch-list #93: a retired lure's own row now records
                    # whichever spot was current when it was fished, which can
                    # legitimately differ from other lures' rows in the same
                    # session once a mid-session relocation happens.
                    _lure_spot = lure["entry_kwargs"].get("spot_name") or spot["name"]
                    st.caption(f"{lure['label']} @ 📍 {_lure_spot} - {fish_count} fish - {start} to {end}")

    st.divider()
    # Punch-list #49 (extended by #93 - the angler's own explicit ask:
    # "modify this so that I can change both the conditions and location
    # without ending the session or having to re enter any lures that I am
    # using"): moved to a different spot, or conditions shifted mid-session -
    # adjust either or both here and preview fresh lure suggestions (and
    # why) right away. Unlike a plain preview, tapping "Update conditions &
    # location" is a real write: it closes out (end-stamps + retires) every
    # currently-active lure's existing row and opens a brand-new
    # continuation row for that same lure under the new spot/conditions
    # (see _relocate_active_session()'s own docstring for the full "why") -
    # so fish already logged stay attributed to the location/conditions
    # that were true when they were caught, while any fish landed from this
    # point on land on the new row. No lure needs to be re-picked; the same
    # session_id carries through the whole thing.
    #
    # Punch-list #56: the score updates live as soon as a condition changes,
    # but the lure suggestion cards below it are tucked into their OWN
    # nested, collapsed-by-default expander - most of the time an angler
    # opens this panel just to nudge a reading and re-check the score, and
    # doesn't want a full recommendation list (with per-lure "why" text)
    # shoving that out of view every time. The update button itself stays
    # OUTSIDE that nested expander, directly under the score.
    with st.expander("🔄 Conditions changed? Relocate or get updated suggestions", expanded=False):
        st.caption(
            "Moved to a different spot, or conditions shifted mid-session? Adjust either (or both) below, then "
            "tap \"Update conditions & location\" to apply them. Every lure currently in play carries forward "
            "automatically - you never need to re-pick a lure you're already using - while fish already logged "
            "stay right where they were caught."
        )
        mc_ns = f"midsession_{spot['spot_id']}_{_angler_session_slug(resolved_angler)}"
        mc_base = active.get("base_conditions") or {}
        current_relocate_spot_id = active.get("spot_id") or spot["spot_id"]

        mc_spot_default_idx = next(
            (i for i, s in enumerate(sorted_spots) if s["spot_id"] == current_relocate_spot_id), 0,
        )
        mc_spot_key = f"{mc_ns}_spot_idx"
        st.session_state.setdefault(mc_spot_key, mc_spot_default_idx)
        mc_spot_idx = st.selectbox(
            "📍 Location", options=range(len(sorted_spots)), format_func=lambda i: sorted_spots[i]["name"],
            key=mc_spot_key,
        )
        mid_spot = sorted_spots[mc_spot_idx]
        mid_structure_type = LOCATION_TYPE_TO_STRUCTURE_TYPE.get(mid_spot.get("location_type"), "Main-lake point")
        if mid_spot["spot_id"] != current_relocate_spot_id:
            st.caption(f"📍 This session will move to **{mid_spot['name']}** ({mid_structure_type}) once you tap Update below.")

        mid_weather_defaults = _weather_defaults(bundle, session_date, lake_now_naive())
        mid_cond = render_conditions_block(mc_ns, mid_weather_defaults, prefill=mc_base)

        _mid_now = lake_now_naive()
        _mid_segment = _guess_segment(_mid_now.hour, _mid_now)
        mid_water_clarity, mid_season, mid_avg_cloud_pct, mid_avg_wind_mph, mid_rt, mid_score_result = _compute_scoring(
            mid_cond, session_date, bundle, _mid_now, _mid_segment, spot_id=mid_spot["spot_id"],
        )

        st.divider()
        mm1, mm2 = st.columns([1, 2])
        with mm1:
            st.metric(f"{_mid_segment} activity score", f"{mid_score_result.score}/10")
            render_score_breakdown(mid_score_result.breakdown, mid_score_result.score, key=f"{mc_ns}_score_breakdown")
        mm2.write(
            f"**Season:** {mid_season.replace('_', ' ').title()}  \n"
            f"**Structure:** {mid_structure_type}  \n"
            f"**Water clarity:** {mid_water_clarity}"
        )
        if mid_score_result.notes:
            st.caption(" · ".join(mid_score_result.notes))
        for warn in mid_score_result.warnings:
            st.warning(warn)

        mid_inventory = get_inventory()
        mid_rec = recommend(
            # Punch-list #69: mid_cond.get("water_temp_f", 85.0) - not just
            # .get("water_temp_f") - for the same reason _compute_scoring()
            # above now defaults it: a reconstructed session's base_conditions
            # can genuinely lack this (a legacy row, or one logged via "Log
            # this session" without ever filling in Conditions - punch-list
            # #42), and recommend() does an unguarded `<= 68` comparison on
            # it that crashes outright on None.
            mid_season, mid_cond.get("water_temp_f", 85.0), _mid_segment, mid_rt["pressure_trend_24h"],
            structure_type=mid_structure_type, water_clarity=mid_water_clarity,
            fish_depth_ft=mid_cond.get("fish_depth_ft"), forage=mid_cond.get("forage_seen"),
            inventory=mid_inventory, trip_history=get_trip_history(), spot_id=mid_spot["spot_id"],
            fish_activity=mid_cond.get("fish_activity"), forage_activity=mid_cond.get("forage_activity"),
            wind_mph=wind_mph_for_band(mid_cond.get("wind_band")),
        )
        with st.expander("🎣 See updated lure suggestions", expanded=False):
            render_lure_recommendation(mid_rec, inventory=mid_inventory)

        if st.button(
            "🔄 Update conditions & location", key=f"{mc_ns}_apply", type="primary",
            help=(
                "Closes out every lure currently in play and re-opens it fresh under these readings/location - "
                "fish already logged keep the original location/conditions; you don't need to re-add any lure."
            ),
        ):
            moved = _relocate_active_session(
                spot["spot_id"], resolved_angler, mid_spot, mid_cond, session_date, bundle,
            )
            if moved is not None:
                # Punch-list #93: st.rerun() right after this - like "🔄
                # Change" already does - so the "Session in progress"
                # caption, the lure list, and the "Retired lures" expander
                # all immediately reflect the new location/conditions
                # rather than lagging a click behind. A plain st.success()
                # here would never survive that rerun (its output belongs
                # to the run being thrown away); st.toast() is what
                # _push_or_toast() itself already uses for exactly this
                # reason, and does survive it.
                if mid_spot["spot_id"] != current_relocate_spot_id:
                    st.toast(
                        f"Moved to {mid_spot['name']} with updated conditions - {len(moved)} lure(s) carried "
                        "forward. Fish already logged stay attributed to the original location/conditions.",
                        icon="📍",
                    )
                else:
                    st.toast(
                        f"Conditions updated - {len(moved)} lure(s) carried forward under the new readings.",
                        icon="🔄",
                    )
                st.rerun()

    st.divider()
    with st.expander("➕ Add a lure to this session"):
        inventory_items = get_inventory()
        _multi_lure_picker(
            inventory_items, key_prefix=f"active_lure_picker_{spot['spot_id']}",
            spot_id=spot["spot_id"], seq=0, mode="active", angler=resolved_angler,
        )
        st.markdown("**Not in your inventory?**")
        active_manual_seq_key = f"active_manual_lure_seq_{spot['spot_id']}"
        st.session_state.setdefault(active_manual_seq_key, 0)
        active_manual_seq = st.session_state[active_manual_seq_key]
        amc1, amc2 = st.columns([4, 1])
        active_manual_name = amc1.text_input(
            "Lure name", key=f"active_manual_lure_name_{spot['spot_id']}_{active_manual_seq}",
            label_visibility="collapsed", placeholder="Type a lure name to add it manually",
        )
        if amc2.button("+ Add", key=f"active_manual_lure_add_{spot['spot_id']}_{active_manual_seq}"):
            if active_manual_name.strip():
                st.session_state[active_manual_seq_key] = active_manual_seq + 1
                _handle_lure_add_click(
                    spot["spot_id"], 0, {"item_id": None, "label": active_manual_name.strip(), "category": None},
                    None, "active", resolved_angler,
                )

    st.divider()
    escol1, escol2 = st.columns(2)
    if escol1.button("⏹ End Session", key=f"end_session_{spot['spot_id']}", type="primary", width='stretch'):
        _end_session(spot["spot_id"], resolved_angler)
        st.rerun()

    # "❌ Cancel Session" (punch-list #32) - discards the whole in-progress
    # session instead of finalizing it, for testing sessions or wanting a
    # clean restart without keeping anything logged. This permanently
    # deletes every trip_log.csv row the session created with no undo, so
    # it gets the same two-step "are you sure" confirm Trip History's own
    # "🗑️ Delete this trip" uses, rather than acting on the first click.
    # (cancel_pending_key itself is defined up where "Session in progress"
    # is first rendered - punch-list #66 - so the autosave-heartbeat guard
    # up there can see it too.)
    if not st.session_state.get(cancel_pending_key):
        if escol2.button("❌ Cancel Session", key=f"cancel_session_{spot['spot_id']}", width='stretch'):
            st.session_state[cancel_pending_key] = True
            st.rerun()
    else:
        _cancel_fish_count = sum(
            (f.get("count") or 1) for lure in active["lures"] for f in lure["fish"]
        )
        st.warning(
            f"Cancel this session? This permanently discards everything logged so far - "
            f"{len(active['lures'])} lure(s) and {_cancel_fish_count} fish - and can't be undone."
        )
        # Punch-list #66 (third pass): the st.form()/form_submit_button()
        # switch from the second pass did NOT fix this - live-reproduced
        # again (this session) on a completely fresh session (Northwest
        # Channel Point / Alex): the very first tap on "Yes, cancel it"
        # still silently did nothing (no banner, session unchanged, dialog
        # just closed back to the plain "❌ Cancel Session" button), and a
        # second identical tap went through immediately. Both the plain-
        # button version (first pass) and the form version (second pass)
        # share one thing in common that this pass finally changes: both
        # read the widget's return value INLINE, after the fact, in the
        # script run that (might) follow the click. Streamlit's own
        # recommended fix for "a widget's action doesn't reliably fire on
        # the exact interaction that created it" is `on_click=` - a
        # callback Streamlit invokes directly as part of handling the
        # click event itself, before the next script run even starts,
        # rather than something this page has to notice by re-reading
        # session state afterward. Switched both confirm buttons to
        # `on_click` callbacks (`_confirm_cancel_session`/`_keep_session`
        # below) instead of branching on the submit buttons' return
        # values - no more `if confirmed:` / `if kept:` to potentially miss.
        # Streamlit reruns the script once automatically after any widget
        # callback, so neither callback calls st.rerun() itself. Still
        # logged as a mitigation until live-reverified post-deploy - see
        # SESSION_NOTES.md punch-list #66.
        with st.form(key=f"cancel_confirm_form_{spot['spot_id']}", border=False):
            ccol1, ccol2 = st.columns(2)
            ccol1.form_submit_button(
                "Yes, cancel it", type="primary", width='stretch',
                on_click=_confirm_cancel_session, args=(spot, cancel_pending_key, resolved_angler),
            )
            ccol2.form_submit_button(
                "Keep session", width='stretch',
                on_click=_keep_session, args=(cancel_pending_key,),
            )

else:
    session_build_seq_key = f"session_build_seq_{spot['spot_id']}"
    # Punch-list #53: only look for a draft to restore when session_state
    # is genuinely fresh for this spot (the key not existing yet means this
    # browser has never rendered a pending build here since it last reset -
    # a real reconnect, not just a normal rerun) - otherwise this would
    # re-apply a stale URL value over whatever's actually live every single
    # render, fighting a manual edit made moments ago.
    _pending_draft = {} if session_build_seq_key in st.session_state else _load_pending_draft(spot["spot_id"])
    st.session_state.setdefault(session_build_seq_key, _pending_draft.get("seq", 0))
    session_build_seq = st.session_state[session_build_seq_key]
    # Only actually usable if its seq still matches - if session_state
    # already had a DIFFERENT (newer) seq for this spot by the time this
    # ran, the draft is for a build that's already moved on.
    if _pending_draft.get("seq") != session_build_seq:
        _pending_draft = {}
    st.session_state.setdefault(_pending_lures_key(spot["spot_id"], session_build_seq), _pending_draft.get("lures", []))

    st.divider()
    with st.container(key="spotsession_conditions_card"):
        st.header("Conditions")
        st.caption(
            "Enter what you're actually seeing at the water - weather-related fields below default from the "
            "live forecast, override any of them if what you see is different. Once you've picked your "
            "lure(s) below, Start Session locks in the exact time and this whole snapshot."
        )
        weather_defaults = _weather_defaults(bundle, session_date, lake_now_naive())
        cond_key_ns = f"cond_{spot['spot_id']}_{session_build_seq}"
        cond_values = render_conditions_block(cond_key_ns, weather_defaults, prefill=_pending_draft.get("cond"))

    _preview_now = lake_now_naive()
    _preview_segment = _guess_segment(_preview_now.hour, _preview_now)
    water_clarity, season, avg_cloud_pct, avg_wind_mph, rt, score_result = _compute_scoring(
        cond_values, session_date, bundle, _preview_now, _preview_segment, spot_id=spot["spot_id"],
    )

    st.divider()
    # Punch-list #33: starts collapsed now (was expanded=True) - the angler's
    # own ask, so the score/lure-suggestion block doesn't take up the whole
    # screen above the actual "Lures for this session" picker every time this
    # page loads; still one tap away whenever it's actually wanted. Punch-list
    # #87 follow-up #2 briefly also drove this expander's `expanded=` from
    # _tackle_box_expander_open_key() (same as "Add from tackle box" below),
    # but the angler explicitly asked for this one to stay untouched - "the
    # suggestions for right now should stay collapsed. That section should
    # only open if I deliberately uncollapse it" - so it's back to a bare
    # `expanded=False` and does NOT track that flag; only "Add from tackle
    # box" (the section the angler was actually complaining about, since
    # that's where the "Add more lures" cycle lives) stays open across a
    # session build.
    with st.expander("Suggestions for right now", expanded=False):
        m1, m2 = st.columns([1, 2])
        with m1:
            st.metric(f"{_preview_segment} activity score", f"{score_result.score}/10")
            render_score_breakdown(
                score_result.breakdown, score_result.score, key=f"preview_score_breakdown_{spot['spot_id']}",
            )
        m2.write(
            f"**Season:** {season.replace('_', ' ').title()}  \n"
            f"**Structure:** {structure_type} (from this spot's saved type)  \n"
            f"**Water clarity:** {water_clarity}"
        )
        if score_result.notes:
            st.caption(" · ".join(score_result.notes))
        for warn in score_result.warnings:
            st.warning(warn)
        if bundle is None:
            st.caption("Pressure trend and solunar timing aren't factored into the score above - no weather forecast data was available just now.")

        inventory_items = get_inventory()
        # Punch-list #37: spot_id lets recommend()'s personal-history boost use
        # the strongest possible match - "have I actually caught fish on this
        # lure AT THIS SPOT before" - not just a general structure-type match.
        # Punch-list #49: fish_activity/forage_activity/wind_mph are Spot
        # Session's own live, on-the-water read (render_conditions_block()'s
        # sliders/wind picker above) - the one thing this page can offer that
        # the 7-Day Forecast page never can, since it's an actual observation,
        # not a forecast.
        rec = recommend(
            season, cond_values["water_temp_f"], _preview_segment, rt["pressure_trend_24h"],
            structure_type=structure_type, water_clarity=water_clarity,
            fish_depth_ft=cond_values.get("fish_depth_ft"), forage=cond_values.get("forage_seen"),
            inventory=inventory_items, trip_history=get_trip_history(), spot_id=spot["spot_id"],
            fish_activity=cond_values.get("fish_activity"), forage_activity=cond_values.get("forage_activity"),
            wind_mph=wind_mph_for_band(cond_values.get("wind_band")),
        )
        _render_recommendation_with_quick_add(
            rec, spot["spot_id"], session_build_seq, key_prefix=f"quickadd_{spot['spot_id']}_{session_build_seq}",
            inventory=inventory_items,
        )

    st.divider()
    with st.container(key="spotsession_pending_lures_card"):
        st.markdown("#### Lures for this session")
        pending_lures = st.session_state.get(_pending_lures_key(spot["spot_id"], session_build_seq), [])
        # Punch-list #87: a lure was just added (from the suggestions quick-add,
        # the tackle-box picker, manual entry, or the trailer dialog - see
        # _lure_added_popup_key()) - show the confirmation popup, right now,
        # before anything else on this rerun renders. Deliberately a plain
        # `.get()`, NOT a `.pop()`: an `@st.dialog` function has to be reachable
        # on every rerun ITS OWN widgets trigger (e.g. just re-rendering while
        # open) or Streamlit has nothing left to show once the user interacts
        # with anything inside it - a one-shot pop-on-render would close this
        # popup the instant it first renders, before either of its own buttons
        # ever got a chance to be clicked. The flag is cleared explicitly
        # instead, by whichever of _lure_added_dialog()'s two buttons actually
        # dismisses it ("Add more lures" pops it directly; "Start Session"
        # advances session_build_seq, so this exact key - scoped to the OLD
        # seq - simply stops matching on the very next render).
        if st.session_state.get(_lure_added_popup_key(spot["spot_id"], session_build_seq), False):
            _lure_added_dialog(
                spot, cond_values, session_date, bundle, structure_type, resolved_angler,
                pending_lures, session_build_seq, session_build_seq_key, active_session_key,
            )
        # Punch-list #53: keep the URL's draft in sync with wherever this build
        # actually is right now - conditions form values plus whatever lures
        # are queued so far - every render, so a reconnect at any point (even
        # before a single lure's been picked) restores it instead of starting
        # over blank.
        _save_pending_draft(spot["spot_id"], session_build_seq, cond_values, pending_lures)
        if pending_lures:
            for i, lure in enumerate(pending_lures):
                lcol1, lcol2 = st.columns([5, 1])
                trailer = lure.get("trailer")
                trailer_bit = f" + {trailer['label']} trailer" if trailer else ""
                lcol1.write(f"🎣 {lure['label']}{trailer_bit}")
                if lcol2.button("Remove", key=f"remove_pending_lure_{spot['spot_id']}_{session_build_seq}_{i}"):
                    # Removing a lure removes its trailer too, since the trailer
                    # is stored nested inside this same pending-list entry, not
                    # tracked separately.
                    _remove_lure_from_pending(spot["spot_id"], session_build_seq, i)
                    st.rerun()
        else:
            st.caption("No lures selected yet - use the suggestions above or the tackle box below.")

    with st.expander(
        "➕ Add from tackle box",
        expanded=st.session_state.get(_tackle_box_expander_open_key(spot["spot_id"], session_build_seq), False),
    ):
        _multi_lure_picker(
            inventory_items, key_prefix=f"session_lure_picker_{spot['spot_id']}_{session_build_seq}",
            spot_id=spot["spot_id"], seq=session_build_seq,
        )
        st.markdown("**Not in your inventory?**")
        manual_seq_key = f"manual_lure_seq_{spot['spot_id']}_{session_build_seq}"
        st.session_state.setdefault(manual_seq_key, 0)
        manual_seq = st.session_state[manual_seq_key]
        manual_col1, manual_col2 = st.columns([4, 1])
        manual_name = manual_col1.text_input(
            "Lure name", key=f"manual_lure_name_{spot['spot_id']}_{session_build_seq}_{manual_seq}",
            label_visibility="collapsed", placeholder="Type a lure name to add it manually",
        )
        if manual_col2.button("+ Add", key=f"manual_lure_add_{spot['spot_id']}_{session_build_seq}_{manual_seq}"):
            if manual_name.strip():
                st.session_state[manual_seq_key] = manual_seq + 1
                _handle_lure_add_click(
                    spot["spot_id"], session_build_seq,
                    {"item_id": None, "label": manual_name.strip(), "category": None}, None, "pending",
                )

    st.divider()
    if st.button(
        "▶ Start Session", type="primary", width='stretch', disabled=not pending_lures,
        key=f"start_session_{spot['spot_id']}_{session_build_seq}",
    ):
        _start_pending_session(
            spot, cond_values, session_date, bundle, structure_type, resolved_angler,
            pending_lures, session_build_seq, session_build_seq_key, active_session_key,
        )
    if not pending_lures:
        st.caption("Select at least one lure above before starting the session.")
