"""
Lure / color / trailer / depth / presentation recommendation engine for
largemouth bass on Nolin River Lake.

Design: each lure is a self-contained profile (LURE_PROFILES) carrying its
own colors-by-water-condition, trailer (type + color, if one is typically
used with that lure), depth to run, and presentation style. Separately,
situational rules (season, segment/light level, pressure trend, structure
type, water condition) pick which lure keys are the "first choice" picks
for that exact situation, and which are solid "second choice" alternates -
this is where crankbaits, jerkbaits, and topwater show up across more
conditions than just their single best-case scenario.

Water condition model: Nolin Lake normally runs a greenish-brown stain
(leaning brown), but wind/rain can stir it up to muddy regardless of the
usual color. So the UI captures two independent things - a base stain
color (Clear / Green stained / Brown stained) and a separate "stirred up"
flag - and this module resolves them to one of four color-table keys:
"Clear", "Green stained", "Brown stained", or "Muddy".

`recommend()` returns a LureRecommendation with `first_choice` and
`second_choice` lists of fully-resolved LureBlock objects - everything
needed to render one self-contained block per lure (name, colors,
trailer, depth, presentation, and a couple of how-to videos).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from .videos import get_videos_by_key
from .thermocline import thermocline_caveat
from .lure_history import lure_track_records, track_record_note

# Base stain color the angler picks (Nolin runs greenish-brown, leaning brown,
# under normal conditions - "Brown stained" is the default). A separate
# "stirred up" flag (wind/rain) overrides to "Muddy" regardless of base color.
BASE_STAIN_OPTIONS = ["Clear", "Green stained", "Brown stained"]
DEFAULT_BASE_STAIN = "Brown stained"

# Full set of resolved water-condition keys used to look up lure colors.
WATER_CLARITY_OPTIONS = ["Clear", "Green stained", "Brown stained", "Muddy"]

# Punch-list #8: "if you show options from my inventory, only show the top 2
# recommendations in each category... with a #1 and a #2 choice" - caps how
# many color-matched owned items a single LureBlock ever carries, regardless
# of how many actually match. See _color_matched_owned_items() below for the
# ranking (most on-hand stock first) used to pick which ones are "top."
MAX_OWNED_ITEMS_PER_BLOCK = 2

STRUCTURE_TYPES = [
    "Main-lake point",
    "Creek channel / ledge",
    "Cove / pocket (shallow cover)",
    "Flat",
    "Standing timber",
    "Riprap / dam face",
    "Bridge piling",
    "Boat dock",
]

LIGHT_LOW = {"Dawn", "Dusk", "Night"}

# Forage types actually present/available in Nolin Lake. Gizzard shad and
# bluegill are both explicitly documented as forage base here (KDFWR/Kentucky
# Afield Outdoors coverage of Nolin bass fishing calls gizzard shad the main
# forage fish, with bluegill also serving as forage) - those two are the
# default selection. Crawfish and shiners/minnows are near-universal
# secondary forage in Kentucky hill-land reservoirs (craw-pattern jig/worm
# colors are standard advice for exactly this lake type) and are offered as
# optional add-ons rather than defaults, since they're less specifically
# documented for Nolin itself. Threadfin shad are also a common reservoir
# baitfish, but (unlike gizzard shad) aren't specifically documented for
# Nolin in the sources used elsewhere in this app, and they're more
# cold-sensitive than gizzard shad, so they're offered as an optional
# add-on rather than a default - check it if you're actually seeing them.
# Stonerollers (small bottom-grazing minnows around gravel/rock) are a
# similar optional add-on - present in Kentucky hill-land reservoir
# tributaries generally, but not a documented Nolin-specific default.
FORAGE_OPTIONS = ["Gizzard Shad", "Threadfin Shad", "Bluegill / Sunfish", "Crawfish", "Shiners / Minnows", "Stonerollers"]
DEFAULT_FORAGE = ["Gizzard Shad", "Bluegill / Sunfish"]

# Short, forage-specific color/pattern guidance surfaced in the rationale.
FORAGE_NOTES = {
    "Gizzard Shad": (
        "Shad are in play - lean on shad-imitating colors (chrome/pearl/white, "
        "blue-back) on reaction baits."
    ),
    "Threadfin Shad": (
        "Threadfin shad are in play - similar to gizzard shad but smaller and slimmer; lean on "
        "smaller shad-imitating profiles/colors (chrome/pearl/white, blue-back) on reaction baits."
    ),
    "Bluegill / Sunfish": (
        "Bluegill are in play - bream-pattern colors (green pumpkin, orange belly, "
        "black/blue) shine around bedding areas, docks, and bluegill cover."
    ),
    "Crawfish": (
        "Crawfish are in play - craw patterns (green pumpkin, brown, red/orange) "
        "excel on bottom-contact baits deflecting off rock/wood, especially in cooler water."
    ),
    "Shiners / Minnows": (
        "Shiners/minnows are in play - natural, translucent, silver patterns on "
        "finesse baits match them well, especially in clearer water."
    ),
    "Stonerollers": (
        "Stonerollers are in play - these are small, dark, bottom-grazing minnows found around "
        "gravel/rock (creek arms, riprap, tributary mouths); dark natural/brown minnow patterns on "
        "bottom-contact or bottom-hugging baits match them well."
    ),
}

# Lure keys that most directly imitate each forage type - used to make sure at
# least one forage-matched option shows up even if the seasonal pattern
# didn't happen to include one.
FORAGE_LURE_BOOST = {
    "Gizzard Shad": ["lipless_crankbait", "spinnerbait", "suspending_jerkbait",
                      "squarebill_crankbait", "deep_diving_crankbait", "swim_jig", "soft_swimbait"],
    "Threadfin Shad": ["lipless_crankbait", "spinnerbait", "suspending_jerkbait",
                        "squarebill_crankbait", "medium_diving_crankbait", "swim_jig", "soft_swimbait"],
    "Bluegill / Sunfish": ["swim_jig", "walking_topwater", "popper",
                            "squarebill_crankbait", "chatterbait"],
    "Crawfish": ["football_jig", "texas_rig_creature", "carolina_rig", "squarebill_crankbait"],
    "Shiners / Minnows": ["finesse_shaky_head", "wacky_rig_senko", "suspending_jerkbait",
                           "weightless_soft_plastic"],
    "Stonerollers": ["football_jig", "carolina_rig", "finesse_shaky_head", "squarebill_crankbait"],
}


def resolve_water_clarity(base_stain: str, stirred_up: bool) -> str:
    """Combine the base stain color + stirred-up flag into one effective key."""
    if stirred_up:
        return "Muddy"
    return base_stain if base_stain in BASE_STAIN_OPTIONS else DEFAULT_BASE_STAIN


# ---------------------------------------------------------------------------
# Lure library: one profile per lure, independent of any specific day/segment.
# ---------------------------------------------------------------------------
LURE_PROFILES = {
    "football_jig": {
        "name": "Football Jig",
        "video_key": "football_jig",
        "vertical_style": "bottom",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon red"],
            "Green stained": ["Green pumpkin/chartreuse", "Brown/chartreuse"],
            "Brown stained": ["Brown/orange", "Red craw"],
            "Muddy": ["Black/blue", "Junebug"],
        },
        "trailer": {
            "type": "Craw trailer",
            "colors": {
                "Clear": ["Green pumpkin", "Watermelon red"],
                "Green stained": ["Green pumpkin chartreuse-tip", "Chartreuse"],
                "Brown stained": ["Brown/orange", "Red craw"],
                "Muddy": ["Black/blue", "Black"],
            },
        },
        "depth_range_ft": (12, 30), "depth_style": "dragged/hopped on bottom",
        "presentation": "Long cast, let it settle to bottom, then drag/hop slowly with the rod tip at 9-10 o'clock, reeling up slack between strokes. Most bites come on the fall or the pause.",
    },
    "suspending_jerkbait": {
        "name": "Suspending Jerkbait",
        "video_key": "suspending_jerkbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Ghost minnow"],
            "Green stained": ["Chartreuse/black back", "Green shad"],
            "Brown stained": ["Craw pattern", "Brown/orange"],
            "Muddy": ["Firetiger", "Chartreuse/black"],
        },
        "trailer": None,
        "depth_range_ft": (2, 8), "depth_style": "suspended in the water column",
        "presentation": "Jerk-jerk-pause cadence with the rod tip down - let it sit motionless on the pause (longer pause in colder water). Most strikes come on the pause, not the jerk.",
    },
    "blade_bait": {
        "name": "Blade Bait",
        "video_key": "blade_bait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Silver/natural shad"],
            "Green stained": ["Gold/chartreuse"],
            "Brown stained": ["Craw/brown-gold"],
            "Muddy": ["Chartreuse/black"],
        },
        "trailer": None,
        "depth_range_ft": (0, 20), "depth_style": "lift-and-fall (yo-yo), bottom to mid-depth",
        "presentation": "Let it sink to bottom on semi-slack line, then lift-and-fall (yo-yo) vertically or on a slow retrieve - the vibration comes on the fall, so stay in contact for subtle bites.",
    },
    "lipless_crankbait": {
        "name": "Lipless Crankbait",
        "video_key": "lipless_crankbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Chrome/blue"],
            "Green stained": ["Chartreuse/black back", "Green shad"],
            "Brown stained": ["Red craw", "Brown craw"],
            "Muddy": ["Firetiger", "Solid chartreuse"],
        },
        "trailer": None,
        "depth_range_ft": (2, 10), "depth_style": "burned over grass flats/humps",
        "presentation": "Steady burn over grass with occasional bottom contact, or yo-yo (rip it free, let it flutter back down) when fish are less aggressive - most bites come on the flutter fall.",
    },
    "chatterbait": {
        "name": "Chatterbait (Bladed Jig)",
        "video_key": "chatterbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Green pumpkin", "Bluegill"],
            "Green stained": ["Chartreuse/green pumpkin", "Green shad"],
            "Brown stained": ["Bama craw", "Brown/orange"],
            "Muddy": ["Black/blue", "Firetiger"],
        },
        "trailer": {
            "type": "Paddle-tail swimbait trailer",
            "colors": {
                "Clear": ["Green pumpkin", "White pearl"],
                "Green stained": ["Chartreuse/white", "White pearl"],
                "Brown stained": ["White/brown", "Bama craw"],
                "Muddy": ["Black", "Chartreuse"],
            },
        },
        "depth_range_ft": (1, 6), "depth_style": "swum just above grass/cover",
        "presentation": "Steady retrieve just above cover so it ticks the tops of grass/wood; occasional rip-and-fall when it hangs up triggers reaction strikes.",
    },
    "squarebill_crankbait": {
        "name": "Squarebill Crankbait",
        "video_key": "squarebill_crankbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Green craw"],
            "Green stained": ["Chartreuse/green craw", "Green shad"],
            "Brown stained": ["Brown craw", "Red craw"],
            "Muddy": ["Firetiger", "Chartreuse/black"],
        },
        "trailer": None,
        "depth_range_ft": (2, 6), "depth_style": "deflecting off cover",
        "presentation": "Stop-and-go retrieve that bumps wood/rock/riprap - deflection off cover is what triggers the strike, so aim to hit something on every cast.",
    },
    "medium_diving_crankbait": {
        "name": "Medium-Diving Crankbait",
        "video_key": "medium_diving_crankbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Chrome/blue"],
            "Green stained": ["Chartreuse/black back", "Green shad"],
            "Brown stained": ["Craw pattern", "Brown/orange"],
            "Muddy": ["Firetiger", "Solid chartreuse"],
        },
        "trailer": None,
        "depth_range_ft": (6, 12), "depth_style": "grinding mid-depth cover, ledges, and secondary points",
        "presentation": "Long cast, reel down to get it into the 6-12 ft zone, then hold bottom/cover contact through the retrieve - deflection off wood or rock at this depth is what triggers reaction strikes.",
    },
    "deep_diving_crankbait": {
        "name": "Deep-Diving Crankbait",
        "video_key": "deep_diving_crankbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Chrome/blue"],
            "Green stained": ["Chartreuse/black back", "Green shad"],
            "Brown stained": ["Craw pattern", "Brown/orange"],
            "Muddy": ["Firetiger", "Solid chartreuse"],
        },
        "trailer": None,
        "depth_range_ft": (15, 25), "depth_style": "grinding bottom/ledges",
        "presentation": "Long cast, reel down to get it to depth, then grind bottom contact through ledges/humps - deflecting off hard bottom triggers reaction bites.",
    },
    "texas_rig_creature": {
        "name": "Texas-Rigged Creature Bait",
        "video_key": "texas_rig",
        "vertical_style": "bottom",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon red"],
            "Green stained": ["Green pumpkin/chartreuse", "Chartreuse"],
            "Brown stained": ["Junebug", "Brown/red craw"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth_range_ft": (1, 8), "depth_style": "pitched/flipped to cover",
        "presentation": "Pitch or flip to isolated cover/beds, let it sink on slack line, then hop/shake in place - most bites happen on the initial fall or right after it settles.",
    },
    "texas_rig_worm": {
        "name": "Texas-Rigged Worm",
        "video_key": "texas_rig",
        "vertical_style": "bottom",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Green stained": ["Green pumpkin chartreuse", "Chartreuse"],
            "Brown stained": ["Red bug", "June bug"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth_range_ft": (2, 10), "depth_style": "dragged along shoreline cover",
        "presentation": "Cast past cover, drag/hop it along the bottom back to the boat, pausing over wood or grass edges.",
    },
    "wacky_rig_senko": {
        "name": "Wacky-Rigged Senko",
        "video_key": "wacky_rig_senko",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Green stained": ["Green pumpkin/chartreuse-tip", "Chartreuse"],
            "Brown stained": ["June bug", "Brown/red"],
            "Muddy": ["Black", "Black/blue"],
        },
        "trailer": None,
        "depth_range_ft": (0, 6), "depth_style": "weightless fall",
        "presentation": "Cast to cover and let it sink with a slow, shimmying fall on slack line - most strikes happen before it hits bottom, so watch your line.",
    },
    "weightless_soft_plastic": {
        "name": "Weightless Soft Plastic (Fluke-style)",
        "video_key": "weightless_soft_plastic",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Pearl white"],
            "Green stained": ["Chartreuse/white", "White pearl"],
            "Brown stained": ["Bone", "Brown shad"],
            "Muddy": ["Black", "Chartreuse"],
        },
        "trailer": None,
        "depth_range_ft": (0, 4), "depth_style": "near surface",
        "presentation": "Twitch-twitch-pause so it darts and glides just under the surface, imitating a dying baitfish.",
    },
    "spinnerbait": {
        "name": "Spinnerbait",
        "video_key": "spinnerbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["White/silver blade", "Natural shad skirt"],
            "Green stained": ["Chartreuse/white skirt", "Gold blade"],
            "Brown stained": ["Brown/orange skirt", "Gold blade"],
            "Muddy": ["Black/blue skirt", "Colorado gold blade"],
        },
        "trailer": {
            "type": "Curly-tail grub or trailer hook",
            "colors": {
                "Clear": ["White", "Natural shad"],
                "Green stained": ["Chartreuse/white"],
                "Brown stained": ["Brown/orange"],
                "Muddy": ["Black", "Chartreuse"],
            },
        },
        "depth_range_ft": (1, 10), "depth_style": "depending on retrieve speed/slow-roll depth",
        "presentation": "Slow-roll along the bottom near cover in cold/tough conditions, or burn it just under the surface over grass when fish are active.",
    },
    "swim_jig": {
        "name": "Swim Jig",
        "video_key": "swim_jig",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Green pumpkin/shad", "Bluegill"],
            "Green stained": ["Chartreuse/green pumpkin", "Green shad"],
            "Brown stained": ["Bama craw", "Brown/orange"],
            "Muddy": ["Black/blue", "Firetiger"],
        },
        "trailer": {
            "type": "Paddle-tail swimbait trailer",
            "colors": {
                "Clear": ["White pearl", "Green pumpkin"],
                "Green stained": ["Chartreuse/white", "White pearl"],
                "Brown stained": ["White/brown", "Bama craw"],
                "Muddy": ["Black", "Chartreuse"],
            },
        },
        "depth_range_ft": (1, 6), "depth_style": "through/over grass and wood",
        "presentation": "Steady swim just fast enough to keep it ticking the top of cover; pause briefly when it deflects off wood to trigger a reaction bite.",
    },
    "carolina_rig": {
        "name": "Carolina-Rigged Worm",
        "video_key": "carolina_rig",
        "vertical_style": "bottom",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Green stained": ["Green pumpkin chartreuse", "Chartreuse"],
            "Brown stained": ["June bug", "Red bug"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth_range_ft": (8, 20), "depth_style": "dragged behind the weight on bottom",
        "presentation": "Long cast, drag the rig slowly along the bottom with sweeps of the rod - the clacking weight/bead calls fish in, then the trailing bait gets eaten.",
    },
    "buzzbait": {
        "name": "Buzzbait",
        "video_key": "buzzbait",
        "vertical_style": "surface",
        "colors": {
            "Clear": ["White", "Shad"],
            "Green stained": ["Chartreuse/white", "White"],
            "Brown stained": ["White/brown", "Black"],
            "Muddy": ["Black", "Solid chartreuse"],
        },
        "trailer": {
            "type": "Trailer hook, optional soft-plastic trailer (twin-tail grub)",
            "colors": {
                "Clear": ["White"],
                "Green stained": ["Chartreuse/white"],
                "Brown stained": ["White"],
                "Muddy": ["Black"],
            },
        },
        "depth_range_ft": (0, 0), "depth_style": "",
        "presentation": "Cast past cover, start the retrieve the instant it lands so it plans out on top, and keep a steady-to-slow retrieve so it gurgles across the surface.",
    },
    "walking_topwater": {
        "name": "Walking Topwater (Spook-style)",
        "video_key": "walking_topwater",
        "vertical_style": "surface",
        "colors": {
            "Clear": ["Bone/white", "Chrome/blue"],
            "Green stained": ["Chartreuse/white", "Bone"],
            "Brown stained": ["Bone", "Brown/orange"],
            "Muddy": ["Black", "Solid white"],
        },
        "trailer": None,
        "depth_range_ft": (0, 0), "depth_style": "",
        "presentation": "Steady 'walk-the-dog' cadence with rod tip down, snapping slack rhythmically so the bait zig-zags side to side.",
    },
    "popper": {
        "name": "Popper",
        "video_key": "popper",
        "vertical_style": "surface",
        "colors": {
            "Clear": ["Shad/natural", "Bone"],
            "Green stained": ["Chartreuse/white", "Bone"],
            "Brown stained": ["Firetiger", "Brown/orange"],
            "Muddy": ["Black", "Solid chartreuse"],
        },
        "trailer": None,
        "depth_range_ft": (0, 0), "depth_style": "",
        "presentation": "Sharp pop-pause-pop with occasional long pauses over calm water/isolated cover - most strikes happen right after the pause, not the pop itself.",
    },
    "hollow_body_frog": {
        "name": "Hollow-Body Frog",
        "video_key": "hollow_body_frog",
        "vertical_style": "surface",
        "colors": {
            "Clear": ["Natural frog green", "White belly"],
            "Green stained": ["Natural frog green", "Black"],
            "Brown stained": ["Brown/black", "White belly"],
            "Muddy": ["Black", "Solid white"],
        },
        "trailer": None,
        "depth_range_ft": (0, 0), "depth_style": "over mats/pads/grass",
        "presentation": "Walk or hop it across matted grass/pads with pauses over holes in the cover; wait for the fish to fully engulf it before setting the hook.",
    },
    "finesse_shaky_head": {
        "name": "Finesse Worm / Shaky Head",
        "video_key": "finesse_shaky_head",
        "vertical_style": "bottom",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Green stained": ["Green pumpkin/chartreuse", "Chartreuse"],
            "Brown stained": ["June bug", "Brown/red"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth_range_ft": (6, 20), "depth_style": "dragged/shaken in place",
        "presentation": "Cast out, let it hit bottom, then shake it in place with the rod tip without moving it far - a subtle, tough-bite bait for high-pressure days.",
    },
    # Punch-list #37: drop_shot and soft_swimbait below are new - neither
    # existed in this taxonomy before. Both came out of actually researching
    # real, documented Nolin Lake experience (not just generic bass-fishing
    # knowledge) rather than being added speculatively: a real angler forum
    # tip (fishin.com's "Nolin Lake Tips?" thread) specifically describes
    # drop-shotting ~45 ft dam points and bluff walls at Nolin, and Omnia
    # Fishing's documented Nolin-specific season-by-season pattern data lists
    # "soft swimbaits (small/medium)" as a real post-spawn/winter Nolin lure -
    # see the season-pattern comments in recommend() below for the full
    # source-by-source breakdown. Neither lure had a home in this taxonomy
    # until that research surfaced them as things that specifically catch
    # fish here, which is exactly the gap the angler asked to close.
    "drop_shot": {
        "name": "Drop Shot",
        "video_key": "drop_shot",
        "vertical_style": "bottom",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon shad"],
            "Green stained": ["Green pumpkin/chartreuse", "Natural shad"],
            "Brown stained": ["Green pumpkin", "June bug"],
            "Muddy": ["Black/blue", "Junebug"],
        },
        "trailer": None,
        "depth_range_ft": (15, 45), "depth_style": "suspended just off bottom on deep points/bluffs",
        "presentation": "Drop straight down (or cast and let it settle) on deep main-lake structure - dam-face points, "
                         "bluff walls, humps - then work it in place with small, subtle rod-tip shakes rather than "
                         "moving it far; a real Nolin angler report specifically describes this working ~45 ft off "
                         "deep dam points for bass that won't commit to anything moving fast.",
    },
    "soft_swimbait": {
        "name": "Soft Swimbait (paddle tail)",
        "video_key": "soft_swimbait",
        "vertical_style": "column",
        "colors": {
            "Clear": ["Natural shad", "Ghost shad"],
            "Green stained": ["Chartreuse shad", "Natural shad"],
            "Brown stained": ["Natural shad", "Green pumpkin"],
            "Muddy": ["Black/chartreuse", "Solid white"],
        },
        "trailer": None,
        "depth_range_ft": (2, 12), "depth_style": "swum through the water column on a steady/rolling retrieve",
        "presentation": "Cast out and reel with a steady-to-rolling retrieve, letting the paddle tail do the work - "
                         "a real, documented Nolin post-spawn and fall pattern (per Omnia Fishing's Nolin-specific "
                         "pattern data) for shad-imitating baitfish presentations without a hard bill to snag cover.",
    },
}


# Largemouth bass have a strike window heavily biased forward and UP: binocular
# vision is limited to a narrow cone in front of and slightly above the snout,
# there's a blind spot below/behind, and the jaw hinges upward to create suction.
# Net effect (well documented in bass biology/tackle-industry tutorials): bass
# strike up at prey far more readily than they dive down for it. So a bait
# fished level with or a couple feet ABOVE a marked depth is usually a better
# target than one fished at the same depth or below.
STRIKE_UP_OFFSET_FT = (1.0, 2.0)  # (min, max) feet above the marked depth to target


def _target_depth_for_fish(fish_depth_ft: float, vertical_style: str):
    """Returns (lo, hi) target running depth in feet for this style of lure."""
    if vertical_style == "bottom":
        # Slow/finesse presentations are fished IN the zone, not necessarily above it -
        # the "up" bias still applies, but these baits give fish time to adjust, so the
        # actionable advice is where to stop/count it down to, not a strict offset.
        return (max(0.0, fish_depth_ft - 1), fish_depth_ft)
    off_lo, off_hi = STRIKE_UP_OFFSET_FT
    lo = max(0.0, fish_depth_ft - off_hi)
    hi = max(0.5, fish_depth_ft - off_lo)
    return (round(lo, 1), round(hi, 1))


def _depth_match_score(profile: dict, fish_depth_ft: float) -> float:
    """0 = fish are right in this lure's natural zone; positive = how far off (ft)."""
    lo, hi = profile["depth_range_ft"]
    style = profile.get("vertical_style", "column")
    if lo == 0 and hi == 0:  # surface bait
        return max(0.0, fish_depth_ft - 3)  # topwater still "matches" very shallow fish
    target_lo, target_hi = _target_depth_for_fish(fish_depth_ft, style)
    if lo <= target_lo <= hi or lo <= target_hi <= hi or (target_lo <= lo and target_hi >= hi):
        return 0.0
    return min(abs(target_lo - lo), abs(target_lo - hi), abs(target_hi - lo), abs(target_hi - hi))


def _depth_text(profile: dict, fish_depth_ft: float = None) -> str:
    lo, hi = profile["depth_range_ft"]
    surface = lo == 0 and hi == 0
    if surface:
        base = f"Surface, {profile['depth_style']}" if profile["depth_style"] else "Surface"
    else:
        base = f"{lo}-{hi} ft, {profile['depth_style']}"

    if fish_depth_ft is None:
        return base

    if surface:
        if fish_depth_ft > 6:
            return base + (f" (you're marking fish deeper, around {fish_depth_ft:.0f} ft - bass can rise "
                            f"several feet for topwater, but the bite gets tougher the deeper they're holding)")
        return base + " (matches the shallow fish you're marking - bass strike up, so this is a good call)"

    style = profile.get("vertical_style", "column")
    if style == "bottom":
        target_lo, target_hi = _target_depth_for_fish(fish_depth_ft, style)
        if lo <= fish_depth_ft <= hi:
            return base + (f" - count it down to about {target_lo:.0f}-{target_hi:.0f} ft before working it, "
                            f"right where you're marking fish")
        if fish_depth_ft < lo:
            return base + f" - you're marking fish shallower (~{fish_depth_ft:.0f} ft); don't let it fall all the way to bottom, work it in that upper zone instead"
        return base + f" - you're marking fish deeper (~{fish_depth_ft:.0f} ft); let it settle longer before working it"

    # column (reaction/moving baits): target a specific band above the marked depth
    target_lo, target_hi = _target_depth_for_fish(fish_depth_ft, style)
    if fish_depth_ft <= 2:
        return base + " - fish are shallow; run this right at/just above their level"
    if lo <= target_lo <= hi or lo <= target_hi <= hi:
        return base + (f" - target ~{target_lo:.0f}-{target_hi:.0f} ft (1-2 ft above the {fish_depth_ft:.0f} ft "
                        f"you're marking - bass strike up more readily than down)")
    if fish_depth_ft < lo:
        return base + f" - you're marking fish shallower (~{fish_depth_ft:.0f} ft) than this bait's usual zone; slow down/shorten your count-down to get up in range"
    return base + (f" - you're marking fish deeper (~{fish_depth_ft:.0f} ft); this bait tops out at {hi:.0f} ft, "
                    f"so let it sink/slow-roll deeper, or lean on a deeper-running option instead")


# Connector/filler words that show up inside the color-suggestion strings
# (e.g. "Chartreuse/black back", "Craw pattern") but aren't themselves
# color/pattern words - stripped out before matching so they don't cause
# false "matches" against unrelated owned-item descriptions.
_COLOR_MATCH_STOPWORDS = {
    "and", "the", "with", "back", "belly", "pattern", "skirt", "tip", "solid",
    "trailer", "blade", "tail",
}


def _color_tokens(text: str) -> set:
    """Break a color-suggestion or lure-description string into lowercase
    word tokens for a simple, explainable keyword match. This is NOT a real
    color model - it has no notion of "close" colors, and a compound name
    like "green pumpkin" becomes two independent tokens - but it's good
    enough to flag when an owned item's description shares real color/
    pattern language with today's suggested color, and, just as usefully,
    to flag when it doesn't."""
    if not text:
        return set()
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _COLOR_MATCH_STOPWORDS}


def _color_matched_owned_items(owned_items: list, suggested_colors: list) -> list:
    """Keep only the owned items whose description shares color/pattern
    language with this lure block's suggested colors for today's water
    clarity - owned items in the same lure category but a different color
    are dropped entirely rather than shown alongside the match.

    Earlier version of this showed every owned item in the category
    regardless of color (a Chili Craw crankbait shown next to a
    "Chartreuse/black back" suggestion with nothing telling you they don't
    match), then a version that showed all of them split into matched/
    unmatched groups. Per follow-up feedback, only the color-matched
    item(s) are surfaced now - if none of your on-hand items are actually
    the suggested color, this comes back empty and the block falls back to
    the normal "not in your inventory" treatment, since owning the right
    lure type in the wrong color isn't the same as being ready to go.

    Per punch-list #8, even among color-matched items only the top
    MAX_OWNED_ITEMS_PER_BLOCK are kept (ranked #1/#2 in the UI - see
    core.ui.render_lure_block) rather than listing every match, so a
    category with a dozen color-matched items on hand doesn't dominate the
    card. "Best" is ranked by quantity on hand (more in reserve = more
    ready to go), ties keeping their original relative order since Python's
    sort is stable."""
    suggested_tokens = set()
    for c in suggested_colors:
        suggested_tokens |= _color_tokens(c)
    matched = [it for it in owned_items if _color_tokens(it.get("description", "")) & suggested_tokens]
    matched.sort(key=lambda it: -(it.get("quantity") or 0))
    return matched[:MAX_OWNED_ITEMS_PER_BLOCK]


def _build_block(key: str, water_clarity: str, fish_depth_ft: float = None, note: str = "",
                  owned_items: list = None) -> "LureBlock":
    profile = LURE_PROFILES[key]
    colors = profile["colors"].get(water_clarity, profile["colors"][DEFAULT_BASE_STAIN])
    trailer = None
    if profile["trailer"]:
        t_colors = profile["trailer"]["colors"].get(water_clarity, profile["trailer"]["colors"][DEFAULT_BASE_STAIN])
        trailer = TrailerInfo(type=profile["trailer"]["type"], colors=t_colors)
    return LureBlock(
        key=key,
        name=profile["name"],
        colors=colors,
        trailer=trailer,
        depth=_depth_text(profile, fish_depth_ft),
        presentation=profile["presentation"],
        videos=get_videos_by_key(profile["video_key"], profile["name"]),
        note=note,
        owned_items=_color_matched_owned_items(owned_items, colors) if owned_items else [],
    )


def _group_owned_by_category(inventory: list) -> dict:
    """Group in-hand tackle-inventory rows (data/lure_inventory.csv, via
    core.lure_inventory) by their `category` field, which is one of the
    LURE_PROFILES keys - keeps the tackle box (a separate, physical
    inventory) matched to the recommendation engine's lure taxonomy without
    the two modules depending on each other's internals. Rows with no
    category, an unrecognized category, or zero quantity on hand are
    skipped (not currently owned).

    Each grouped item dict includes the source row's `item_id` (Spot
    Session's recommendation-card "+ Add to session" quick-add buttons key
    off this directly, rather than re-matching the item by its display
    label the way the page's older edit-mode code had to)."""
    grouped: dict = {}
    if not inventory:
        return grouped
    for row in inventory:
        category = (row.get("category") or "").strip()
        if category not in LURE_PROFILES:
            continue
        try:
            qty = int(row.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        grouped.setdefault(category, []).append({
            "item_id": row.get("item_id", ""),
            "brand": row.get("brand", ""),
            "description": row.get("description", ""),
            "quantity": qty,
            "sku": row.get("sku", ""),
            "image_url": row.get("image_url", ""),
            "image_filename": row.get("image_filename", ""),
        })
    return grouped


def find_inventory_gaps(inventory: list) -> list:
    """Punch-list #14: every LURE_PROFILES category the angler owns zero of
    (no row tagged with that category, or every such row is at quantity 0) -
    i.e. types of bass lures useful for Nolin Lake with nothing in the
    tackle box to fill that role. Trailers aren't a separate concept here:
    texas_rig_creature and weightless_soft_plastic (see
    TRAILER_ELIGIBLE_CATEGORIES below) are themselves LURE_PROFILES entries,
    so a single pass over all 20 categories already covers "lure types and
    trailers" the way the angler's own ask grouped them.

    Returns category keys in LURE_PROFILES' own definition order (a rough
    most-versatile-to-most-niche curation, not alphabetical) rather than
    sorted some other way, so the Tackle Box page's gap-filling section
    reads as a sensible priority list."""
    owned = _group_owned_by_category(inventory)
    return [key for key in LURE_PROFILES if key not in owned]


@dataclass
class TrailerInfo:
    type: str
    colors: list


@dataclass
class LureBlock:
    key: str
    name: str
    colors: list
    depth: str
    presentation: str
    videos: list
    trailer: TrailerInfo = None
    note: str = ""
    # list[dict]: brand/description/quantity/sku for on-hand items that both match this
    # lure's category AND match today's suggested color (see _color_matched_owned_items) -
    # an item you own in the wrong color for today's water clarity won't appear here.
    owned_items: list = field(default_factory=list)

    @property
    def owned(self) -> bool:
        return bool(self.owned_items)


@dataclass
class LureRecommendation:
    first_choice: list       # list[LureBlock]
    second_choice: list      # list[LureBlock]
    rationale: list = field(default_factory=list)


def recommend(
    season: str,
    water_temp_f: float,
    segment_name: str,
    pressure_trend_24h: float,
    structure_type: str = "Main-lake point",
    water_clarity: str = "Brown stained",
    fish_depth_ft: float = None,
    forage: list = None,
    thermocline_ft: float = None,
    inventory: list = None,
    trip_history: list = None,
    spot_id: str = None,
) -> LureRecommendation:
    low_light = segment_name in LIGHT_LOW
    rationale = []
    if fish_depth_ft is not None:
        rationale.append(
            f"You're marking fish around {fish_depth_ft:.0f} ft - bass have upward-biased vision and an "
            f"upward-hinging jaw, so they strike up more readily than down. Reaction/moving baits below are "
            f"re-ordered and targeted to run 1-2 ft above that reading; bottom baits are targeted to count "
            f"down to it."
        )
    caveat = thermocline_caveat(thermocline_ft, fish_depth_ft)
    if caveat:
        rationale.append(caveat)

    # --- Seasonal base pattern: which lure keys are first vs second choice -----
    #
    # Punch-list #37 rewrite: these used to be generic, unsourced bass-fishing
    # rules ("crankbaits pre-spawn, jigs in cold water" - true of largemouth
    # bass almost anywhere, not specific to this lake). The angler's own ask
    # was direct: "general information is really not all the helpful ...
    # we need to get this more specific to the lake." So each branch below
    # now leads with Omnia Fishing's documented, Nolin-Lake-specific
    # season-by-season pattern data (structure/lure/color/depth, scraped from
    # real reports at https://www.omniafishing.com/w/nolin-lake-2-fishing-
    # reports/fishing-patterns), folding in a couple of corroborating,
    # independently-found real sources rather than replacing proven general
    # picks outright: a real angler's first-hand report on Nolin specifically
    # (fishin.com forum thread "Nolin Lake Tips?" - bluff walls, ~45 ft dam
    # points fished on drop shot, dawn/dusk topwater "jumps" with poppers and
    # soft jerkbaits) and KDFWR's own official 2026 Fishing Forecast, which
    # calls out Nolin by name for one specific tactical note: "During late
    # spring through summer, best results are often at night" (applied below
    # as a Night-segment rationale note, not just folded silently into the
    # lure list). Previously-first-choice generic picks that aren't
    # contradicted by any of this stay on as second choices rather than being
    # dropped, so a real pattern someone here has actually caught fish on
    # (this app's own trip log, see the personal-history section further
    # down) still gets full credit even if Omnia's data doesn't happen to
    # mention it by name.
    if season == "winter":
        # Omnia (47-52F): rock piles/boulders near channel swings, points with
        # deep access; hard jerkbaits (long pauses), medium divers (7-12ft),
        # soft swimbaits. A local Nolin guide's own paid tip content on
        # fishtips.com is literally titled "Winter time cranking," backing
        # the crankbait emphasis specifically for this lake.
        first_keys = ["suspending_jerkbait", "medium_diving_crankbait", "football_jig"]
        second_keys = ["soft_swimbait", "blade_bait", "deep_diving_crankbait"]
        rationale.append(
            "Cold water (<50F) - Nolin's own documented winter pattern (Omnia Fishing) targets rock piles/"
            "boulders near channel swings and deep-access points with long-pause jerkbaits and 7-12 ft "
            "crankbaits; a local Nolin guide's own paid tip content is literally titled 'Winter time cranking.'"
        )
    elif season == "pre_spawn":
        # Omnia (47-58F): rip-rap with stumps/laydowns, creek mouths with chunk
        # rock; medium diving cranks (7-12ft), Texas rigs, shallow divers (0-6ft).
        first_keys = ["medium_diving_crankbait", "texas_rig_worm", "lipless_crankbait"]
        second_keys = ["squarebill_crankbait", "chatterbait", "football_jig"]
        rationale.append(
            "Pre-spawn (50-60F) - Nolin's documented pattern (Omnia Fishing) is rip-rap with stumps/laydowns "
            "and creek mouths with chunk rock, worked with 7-12 ft crankbaits and Texas rigs as fish stage "
            "before the move shallow."
        )
    elif season == "spawn":
        # Omnia (58-68F): protected shallow bays/coves with hard bottom near
        # rip-rap; Texas rigs (pitch/flip), shakey heads, shallow divers.
        first_keys = ["texas_rig_creature", "finesse_shaky_head", "squarebill_crankbait"]
        second_keys = ["wacky_rig_senko", "weightless_soft_plastic"]
        rationale.append(
            "Spawn window (60-75F) - Nolin's documented pattern (Omnia Fishing) is protected shallow bays/"
            "coves with hard bottom near rip-rap, pitched/flipped with Texas rigs and shakey heads."
        )
    elif season == "post_spawn_summer":
        # Omnia post-spawn (62-75F): stumps/woody cover, rip-rap near bridges;
        # shakey heads, walking topwater, small/medium soft swimbaits.
        first_keys = ["finesse_shaky_head", "walking_topwater", "soft_swimbait"]
        second_keys = ["spinnerbait", "swim_jig", "texas_rig_worm"]
        rationale.append(
            "Post-spawn recovery - Nolin's documented pattern (Omnia Fishing) is stumps/woody cover and "
            "rip-rap near bridges, worked with shakey heads, walking topwater, and small/medium swimbaits as "
            "fish move from spawning flats toward summer haunts."
        )
    elif season == "summer_peak":
        if low_light:
            # A real Nolin angler report (fishin.com forum) specifically
            # describes "poppers and white super flukes" working dawn/dusk
            # ("the jumps") - flukes map to weightless_soft_plastic here.
            first_keys = ["walking_topwater", "buzzbait", "weightless_soft_plastic"]
            second_keys = ["popper", "swim_jig", "squarebill_crankbait"]
            if segment_name == "Night":
                rationale.append(
                    "KDFWR's own 2026 official Fishing Forecast calls out Nolin by name: 'During late spring "
                    "through summer, best results are often at night' - the same real angler report also "
                    "notes night fishing is productive here in summer."
                )
        else:
            # Omnia (75-85F): main-lake points with deep-water access and rock
            # structure; deep crankbaits (13ft+), football jigs, Carolina rigs -
            # this already matched the app's prior generic picks closely. Added
            # drop_shot as a second choice per the same forum report's specific
            # ~45 ft dam-point/bluff-wall drop-shot tip for scattered, tough-
            # bite summer fish that won't commit to anything moving fast.
            first_keys = ["football_jig", "deep_diving_crankbait", "carolina_rig"]
            second_keys = ["drop_shot", "suspending_jerkbait", "lipless_crankbait"]
        rationale.append(
            "Summer heat - Nolin's documented pattern (Omnia Fishing) is main-lake points with deep-water "
            "access and rock structure, worked with 13 ft+ crankbaits, football jigs, and Carolina rigs "
            "outside low light."
        )
    elif season == "fall_feed_up":
        # Omnia fall (58-72F): laydowns, timber in pockets, bluff walls with
        # woody cover; popping topwater, Texas rigs, drop shot, buzzbaits.
        first_keys = ["popper", "texas_rig_worm", "buzzbait"]
        second_keys = ["drop_shot", "squarebill_crankbait", "spinnerbait"]
        rationale.append(
            "Fall feed-up - Nolin's documented pattern (Omnia Fishing) is laydowns/timber in pockets and "
            "bluff walls with woody cover, worked with popping topwater, Texas rigs, and drop shot as shad "
            "move shallow/into creeks and bass feed aggressively to follow."
        )
    else:  # fall_turnover
        first_keys = ["football_jig", "suspending_jerkbait", "blade_bait"]
        second_keys = ["drop_shot", "lipless_crankbait", "deep_diving_crankbait"]
        rationale.append(
            "Fall turnover - oxygen/temp mixing makes bass location and mood unpredictable; added drop shot "
            "as a second choice for scattered, suspended fish (same deep-structure pattern that works Nolin's "
            "bluff walls/dam points per real angler reports, not turnover-specific on its own)."
        )

    # --- Structure-specific nudge (context note, not a lure swap) ---------------
    structure_notes = {
        "Main-lake point": "Fan-cast the point from shallow to deep, focus on the fastest breakline.",
        "Creek channel / ledge": "Idle/graph to find the ledge lip, then work baits parallel to it.",
        "Cove / pocket (shallow cover)": "Target isolated wood, laydowns, and grass clumps inside the cove.",
        "Flat": "Cover water efficiently - flats reward moving baits (spinnerbait, swim jig, crank).",
        "Standing timber": "Vertical presentations (jig, drop shot) worked tight to individual trees.",
        "Riprap / dam face": (
            "Parallel casts down the rock, crawl a jig or crank to deflect off rip-rap. A real Nolin angler "
            "report also specifically describes bluff walls with channels nearby and deep points along the "
            "dam (~45 ft) as a drop-shot pattern for fish that won't commit to anything faster."
        ),
        "Bridge piling": "Cast tight to pilings/riprap transitions; vertical jig the shady side.",
        "Boat dock": "Skip a jig or wacky worm under the dock into the shade line.",
    }
    if structure_type in structure_notes:
        rationale.append(structure_notes[structure_type])

    # Crankbaits are broadly useful on hard cover/rock/wood regardless of season -
    # make sure one shows up as a second-choice option whenever it isn't already picked.
    crank_keys = {"squarebill_crankbait", "lipless_crankbait", "deep_diving_crankbait", "medium_diving_crankbait"}
    if not (crank_keys & set(first_keys) | crank_keys & set(second_keys)) and structure_type in (
        "Riprap / dam face", "Bridge piling", "Flat", "Main-lake point", "Creek channel / ledge"
    ) and season != "winter":
        pick = "squarebill_crankbait" if water_temp_f >= 60 else "lipless_crankbait"
        second_keys.append(pick)

    # Topwater is worth a mention on any low-light segment in warmer seasons even if not first choice.
    topwater_keys = {"buzzbait", "walking_topwater", "popper", "hollow_body_frog"}
    if not (topwater_keys & set(first_keys) | topwater_keys & set(second_keys)) and low_light and season in (
        "post_spawn_summer", "summer_peak", "fall_feed_up", "spawn"
    ):
        second_keys.append("walking_topwater")

    # Jerkbaits shine in clearer, cooler water - flag as a second choice outside their primary seasons too.
    if "suspending_jerkbait" not in first_keys and "suspending_jerkbait" not in second_keys:
        if water_temp_f <= 68 and water_clarity in ("Clear", "Green stained", "Brown stained"):
            second_keys.append("suspending_jerkbait")

    # --- Pressure trend nudge ---------------------------------------------------
    if pressure_trend_24h <= -1.5:
        rationale.append("Falling pressure - bass are often more aggressive; reaction baits can shine.")
    elif pressure_trend_24h >= 2.0:
        if "finesse_shaky_head" not in second_keys and "finesse_shaky_head" not in first_keys:
            second_keys.insert(0, "finesse_shaky_head")
        rationale.append("High, stable pressure after a front - added a finesse bait for a tougher bite.")

    # --- Forage nudge: make sure at least one forage-matched lure shows up ------
    if forage:
        forage_boost_keys = []
        for f in forage:
            for k in FORAGE_LURE_BOOST.get(f, []):
                if k not in forage_boost_keys:
                    forage_boost_keys.append(k)
        already_covered = set(first_keys) | set(second_keys)
        for k in forage_boost_keys:
            if k not in already_covered:
                second_keys.insert(0, k)
                break
        forage_notes = [FORAGE_NOTES[f] for f in forage if f in FORAGE_NOTES]
        if forage_notes:
            rationale.append(" ".join(forage_notes))

    # --- Depth-driven crank swap -------------------------------------------------
    # Every seasonal pattern above already includes some crankbait, but its depth
    # range is picked for the season/light in general, not for the specific sonar
    # reading you gave us. If that reading (6-12 ft) actually falls in the
    # medium-diving crank's zone instead, swap the first shallower/deeper crank
    # already in play for it - a genuine depth-accuracy improvement independent of
    # inventory, and what lets an owned medium-diving crank ever get suggested.
    if (fish_depth_ft is not None and 6 <= fish_depth_ft <= 12
            and "medium_diving_crankbait" not in first_keys and "medium_diving_crankbait" not in second_keys):
        for keys_list in (first_keys, second_keys):
            swap_at = next((i for i, k in enumerate(keys_list)
                             if k in ("squarebill_crankbait", "deep_diving_crankbait")), None)
            if swap_at is not None:
                keys_list[swap_at] = "medium_diving_crankbait"
                break

    # De-dupe while preserving order, never let a key appear in both lists.
    seen = set()
    first_keys_unique = []
    for k in first_keys:
        if k not in seen:
            first_keys_unique.append(k)
            seen.add(k)
    second_keys_unique = []
    for k in second_keys:
        if k not in seen:
            second_keys_unique.append(k)
            seen.add(k)

    # If we have a sonar depth reading, reorder each list (best depth match first)
    # without changing which lures are in play - season/structure/pressure still
    # decide *what*, the depth reading just decides *which of those, first*.
    if fish_depth_ft is not None:
        first_keys_unique.sort(key=lambda k: _depth_match_score(LURE_PROFILES[k], fish_depth_ft))
        second_keys_unique.sort(key=lambda k: _depth_match_score(LURE_PROFILES[k], fish_depth_ft))

    # --- Personal history: your own catch record in similar situations ----------
    # Punch-list #37, the angler's own direct ask: "influence the lure choice by
    # my actual experience ... take into account where the lure was used in the
    # past, that success, and where it is planned to be used." See
    # core.lure_history for the full matching/gating logic (situation-similarity
    # scored, minimum-sample-gated - conservative by design, same "small data,
    # capped nudge" philosophy as core.calibration.py's score-weight nudging).
    # This never overrides the season/structure/pressure picks above - it only
    # (a) tags an already-recommended lure with your own real track record on it
    # in a similar spot/situation, and (b) surfaces up to two additional lures
    # you've genuinely caught fish on before in a similar spot/situation, even
    # if they're not part of this situation's seasonal pattern and even if
    # they're not in your tackle box today - the exact "before I decide to go
    # out and buy that lure" case the angler described.
    history_notes = {}
    if trip_history:
        situation = {
            "spot_id": spot_id,
            "structure_type": structure_type,
            "water_clarity": water_clarity,
            "low_light": low_light,
            "water_temp_f": water_temp_f,
        }
        records = lure_track_records(trip_history, situation)
        already_picked = set(first_keys_unique) | set(second_keys_unique)
        for key in already_picked:
            if key in records:
                history_notes[key] = track_record_note(records[key], in_plan_already=True)
        # Inject genuinely fish-producing lures not already in either tier -
        # capped at 2 so this can't balloon the list, best-catch-rate-first
        # among candidates that actually have one.
        injectable = sorted(
            (rec for key, rec in records.items() if key not in already_picked and rec.trips_with_fish > 0),
            key=lambda r: (r.catch_rate, r.similar_trips), reverse=True,
        )
        for rec in injectable[:2]:
            second_keys_unique.insert(0, rec.lure_category)
            history_notes[rec.lure_category] = track_record_note(rec, in_plan_already=False)

    # --- Tackle-box inventory: annotate + surface what you actually have --------
    # This never adds/removes/reorders-by-situation which lures are recommended -
    # season/structure/pressure/forage/depth/history above already decided that.
    # It only tags each resulting block with any matching inventory you own
    # (category field on data/lure_inventory.csv rows, see core.lure_inventory),
    # then, only when inventory was passed in, stable-sorts each tier so owned
    # lures bubble to the top ("best options you have") while unowned ones stay
    # in the list right behind them as pick-up suggestions.
    owned_by_category = _group_owned_by_category(inventory)

    first_choice = [
        _build_block(k, water_clarity, fish_depth_ft, note=history_notes.get(k, ""), owned_items=owned_by_category.get(k))
        for k in first_keys_unique
    ]
    second_choice = [
        _build_block(k, water_clarity, fish_depth_ft, note=history_notes.get(k, ""), owned_items=owned_by_category.get(k))
        for k in second_keys_unique
    ]

    if owned_by_category:
        first_choice.sort(key=lambda b: not b.owned)
        second_choice.sort(key=lambda b: not b.owned)

    return LureRecommendation(first_choice=first_choice, second_choice=second_choice, rationale=rationale)


# (key, display name) pairs for every lure category the recommendation engine
# knows about - used by the Tackle Box page to let you tag/re-tag each
# tackle item with the category it matches here, so ownership can be matched
# up against the forecast's lure suggestions.
LURE_CATEGORY_OPTIONS = [(key, profile["name"]) for key, profile in LURE_PROFILES.items()]

# Ordered (category key, [keyword phrases]) rules for guess_category_from_text()
# below - first match wins, so more specific phrases must come before more
# generic ones (e.g. "square bill" before the bare "crankbait" fallback, or
# this would tag every squarebill as a medium-diving crankbait instead).
# This is intentionally just a best-effort heuristic over a product name/
# description string, the same kind of guess a person skimming the name
# would make - it's meant to prefill a category the angler can spot-check
# and correct, not to be authoritative. Used by both the Cabela's
# order-history/cart import workflow and the Tackle Box "Scan a lure"
# feature (core.cabelas_lookup) to auto-tag newly added items.
_CATEGORY_KEYWORD_RULES = [
    ("hollow_body_frog", ["hollow body frog", "hollow-body frog", " frog"]),
    ("buzzbait", ["buzzbait", "buzz bait", "buzz king"]),
    ("walking_topwater", ["walking topwater", "walk the dog", "spook", "walking bait"]),
    ("popper", ["popper"]),
    ("chatterbait", ["chatterbait", "chatter bait", "bladed jig", "thunder cricket"]),
    ("swim_jig", ["swim jig", "swimjig", "rage swimmer"]),
    ("football_jig", ["football jig"]),
    ("finesse_shaky_head", ["shaky head", "ned rig", "finesse trd", "finesse worm"]),
    ("wacky_rig_senko", ["wacky rig", "senko", "wacky worm", "straight worm"]),
    ("carolina_rig", ["carolina rig", "c-rig"]),
    ("texas_rig_creature", ["creature bait", "beaver bait", "rage tail craw", "krackin"]),
    ("texas_rig_worm", ["texas rig", "ribbon tail worm"]),
    ("lipless_crankbait", ["lipless"]),
    ("squarebill_crankbait", ["square bill", "squarebill"]),
    ("deep_diving_crankbait", [
        "deep diving", "deep-diving", "5xd", "6xd",
        "dives to 15", "dives to 16", "dives to 17", "dives to 18",
        "dives to 19", "dives to 20", "dives to 25",
    ]),
    ("medium_diving_crankbait", [
        "medium diving", "medium-diving", "3xd", "dt10", "dt-10", "dt 10",
        "dives to 8", "dives to 9", "dives to 10", "dives to 12",
    ]),
    ("blade_bait", ["blade bait"]),
    ("suspending_jerkbait", ["jerkbait", "jerk bait"]),
    ("spinnerbait", ["spinnerbait", "spinner bait"]),
    ("drop_shot", ["drop shot", "dropshot", "drop-shot"]),  # punch-list #37
    # Punch-list #37: "swimbait" used to route here too (weightless_soft_plastic
    # was this app's only soft-plastic-that-swims category before soft_swimbait
    # existed) - now that a real paddle-tail swimbait category exists, "swimbait"
    # routes there instead; "fluke"/"soft jerkbait" stay here since a fluke-style
    # bait is a genuinely different presentation (darted/twitched, no paddle
    # tail) from a steady-retrieve paddle-tail swimbait.
    ("weightless_soft_plastic", ["fluke", "soft jerkbait"]),
    ("soft_swimbait", ["swimbait", "paddle tail", "paddletail"]),  # punch-list #37
    ("medium_diving_crankbait", ["crankbait"]),  # generic fallback - depth unknown, assume mid-range
]


def guess_category_from_text(*texts: str) -> str:
    """Best-guess one of LURE_CATEGORY_OPTIONS' keys from free-text product
    name(s)/description(s) - or "" if nothing matches. Pure/offline (no
    lookups), so it's safe to run on any text, including a vision model's
    read of a package label before that's even been matched to a real
    product."""
    combined = " ".join(t for t in texts if t).lower()
    if not combined:
        return ""
    for category_key, phrases in _CATEGORY_KEYWORD_RULES:
        if any(phrase in combined for phrase in phrases):
            return category_key
    return ""


# --- Trailer eligibility (Spot Session's "Used a trailer" picker) ------------
# A "trailer" is a soft plastic that CAN be added onto another bait's hook (a
# jig, chatterbait, spinnerbait, swim jig, or buzzbait - see each profile's
# own "trailer" dict above, e.g. "Craw trailer"/"Paddle-tail swimbait
# trailer"). This is used to build the trailer-only picker inside the "Add a
# trailer?" dialog (core.lures.is_trailer_eligible) - it is NOT used to
# exclude these baits from the main lure picker (punch-list #46): a
# Texas-rigged creature bait or a weightless soft plastic is very often
# fished on its own too, not just attached to another lure, so both are
# fully pickable as a standalone lure everywhere else in the app. Worm-style
# baits (Texas-rigged worm, wacky-rigged senko, etc.) never belong in the
# trailer picker at all - see the keyword safety net below - but they were
# always standalone-pickable regardless. Deliberately narrow: only the two
# LURE_PROFILES categories that
# actually match a documented trailer TYPE. texas_rig_creature covers craw/
# creature-style trailers (the classic jig trailer); weightless_soft_plastic
# covers fluke/soft-jerkbait-style trailers - an established convention from
# before this app had a real "swimbait" category of its own (see the earlier
# tests already locking in weightless_soft_plastic as trailer-eligible),
# deliberately left as-is here rather than swapped for the newer, more
# anatomically-correct soft_swimbait (punch-list #37) - that would be a real
# behavior change to the existing trailer picker with no angler ask behind
# it, out of scope for the lure-recommendation work that added soft_swimbait.
# Every other category - including the worm-style ones (texas_rig_worm,
# wacky_rig_senko, finesse_shaky_head, carolina_rig) the angler specifically
# said NOT to show here - is excluded.
TRAILER_ELIGIBLE_CATEGORIES = {"texas_rig_creature", "weightless_soft_plastic"}

# Keyword safety net on top of the category check, same "no black box"
# keyword-matching philosophy as _color_tokens() elsewhere in this module -
# excludes an item even if it's mis-categorized, for product lines that are
# unambiguously worms rather than trailers. Z-Man's "TRD" line is explicitly
# called out here because it's a real, common miscategorization risk: a TRD
# is a finesse worm (normally tagged finesse_shaky_head, already excluded by
# category above), but "TRD" alone gives no hint of that if someone tags it
# something else by hand.
TRAILER_EXCLUDE_KEYWORDS = ("worm", "senko", "trd", "stick bait", "stickbait")


def is_trailer_eligible(item: dict) -> bool:
    """Whether an inventory item belongs in the "Trailer" picker (as opposed
    to the main "Lure used" picker, which shows the whole tackle box).
    Category-based first, then the keyword safety net above on the item's
    own brand/description text."""
    if item.get("category") not in TRAILER_ELIGIBLE_CATEGORIES:
        return False
    text = f"{item.get('brand', '')} {item.get('description', '')}".lower()
    return not any(kw in text for kw in TRAILER_EXCLUDE_KEYWORDS)
