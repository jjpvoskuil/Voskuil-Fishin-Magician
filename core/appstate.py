"""Shared, cached accessors used by every Streamlit page."""
from __future__ import annotations
import streamlit as st

from .weather import fetch_forecast
from .lake_level import fetch_lake_level, fetch_lake_level_history
from .lake_water_quality import fetch_surface_water_quality
from .water_quality_log import parsed_log as read_water_quality_log
from .cabelas_lookup import search_lures
from .cabelas_picks_cache import get_cached_picks
from .spots import load_spots
from .storage import read_all_trips
from .calibration import calibrate_weights
from .lure_inventory import read_all_items
from .lake_spots import read_all_spots
from .dev_tasks import read_all_tasks as read_all_dev_tasks
from .anglers import read_anglers


@st.cache_data(ttl=60 * 60, show_spinner="Fetching weather forecast...")
def get_weather_bundle(days: int = 7):
    return fetch_forecast(days=days)


@st.cache_data(ttl=60 * 15, show_spinner="Fetching lake level...")
def get_lake_level():
    return fetch_lake_level()


# Punch-list #13: same site/TTL as get_lake_level() above (same live USGS
# source, just a wider window - one real request covers both use cases'
# freshness needs) - a separate cache entry (different function name means
# a different cache key) since the two callers want different shapes back
# (single latest reading vs. the whole trailing series for a chart).
@st.cache_data(ttl=60 * 15, show_spinner="Fetching lake level history...")
def get_lake_level_history(days: int = 3):
    return fetch_lake_level_history(days=days)


# Much longer TTL than the other live sources - USACE only republishes this
# survey roughly every 1-2 weeks, so there's no benefit to re-fetching more
# than a few times a day, and it saves hammering a non-API legacy page.
@st.cache_data(ttl=60 * 60 * 6, show_spinner="Fetching USACE water-quality survey...")
def get_surface_water_quality():
    return fetch_surface_water_quality()


# Punch-list #13: the locally-recorded historical archive of the reading
# above (see core/water_quality_log.py for why - the live USACE page itself
# has no history to fetch). Short TTL: this is a cheap local CSV read, not
# a network fetch, so there's no real cost to keeping it fresh within a
# session - the TTL just avoids re-reading the file on every single rerun.
@st.cache_data(ttl=60)
def get_water_quality_log():
    return read_water_quality_log()


@st.cache_data(ttl=60 * 5)
def get_spots():
    return load_spots()


# Punch-list #8: cache Cabela's lookups by lure-name query, well past the
# lifetime of a single page render. The 7-Day Forecast page alone calls
# core.lures.recommend() once per segment per day (~28 calls), each
# producing several lure blocks - without caching, every one of those
# blocks with nothing color-matched in inventory would trigger its own live
# Cabela's round trip on every single page load, for what's usually the
# same handful of lure names repeating over and over. A day's worth of TTL
# is plenty since this is "worth considering buying," not a live price
# feed - Cabela's own inventory/pricing doesn't need to be second-fresh
# here.
#
# Punch-list #22: falls back to a curated data/cabelas_picks_cache.csv
# (core.cabelas_picks_cache.get_cached_picks) whenever the live lookup
# comes back empty - confirmed the live Cabela's/Coveo search can fail from
# this app's own deployed server while working fine from a real browser
# (see core/cabelas_lookup.py and core/cabelas_picks_cache.py's own
# docstrings for the full story), so an empty live result here isn't
# necessarily "no matches" - it might just be this app's server-side calls
# being blocked. Returns (suggestions, is_live) instead of a plain list now
# so core.ui.render_cabelas_suggestions can be honest with the angler about
# which one they're looking at.
@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def get_cabelas_suggestions(query: str, num_results: int = 2):
    live = search_lures(query, num_results=num_results)
    if live:
        return live, True
    return get_cached_picks(query)[:num_results], False


@st.cache_data(ttl=60 * 5)
def get_calibrated_weights():
    trips = read_all_trips()
    return calibrate_weights(trips), len(trips)


# Punch-list #37: core.lures.recommend()'s personal-history lure boost
# (core.lure_history) needs the raw trip rows too - a separate cache entry
# from get_calibrated_weights() above (different return shape: raw rows vs.
# a weights dict) even though both start from the same read_all_trips()
# call. Same 5-minute TTL/reasoning as that one: trip data only changes when
# the angler logs something, no need to re-read the CSV on every rerun.
@st.cache_data(ttl=60 * 5)
def get_trip_history():
    return read_all_trips()


@st.cache_data(ttl=60)
def get_inventory():
    return read_all_items()


@st.cache_data(ttl=60)
def get_lake_spots():
    return read_all_spots()


@st.cache_data(ttl=60)
def get_dev_tasks():
    return read_all_dev_tasks()


# Punch-list #26: the "Who's fishing" dropdown's roster (core/anglers.py) -
# short TTL, same reasoning as get_inventory()/get_lake_spots()/
# get_dev_tasks() above (a cheap local CSV read, just enough caching to
# avoid re-reading the file on every single rerun).
@st.cache_data(ttl=60)
def get_anglers():
    return read_anglers()


def github_token() -> str:
    try:
        return st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        return ""


def repo_slug() -> str:
    try:
        return st.secrets.get("GITHUB_REPO", "jjpvoskuil/Voskuil-Fishin-Magician")
    except Exception:
        return "jjpvoskuil/Voskuil-Fishin-Magician"


def github_connection_status() -> tuple:
    """Punch-list #62: whether this running process can actually see a
    GITHUB_TOKEN right now, plus a masked preview (first 10 + last 4
    characters - enough to visually match against what's pasted into
    Streamlit secrets, never enough to reconstruct the real value) if it
    can. Exists because github_token() failing (missing secret, a typo in
    the key name, a TOML syntax error elsewhere in the secrets file that
    breaks parsing entirely, a stale/revoked token) has always failed
    *silently* by design - every save still "succeeds" locally with only a
    st.toast() (or, with no token at all, an even quieter info toast) to
    say so, and a toast is easy to miss entirely on a phone mid-session.
    An angler debugging "did my save actually reach GitHub?" had no way to
    check the answer without fishing for a toast or reading this app's own
    source - this gives a persistent (not a toast), always-visible answer
    instead. Never raises, matching github_token()'s own contract."""
    token = github_token()
    if not token:
        return False, ""
    masked = f"{token[:10]}...{token[-4:]}" if len(token) > 18 else "(configured)"
    return True, masked


def anthropic_api_key() -> str:
    """API key for the Tackle Box page's "Scan a lure" photo-identify
    feature (core.lure_vision). Same graceful-degradation pattern as
    github_token() above - an empty string just means that feature stays
    hidden, not an error."""
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        return ""


def anthropic_model() -> str:
    try:
        return st.secrets.get("ANTHROPIC_MODEL", "") or None
    except Exception:
        return None
