"""
Weather data via Open-Meteo (free, no API key required).
https://open-meteo.com/en/docs

We pull an hourly forecast (temperature, pressure, cloud cover, wind,
precipitation probability) plus daily sunrise/sunset, for Nolin River
Lake's approximate center point.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
import requests

# Approx center of Nolin River Lake at summer pool, KY (near the dam / main basin)
LAKE_LAT = 37.2783
LAKE_LON = -86.2475
LAKE_TZ = "America/Chicago"  # Nolin Lake, KY is in the Central time zone
LAKE_TZ_UTC_OFFSET_HOURS = -5  # CDT (summer); adjust to -6 for CST if needed

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


@dataclass
class WeatherBundle:
    hourly: dict  # raw Open-Meteo hourly dict (parallel lists)
    daily: dict   # raw Open-Meteo daily dict (parallel lists)
    fetched_at: datetime = field(default_factory=datetime.utcnow)


def fetch_forecast(days: int = 7, lat: float = LAKE_LAT, lon: float = LAKE_LON) -> WeatherBundle:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": LAKE_TZ,
        "forecast_days": min(max(days, 1), 16),
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
    i_prev = nearest_idx(at_time.replace(hour=at_time.hour) - __import__("datetime").timedelta(hours=24))
    p_now = pressures[i_now] if i_now < len(pressures) else None
    p_prev = pressures[i_prev] if i_prev < len(pressures) else None
    if p_now is None or p_prev is None:
        return 0.0
    return p_now - p_prev


def estimate_water_temp_f(bundle: WeatherBundle, d: date, day_of_year: int) -> float:
    """
    Rough water-temperature estimate since Nolin Lake has no live buoy feed.
    Blends a 5-day trailing average of air temps (lagged, since water warms/cools
    slower than air) with a seasonal baseline curve for a KY reservoir.
    This is clearly surfaced in the UI as an ESTIMATE, not a measurement.
    """
    times = [datetime.fromisoformat(t) for t in bundle.hourly.get("time", [])]
    temps = bundle.hourly.get("temperature_2m", [])
    if times:
        window_start = datetime.combine(d, datetime.min.time()) - __import__("datetime").timedelta(days=5)
        window_vals = [temps[i] for i, t in enumerate(times) if window_start <= t <= datetime.combine(d, datetime.min.time())]
        air_avg = sum(window_vals) / len(window_vals) if window_vals else None
    else:
        air_avg = None

    # Seasonal baseline (rough, KY reservoir climatology), keyed by day-of-year
    import math
    seasonal = 60 + 24 * math.sin(2 * math.pi * (day_of_year - 105) / 365.0)

    if air_avg is None:
        return round(seasonal, 1)
    # Water lags/damps air temp - blend 45% recent air trend (offset cooler than air), 55% seasonal norm
    blended = 0.45 * (air_avg - 4) + 0.55 * seasonal
    return round(blended, 1)
