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
