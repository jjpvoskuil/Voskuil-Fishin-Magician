"""
Modeled thermocline depth for Nolin River Lake.

Nolin has no public real-time water-quality/dissolved-oxygen profile buoy we
can query for free (the USACE Louisville District's lake-profile tool -
https://www.lrl.usace.army.mil/Missions/Civil-Works/Water-Information/Water-Quality-Data/
- has live readings per lake, but it's a manual web page, not a callable API).
So, like the modeled bathymetry, this is a clearly-labeled MODEL, not a live
measurement - built from one hard data point plus general reservoir-limnology
timing:

- Kentucky Department of Fish and Wildlife Resources (Lee McLellan, "Kentucky
  Afield Outdoors: Find the thermocline for productive late-summer bass
  fishing," nkytribune.com, July 20 2019) reported the thermocline on
  Nolin River Lake specifically - grouped with Green River, Barren River, and
  Rough River as similar mid-depth, relatively clear hill-land reservoirs -
  at about 15 feet in mid/late July. That's our anchor point.
- General stratification timing for mid-latitude, mid-depth reservoirs: the
  lake is fully mixed (isothermal, no thermocline) in winter and early
  spring, stratification sets up as surface water warms faster than the
  bottom (roughly May in KY), the thermocline is best-established through
  the hot season (June-August, matching the KDFWR-confirmed ~15 ft reading
  in July), then breaks down during fall turnover (roughly September-
  October) as nights cool and the lake re-mixes.

Below the thermocline, dissolved oxygen typically drops too low to hold
active bass (per the same KDFWR piece) - that's the main practical use here:
flagging when a marked fish depth is likely below the oxygen-depleted zone.
"""
from __future__ import annotations
from datetime import date
from typing import Optional, Tuple

# Month -> (low, high) modeled thermocline depth band in feet, or None if the
# lake is expected to be well-mixed (no thermocline) that month.
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


def estimate_thermocline_band_ft(the_date: date) -> Optional[Tuple[float, float]]:
    """Modeled (low, high) thermocline depth in feet for this date, or None if
    the lake is expected to be well-mixed (no stratification) that time of year."""
    return MONTHLY_THERMOCLINE_BAND_FT.get(the_date.month)


def thermocline_caveat(band: Optional[Tuple[float, float]], fish_depth_ft: Optional[float]) -> Optional[str]:
    """If a marked fish depth reading is below the modeled thermocline band,
    return a caveat explaining why that's probably not active, oxygenated
    water for bass - otherwise None."""
    if band is None or fish_depth_ft is None:
        return None
    lo, hi = band
    if fish_depth_ft > hi:
        return (
            f"Heads up: {fish_depth_ft:.0f} ft is below the modeled thermocline (~{lo:.0f}-{hi:.0f} ft) - "
            f"water that deep is usually too oxygen-depleted to hold active bass this time of year. That "
            f"reading may be another species or fish just passing through; consider targeting suspended "
            f"fish nearer the thermocline itself instead."
        )
    return None
