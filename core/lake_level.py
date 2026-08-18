"""
Real-time Nolin Lake pool elevation via USGS Water Services
(waterservices.usgs.gov) - free, no API key required, same "no key
required" convention as core.weather's Open-Meteo integration.

Unlike water temperature (core.scoring.estimate_water_temp_f - Nolin Lake
has no public water-temp sensor, so that stays a model-based ESTIMATE),
lake level is a genuine live measurement: USGS gauge 03310900 ("Nolin Lake
near Kyrock, KY") reports the reservoir's actual real-time pool elevation,
telemetered every few minutes. Confirmed live against the real USGS API
before wiring this in - see SESSION_NOTES.md's punch-list #7 entry.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import requests

# "Nolin Lake near Kyrock, KY" - the USGS gauge actually on the lake pool
# itself (as opposed to the separate downstream river gauges at White Mills/
# Kyrock, which report river stage below the dam, not lake elevation).
USGS_SITE_ID = "03310900"

# "Lake or reservoir water surface elevation above NGVD 1929, ft" - the one
# parameter of the three this site reports (alongside gage height and
# precipitation) that's actually the lake's own pool elevation.
USGS_LAKE_ELEVATION_PARAM_CD = "62614"

USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"

# USACE's published normal/summer pool elevation for Nolin Lake - same
# figure already quoted in this app's own footer caption (home.py) and
# README, used here just to label how the live reading compares.
NORMAL_SUMMER_POOL_FT = 515.0


@dataclass
class LakeLevel:
    elevation_ft: float
    observed_at: datetime
    site_name: str


def fetch_lake_level(site_id: str = USGS_SITE_ID) -> LakeLevel:
    """Fetches the most recent real-time pool elevation reading for
    `site_id`. Raises (requests' HTTPError, KeyError/IndexError on an
    unexpected payload shape, or ValueError if the site returned zero
    readings) on any failure - callers should catch and degrade
    gracefully, same convention as core.weather.fetch_forecast()."""
    resp = requests.get(
        USGS_IV_URL,
        params={
            "sites": site_id,
            "format": "json",
            "period": "P1D",
            "parameterCd": USGS_LAKE_ELEVATION_PARAM_CD,
        },
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    series = payload["value"]["timeSeries"][0]
    site_name = series["sourceInfo"]["siteName"]
    values = series["values"][0]["value"]
    if not values:
        raise ValueError(f"USGS site {site_id} returned no lake elevation readings.")
    latest = values[-1]
    return LakeLevel(
        elevation_ft=round(float(latest["value"]), 2),
        observed_at=datetime.fromisoformat(latest["dateTime"]),
        site_name=site_name,
    )
