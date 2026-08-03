"""
Lure / color / presentation recommendation engine for largemouth bass on
Nolin River Lake.

This is a transparent rule table built on well-established bass-fishing
principles (seasonal patterns, light penetration & color visibility,
structure type, and pressure/front timing) rather than a black box. It
takes the outputs of core.scoring (season, water temp, segment/light
level, pressure trend) plus a structure type and water clarity (both
user-selectable, since Nolin doesn't have a live clarity feed) and
returns a concrete recommendation.
"""
from __future__ import annotations
from dataclasses import dataclass, field

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
LIGHT_HIGH = {"Midday"}


@dataclass
class LureRecommendation:
    primary_lures: list
    colors: list
    technique: str
    retrieve: str
    target_depth: str
    rationale: list = field(default_factory=list)


def _color_for_clarity(clarity: str, low_light: bool) -> list:
    if clarity == "Muddy":
        return ["Black/blue", "Junebug", "Chartreuse/black"] if not low_light else ["Black", "Black/blue"]
    if clarity == "Stained":
        return ["Chartreuse/white", "Green pumpkin", "Red/orange craw"] if not low_light else [
            "Black", "Black/blue", "Firetiger"
        ]
    # Clear
    return ["Natural shad", "Green pumpkin", "Watermelon red"] if not low_light else [
        "Bone/white", "Black (silhouette)", "Natural shad"
    ]


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
    colors = _color_for_clarity(water_clarity, low_light)

    # --- Seasonal base pattern -------------------------------------------------
    if season == "winter":
        primary = ["Football jig + craw trailer", "Suspending jerkbait", "Blade bait"]
        technique = "Slow-drag/deadstick the jig on bottom; long pauses on the jerkbait."
        retrieve = "Very slow - fish metabolism is low, give them time to react."
        depth = "Deep main-lake structure: channel bends, bluff ends, deep points (15-30 ft)."
        rationale.append("Cold water (<50F) - bass are lethargic and hold on deep, stable structure.")
    elif season == "pre_spawn":
        primary = ["Lipless crankbait", "Chatterbait", "Jig + craw trailer"]
        technique = "Fan-cast secondary points and creek mouths; yo-yo retrieve for lipless baits."
        retrieve = "Moderate, with occasional rips to trigger reaction strikes."
        depth = "Staging areas: secondary points and creek channels near spawning coves (6-15 ft)."
        rationale.append("Pre-spawn (50-60F) - fish are staging and feeding heavily before the move shallow.")
    elif season == "spawn":
        primary = ["Texas-rigged creature bait", "Wacky-rigged senko", "Weightless soft plastic"]
        technique = "Pitch/flip to isolated shallow cover, beds, and pockets; let it sit."
        retrieve = "Very slow, sight-fishing style presentation with long pauses."
        depth = "Shallow coves and pockets, 1-6 ft, near hard bottom (spawning flats)."
        rationale.append("Spawn window (60-75F) - bass are shallow and cover/bed-oriented.")
    elif season == "post_spawn_summer":
        primary = ["Spinnerbait", "Swim jig", "Texas-rigged worm"]
        technique = "Work shoreline cover and drop-offs adjacent to spawning flats."
        retrieve = "Steady moderate retrieve, slow-rolled around wood/grass edges."
        depth = "Transition zones: 4-10 ft, edges between spawning flats and deeper water."
        rationale.append("Post-spawn recovery - fish are moving from spawning flats toward summer haunts.")
    elif season == "summer_peak":
        if segment_name in LIGHT_LOW:
            primary = ["Buzzbait", "Popper/walking topwater", "Swim jig"]
            technique = "Work shallow cover and points early/late; topwater around calm shorelines."
            retrieve = "Steady walking cadence at dawn/dusk; slow down as light increases."
            depth = "Shallow cover 1-6 ft at dawn/dusk, sliding to nearby deep structure by midday."
        else:
            primary = ["Football jig", "Deep-diving crankbait", "Carolina-rigged worm"]
            technique = "Drag/crawl bottom on ledges and humps; slow-roll deep points."
            retrieve = "Slow and methodical - grind bottom contact through the strike zone."
            depth = "Deep structure: 15-25+ ft ledges, humps, and creek channels."
        rationale.append("Summer heat - fish relate to shade/current early/late and deep structure midday.")
    elif season == "fall_feed_up":
        primary = ["Squarebill crankbait", "Spinnerbait", "Swim jig"]
        technique = "Cover water fast on secondary points and creek arms chasing shad."
        retrieve = "Faster, reaction-style retrieve to match active baitfish."
        depth = "Mid-depth 4-12 ft, following bait schools into creek arms."
        rationale.append("Fall feed-up - shad move shallow/into creeks and bass feed aggressively to follow.")
    else:  # fall_turnover
        primary = ["Jig + craw trailer", "Suspending jerkbait", "Blade bait"]
        technique = "Fish deliberately through turnover's unpredictable bite; vary depth until you find fish."
        retrieve = "Slow to moderate, mix retrieves until a pattern emerges."
        depth = "Variable - test both mid-depth cover and deeper structure."
        rationale.append("Fall turnover - oxygen/temp mixing makes bass location and mood unpredictable.")

    # --- Structure-specific nudge ----------------------------------------------
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

    # --- Pressure trend nudge ---------------------------------------------------
    if pressure_trend_24h <= -1.5:
        rationale.append("Falling pressure - bass are often more aggressive; reaction baits can shine.")
    elif pressure_trend_24h >= 2.0:
        primary = primary[:2] + ["Finesse worm / shaky head"]
        rationale.append("High, stable pressure after a front - add a finesse bait for a tougher bite.")

    return LureRecommendation(
        primary_lures=primary,
        colors=colors,
        technique=technique,
        retrieve=retrieve,
        target_depth=depth,
        rationale=rationale,
    )
