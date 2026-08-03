"""Shared, cached accessors used by every Streamlit page."""
from __future__ import annotations
import streamlit as st

from .weather import fetch_forecast
from .spots import load_spots
from .storage import read_all_trips
from .calibration import calibrate_weights
from .lure_inventory import read_all_items


@st.cache_data(ttl=60 * 60, show_spinner="Fetching weather forecast...")
def get_weather_bundle(days: int = 7):
    return fetch_forecast(days=days)


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
