"""Site-wide navigation chrome (Phase 1 of the app's visual redesign - see
SESSION_NOTES). Replaces Streamlit's own auto-generated sidebar page list
(app.py's st.navigation(..., position="hidden") turns that off) with a
single sticky bottom bar: the 5 pages used day-to-day as direct links,
plus a "☰ More" button that opens EVERY page (all 9, including the 5
already on the bar) in a popover - the angler's own ask: "we should have
the option to go to any of our pages, not just the ones that aren't on
the main bar."

A page's own st.sidebar content (e.g. the 7-Day Forecast's Lake Setup
Options, core.ui.render_lake_setup_sidebar) is a separate mechanism from
the auto page-list this replaces and keeps working completely unaffected -
position="hidden" only turns off st.navigation's own generated nav UI, not
st.sidebar itself.

render_bottom_nav(active_path) is the one call every page needs, right
after its own inject_mobile_css() call (same spot every page already
calls that from, so this reads as "the next line of site-wide chrome
setup" rather than a new pattern)."""
from __future__ import annotations
import streamlit as st

# Punch-list #96: single source of truth for every page's nav identity, in
# the same order the old sidebar showed them - app.py's st.navigation()
# call and this module both build off ALL_PAGES, so a page's title/icon/
# order never has to be kept in sync by hand across two files. Each tuple
# is (path, title, icon), matching st.Page()'s / st.page_link()'s own args
# - path strings are relative to app.py (the entry point Streamlit resolves
# every page identity against), not to whichever file happens to call
# render_bottom_nav(), so these are safe to reuse verbatim from any page.
ALL_PAGES = [
    ("home.py", "Today", "🎣"),
    ("pages/1_7_Day_Forecast.py", "Forecast", "📅"),
    ("pages/2_Lake_Map.py", "Lake Map", "🗺️"),
    ("pages/6_Spot_Session.py", "Session", "🎯"),
    ("pages/4_Trip_History.py", "Trip History", "📊"),
    ("pages/8_Leaderboard.py", "Leaderboard", "🏆"),
    ("pages/9_Reports.py", "Reports", "📈"),
    ("pages/5_Lure_Inventory.py", "Tackle Box", "🧰"),
    ("pages/7_Development.py", "Development", "🛠️"),
]

# The 5 pages that get their own direct spot on the bottom bar (matches
# what the angler asked to keep front-and-center) - everything else (and
# these 5 too, for one complete list) lives behind the "☰ More" popover.
_PRIMARY_PATHS = {
    "home.py", "pages/1_7_Day_Forecast.py", "pages/6_Spot_Session.py",
    "pages/5_Lure_Inventory.py", "pages/8_Leaderboard.py",
}
PRIMARY_PAGES = [p for p in ALL_PAGES if p[0] in _PRIMARY_PATHS]


def render_bottom_nav(active_path: str) -> None:
    """Sticky bottom tab bar. st.bottom (used as `with st.bottom:`, the
    same calling convention as `with st.sidebar:`) is a native Streamlit
    container pinned to the bottom of the main app area (the same
    mechanism st.chat_input uses for its own always-at-the-bottom input
    box) - no custom component or CSS position:fixed hack needed for the
    pinning itself. Holds 5 direct st.page_link()s plus a "☰ More"
    st.popover() listing every page.

    `active_path` should be the exact path string this calling page is
    registered under in ALL_PAGES (e.g. "pages/8_Leaderboard.py") - used
    only to strengthen that one tab's highlight via CSS below; every page
    still renders all 5 links (including a link to itself) so the bar
    looks identical everywhere, rather than a tab mysteriously missing
    itself on its own page. (Streamlit's own st.page_link already bolds
    whichever link points at the current page automatically - this CSS
    adds a stronger color difference on top of that, since bold alone
    against the dark bar below is easy to miss.)

    A no-op (renders nothing, raises nothing) when called outside a real
    st.navigation() context - st.page_link() validates its target against
    whatever page list st.navigation() registered for this run, and this
    app's own ~600-test suite exercises most pages directly via
    AppTest.from_file("pages/whatever.py") (this app's own established
    pattern, unrelated to this nav bar - see tests/test_app.py's own
    comment on why APP_PATH vs PAGE_PATH are separate fixtures), which
    never goes through app.py/st.navigation() at all. That's the expected,
    common case for a page test - only test_app.py's own 3 tests actually
    exercise real navigation - so this fails the same soft way every other
    context-dependent helper in this app does (see e.g. core.appstate.
    github_token()'s own docstring) rather than raising and failing every
    other page's content tests over chrome those tests aren't about.
    """
    active_idx = next((i for i, (p, _, _) in enumerate(PRIMARY_PAGES) if p == active_path), None)

    try:
        with st.bottom:
            with st.container(key="app_bottom_nav"):
                cols = st.columns(len(PRIMARY_PAGES) + 1)
                for (path, title, icon), col in zip(PRIMARY_PAGES, cols):
                    with col:
                        st.page_link(path, label=title, icon=icon, use_container_width=True)
                with cols[-1]:
                    with st.popover("☰", use_container_width=True, help="All pages"):
                        for path, title, icon in ALL_PAGES:
                            st.page_link(path, label=title, icon=icon)
    except st.errors.StreamlitPageNotFoundError:
        return

    # nth-child is 1-indexed; active_idx (0-indexed) lines up directly
    # since PRIMARY_PAGES fills the first len(PRIMARY_PAGES) columns in
    # order and the "☰ More" column is always last, never one of these.
    active_css = ""
    if active_idx is not None:
        active_css = f"""
        .st-key-app_bottom_nav [data-testid="stColumn"]:nth-child({active_idx + 1})
            [data-testid="stPageLink-NavLink"] {{
            color: #F2F4F0 !important;
        }}
        """

    st.markdown(
        f"""
        <style>
        /* Punch-list #96: st.bottom()'s own container, restyled from
           Streamlit's default (theme background + top border) to a plain
           dark bar - see SESSION_NOTES for the "one accent, otherwise
           monochrome" direction this whole redesign is following. */
        [data-testid="stBottomBlockContainer"] {{
            background: #10140F !important;
            border-top: none !important;
            padding-top: 6px !important;
            padding-bottom: 6px !important;
        }}
        .st-key-app_bottom_nav [data-testid="stPageLink-NavLink"] {{
            justify-content: center !important;
            text-decoration: none !important;
            color: #828C84 !important;
            font-size: 0.8rem !important;
        }}
        .st-key-app_bottom_nav [data-testid="stPopoverButton"] {{
            color: #828C84 !important;
        }}
        .st-key-app_bottom_nav [data-testid="stPopoverButton"] p {{
            text-align: center !important;
            font-weight: 700 !important;
        }}
        {active_css}
        </style>
        """,
        unsafe_allow_html=True,
    )
