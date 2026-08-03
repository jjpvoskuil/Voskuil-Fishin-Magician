"""
Lure / color / trailer / depth / presentation recommendation engine for
largemouth bass on Nolin River Lake.

Design: each lure is a self-contained profile (LURE_PROFILES) carrying its
own colors-by-water-clarity, trailer (type + color, if one is typically
used with that lure), depth to run, and presentation style. Separately,
situational rules (season, segment/light level, pressure trend, structure
type, water clarity) pick which lure keys are the "first choice" picks for
that exact situation, and which are solid "second choice" alternates -
this is where crankbaits, jerkbaits, and topwater show up across more
conditions than just their single best-case scenario.

`recommend()` returns a LureRecommendation with `first_choice` and
`second_choice` lists of fully-resolved LureBlock objects - everything
needed to render one self-contained block per lure (name, colors,
trailer, depth, presentation, and a couple of how-to videos).
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .videos import get_videos_by_key

WATER_CLARITY_OPTIONS = ["Clear", "Stained", "Muddy"]
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

# ---------------------------------------------------------------------------
# Lure library: one profile per lure, independent of any specific day/segment.
# ---------------------------------------------------------------------------
LURE_PROFILES = {
    "football_jig": {
        "name": "Football Jig",
        "video_key": "football_jig",
        "colors": {
            "Clear": ["Green pumpkin", "Brown/orange"],
            "Stained": ["Brown/orange", "Green pumpkin/chartreuse"],
            "Muddy": ["Black/blue", "Junebug"],
        },
        "trailer": {
            "type": "Craw trailer",
            "colors": {
                "Clear": ["Green pumpkin", "Watermelon red"],
                "Stained": ["Brown/orange", "Green pumpkin chartreuse-tip"],
                "Muddy": ["Black/blue", "Black"],
            },
        },
        "depth": "12-30 ft, dragged/hopped on bottom",
        "presentation": "Long cast, let it settle to bottom, then drag/hop slowly with the rod tip at 9-10 o'clock, reeling up slack between strokes. Most bites come on the fall or the pause.",
    },
    "suspending_jerkbait": {
        "name": "Suspending Jerkbait",
        "video_key": "suspending_jerkbait",
        "colors": {
            "Clear": ["Natural shad", "Ghost minnow"],
            "Stained": ["Chrome/blue", "Clown (chartreuse/orange)"],
            "Muddy": ["Firetiger", "Chartreuse/black"],
        },
        "trailer": None,
        "depth": "2-8 ft, suspended in the water column",
        "presentation": "Jerk-jerk-pause cadence with the rod tip down - let it sit motionless on the pause (longer pause in colder water). Most strikes come on the pause, not the jerk.",
    },
    "blade_bait": {
        "name": "Blade Bait",
        "video_key": "blade_bait",
        "colors": {
            "Clear": ["Silver/natural shad"],
            "Stained": ["Gold/chartreuse"],
            "Muddy": ["Chartreuse/black"],
        },
        "trailer": None,
        "depth": "Bottom to 20 ft",
        "presentation": "Let it sink to bottom on semi-slack line, then lift-and-fall (yo-yo) vertically or on a slow retrieve - the vibration comes on the fall, so stay in contact for subtle bites.",
    },
    "lipless_crankbait": {
        "name": "Lipless Crankbait",
        "video_key": "lipless_crankbait",
        "colors": {
            "Clear": ["Natural shad", "Chrome/blue"],
            "Stained": ["Chartreuse/black back", "Red craw"],
            "Muddy": ["Firetiger", "Solid chartreuse"],
        },
        "trailer": None,
        "depth": "2-10 ft (grass flats/humps)",
        "presentation": "Steady burn over grass with occasional bottom contact, or yo-yo (rip it free, let it flutter back down) when fish are less aggressive - most bites come on the flutter fall.",
    },
    "chatterbait": {
        "name": "Chatterbait (Bladed Jig)",
        "video_key": "chatterbait",
        "colors": {
            "Clear": ["Green pumpkin", "Bluegill"],
            "Stained": ["Chartreuse/white", "Bama craw"],
            "Muddy": ["Black/blue", "Firetiger"],
        },
        "trailer": {
            "type": "Paddle-tail swimbait trailer",
            "colors": {
                "Clear": ["Green pumpkin", "White pearl"],
                "Stained": ["Chartreuse/white", "White"],
                "Muddy": ["Black", "Chartreuse"],
            },
        },
        "depth": "1-6 ft over grass/cover",
        "presentation": "Steady retrieve just above cover so it ticks the tops of grass/wood; occasional rip-and-fall when it hangs up triggers reaction strikes.",
    },
    "squarebill_crankbait": {
        "name": "Squarebill Crankbait",
        "video_key": "squarebill_crankbait",
        "colors": {
            "Clear": ["Natural shad", "Green craw"],
            "Stained": ["Chartreuse/brown craw", "Red craw"],
            "Muddy": ["Firetiger", "Chartreuse/black"],
        },
        "trailer": None,
        "depth": "2-6 ft, deflecting off cover",
        "presentation": "Stop-and-go retrieve that bumps wood/rock/riprap - deflection off cover is what triggers the strike, so aim to hit something on every cast.",
    },
    "deep_diving_crankbait": {
        "name": "Deep-Diving Crankbait",
        "video_key": "deep_diving_crankbait",
        "colors": {
            "Clear": ["Natural shad", "Chrome/blue"],
            "Stained": ["Chartreuse/black back", "Craw pattern"],
            "Muddy": ["Firetiger", "Solid chartreuse"],
        },
        "trailer": None,
        "depth": "15-25+ ft, grinding bottom",
        "presentation": "Long cast, reel down to get it to depth, then grind bottom contact through ledges/humps - deflecting off hard bottom triggers reaction bites.",
    },
    "texas_rig_creature": {
        "name": "Texas-Rigged Creature Bait",
        "video_key": "texas_rig",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon red"],
            "Stained": ["Black/blue", "Junebug"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth": "1-8 ft, pitched/flipped to cover",
        "presentation": "Pitch or flip to isolated cover/beds, let it sink on slack line, then hop/shake in place - most bites happen on the initial fall or right after it settles.",
    },
    "texas_rig_worm": {
        "name": "Texas-Rigged Worm",
        "video_key": "texas_rig",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Stained": ["Red bug", "June bug"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth": "2-10 ft along shoreline cover",
        "presentation": "Cast past cover, drag/hop it along the bottom back to the boat, pausing over wood or grass edges.",
    },
    "wacky_rig_senko": {
        "name": "Wacky-Rigged Senko",
        "video_key": "wacky_rig_senko",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Stained": ["Black", "June bug"],
            "Muddy": ["Black", "Black/blue"],
        },
        "trailer": None,
        "depth": "0-6 ft, weightless fall",
        "presentation": "Cast to cover and let it sink with a slow, shimmying fall on slack line - most strikes happen before it hits bottom, so watch your line.",
    },
    "weightless_soft_plastic": {
        "name": "Weightless Soft Plastic (Fluke-style)",
        "video_key": "weightless_soft_plastic",
        "colors": {
            "Clear": ["Natural shad", "Pearl white"],
            "Stained": ["Chartreuse/white", "Bone"],
            "Muddy": ["Black", "Chartreuse"],
        },
        "trailer": None,
        "depth": "0-4 ft, near surface",
        "presentation": "Twitch-twitch-pause so it darts and glides just under the surface, imitating a dying baitfish.",
    },
    "spinnerbait": {
        "name": "Spinnerbait",
        "video_key": "spinnerbait",
        "colors": {
            "Clear": ["White/silver blade", "Natural shad skirt"],
            "Stained": ["Chartreuse/white skirt", "Gold blade"],
            "Muddy": ["Black/blue skirt", "Colorado gold blade"],
        },
        "trailer": {
            "type": "Curly-tail grub or trailer hook",
            "colors": {
                "Clear": ["White", "Natural shad"],
                "Stained": ["Chartreuse/white"],
                "Muddy": ["Black", "Chartreuse"],
            },
        },
        "depth": "1-10 ft depending on retrieve speed",
        "presentation": "Slow-roll along the bottom near cover in cold/tough conditions, or burn it just under the surface over grass when fish are active.",
    },
    "swim_jig": {
        "name": "Swim Jig",
        "video_key": "swim_jig",
        "colors": {
            "Clear": ["Green pumpkin/shad", "Bluegill"],
            "Stained": ["Chartreuse/white", "Bama craw"],
            "Muddy": ["Black/blue", "Firetiger"],
        },
        "trailer": {
            "type": "Paddle-tail swimbait trailer",
            "colors": {
                "Clear": ["White pearl", "Green pumpkin"],
                "Stained": ["Chartreuse/white", "White"],
                "Muddy": ["Black", "Chartreuse"],
            },
        },
        "depth": "1-6 ft through/over grass and wood",
        "presentation": "Steady swim just fast enough to keep it ticking the top of cover; pause briefly when it deflects off wood to trigger a reaction bite.",
    },
    "carolina_rig": {
        "name": "Carolina-Rigged Worm",
        "video_key": "carolina_rig",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Stained": ["June bug", "Red bug"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth": "8-20 ft, dragged behind the weight on bottom",
        "presentation": "Long cast, drag the rig slowly along the bottom with sweeps of the rod - the clacking weight/bead calls fish in, then the trailing bait gets eaten.",
    },
    "buzzbait": {
        "name": "Buzzbait",
        "video_key": "buzzbait",
        "colors": {
            "Clear": ["White", "Shad"],
            "Stained": ["Chartreuse/white", "Black"],
            "Muddy": ["Black", "Solid chartreuse"],
        },
        "trailer": {
            "type": "Trailer hook, optional soft-plastic trailer (twin-tail grub)",
            "colors": {
                "Clear": ["White"],
                "Stained": ["Chartreuse/white"],
                "Muddy": ["Black"],
            },
        },
        "depth": "Surface",
        "presentation": "Cast past cover, start the retrieve the instant it lands so it plans out on top, and keep a steady-to-slow retrieve so it gurgles across the surface.",
    },
    "walking_topwater": {
        "name": "Walking Topwater (Spook-style)",
        "video_key": "walking_topwater",
        "colors": {
            "Clear": ["Bone/white", "Chrome/blue"],
            "Stained": ["Chartreuse/white", "Bone"],
            "Muddy": ["Black", "Solid white"],
        },
        "trailer": None,
        "depth": "Surface",
        "presentation": "Steady 'walk-the-dog' cadence with rod tip down, snapping slack rhythmically so the bait zig-zags side to side.",
    },
    "popper": {
        "name": "Popper",
        "video_key": "popper",
        "colors": {
            "Clear": ["Shad/natural", "Bone"],
            "Stained": ["Chartreuse/white", "Firetiger"],
            "Muddy": ["Black", "Solid chartreuse"],
        },
        "trailer": None,
        "depth": "Surface",
        "presentation": "Sharp pop-pause-pop with occasional long pauses over calm water/isolated cover - most strikes happen right after the pause, not the pop itself.",
    },
    "hollow_body_frog": {
        "name": "Hollow-Body Frog",
        "video_key": "hollow_body_frog",
        "colors": {
            "Clear": ["Natural frog green", "White belly"],
            "Stained": ["Black", "White"],
            "Muddy": ["Black", "Solid white"],
        },
        "trailer": None,
        "depth": "Surface, over mats/pads/grass",
        "presentation": "Walk or hop it across matted grass/pads with pauses over holes in the cover; wait for the fish to fully engulf it before setting the hook.",
    },
    "finesse_shaky_head": {
        "name": "Finesse Worm / Shaky Head",
        "video_key": "finesse_shaky_head",
        "colors": {
            "Clear": ["Green pumpkin", "Watermelon"],
            "Stained": ["June bug", "Green pumpkin/chartreuse"],
            "Muddy": ["Black/blue", "Black"],
        },
        "trailer": None,
        "depth": "8-20 ft (deeper), or shallow cover in clear water",
        "presentation": "Cast out, let it hit bottom, then shake it in place with the rod tip without moving it far - a subtle, tough-bite bait for high-pressure days.",
    },
}


def _build_block(key: str, water_clarity: str, note: str = "") -> "LureBlock":
    profile = LURE_PROFILES[key]
    colors = profile["colors"].get(water_clarity, profile["colors"]["Stained"])
    trailer = None
    if profile["trailer"]:
        t_colors = profile["trailer"]["colors"].get(water_clarity, profile["trailer"]["colors"]["Stained"])
        trailer = TrailerInfo(type=profile["trailer"]["type"], colors=t_colors)
    return LureBlock(
        key=key,
        name=profile["name"],
        colors=colors,
        trailer=trailer,
        depth=profile["depth"],
        presentation=profile["presentation"],
        videos=get_videos_by_key(profile["video_key"], profile["name"]),
        note=note,
    )


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
    water_clarity: str = "Stained",
) -> LureRecommendation:
    low_light = segment_name in LIGHT_LOW
    rationale = []

    # --- Seasonal base pattern: which lure keys are first vs second choice -----
    if season == "winter":
        first_keys = ["football_jig", "suspending_jerkbait", "blade_bait"]
        second_keys = ["deep_diving_crankbait"]
        rationale.append("Cold water (<50F) - bass are lethargic and hold on deep, stable structure.")
    elif season == "pre_spawn":
        first_keys = ["lipless_crankbait", "chatterbait", "football_jig"]
        second_keys = ["suspending_jerkbait", "squarebill_crankbait"]
        rationale.append("Pre-spawn (50-60F) - fish are staging and feeding heavily before the move shallow.")
    elif season == "spawn":
        first_keys = ["texas_rig_creature", "wacky_rig_senko", "weightless_soft_plastic"]
        second_keys = ["hollow_body_frog", "squarebill_crankbait"]
        rationale.append("Spawn window (60-75F) - bass are shallow and cover/bed-oriented.")
    elif season == "post_spawn_summer":
        first_keys = ["spinnerbait", "swim_jig", "texas_rig_worm"]
        second_keys = ["squarebill_crankbait", "walking_topwater"]
        rationale.append("Post-spawn recovery - fish are moving from spawning flats toward summer haunts.")
    elif season == "summer_peak":
        if low_light:
            first_keys = ["buzzbait", "walking_topwater", "swim_jig"]
            second_keys = ["popper", "squarebill_crankbait", "hollow_body_frog"]
        else:
            first_keys = ["football_jig", "deep_diving_crankbait", "carolina_rig"]
            second_keys = ["suspending_jerkbait", "lipless_crankbait"]
        rationale.append("Summer heat - fish relate to shade/current early/late and deep structure midday.")
    elif season == "fall_feed_up":
        first_keys = ["squarebill_crankbait", "spinnerbait", "swim_jig"]
        second_keys = ["walking_topwater", "lipless_crankbait", "suspending_jerkbait"]
        rationale.append("Fall feed-up - shad move shallow/into creeks and bass feed aggressively to follow.")
    else:  # fall_turnover
        first_keys = ["football_jig", "suspending_jerkbait", "blade_bait"]
        second_keys = ["lipless_crankbait", "deep_diving_crankbait"]
        rationale.append("Fall turnover - oxygen/temp mixing makes bass location and mood unpredictable.")

    # --- Structure-specific nudge (context note, not a lure swap) ---------------
    structure_notes = {
        "Main-lake point": "Fan-cast the point from shallow to deep, focus on the fastest breakline.",
        "Creek channel / ledge": "Idle/graph to find the ledge lip, then work baits parallel to it.",
        "Cove / pocket (shallow cover)": "Target isolated wood, laydowns, and grass clumps inside the cove.",
        "Flat": "Cover water efficiently - flats reward moving baits (spinnerbait, swim jig, crank).",
        "Standing timber": "Vertical presentations (jig, drop shot) worked tight to individual trees.",
        "Riprap / dam face": "Parallel casts down the rock, crawl a jig or crank to deflect off rip-rap.",
        "Bridge piling": "Cast tight to pilings/riprap transitions; vertical jig the shady side.",
        "Boat dock": "Skip a jig or wacky worm under the dock into the shade line.",
    }
    if structure_type in structure_notes:
        rationale.append(structure_notes[structure_type])

    # Crankbaits are broadly useful on hard cover/rock/wood regardless of season -
    # make sure one shows up as a second-choice option whenever it isn't already picked.
    crank_keys = {"squarebill_crankbait", "lipless_crankbait", "deep_diving_crankbait"}
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
        if water_temp_f <= 68 and water_clarity in ("Clear", "Stained"):
            second_keys.append("suspending_jerkbait")

    # --- Pressure trend nudge ---------------------------------------------------
    if pressure_trend_24h <= -1.5:
        rationale.append("Falling pressure - bass are often more aggressive; reaction baits can shine.")
    elif pressure_trend_24h >= 2.0:
        if "finesse_shaky_head" not in second_keys and "finesse_shaky_head" not in first_keys:
            second_keys.insert(0, "finesse_shaky_head")
        rationale.append("High, stable pressure after a front - added a finesse bait for a tougher bite.")

    # De-dupe while preserving order, and don't let a key appear in both lists.
    seen = set()
    first_choice = []
    for k in first_keys:
        if k not in seen:
            first_choice.append(_build_block(k, water_clarity))
            seen.add(k)
    second_choice = []
    for k in second_keys:
        if k not in seen:
            second_choice.append(_build_block(k, water_clarity))
            seen.add(k)

    return LureRecommendation(first_choice=first_choice, second_choice=second_choice, rationale=rationale)
