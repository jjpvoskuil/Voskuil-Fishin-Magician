"""
"What do you see right now" condition bands for the spot-specific fishing
session page (pages/6_Spot_Session.py) - sky/cloud cover, wind, water
visibility, and water temperature, each broken into a small number of named
bands with a plain-language description of what that band means for the
fish. Most of the exact thresholds and band names here were supplied
directly by the user (not derived from a public source the way most of this
app's other reference data is), based on Secchi-depth/metabolic-rate
ecology concepts, and are treated as domain input the same way a
hand-entered water-temp reading is - not modeled or estimated by this app.
The sky-condition bands below are the one exception: they follow the
National Weather Service's own published oktas-based sky-condition
terminology (see LIGHT_CONDITIONS below for the source), rather than a
purely hand-picked scale, since "how cloudy does the sky look" is a
question with an existing public standard to borrow from.

This module is deliberately just vocabulary + classification (what band is
a given reading in, and what does it mean) - how a band feeds the actual
1-10 activity score is core.scoring.manual_segment_score()'s job, and how
water clarity ties into the lure-color engine is core.lures' job. Keeping
the band tables here means both of those can stay simple numeric inputs on
their own end.
"""
from __future__ import annotations

from .lures import WATER_CLARITY_OPTIONS

# --- Sky conditions (cloud cover) --------------------------------------------
# Punch-list #10: the original 4-option scale here ("Night", "Crepuscular
# (Dawn/Dusk)", "Overcast / Diffuse Day", "Direct High Sun") mixed two
# different things into one field - time-of-day light level (which the
# separate "Time window" dropdown already captures via segment_name, see
# pages/6_Spot_Session.py's _guess_segment()) and actual cloud cover (this
# field's only real downstream use - see cloud_proxy_for_light_condition()
# below). That conflation produced a real, if minor, scoring oddity: "Night"
# mapped to a cloud proxy of 20.0, which used to fall in the "clear/bright
# bluebird tough-bite" penalty range below (avg_cloud <= 25 in
# core.scoring._segment_score()) - a penalty whose whole rationale is glare/
# high-sun visibility, nonsensical to apply in full darkness.
#
# Replaced with the National Weather Service's own published sky-condition
# terminology (oktas - eighths of the sky covered by opaque clouds; see
# NOAA's forecast glossary, https://forecast.weather.gov/glossary.php?word=sky+condition):
# Clear/Sunny (0/8), Mostly Clear/Mostly Sunny (1-2/8), Partly Cloudy/Partly
# Sunny (3-4/8), Mostly Cloudy (5-7/8), Cloudy/Overcast (8/8) - a real public
# standard for exactly the "how cloudy does the sky look" question an
# angler can judge by eye, and (unlike the old scale) purely about cloud
# cover, not time of day - a clear night sky and a clear midday sky now both
# just read "Clear / Sunny."
LIGHT_CONDITIONS = ["Clear / Sunny", "Mostly Clear", "Partly Cloudy", "Mostly Cloudy", "Overcast"]

LIGHT_CONDITION_INFO = {
    "Clear / Sunny":  {"range": "0/8 oktas (~0% cloud)",   "detail": "No clouds, or so few they don't matter."},
    "Mostly Clear":   {"range": "1-2/8 oktas (~10-25%)",   "detail": "A few scattered clouds, mostly open sky."},
    "Partly Cloudy":  {"range": "3-4/8 oktas (~35-50%)",   "detail": "A mix of sun and clouds, roughly half and half."},
    "Mostly Cloudy":  {"range": "5-7/8 oktas (~60-90%)",   "detail": "Sun mostly blocked, patches of blue at most."},
    "Overcast":       {"range": "8/8 oktas (100%)",        "detail": "Solid cloud deck, no direct sun anywhere."},
}

# Average-cloud-cover-percent proxy for each sky condition, so the same
# activity-score formula score_day() uses for a real forecast (which reacts
# to avg_cloud_pct >= 60 for an "overcast" bonus and <= 25 for a "clear/
# bright bluebird" penalty - see core.scoring._segment_score()) can be
# driven by this hand-picked band instead. Values are each band's real
# okta-range midpoint (see LIGHT_CONDITIONS above) converted to a percent,
# chosen so the bands land on the correct side of both of those thresholds:
# Clear/Sunny and Mostly Clear both fall at or under the 25% clear-sky
# threshold, Mostly Cloudy and Overcast both clear the 60% overcast
# threshold, and Partly Cloudy sits deliberately in the neutral middle -
# same three-way split a real forecast's cloudcover reading would produce.
_LIGHT_CONDITION_CLOUD_PROXY = {
    "Clear / Sunny": 5.0,
    "Mostly Clear": 20.0,
    "Partly Cloudy": 45.0,
    "Mostly Cloudy": 75.0,
    "Overcast": 95.0,
}


def cloud_proxy_for_light_condition(light_condition: str) -> float:
    return _LIGHT_CONDITION_CLOUD_PROXY.get(light_condition, 40.0)


# Reverse of the proxy table above - lets the Spot Session page default its
# "Sky condition" picker from a live forecast's cloudcover percentage
# (core.weather's hourly_rows_for_date()) instead of a hardcoded literal,
# while still leaving the field a normal overridable selectbox. Boundaries
# are the midpoints between each pair of proxy values above (5/20/45/75/95),
# so a cloud_pct that exactly matches a band's own proxy always rounds back
# to that same band.
def light_condition_for_cloud_pct(cloud_pct: float) -> str:
    """Buckets a live cloudcover percentage (0-100) into one of LIGHT_CONDITIONS."""
    if cloud_pct is None:
        return LIGHT_CONDITIONS[2]  # Partly Cloudy - neutral fallback
    if cloud_pct <= 12.5:
        return "Clear / Sunny"
    if cloud_pct <= 32.5:
        return "Mostly Clear"
    if cloud_pct <= 60.0:
        return "Partly Cloudy"
    if cloud_pct <= 85.0:
        return "Mostly Cloudy"
    return "Overcast"


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


# 8-point compass, plus the two common "no clean direction" cases an angler
# actually needs to log after the fact - used only for the per-lure result
# entry on the Spot Session page (distinct from the plain-language WIND_BANDS
# picker above, which drives the live score instead of being a logged fact).
WIND_DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "Variable", "Calm"]

_COMPASS_POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def wind_direction_for_degrees(deg: float) -> str:
    """Buckets a live wind-direction reading (degrees, meteorological
    convention - 0/360=N, 90=E, etc., matching Open-Meteo's winddirection_10m)
    into one of the 8 compass points in WIND_DIRECTIONS. Each point covers a
    45-degree sector centered on itself (e.g. "N" is 337.5-22.5).

    Only returns a compass point or "Variable" for a missing reading - it has
    no way to know the wind is calm from direction alone, so callers that
    want to default to "Calm" should check the paired wind-speed reading
    themselves (e.g. treat anything under ~2 mph as calm) before falling
    back to this function."""
    if deg is None:
        return "Variable"
    idx = int(((deg % 360) + 22.5) // 45) % 8
    return _COMPASS_POINTS[idx]


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


# Reverse of the proxy table above - lets the Spot Session page default its
# "Precipitation" picker from a live forecast's hourly precipitation amount
# + probability (core.weather's hourly_rows_for_date()) instead of always
# defaulting to "None". Boundaries are the midpoints between each pair of
# proxy values above for both signals (in: 0.0/0.3/0.8/1.5, prob:
# 0/40/70/95); either signal alone crossing its threshold is enough to bump
# the bucket, since a forecast can show a confident probability with a low
# modeled amount (or vice versa) and either should be enough to warn an
# angler checking the default before heading out.
def precipitation_option_for_forecast(precip_in: float, precip_prob_pct: float) -> str:
    """Buckets a live precipitation amount (inches) + probability (0-100)
    into one of PRECIPITATION_OPTIONS."""
    precip_in = precip_in or 0.0
    precip_prob_pct = precip_prob_pct or 0.0
    if precip_in >= 1.15 or precip_prob_pct >= 82.5:
        return "Heavy rain / storm"
    if precip_in >= 0.55 or precip_prob_pct >= 55.0:
        return "Steady rain"
    if precip_in >= 0.15 or precip_prob_pct >= 20.0:
        return "Light rain"
    return "None"
