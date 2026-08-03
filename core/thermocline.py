"""
Thermocline depth for Nolin River Lake.

Nolin has no public real-time water-quality/dissolved-oxygen profile buoy we
can query for free (the USACE Louisville District's lake-profile tool -
https://www.lrl.usace.army.mil/Missions/Civil-Works/Water-Information/Water-Quality-Data/
- has live readings per lake, but it's a manual web page, not a callable API).
So this module does two things:

1. Provides a MODELED seasonal estimate (`estimate_thermocline_band_ft` /
   `estimate_thermocline_ft`), used only to pre-fill a sensible default in the
   sidebar - built from one hard data point plus general reservoir-limnology
   timing:
   - Kentucky Department of Fish and Wildlife Resources (Lee McLellan,
     "Kentucky Afield Outdoors: Find the thermocline for productive
     late-summer bass fishing," nkytribune.com, July 20 2019) reported the
     thermocline on Nolin River Lake specifically - grouped with Green
     River, Barren River, and Rough River as similar mid-depth, relatively
     clear hill-land reservoirs - at about 15 feet in mid/late July. That's
     our anchor point.
   - General stratification timing for mid-latitude, mid-depth reservoirs:
     the lake is fully mixed (isothermal, no thermocline) in winter and
     early spring, stratification sets up as surface water warms faster
     than the bottom (roughly May in KY), the thermocline is best-
     established through the hot season (June-August, matching the
     KDFWR-confirmed ~15 ft reading in July), then breaks down during fall
     turnover (roughly September-October) as nights cool and the lake
     re-mixes.
2. The actual value used for recommendations is a direct sidebar INPUT
   (`LakeSetupOptions.thermocline_ft`, in core/ui.py) - the angler's own
   electronics/temp-probe reading always wins over the seasonal estimate,
   the same way water temp and fish depth work elsewhere in this app.

Below the thermocline, dissolved oxygen typically drops too low to hold
active bass (per the same KDFWR piece) - that's the main practical use here:
flagging when a marked fish depth is likely below the oxygen-depleted zone.
"""
from __future__ import annotations
from datetime import date
from typing import Optional, Tuple

# Month -> (low, high) modeled thermocline depth band in feet, or None if the
# lake is expected to be well-mixed (no thermocline) that month. Used only to
# seed the sidebar's default value - see module docstring.
MONTHLY_THERMOCLINE_BAND_FT = {
    1: None,
    2: None,
    3: None,
    4: None,
    5: (8.0, 12.0),    # Forming - stratification just setting up as surface warms
    6: (11.0, 15.0),   # Established, still fairly shallow
    7: (13.0, 17.0),   # Peak summer - KDFWR-confirmed ~15 ft for Nolin (Jul 2019)
    8: (14.0, 19.0),   # Late summer - mixed layer deepens somewhat
    9: (17.0, 25.0),   # Early fall - breaking down, deeper and less sharply defined
    10: None,          # Fall turnover - lake fully re-mixes, thermocline dissolves
    11: None,
    12: None,
}

# Sidebar default when the model expects no stratification (lake well-mixed):
# deeper than any realistic bass presentation in this app, so the "below the
# thermocline" caveat simply won't fire unless the angler overrides it with
# their own reading.
NO_STRATIFICATION_DEFAULT_FT = 60.0


def estimate_thermocline_band_ft(the_date: date) -> Optional[Tuple[float, float]]:
    """Modeled (low, high) thermocline depth in feet for this date, or None if
    the lake is expected to be well-mixed (no stratification) that time of year."""
    return MONTHLY_THERMOCLINE_BAND_FT.get(the_date.month)


def estimate_thermocline_ft(the_date: date) -> Optional[float]:
    """Modeled single-value thermocline depth (band midpoint) for this date,
    or None if the lake is expected to be well-mixed that time of year."""
    band = estimate_thermocline_band_ft(the_date)
    if band is None:
        return None
    lo, hi = band
    return round((lo + hi) / 2, 1)


def default_thermocline_input_ft(the_date: date) -> float:
    """What to pre-fill the sidebar's thermocline number_input with: the
    modeled estimate if the lake should be stratified, otherwise a safe
    "deep enough not to matter" default."""
    estimate = estimate_thermocline_ft(the_date)
    return estimate if estimate is not None else NO_STRATIFICATION_DEFAULT_FT


def thermocline_caveat(thermocline_ft: Optional[float], fish_depth_ft: Optional[float]) -> Optional[str]:
    """If a marked fish depth reading is below the angler's set thermocline
    depth, return a caveat explaining why that's probably not active,
    oxygenated water for bass - otherwise None."""
    if thermocline_ft is None or fish_depth_ft is None:
        return None
    if fish_depth_ft > thermocline_ft:
        return (
            f"Heads up: {fish_depth_ft:.0f} ft is below the thermocline depth you've set (~{thermocline_ft:.0f} ft) - "
            f"water that deep is usually too oxygen-depleted to hold active bass. That reading may be "
            f"another species or fish just passing through; consider targeting suspended fish nearer the "
            f"thermocline itself instead."
        )
    return None
