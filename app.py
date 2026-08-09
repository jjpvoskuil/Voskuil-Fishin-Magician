"""
App entry point - Streamlit Cloud and `streamlit run app.py` both point here.

This file only wires up the sidebar navigation (via st.navigation/st.Page,
which is what lets each page get a real title and icon in the sidebar,
instead of the old file-based pages/ auto-discovery showing raw filenames -
that auto-discovery also always listed this entry script itself as a page
named "app", which isn't a real page). The actual landing-page content
that used to live directly in this file has moved to home.py unchanged;
every other page keeps living in pages/ unchanged too, including each
page's own st.set_page_config() call (still safe under st.navigation, since
this file itself calls no Streamlit commands before handing off to the
selected page via pg.run() - so that page's own set_page_config is still
effectively "the first Streamlit command" for that run, exactly like before
this file existed).
"""
import streamlit as st

pg = st.navigation([
    st.Page("home.py", title="Today", icon="🎣", default=True),
    st.Page("pages/1_7_Day_Forecast.py", title="7 Day Forecast", icon="📅"),
    st.Page("pages/2_Lake_Map.py", title="Lake Map", icon="🗺️"),
    st.Page("pages/4_Trip_History.py", title="Trip History", icon="📊"),
    st.Page("pages/5_Lure_Inventory.py", title="Lure Inventory", icon="🧰"),
    st.Page("pages/6_Spot_Session.py", title="Spot Session", icon="🎯"),
])
pg.run()
