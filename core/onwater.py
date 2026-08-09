"""
"What do you see right now" condition bands for the spot-specific fishing
session page (pages/6_Spot_Session.py) - light, wind, water visibility, and
water temperature, each broken into a small number of named bands with a
plain-language description of what that band means for the fish. The exact
thresholds and band names here were supplied directly by the user (not
derived from a public source the way most of this app's other reference
data is), based on lux/Secchi-depth/metabolic-rate ecology concepts, and
are treated as domain input the same way a hand-entered water-temp reading
is - not modeled or estimated by this app.

This module is deliberately just vocabulary + classification (what band is
a given reading in, and what does it mean) - how a band feeds the actual
1-10 activity score is core.scoring.manual_segment_score()'s job, and how
water clarity ties into the lure-color engine is core.lures' job. Keeping
the band tables here means both of those can stay simple numeric inputs on
their own end.
"""
from __future__ import annotations

from .lures import WATER_CLARITY_OPTIONS

# --- Light conditions (light penetration, lux-based) ------------------------
# Named bands rather than a raw lux number, since no angler carries a lux
# meter to the lake - pick the band that matches what you're seeing.
LIGHT_CONDITIONS = ["Night", "Crepuscular (Dawn/Dusk)", "Overcast / Diffuse Day", "Direct High Sun"]

LIGHT_CONDITION_INFO = {
    "Night":                      {"range": "< 1 lux", "detail": "Full dark - no crepuscular offset."},
    "Crepuscular (Dawn/Dusk)":    {"range": "1-1,000 lux", "detail": "Within about 45 min of the horizon."},
    "Overcast / Diffuse Day":     {"range": "1,000-10,000 lux", "detail": "Daytime, cloud-diffused light."},
    "Direct High Sun":            {"range": "> 10,000 lux", "detail": "Clear-sky daytime."},
}

# Rough average-cloud-cover-percent proxy for each light condition, so the
# same activity-score formula score_day() uses for a real forecast (which
# reacts to avg_cloud_pct >= 60) can be driven by this hand-picked band
# instead. "Night" doesn't have a meaningful daytime-cloud reading, so it's
# treated as neutral/not-cloudy for this proxy - the segment/season logic
# elsewhere already accounts for night conditions.
_LIGHT_CONDITION_CLOUD_PROXY = {
    "Night": 20.0,
    "Crepuscular (Dawn/Dusk)": 35.0,
    "Overcast / Diffuse Day": 75.0,
    "Direct High Sun": 10.0,
}


def cloud_proxy_for_light_condition(light_condition: str) -> float:
    return _LIGHT_CONDITION_CLOUD_PROXY.get(light_condition, 40.0)


# --- Wind (current/bait movement) -------------------------------------------
WIND_BANDS = [
    (0.0, 3.0, "Glassy", "Mirror surface intact."),
    (4.0, 9.0, "Light Ripple", "Breaks the surface mirror."),
    (10.0, 16.0, "Moderate Chop / Action Trigger", "Generates shoreward current."),
    (17.0, float("inf"), "Heavy / Turbulent", "Bank turbidity, bait dislocation."),
]


def wind_band(mph: float) -> dict:
    """Returns {"label", "detail"} for the wind band a given mph reading falls in."""
    for lo, hi, label, detail in WIND_BANDS:
        if lo <= mph <= hi:
            return {"label": label, "detail": detail}
    return {"label": WIND_BANDS[-1][2], "detail": WIND_BANDS[-1][3]}


# Most anglers can judge "glassy vs. light ripple vs. whitecapping" far more
# reliably by eye than they can estimate an actual mph figure, so the Spot
# Session page asks for the band by name rather than a number - this is the
# reverse lookup, a representative mph within each band, so the rest of the
# scoring formula (which is expressed in mph, same as a real forecast's
# windspeed_10m) can still be driven by that pick.
WIND_BAND_LABELS = [label for _, _, label, _ in WIND_BANDS]
_WIND_BAND_MPH_PROXY = {label: (lo + min(hi, 25.0)) / 2 for lo, hi, label, _ in WIND_BANDS}


def wind_mph_for_band(label: str) -> float:
    return _WIND_BAND_MPH_PROXY.get(label, 6.5)


# --- Water visibility (Secchi depth / sensory mode) -------------------------
VISIBILITY_BANDS = [
    (4.0, float("inf"), "Clear", "Sight-dominated hunting."),
    (1.5, 4.0, "Stained", "Power-fishing window."),
    (0.0, 1.5, "Dirty / Muddy", "Lateral line / vibration / scent take over."),
]

# The angler-supplied vocabulary here is 3 visibility bands, but core.lures'
# color tables are keyed by 4 water-clarity strings that also encode color,
# not just turbidity (Nolin's normal stain leans green-brown). "Clear" and
# "Dirty / Muddy" map 1:1; the "Stained" band is genuinely ambiguous between
# the two stained colors, so the caller (pages/6_Spot_Session.py) asks for
# the actual stain color only when a Secchi reading lands in that band.
_VISIBILITY_TO_CLARITY = {"Clear": "Clear", "Dirty / Muddy": "Muddy"}
STAIN_COLOR_OPTIONS = ["Green stained", "Brown stained"]


def visibility_band(secchi_ft: float) -> dict:
    """Returns {"label", "detail"} for the visibility band a given Secchi-depth reading falls in."""
    for lo, hi, label, detail in VISIBILITY_BANDS:
        if lo <= secchi_ft <= hi:
            return {"label": label, "detail": detail}
    return {"label": VISIBILITY_BANDS[0][2], "detail": VISIBILITY_BANDS[0][3]}


def resolve_water_clarity(secchi_ft: float, stain_color: str = None, stirred_up: bool = False) -> str:
    """Turn a Secchi-depth reading (+ a stain color, only needed when the
    reading falls in the ambiguous "Stained" band) into one of
    core.lures.WATER_CLARITY_OPTIONS for feeding the lure-color engine.

    `stirred_up` mirrors core.lures.resolve_water_clarity()'s own
    base-stain-color + stirred-up-checkbox model used elsewhere in the app:
    a "just got kicked up by wind or rain" flag always wins regardless of
    the Secchi reading, since a visual/Secchi estimate taken a bit before
    (or after) conditions changed may not reflect it yet."""
    if stirred_up:
        return "Muddy"
    band = visibility_band(secchi_ft)["label"]
    if band in _VISIBILITY_TO_CLARITY:
        return _VISIBILITY_TO_CLARITY[band]
    if stain_color in STAIN_COLOR_OPTIONS:
        return stain_color
    return "Brown stained"  # Nolin's documented normal/default stain color


assert set(_VISIBILITY_TO_CLARITY.values()) | set(STAIN_COLOR_OPTIONS) <= set(WATER_CLARITY_OPTIONS)

# --- Water temperature (metabolic state) ------------------------------------
# Informational only - core.scoring.season_stage() (day-of-year aware, and
# already what drives core.lures.recommend()'s season everywhere else in
# the app) still decides the actual season fed to the recommendation
# engine. This is a supplementary "what does this reading mean for the
# fish's metabolism" caption, shown alongside it.
WATER_TEMP_BANDS = [
    (float("-inf"), 49.999, "Cold / Lethargic", "Digestion 48-72+ hrs; no fast chase."),
    (50.0, 62.0, "Pre-Spawn Transition", "Accelerating metabolism, staging."),
    (63.0, 76.0, "Peak Optimal Prime", "Maximum feeding efficiency."),
    (77.0, 84.0, "Summer Stratified", "High metabolism, shallow O2 drop."),
    (84.001, float("inf"), "Extreme Thermal Load", "Severe oxygen stress."),
]


def water_temp_band(temp_f: float) -> dict:
    """Returns {"label", "detail"} for the metabolic band a given water-temp reading falls in."""
    for lo, hi, label, detail in WATER_TEMP_BANDS:
        if lo <= temp_f <= hi:
            return {"label": label, "detail": detail}
    return {"label": WATER_TEMP_BANDS[-1][2], "detail": WATER_TEMP_BANDS[-1][3]}


# --- Precipitation -----------------------------------------------------------
PRECIPITATION_OPTIONS = ["None", "Light rain", "Steady rain", "Heavy rain / storm"]

# (total_precip_in, max_precip_prob_pct) proxy per choice, calibrated so
# "Heavy rain / storm" crosses score_day()'s existing storm-penalty/warning
# thresholds (total_precip > 1.0 in or max_precip_prob > 85%) the same way
# a real forecast would.
_PRECIPITATION_PROXY = {
    "None": (0.0, 0.0),
    "Light rain": (0.3, 40.0),
    "Steady rain": (0.8, 70.0),
    "Heavy rain / storm": (1.5, 95.0),
}


def precipitation_proxy(precipitation: str) -> tuple:
    return _PRECIPITATION_PROXY.get(precipitation, (0.0, 0.0))
