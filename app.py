"""
App entry point - Streamlit Cloud and `streamlit run app.py` both point here.

This file wires up the sidebar navigation (via st.navigation/st.Page, which
is what lets each page get a real title and icon in the sidebar, instead of
the old file-based pages/ auto-discovery showing raw filenames - that
auto-discovery also always listed this entry script itself as a page named
"app", which isn't a real page). The actual landing-page content that used
to live directly in this file has moved to home.py unchanged; every other
page keeps living in pages/ unchanged too, including each page's own
st.set_page_config() call (still safe here, since _sync_data_once() below
never renders anything - st.cache_resource(show_spinner=False) means no
delta is generated on a cache hit, and none on a cache miss either - so
that page's own set_page_config is still effectively "the first Streamlit
RENDER command" for that run, exactly like before this function existed).

Punch-list #52: _sync_data_once() overlays data/ with the latest content
from the "data" branch every data save now pushes to (see
core/storage.py's module docstring for the full "why" - short version:
Streamlit Cloud only redeploys on pushes to `main`, and moving data saves
off of `main` means routine saves no longer wipe everyone's session, but
it also means a freshly booted process's own `main` checkout has whatever
data/ was frozen at the punch-list #52 cutover, not what's actually been
logged since - this closes that gap). st.cache_resource makes this run
exactly ONCE per process (shared across every user/session/page, unlike
st.cache_data or st.session_state), not on every rerun - this file's own
top-level code re-executes on every single page interaction, so without
that guard this would re-fetch from GitHub on every click.
"""
import streamlit as st

from core.appstate import github_token, repo_slug
from core.storage import sync_data_from_data_branch


@st.cache_resource(show_spinner=False)
def _sync_data_once():
    token = github_token()
    if token:
        sync_data_from_data_branch(token, repo_slug())
    return True


_sync_data_once()

pg = st.navigation([
    st.Page("home.py", title="Today", icon="🎣", default=True),
    st.Page("pages/1_7_Day_Forecast.py", title="7 Day Forecast", icon="📅"),
    st.Page("pages/2_Lake_Map.py", title="Lake Map", icon="🗺️"),
    st.Page("pages/6_Spot_Session.py", title="Spot Session", icon="🎯"),
    st.Page("pages/4_Trip_History.py", title="Trip History", icon="📊"),
    st.Page("pages/8_Leaderboard.py", title="Leaderboard", icon="🏆"),
    st.Page("pages/5_Lure_Inventory.py", title="Tackle Box", icon="🧰"),
    st.Page("pages/7_Development.py", title="Development", icon="🛠️"),
])
pg.run()
