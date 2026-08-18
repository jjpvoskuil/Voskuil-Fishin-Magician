"""Shared, cached accessors used by every Streamlit page."""
from __future__ import annotations
import streamlit as st

from .weather import fetch_forecast
from .lake_level import fetch_lake_level
from .spots import load_spots
from .storage import read_all_trips
from .calibration import calibrate_weights
from .lure_inventory import read_all_items
from .lake_spots import read_all_spots
from .dev_tasks import read_all_tasks as read_all_dev_tasks


@st.cache_data(ttl=60 * 60, show_spinner="Fetching weather forecast...")
def get_weather_bundle(days: int = 7):
    return fetch_forecast(days=days)


@st.cache_data(ttl=60 * 15, show_spinner="Fetching lake level...")
def get_lake_level():
    return fetch_lake_level()


@st.cache_data(ttl=60 * 5)
def get_spots():
    return load_spots()


@st.cache_data(ttl=60 * 5)
def get_calibrated_weights():
    trips = read_all_trips()
    return calibrate_weights(trips), len(trips)


@st.cache_data(ttl=60)
def get_inventory():
    return read_all_items()


@st.cache_data(ttl=60)
def get_lake_spots():
    return read_all_spots()


@st.cache_data(ttl=60)
def get_dev_tasks():
    return read_all_dev_tasks()


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


def anthropic_api_key() -> str:
    """API key for the Lure Inventory page's "Scan a lure" photo-identify
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
