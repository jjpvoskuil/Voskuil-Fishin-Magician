"""
Moon phase and solunar (moon rise/transit/set) calculations.

Two independent pieces, both self-contained (no external ephemeris files
or network calls needed, so this works fully offline on Streamlit Cloud):

1. Phase / illumination — uses the mean synodic month against a known
   reference new moon. Standard approach for "phase name + % illuminated".

2. Rise / transit / set times — uses Jean Meeus' widely-published low
   precision lunar position formulas (accurate to a few arc-minutes,
   which translates to roughly +/- 2-3 minutes on rise/set/transit times
   -- plenty of precision for solunar fishing windows, which are
   themselves 1-2 hour blocks).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SYNODIC_MONTH = 29.530588861
REF_NEW_MOON_JD = 2451550.1  # 2000-01-06 18:14 UTC

PHASE_NAMES = [
    (0.0, 0.033, "New Moon"),
    (0.033, 0.25, "Waxing Crescent"),
    (0.25, 0.283, "First Quarter"),
    (0.283, 0.467, "Waxing Gibbous"),
    (0.467, 0.533, "Full Moon"),
    (0.533, 0.717, "Waning Gibbous"),
    (0.717, 0.75, "Last Quarter"),
    (0.75, 0.967, "Waning Crescent"),
    (0.967, 1.001, "New Moon"),
]


def julian_day(dt_utc: datetime) -> float:
    dt_utc = dt_utc.astimezone(timezone.utc)
    y, m = dt_utc.year, dt_utc.month
    d = (
        dt_utc.day
        + dt_utc.hour / 24.0
        + dt_utc.minute / 1440.0
        + dt_utc.second / 86400.0
    )
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


@dataclass
class MoonPhase:
    age_days: float
    fraction: float          # 0=new, 0.5=full, 1=new again
    illumination_pct: float  # 0-100
    name: str
    is_new_or_full_window: bool  # within ~2 days of new or full (best fishing per solunar lore)


def moon_phase(dt_utc: datetime) -> MoonPhase:
    jd = julian_day(dt_utc)
    age = (jd - REF_NEW_MOON_JD) % SYNODIC_MONTH
    fraction = age / SYNODIC_MONTH
    illum = (1 - math.cos(2 * math.pi * fraction)) / 2 * 100
    name = next(n for lo, hi, n in PHASE_NAMES if lo <= fraction < hi)
    near_new = age <= 2 or age >= SYNODIC_MONTH - 2
    near_full = abs(age - SYNODIC_MONTH / 2) <= 2
    return MoonPhase(age, fraction, illum, name, near_new or near_full)


# ---------------------------------------------------------------------------
# Low-precision lunar ecliptic position (Meeus, "Astronomical Formulae for
# Calculators" style truncated series) -> equatorial RA/Dec -> altitude ->
# rise / transit / set via sampling + linear-interpolation root finding.
# ---------------------------------------------------------------------------

def _d2r(d):
    return d * math.pi / 180.0


def _moon_radec(jd: float):
    T = (jd - 2451545.0) / 36525.0
    Lp = 218.316 + 481267.881 * T
    M = _d2r((134.963 + 477198.867 * T) % 360)
    Msun = _d2r((357.529 + 35999.050 * T) % 360)
    D = _d2r((297.850 + 445267.111 * T) % 360)
    F = _d2r((93.272 + 483202.017 * T) % 360)

    lon = (
        Lp
        + 6.289 * math.sin(M)
        - 1.274 * math.sin(M - 2 * D)
        + 0.658 * math.sin(2 * D)
        - 0.186 * math.sin(Msun)
        - 0.059 * math.sin(2 * M - 2 * D)
        - 0.057 * math.sin(M - 2 * D + Msun)
        + 0.053 * math.sin(M + 2 * D)
        + 0.046 * math.sin(2 * D - Msun)
        + 0.041 * math.sin(M - Msun)
        - 0.035 * math.sin(D)
        - 0.031 * math.sin(M + Msun)
        - 0.015 * math.sin(2 * F - 2 * D)
        + 0.011 * math.sin(M - 4 * D)
    )
    lat = (
        5.128 * math.sin(F)
        + 0.281 * math.sin(M + F)
        - 0.278 * math.sin(F - M)
        - 0.173 * math.sin(2 * D - F)
        + 0.055 * math.sin(2 * D + F - M)
        + 0.046 * math.sin(2 * D - F - M)
        + 0.033 * math.sin(F + 2 * M)
        + 0.017 * math.sin(2 * D - M + F)
    )
    lon = _d2r(lon % 360)
    lat = _d2r(lat)

    eps = _d2r(23.439291 - 0.0130042 * T)
    ra = math.atan2(
        math.sin(lon) * math.cos(eps) - math.tan(lat) * math.sin(eps), math.cos(lon)
    )
    dec = math.asin(
        math.sin(lat) * math.cos(eps) + math.cos(lat) * math.sin(eps) * math.sin(lon)
    )
    return ra % (2 * math.pi), dec


def _gmst_hours(jd: float) -> float:
    T = (jd - 2451545.0) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * T * T
        - T ** 3 / 38710000.0
    )
    return (gmst % 360) / 15.0


def _moon_altitude(dt_utc: datetime, lat_deg: float, lon_deg: float) -> float:
    jd = julian_day(dt_utc)
    ra, dec = _moon_radec(jd)
    gmst = _gmst_hours(jd)
    lst_hours = (gmst + lon_deg / 15.0) % 24.0
    H = _d2r(lst_hours * 15.0) - ra
    lat_r = _d2r(lat_deg)
    alt = math.asin(
        math.sin(lat_r) * math.sin(dec) + math.cos(lat_r) * math.cos(dec) * math.cos(H)
    )
    return alt * 180 / math.pi


def _hour_angle_deg(dt_utc: datetime, lon_deg: float) -> float:
    jd = julian_day(dt_utc)
    ra, _ = _moon_radec(jd)
    gmst = _gmst_hours(jd)
    lst_hours = (gmst + lon_deg / 15.0) % 24.0
    H = (lst_hours * 15.0) - (ra * 180 / math.pi)
    H = (H + 180) % 360 - 180
    return H


@dataclass
class SolunarTimes:
    moonrise: datetime | None
    moon_transit: datetime | None      # "overhead" major period center
    moonset: datetime | None
    moon_underfoot: datetime | None    # opposite transit, other major period center
    major_periods: list                # list of (start, end) datetimes, ~2hr windows
    minor_periods: list                # list of (start, end) datetimes, ~1hr windows


def solunar_times(date_local, lat_deg: float, lon_deg: float, tz_offset_hours: float) -> SolunarTimes:
    """date_local: a `date` object, in the lake's local calendar day."""
    start = datetime(date_local.year, date_local.month, date_local.day, tzinfo=timezone.utc) - timedelta(
        hours=tz_offset_hours
    )
    step = timedelta(minutes=5)
    n_steps = int(timedelta(hours=30) / step)  # scan a bit past midnight to catch late events

    h0 = 0.125  # deg, standard moon rise/set altitude threshold (refraction - parallax)

    samples = []
    t = start
    for _ in range(n_steps):
        alt = _moon_altitude(t, lat_deg, lon_deg)
        H = _hour_angle_deg(t, lon_deg)
        samples.append((t, alt, H))
        t += step

    def in_window(t):
        local = t + timedelta(hours=tz_offset_hours)
        return local.date() == date_local

    rise = set_ = transit = underfoot = None
    for i in range(len(samples) - 1):
        t0, a0, h0_ha = samples[i]
        t1, a1, h1_ha = samples[i + 1]
        # rise: altitude crosses h0 going up
        if a0 < h0 <= a1 and in_window(t0):
            frac = (h0 - a0) / (a1 - a0) if a1 != a0 else 0
            rise = t0 + (t1 - t0) * frac
        if a0 >= h0 > a1 and in_window(t0):
            frac = (a0 - h0) / (a0 - a1) if a0 != a1 else 0
            set_ = t0 + (t1 - t0) * frac
        # transit: hour angle crosses 0 going from - to +
        if h0_ha < 0 <= h1_ha and in_window(t0):
            frac = (0 - h0_ha) / (h1_ha - h0_ha) if h1_ha != h0_ha else 0
            transit = t0 + (t1 - t0) * frac
        # underfoot: hour angle crosses 180/-180
        if h0_ha < 180 <= h1_ha + 360 and abs(h0_ha) > 170 and abs(h1_ha) > 170 and (h0_ha * h1_ha < 0):
            underfoot = t0 + (t1 - t0) * 0.5

    def to_local_naive(t):
        if t is None:
            return None
        return (t + timedelta(hours=tz_offset_hours)).replace(tzinfo=None)

    rise_l, set_l, transit_l, underfoot_l = (
        to_local_naive(rise), to_local_naive(set_), to_local_naive(transit), to_local_naive(underfoot)
    )

    majors, minors = [], []
    if transit_l:
        majors.append((transit_l - timedelta(hours=1), transit_l + timedelta(hours=1)))
    if underfoot_l:
        majors.append((underfoot_l - timedelta(hours=1), underfoot_l + timedelta(hours=1)))
    if rise_l:
        minors.append((rise_l - timedelta(minutes=30), rise_l + timedelta(minutes=30)))
    if set_l:
        minors.append((set_l - timedelta(minutes=30), set_l + timedelta(minutes=30)))

    return SolunarTimes(rise_l, transit_l, set_l, underfoot_l, majors, minors)
