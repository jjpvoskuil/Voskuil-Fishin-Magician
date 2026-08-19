"""
Vocabulary + small helpers for the "Log actual activity" section of
pages/6_Spot_Session.py - describing what actually happened during a
session (lure/trailer picked from inventory or entered by hand, how it was
fished, how active the fish/forage were). This is deliberately separate
from core/onwater.py, which describes the conditions going INTO a
suggestion rather than the outcome of fishing it.

None of this needs its own storage schema - pages/6_Spot_Session.py packs
it into core.storage.TripEntry's existing flexible `conditions` dict
(serialized as JSON), the same way spot-session-specific fields like
`modeled_thermocline_ft` already are, so no changes to core/storage.py or
the trip_log.csv column layout were needed to add it.
"""
from __future__ import annotations

import re
from typing import Optional

from .lures import LURE_PROFILES

# Sentinel option in the lure/trailer inventory pickers meaning "not in my
# inventory - let me type it in instead."
OTHER_LABEL = "Other / not in inventory (enter manually)"


def inventory_item_label(item: dict) -> str:
    """Human-readable label for one inventory row, used in both the lure
    and trailer pickers."""
    brand = (item.get("brand") or "").strip()
    description = (item.get("description") or "").strip()
    label = " - ".join(p for p in (brand, description) if p)
    return label or item.get("item_id") or "Unnamed item"


def lure_picker_options(inventory: list) -> tuple:
    """Returns (labels, items) for a selectbox covering the whole
    inventory plus OTHER_LABEL as the first choice. `items[i]` is the
    inventory row `labels[i]` refers to, or None for the OTHER_LABEL slot -
    so callers can index back into the original row with the same index
    the selectbox returns."""
    items = [None] + list(inventory)
    labels = [OTHER_LABEL] + [inventory_item_label(it) for it in inventory]
    return labels, items


def lure_can_take_trailer(item: dict) -> bool:
    """Whether the trailer picker is worth showing for this lure. True
    (show it) unless we have positive proof this lure category never takes
    a trailer (core.lures.LURE_PROFILES marks crankbaits/jerkbaits/
    topwaters etc. with trailer=None) - defaults to True for a manually-
    entered lure or an uncategorized/unrecognized inventory item, since
    hiding a trailer option that might actually apply is worse than
    showing one that doesn't."""
    if item is None:
        return True
    profile = LURE_PROFILES.get(item.get("category"))
    if profile is None:
        return True
    return profile.get("trailer") is not None


# --- "How it was fished" / outcome vocabulary --------------------------------
DEPTH_MODES = ["Single depth", "Varied / multiple depths"]

FISH_ACTIVITY_OPTIONS = ["Very active", "Active", "Moderate", "Sluggish", "Inactive / shut down"]

FORAGE_ACTIVITY_OPTIONS = [
    "None seen", "Sparse / scattered", "Moderate", "Active / schooling", "Frenzied (busting bait)",
]

RETRIEVE_SPEED_OPTIONS = ["Slow", "Medium", "Fast"]

RETRIEVE_STYLE_OPTIONS = [
    "Straight retrieve (no action)", "Twitch", "Jerk", "Stop-and-go", "Slow-roll",
    "Burn (fast retrieve)", "Hop / drag (bottom contact)", "Deadstick (no movement)",
]

# Per-fish species picker for individual catch records - the angler's own
# on-the-water categorization, not a strict biological survey list. Replaced
# (Spot Session redesign) with the exact 6-species list the angler asked
# for; "Other" is kept as a trailing catch-all so anything not on the list
# is still free-text-extensible rather than unrepresentable.
FISH_SPECIES_OPTIONS = [
    "Largemouth Bass", "White Bass", "Crappie", "Smallmouth Bass", "Walleye", "Catfish",
    "Other (type in species)",
]

# Multiple-choice "how did the fish take it" picker for individual catch
# records (Spot Session redesign) - a fish can legitimately match more than
# one of these in the same strike (e.g. a "light hit" that turned out
# "fouled"), so the Spot Session page presents this as a multiselect rather
# than a single dropdown.
HIT_TYPE_OPTIONS = ["Hard hit", "Light hit", "Double tap", "Swallowed", "Fouled", "Surface hit"]

# Weight/length pickers for individual catch records (Spot Session
# redesign) - presented as st.select_slider bands rather than raw number
# inputs, since a rod-side fish entry is faster/easier to do by eye/feel
# against a short labeled scale than by typing a precise decimal. Same
# representative-value-per-band approach core.onwater's wind_mph_for_band()/
# precipitation_proxy() already use for their own hand-picked pickers - see
# weight_lb_for_slider_option()/length_in_for_slider_option() below for the
# reverse mapping back to the decimal lb/in this app stores everywhere else.
WEIGHT_SLIDER_OPTIONS = ["<1 lb", "1 lb", "2 lb", "3 lb", "4 lb", "5 lb", "6 lb", "7 lb", "8 lb", "9 lb", "10 lb"]

LENGTH_SLIDER_OPTIONS = [
    "<13 in", "13 in", "14 in", "15 in", "16 in", "17 in", "18 in", "19 in", "20 in",
    "21 in", "22 in", "23 in", "24 in", "25 in", "26+ in",
]


def weight_lb_for_slider_option(option) -> Optional[float]:
    """Converts one of WEIGHT_SLIDER_OPTIONS to a decimal-pound value for
    storage (core.storage.TripEntry / Trip History's existing decimal-lb
    schema, same as the old "Weight (lb)" number input used). "<1 lb" stores
    as 0.5 lb (that open-low-end band's representative value) - every other
    option is already a literal whole-pound reading. Returns None for a
    blank/unrecognized option."""
    if not option:
        return None
    s = str(option).strip().lower().replace("lb", "").strip()
    if s == "<1":
        return 0.5
    try:
        return float(s)
    except ValueError:
        return None


def length_in_for_slider_option(option) -> Optional[float]:
    """Converts one of LENGTH_SLIDER_OPTIONS to a decimal-inch value for
    storage, same representative-value approach as
    weight_lb_for_slider_option() above. "<13 in" stores as 12.0 in and
    "26+ in" stores as 27.0 in (each band's representative value); every
    other option is already a literal whole-inch reading. Returns None for a
    blank/unrecognized option."""
    if not option:
        return None
    s = str(option).strip().lower().replace("in", "").strip()
    if s == "<13":
        return 12.0
    if s.endswith("+"):
        try:
            return float(s[:-1].strip()) + 1.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


# --- Weight display: decimal lb (how it's entered/stored) <-> lb-oz (how it's
# shown in Trip History, since that's how most anglers actually think/talk
# about a fish's weight) ------------------------------------------------------
def format_weight_lb_oz(weight_lb) -> str:
    """Render a decimal-pound weight (as stored in trip_log.csv/
    conditions_json - the Add fish form's "Weight (lb)" input is still plain
    decimal) as a lb-oz string, e.g. 3.53 -> "3 lb 8 oz". Rounds to the
    nearest ounce - fish weight was never recorded to hundredths-of-a-pound
    precision to begin with, so this loses nothing meaningful. Returns "" for
    None/blank/zero (no real reading)."""
    try:
        w = float(weight_lb)
    except (TypeError, ValueError):
        return ""
    if w != w or w <= 0:  # w != w is the NaN check (pandas passes NaN for a blank cell)
        return ""
    total_oz = round(w * 16)
    lb, oz = divmod(total_oz, 16)
    if lb and oz:
        return f"{lb} lb {oz} oz"
    if lb:
        return f"{lb} lb"
    return f"{oz} oz"


def parse_weight_lb_oz(text) -> Optional[float]:
    """Parse a lb-oz string back into decimal pounds for storage. Accepts:
    "3 lb 8 oz"/"3lb 8oz" (as produced by format_weight_lb_oz, or hand-typed
    into Trip History's inline-editable grid), "3 - 8" (the Spot Session "Add
    fish" form's own manual weight field, item #2 on the Development punch
    list - a single dash-separated lb/oz field with no +/- steppers), "3 8"
    (space-separated, same idea without the dash), or a plain decimal like
    "3.5" (so pasting/typing an old-style value still works). Returns None
    for anything blank or unparseable, matching every other optional-
    numeric-field convention in this app."""
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    lb_match = re.search(r"(\d+(?:\.\d+)?)\s*lb", s)
    oz_match = re.search(r"(\d+(?:\.\d+)?)\s*oz", s)
    if lb_match or oz_match:
        lb = float(lb_match.group(1)) if lb_match else 0.0
        oz = float(oz_match.group(1)) if oz_match else 0.0
        return round(lb + oz / 16, 4)
    # "3 - 8" (dash-separated) or "3 8" (space-separated) lb/oz shorthand -
    # two plain numbers, first is lb, second is oz (must be < 16, or this
    # isn't really an oz value and the plain-decimal fallback below applies
    # instead - e.g. "3 - 20" isn't a valid lb-oz pair).
    dash_parts = [p for p in re.split(r"-", s) if p.strip()]
    parts = dash_parts if len(dash_parts) == 2 else s.split()
    if len(parts) == 2:
        try:
            lb, oz = float(parts[0].strip()), float(parts[1].strip())
            if 0 <= oz < 16:
                return round(lb + oz / 16, 4)
        except ValueError:
            pass
    try:
        return round(float(s), 4)
    except ValueError:
        return None
