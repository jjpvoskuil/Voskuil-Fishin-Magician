"""
The Stringer - punch-list #97 Phase 2 of the site-wide visual redesign
(Phase 1, the bottom nav bar shell, is punch-list #96 - core/nav.py).

Replaces the old flat "pick a category from a dropdown, see a filterable
dataframe" Leaderboard with the validated "The Stringer" mockup: a
cyclable ring-chart hero showing 2-3 real season stats, an underline tab
bar over six curated rankings (Biggest Fish / Top Anglers / Hot Lures /
Top Spots / Longest Fish / Top Sessions), and a "season activity + species
mix" glance panel underneath. Full design-critique history (two "looks
like PowerPoint"/"too cartoony" rounds before this landed) and the mockup
artifact itself: SESSION_NOTES.md entries 171/172 and punch-list #97's own
text.

This is a full replacement, not an addition - the old page's 14-category
dropdown + angler/species filters are gone. That's a deliberate scope
split validated with the angler, not an oversight: deep ad hoc filtering
and correlation now belongs on the Reports page (punch-list #92), so this
page can be a tight "highlight reel" instead of trying to be both. All the
actual data work (grouping/sorting/formatting) lives in core/stringer.py -
Streamlit-free and unit tested on its own (tests/test_stringer.py), same
split as core/daily_leaderboard.py and core/reports.py - this file is
just the rendering layer over it.

One real design-language gap, flagged rather than silently worked around:
the mockup's page-wide background/typography swap (Plus Jakarta Sans, the
teal accent, the near-flat card look) is scoped to THIS page's own cards
only here, not applied to the rest of the app - Phase 3+ (punch-list #98)
is where that happens everywhere else, one page at a time, per the
angler's own explicit scoping note on #97 ("Reports, Trip History, Lake
Map, Development not yet scoped"). Applying it globally from inside this
one page's code would be exactly the kind of premature, un-asked-for
scope creep this app's own operating notes warn against.
"""
import math
import re
from datetime import date as date_cls

import streamlit as st

from core.appstate import (
    get_lake_spots, get_trip_history, get_calibrated_weights, get_location_adjustments,
    github_token, repo_slug,
)
from core.ui import inject_mobile_css
from core.storage import sync_data_from_data_branch
from core.nav import render_bottom_nav
from core.stringer import (
    build_frames, season_label, hero_states, CATEGORIES, daily_activity_series, species_mix,
)

st.set_page_config(page_title="The Stringer - Nolin Lake", page_icon="🏆", layout="wide")
inject_mobile_css()
render_bottom_nav("pages/8_Leaderboard.py")

# --- Design-language CSS + fonts (punch-list #97 Phase 2) --------------------
# Named --stringer-* rather than reusing/overriding any of Streamlit's own
# theme variables - these are purely additive on :root (harmless on every
# other page, which simply never references them) rather than an attempt
# to re-theme the whole app from inside one page's code (see this file's
# own docstring above for why that's explicitly out of scope right now).
# Exact hex values are copied straight from the validated mockup artifact
# linked on punch-list #97, not re-picked here.
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
    :root {
      --stringer-surface:#FFFFFF; --stringer-surface-sunk:#EEF0EA;
      --stringer-ink:#0F1410; --stringer-ink-soft:#3C443E; --stringer-muted:#6E766F;
      --stringer-border:#E7E9E2; --stringer-accent:#2C7C6E; --stringer-accent-strong:#1F5F54;
      --stringer-accent-track:#D8EAE5;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --stringer-surface:#131A16; --stringer-surface-sunk:#0F1512;
        --stringer-ink:#F1F3EF; --stringer-ink-soft:#C4CCC5; --stringer-muted:#8A948C;
        --stringer-border:#212A24; --stringer-accent:#4FAE9C; --stringer-accent-strong:#6FC2B2;
        --stringer-accent-track:#173630;
      }
    }
    .stringer-topbar, .stringer-hero-desc, .stringer-panel, .stringer-glance,
    .st-key-stringer_hero, .st-key-stringer_tabs, .st-key-stringer_dots {
        font-family: "Plus Jakarta Sans", system-ui, sans-serif;
    }
    .stringer-mono { font-family: "IBM Plex Mono", monospace; }
    .stringer-unit { color: var(--stringer-muted); font-size: 0.78em; }
    /* Top brand row: wordmark + rolling season-date chip. */
    .stringer-topbar {
        display:flex; align-items:center; justify-content:space-between;
        gap:12px; flex-wrap:wrap; margin-bottom:4px;
    }
    .stringer-brand { font-weight:800; font-size:1.05rem; letter-spacing:.04em; color:var(--stringer-ink); }
    .stringer-season-chip {
        font-family:"IBM Plex Mono", monospace; font-size:.72rem; color:var(--stringer-muted);
        background:var(--stringer-surface-sunk); padding:5px 10px; border-radius:100px; white-space:nowrap;
    }
    /* Hero ring card - the whole st.container(key="stringer_hero") becomes
       one visual card; the buttons/columns inside it are real Streamlit
       widgets (needed for the prev/next/dot rerun interactivity), the ring
       SVG itself is one injected HTML block. */
    .st-key-stringer_hero {
        background:var(--stringer-surface); border-radius:16px; padding:14px 18px 18px;
        text-align:center; margin-bottom:14px;
    }
    .st-key-stringer_hero [data-testid="stMarkdownContainer"] h2 {
        font-size:1.05rem; font-weight:700; margin:2px 0 10px;
    }
    .st-key-stringer_hero button[kind="secondary"] {
        background:none !important; border:none !important; color:var(--stringer-ink) !important;
        font-size:1.3rem !important; line-height:1 !important; box-shadow:none !important;
    }
    .st-key-stringer_hero button[kind="secondary"]:hover { color:var(--stringer-accent) !important; }
    .st-key-stringer_dots button[kind="secondary"] {
        background:none !important; border:none !important; box-shadow:none !important;
        color:var(--stringer-border) !important; font-size:.6rem !important; padding:2px !important;
        min-height:0 !important;
    }
    .st-key-stringer_dots button[kind="primary"] {
        background:none !important; border:none !important; box-shadow:none !important;
        color:var(--stringer-ink) !important; font-size:.6rem !important; padding:2px !important;
        min-height:0 !important;
    }
    .stringer-ring-wrap { position:relative; width:190px; height:190px; margin:0 auto; }
    .stringer-ring-wrap svg { width:100%; height:100%; transform:rotate(-90deg); }
    .stringer-ring-center {
        position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
        justify-content:center; text-align:center; gap:4px; padding:0 40px;
    }
    .stringer-ring-legend { display:flex; align-items:center; gap:6px; font-size:.72rem; color:var(--stringer-ink-soft); font-weight:600; }
    .stringer-swatch { width:8px; height:8px; border-radius:2px; background:var(--stringer-accent); display:inline-block; }
    .stringer-ring-value { font-size:2.1rem; font-weight:800; letter-spacing:-.02em; line-height:1; color:var(--stringer-ink); }
    .stringer-ring-desc { font-size:.76rem; color:var(--stringer-muted); max-width:320px; margin:8px auto 0; }
    .stringer-hero-secondary { margin-top:10px; }
    .stringer-hero-label { font-size:.72rem; color:var(--stringer-muted); font-weight:600; margin-bottom:2px; }
    .stringer-hero-big { font-size:1.15rem; font-weight:800; color:var(--stringer-ink); }
    /* Ranked-list panel. */
    .stringer-panel { background:var(--stringer-surface); border-radius:16px; overflow:hidden; margin-bottom:14px; }
    .stringer-panel-head {
        display:flex; align-items:baseline; justify-content:space-between; gap:12px;
        padding:14px 16px 8px; flex-wrap:wrap;
    }
    .stringer-panel-head h3 { font-size:.95rem; font-weight:700; margin:0; color:var(--stringer-ink); }
    .stringer-sort-note { font-size:.72rem; color:var(--stringer-muted); font-family:"IBM Plex Mono",monospace; }
    .stringer-row {
        display:grid; grid-template-columns:24px 1fr auto; align-items:center;
        gap:12px; padding:9px 16px; border-top:1px solid var(--stringer-border);
    }
    .stringer-rank { font-weight:800; font-size:.84rem; color:var(--stringer-muted); }
    .stringer-rank.r1 { color:var(--stringer-ink); }
    .stringer-row-primary { font-weight:700; font-size:.9rem; color:var(--stringer-ink); overflow-wrap:break-word; }
    .stringer-row-secondary { font-size:.74rem; color:var(--stringer-muted); margin-top:2px; overflow-wrap:break-word; }
    .stringer-row-num {
        font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:.9rem;
        color:var(--stringer-ink); text-align:right; white-space:nowrap;
    }
    .stringer-row-tag { display:block; margin-top:2px; font-size:.62rem; color:var(--stringer-muted); text-align:right; }
    .stringer-empty { padding:16px; font-size:.85rem; color:var(--stringer-muted); }
    /* Underline tab bar (st.tabs, restyled via BaseWeb's own stable
       data-baseweb hooks) - not live-DOM-verified against a real browser
       in this sandbox (no browser attached here), same caveat SESSION_NOTES
       entry 171 flagged for the bottom nav bar's own first pass; worth a
       real-device look before calling this pixel-final. */
    .st-key-stringer_tabs [data-baseweb="tab-list"] {
        gap:20px; border-bottom:1px solid var(--stringer-border); background:transparent;
    }
    .st-key-stringer_tabs [data-baseweb="tab"] {
        font-weight:600; font-size:.84rem; color:var(--stringer-muted); background:transparent;
        padding:8px 2px 10px;
    }
    .st-key-stringer_tabs [data-baseweb="tab"][aria-selected="true"] { color:var(--stringer-ink) !important; }
    .st-key-stringer_tabs [data-baseweb="tab-highlight"] { background-color:var(--stringer-accent) !important; }
    .st-key-stringer_tabs [data-baseweb="tab-border"] { background-color:transparent !important; }
    /* Glance panel: season activity chart + species mix. */
    .stringer-glance {
        background:var(--stringer-surface); border-radius:16px; padding:14px 16px 16px;
        display:grid; grid-template-columns:1.3fr 1fr; gap:0;
    }
    @media (max-width:520px) { .stringer-glance { grid-template-columns:1fr; } }
    .stringer-glance-col h4 { font-size:.86rem; font-weight:700; margin:0 0 2px; color:var(--stringer-ink); }
    .stringer-glance-sub { font-size:.72rem; color:var(--stringer-muted); margin-bottom:10px; }
    .stringer-glance-col + .stringer-glance-col { padding-left:16px; border-left:1px solid var(--stringer-border); }
    @media (max-width:520px) {
        .stringer-glance-col + .stringer-glance-col { padding-left:0; border-left:none; border-top:1px solid var(--stringer-border); padding-top:12px; margin-top:12px; }
    }
    .stringer-species-row { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
    .stringer-species-name { width:90px; flex:none; font-size:.76rem; font-weight:600; color:var(--stringer-ink-soft); }
    .stringer-species-track { flex:1; height:6px; border-radius:100px; background:var(--stringer-surface-sunk); overflow:hidden; }
    .stringer-species-fill { height:100%; border-radius:100px; background:var(--stringer-muted); }
    .stringer-species-fill.top { background:var(--stringer-accent); }
    .stringer-species-count { width:30px; flex:none; text-align:right; font-family:"IBM Plex Mono",monospace; font-size:.76rem; color:var(--stringer-ink); }
    </style>
    """,
    unsafe_allow_html=True,
)

_UNIT_RE = re.compile(r"\b(lb|oz|fish|in|days|trips)\b")


def _style_units(text: str) -> str:
    return _UNIT_RE.sub(r'<span class="stringer-unit">\1</span>', text)


# --- Refresh from GitHub (punch-list #61) ------------------------------------
# Carried over unchanged from the old page: get_trip_history() is a
# 5-minute cache that's never cleared by a save made elsewhere, on top of
# this server only syncing from the `data` branch once at boot - see
# core.storage.sync_data_from_data_branch's own docstring.
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
        get_calibrated_weights.clear()
        get_location_adjustments.clear()
        (st.success if _ok else st.warning)(_msg)
    else:
        st.info("No GitHub token configured here - nothing to refresh.")

rows = get_trip_history()

if not rows:
    st.info(
        "No trips logged yet - The Stringer fills in as you log sessions on the "
        "**Spot Session** page."
    )
    st.stop()

_spot_name_by_id = {s["spot_id"]: s["name"] for s in get_lake_spots()}
fish_df, trips_df = build_frames(rows, _spot_name_by_id)

_season = season_label(trips_df) or "All time"
st.markdown(
    f"""
    <div class="stringer-topbar">
        <span class="stringer-brand">🎣 THE STRINGER</span>
        <span class="stringer-season-chip">{_season}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Hero: cyclable ring-chart season stats -----------------------------------
_states = hero_states(fish_df, trips_df)
if _states:
    st.session_state.setdefault("stringer_ring_idx", 0)
    st.session_state["stringer_ring_idx"] %= len(_states)

    with st.container(key="stringer_hero"):
        head_l, head_c, head_r = st.columns([1, 8, 1])
        # Punch-list #97: every one of these buttons calls st.rerun() itself
        # right after moving the index, rather than just falling through to
        # render the rest of this same script run - the dots below are
        # necessarily rendered AFTER the title/ring above them (that's the
        # mockup's own layout), so a click on a dot can't retroactively fix
        # up content this same pass already emitted further up the page.
        # Forcing an immediate fresh rerun (same pattern pages/7_Development.py
        # and pages/6_Spot_Session.py already use after every mutation) means
        # the very next run starts clean and renders title/ring/dots all
        # from one single, already-final index - never a stale title next to
        # an updated ring, or a dot highlight one click behind.
        if head_l.button("‹", key="stringer_ring_prev", help="Previous stat"):
            st.session_state["stringer_ring_idx"] = (st.session_state["stringer_ring_idx"] - 1) % len(_states)
            st.rerun()
        if head_r.button("›", key="stringer_ring_next", help="Next stat"):
            st.session_state["stringer_ring_idx"] = (st.session_state["stringer_ring_idx"] + 1) % len(_states)
            st.rerun()

        s = _states[st.session_state["stringer_ring_idx"]]
        head_c.markdown(f"<h2>{s.title}</h2>", unsafe_allow_html=True)
        pct = (s.value / s.total) if s.total else 0.0
        pct = max(0.0, min(1.0, pct))
        circumference = 2 * math.pi * 86
        offset = circumference * (1 - pct)
        st.markdown(
            f"""
            <div class="stringer-ring-wrap">
                <svg viewBox="0 0 200 200">
                    <circle cx="100" cy="100" r="86" fill="none" stroke="var(--stringer-accent-track)" stroke-width="16"/>
                    <circle cx="100" cy="100" r="86" fill="none" stroke="var(--stringer-accent)" stroke-width="16"
                            stroke-linecap="round" stroke-dasharray="{circumference:.1f}"
                            stroke-dashoffset="{offset:.1f}"/>
                </svg>
                <div class="stringer-ring-center">
                    <div class="stringer-ring-legend"><span class="stringer-swatch"></span>{s.legend}</div>
                    <div class="stringer-ring-value">{round(pct * 100)}%</div>
                </div>
            </div>
            <div class="stringer-ring-desc">{s.desc}</div>
            <div class="stringer-hero-secondary">
                <div class="stringer-hero-label">{s.sec_label}</div>
                <div class="stringer-hero-big">{_style_units(s.sec_value)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if len(_states) > 1:
            with st.container(key="stringer_dots"):
                dot_cols = st.columns(len(_states))
                for i, col in enumerate(dot_cols):
                    is_active = i == st.session_state["stringer_ring_idx"]
                    if col.button(
                        "●", key=f"stringer_dot_{i}", type="primary" if is_active else "secondary",
                        help=f"Show stat {i + 1}",
                    ):
                        st.session_state["stringer_ring_idx"] = i
                        st.rerun()

# --- Underline tabs + ranked list ----------------------------------------------
with st.container(key="stringer_tabs"):
    tab_objs = st.tabs([label for _, label, _, _ in CATEGORIES])
    for tab, (_, label, sort_note, builder) in zip(tab_objs, CATEGORIES):
        with tab:
            category_rows = builder(fish_df, trips_df)
            if not category_rows:
                st.markdown(
                    f"""
                    <div class="stringer-panel">
                        <div class="stringer-panel-head"><h3>{label}</h3></div>
                        <div class="stringer-empty">No data for this category yet.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                continue
            row_html = []
            for i, r in enumerate(category_rows):
                rank = i + 1
                tag_html = f'<span class="stringer-row-tag">{r["tag"]}</span>' if r["tag"] else ""
                row_html.append(f"""
                <div class="stringer-row">
                    <div class="stringer-rank{' r1' if rank == 1 else ''}">{rank}</div>
                    <div>
                        <div class="stringer-row-primary">{r['primary']}</div>
                        <div class="stringer-row-secondary">{r['secondary']}</div>
                    </div>
                    <div>
                        <div class="stringer-row-num">{_style_units(r['num'])}</div>{tag_html}
                    </div>
                </div>
                """.strip())
            st.markdown(
                f"""
                <div class="stringer-panel">
                    <div class="stringer-panel-head"><h3>{label}</h3><span class="stringer-sort-note">{sort_note}</span></div>
                    {''.join(row_html)}
                </div>
                """,
                unsafe_allow_html=True,
            )

# --- Glance panel: season activity + species mix -------------------------------
_dates = trips_df["date"].dropna()
if not _dates.empty:
    _lo, _hi = _dates.min(), _dates.max()
    _daily = daily_activity_series(fish_df, _lo, _hi)
    _mix = species_mix(fish_df)

    _max_fish = max((c for _, c in _daily), default=0)
    _bars = ""
    if _max_fish > 0 and _daily:
        chart_w, chart_h, pad_b = 400, 130, 20
        bar_gap = 1.2
        bar_w = max(chart_w / len(_daily) - bar_gap, 0.6)
        peak_i = max(range(len(_daily)), key=lambda i: _daily[i][1])
        parts = []
        for i, (_, count) in enumerate(_daily):
            x = i * (chart_w / len(_daily))
            h = max((count / _max_fish) * (chart_h - pad_b), 0.6) if count else 0.6
            y = (chart_h - pad_b) - h
            color = "var(--stringer-accent)" if i == peak_i else "var(--stringer-muted)"
            opacity = "1" if i == peak_i else "0.5"
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="0.6" '
                f'fill="{color}" opacity="{opacity}"/>'
            )
        parts.append(
            f'<line x1="0" x2="{chart_w}" y1="{chart_h - pad_b}" y2="{chart_h - pad_b}" '
            f'stroke="var(--stringer-border)" stroke-width="1"/>'
        )
        _bars = (
            f'<svg viewBox="0 0 {chart_w} {chart_h}" preserveAspectRatio="none" '
            f'style="width:100%;height:auto;display:block;">{"".join(parts)}</svg>'
        )
    else:
        _bars = '<div class="stringer-empty">No catches logged yet this season.</div>'

    _species_rows = ""
    if _mix:
        top_count = _mix[0][1]
        for name, count in _mix:
            width_pct = (count / top_count) * 100 if top_count else 0
            fill_cls = "stringer-species-fill top" if count == top_count else "stringer-species-fill"
            _species_rows += f"""
            <div class="stringer-species-row">
                <div class="stringer-species-name">{name}</div>
                <div class="stringer-species-track"><div class="{fill_cls}" style="width:{width_pct:.1f}%"></div></div>
                <div class="stringer-species-count">{count}</div>
            </div>
            """.strip()
    else:
        _species_rows = '<div class="stringer-empty">No per-fish detail logged yet.</div>'

    total_fish_logged = int(fish_df["count"].sum()) if not fish_df.empty else 0
    st.markdown(
        f"""
        <div class="stringer-glance">
            <div class="stringer-glance-col">
                <h4>Season activity</h4>
                <div class="stringer-glance-sub">Fish caught per day, {_season}</div>
                {_bars}
            </div>
            <div class="stringer-glance-col">
                <h4>Species mix</h4>
                <div class="stringer-glance-sub">{total_fish_logged} fish, all spots</div>
                {_species_rows}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
