"""
Weather data via Open-Meteo (free, no API key required).
https://open-meteo.com/en/docs

We pull an hourly forecast (temperature, pressure, cloud cover, wind,
precipitation probability) plus daily sunrise/sunset, for Nolin River
Lake's approximate center point.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests

# Approx center of Nolin River Lake at summer pool, KY (near the dam / main basin)
LAKE_LAT = 37.2783
LAKE_LON = -86.2475
LAKE_TZ = "America/Chicago"  # Nolin Lake, KY is in the Central time zone
LAKE_TZ_UTC_OFFSET_HOURS = -5  # CDT (summer); adjust to -6 for CST if needed
LAKE_ZONEINFO = ZoneInfo(LAKE_TZ)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = [
    "temperature_2m",
    "surface_pressure",
    "cloudcover",
    "windspeed_10m",
    "winddirection_10m",
    "precipitation_probability",
    "precipitation",
]
DAILY_VARS = [
    "sunrise",
    "sunset",
    "temperature_2m_max",
    "temperature_2m_min",
]

# How many real (not forecasted) past days of air-temp history to request
# alongside the forecast, so estimate_water_temp_f()'s "trailing average"
# has actual data to average even when scoring TODAY - without this,
# Open-Meteo's response starts exactly at today's local midnight with
# nothing earlier, so a request for "the last 5 days" would only ever
# have today's own not-yet-elapsed hours (or literally a single instant,
# for the very first hour of the day) to work with. See
# estimate_water_temp_f() below. This value is tuned (see
# estimate_water_temp_f()'s docstring) - it's the trailing-average WINDOW
# for that model, not just "how far back we happen to fetch," so it should
# stay 5 even though the actual API request now reaches back further (see
# HOME_TREND_CHART_PAST_DAYS below).
WATER_TEMP_TREND_PAST_DAYS = 5

# Punch-list #15: how far back home.py's "Today at a glance" trend charts
# (activity score, est. water temp, pressure trend) go. Separate constant
# from WATER_TEMP_TREND_PAST_DAYS above on purpose - that one is a tuned
# model parameter (the water-temp estimate's trailing-average window), this
# one is purely "how many points does the chart show," and conflating them
# would mean any future chart-length change quietly retunes the estimate
# model too. fetch_forecast() below requests max() of the two, so both get
# enough real past days regardless of which is larger.
HOME_TREND_CHART_PAST_DAYS = 14


@dataclass
class WeatherBundle:
    hourly: dict  # raw Open-Meteo hourly dict (parallel lists)
    daily: dict   # raw Open-Meteo daily dict (parallel lists)
    fetched_at: datetime = field(default_factory=datetime.utcnow)


def lake_today() -> date:
    """Today's calendar date AT THE LAKE (America/Chicago), not the server's
    local date. Streamlit Community Cloud runs its server clock on UTC, and
    a plain `date.today()` there is already "tomorrow" (relative to Chicago)
    for roughly 5-6 hours every day, right around UTC midnight - since
    Chicago is UTC-5/-6. fetch_forecast() requests forecast_days starting
    from the lake's own calendar day (timezone=LAKE_TZ), so scoring code
    that used a server-local date.today() as the start of that same window
    could ask for one day past the last day Open-Meteo actually returned,
    raising "No weather data available" for that last day. Use this instead
    of date.today() anywhere "today at the lake" is meant."""
    return datetime.now(LAKE_ZONEINFO).date()


def fetch_forecast(days: int = 7, lat: float = LAKE_LAT, lon: float = LAKE_LON) -> WeatherBundle:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": LAKE_TZ,
        "forecast_days": min(max(days, 1), 16),
        "past_days": max(WATER_TEMP_TREND_PAST_DAYS, HOME_TREND_CHART_PAST_DAYS),
        "temperature_unit": "fahrenheit",
        "windspeed_unit": "mph",
        "precipitation_unit": "inch",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    return WeatherBundle(hourly=payload.get("hourly", {}), daily=payload.get("daily", {}))


def hourly_rows_for_date(bundle: WeatherBundle, d: date):
    """Return list of dicts, one per hour, for the given local date."""
    times = bundle.hourly.get("time", [])
    rows = []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t)
        if dt.date() != d:
            continue
        row = {"time": dt}
        for var in HOURLY_VARS:
            vals = bundle.hourly.get(var, [])
            row[var] = vals[i] if i < len(vals) else None
        rows.append(row)
    return rows


def daily_row_for_date(bundle: WeatherBundle, d: date):
    times = bundle.daily.get("time", [])
    for i, t in enumerate(times):
        if datetime.fromisoformat(t).date() == d:
            row = {"date": d}
            for var in DAILY_VARS:
                vals = bundle.daily.get(var, [])
                val = vals[i] if i < len(vals) else None
                if var in ("sunrise", "sunset") and val:
                    val = datetime.fromisoformat(val)
                row[var] = val
            return row
    return None


def pressure_trend_hpa_per_24h(bundle: WeatherBundle, at_time: datetime) -> float:
    """Approximate 24h pressure change (hPa) centered on at_time, using surface_pressure."""
    times = [datetime.fromisoformat(t) for t in bundle.hourly.get("time", [])]
    pressures = bundle.hourly.get("surface_pressure", [])
    if not times or not pressures:
        return 0.0
    # nearest index to at_time, and nearest index ~24h earlier
    def nearest_idx(target):
        return min(range(len(times)), key=lambda i: abs((times[i] - target).total_seconds()))

    i_now = nearest_idx(at_time)
    i_prev = nearest_idx(at_time.replace(hour=at_time.hour) - timedelta(hours=24))
    p_now = pressures[i_now] if i_now < len(pressures) else None
    p_prev = pressures[i_prev] if i_prev < len(pressures) else None
    if p_now is None or p_prev is None:
        return 0.0
    return p_now - p_prev


def estimate_water_temp_f(bundle: WeatherBundle, d: date, day_of_year: int) -> float:
    """
    Rough SURFACE water-temperature estimate since Nolin Lake has no live
    buoy/sensor feed to read a real number from - see core/lake_level.py
    for the one metric on this page that *is* a genuine live measurement
    (pool elevation, not temperature). Blends a trailing average of recent
    daily HIGH air temps (lagged/offset a couple degrees, since the surface
    layer tracks the day's peak heating more than its overnight low) with a
    seasonal baseline curve for a KY reservoir. Clearly surfaced in the UI
    as an ESTIMATE, not a measurement.

    Two fixes worth calling out, both found (and their impact confirmed)
    against the angler's own real, hand-logged surface-temp readings from
    Spot Session (which run 83-89°F in mid-August 2026 - see SESSION_NOTES.md's
    punch-list #7 entry for the full before/after numbers):

    1. Uses `bundle.daily["temperature_2m_max"]` (each day's actual high),
       not a raw average of every hourly reading. Averaging in overnight
       lows dragged the number down several degrees - a lake's surface
       layer responds to net daily heating, not the pre-dawn low, and
       fetch_forecast() requesting WATER_TEMP_TREND_PAST_DAYS of real past
       days (not just forecast) means there's now genuine multi-day history
       to average even when estimating TODAY's temperature, not just days
       several days out into the forecast window.
    2. The seasonal curve's peak/amplitude were retuned against those real
       readings - the old curve topped out at 84°F on its best day, already
       below several real August readings, and peaked around day 196
       (mid-July) rather than reflecting a reservoir's actual thermal lag
       into early August. Still just a best-effort model outside the window
       this one summer's data actually covers (no real cold-season ground
       truth exists yet to check the curve elsewhere) - a good future
       improvement once trips get logged across more of the year.
    """
    daily_times = [datetime.fromisoformat(t).date() for t in bundle.daily.get("time", [])]
    daily_highs = bundle.daily.get("temperature_2m_max", [])
    window_start = d - timedelta(days=WATER_TEMP_TREND_PAST_DAYS)
    window_vals = [
        daily_highs[i] for i, dd in enumerate(daily_times)
        if window_start <= dd < d and i < len(daily_highs) and daily_highs[i] is not None
    ]
    high_avg = sum(window_vals) / len(window_vals) if window_vals else None

    # Seasonal baseline (rough, KY reservoir climatology), keyed by day-of-year -
    # peak ~87°F around day 215 (early August), trough ~33°F around day 32
    # (early February).
    import math
    seasonal = 60 + 27 * math.sin(2 * math.pi * (day_of_year - 124) / 365.0)

    if high_avg is None:
        return round(seasonal, 1)
    # Water lags/damps air's daily peak - blend 45% recent daily-high trend
    # (offset a few degrees cooler than the air's own peak), 55% seasonal norm.
    blended = 0.45 * (high_avg - 3) + 0.55 * seasonal
    return round(blended, 1)
