"""
Periodic USACE surface water-quality survey (temperature + dissolved oxygen)
for Nolin River Lake, KY.

Unlike core.lake_level (a genuinely live USGS telemetry feed) and
core.weather.estimate_water_temp_f() (a model-based daily ESTIMATE), this is
a REAL measured reading - but Nolin Lake has no live water-quality sensor,
so USACE's Louisville District only publishes one every ~1-2 weeks via a
manual survey. Callers should show this as a clearly-dated secondary
reading ("last measured Aug 6"), never as a live/daily one.

Investigated and ruled out before landing here (see SESSION_NOTES.md for the
full writeup): lake-ready.com (doesn't actually publish water temp anywhere
on the site, despite the name), the modern USACE CWMS Data API (Nolin Lake
is registered but no working/documented timeseries query was found), USGS's
Water Quality Portal for the lake gauge (discontinued since 2017), and USGS
site 03311000 (live, but it's the tailwater/river gauge below the dam -
measures cooler released water, not lake surface conditions).

This legacy report page (lrl-wc.usace.army.mil) is a plain, very regular
HTML table, not a documented/versioned API - reachable fine via a real
browser and via Python's `requests`, but not via every fetcher (some tools'
fetchers hit SSL verification errors against this domain). If USACE ever
retires or restructures this page, fetch_surface_water_quality() will start
raising and home.py degrades gracefully, same as every other external
source in this app.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import re
import requests

from .lake_level import NORMAL_SUMMER_POOL_FT

USACE_WQ_REPORT_URL = "https://www.lrl-wc.usace.army.mil/reports/wq/NRR.html"

# The report profiles multiple stations top-to-bottom; "Dam Site" at 0 ft is
# the lake's own surface reading. "Tailwater" is river water already
# released below the dam - cooler, and not representative of the lake.
SURFACE_STATION_NAME = "Dam Site"
SURFACE_DEPTH_FT = "0"

# Matches one <tr><td>...</td> x5</tr> data row. The header row uses <th>
# instead of <td> so it never matches, and the report's blank <tr></tr>
# separator rows between stations have no <td>s at all, so they don't either.
_ROW_RE = re.compile(
    r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class SurfaceWaterQuality:
    observed_at: datetime
    water_temp_f: float
    do_mg_l: float
    do_saturation_pct: float
    station: str = SURFACE_STATION_NAME


def _do_saturation_concentration_mg_l(water_temp_c: float, elevation_ft: float) -> float:
    """DO saturation concentration (mg/l) for fully air-saturated water at
    this temperature and elevation - i.e. the "100%" reference point that a
    measured DO concentration is compared against.

    Standard APHA Standard Methods 4500-O / Elmore-Hayes polynomial for sea-
    level saturation as a function of temperature (deg C), times a
    barometric correction for elevation (lower pressure at altitude means
    less O2 dissolves at saturation). Hand-verified against the real Nolin
    surface reading (30.3 deg C, 10.66 mg/l DO, 515 ft elevation) during
    development: gives ~147% saturation, a plausible afternoon
    photosynthetic supersaturation reading for a warm, productive summer
    reservoir - see SESSION_NOTES.md."""
    t = water_temp_c
    cs_sea_level = 14.652 - 0.41022 * t + 0.0079910 * t**2 - 0.000077774 * t**3
    elevation_m = elevation_ft * 0.3048
    pressure_ratio = (1 - 2.25577e-5 * elevation_m) ** 5.25588
    return cs_sea_level * pressure_ratio


def fetch_surface_water_quality(url: str = USACE_WQ_REPORT_URL) -> SurfaceWaterQuality:
    """Fetches and parses USACE's periodic water-quality report, returning
    the most recent "Dam Site" surface (0 ft) reading: measured water
    temperature (converted to F) and dissolved oxygen, both as raw mg/l and
    as a computed saturation percentage.

    Raises (requests' HTTPError/ConnectionError, or ValueError if the
    expected surface row isn't found in the page) on any failure - callers
    should catch and degrade gracefully, same convention as
    core.weather.fetch_forecast() and core.lake_level.fetch_lake_level()."""
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    for station, date_time, depth, temp_c, do_mg_l in _ROW_RE.findall(resp.text):
        if station.strip() != SURFACE_STATION_NAME or depth.strip() != SURFACE_DEPTH_FT:
            continue
        observed_at = datetime.strptime(date_time.strip(), "%Y%m%d, %H%M")
        water_temp_c = float(temp_c.strip())
        do = float(do_mg_l.strip())
        cs = _do_saturation_concentration_mg_l(water_temp_c, NORMAL_SUMMER_POOL_FT)
        return SurfaceWaterQuality(
            observed_at=observed_at,
            water_temp_f=round(water_temp_c * 9 / 5 + 32, 1),
            do_mg_l=do,
            do_saturation_pct=round((do / cs) * 100, 1) if cs else 0.0,
        )
    raise ValueError(
        f"Couldn't find a '{SURFACE_STATION_NAME}' surface (0 ft) row in the USACE water-quality report."
    )
