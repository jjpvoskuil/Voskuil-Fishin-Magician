"""
Instructional video lookup for lures/techniques.

Each entry below was found via web search and is a real youtube.com/watch
URL (verified present in search results, not guessed/fabricated). A
couple of techniques didn't turn up a confidently-verifiable direct link
in that search pass, so they fall back to a live YouTube search URL
instead - that always works and always shows current results, it just
isn't hand-picked.
"""
from __future__ import annotations
from urllib.parse import quote_plus

VIDEO_LIBRARY = {
    "football_jig": [
        {"title": "Football Jig Bass Fishing Basics | How and Where to Fish", "url": "https://www.youtube.com/watch?v=catT-Ozq9oE"},
        {"title": "Football Jig MASTERCLASS!! (Everything You NEED To Know)", "url": "https://www.youtube.com/watch?v=BRgrhu8ad7g"},
    ],
    "suspending_jerkbait": [
        {"title": "How To Fish A Jerkbait - Bass Basics (John Crews)", "url": "https://www.youtube.com/watch?v=Bi3jy_fWTZw"},
        {"title": "How to Fish a Jerkbait - What You Need to Know (Scott Martin)", "url": "https://www.youtube.com/watch?v=yfyE-d-U9qo"},
    ],
    "blade_bait": [
        {"title": "Blade Baits 101, Bass Fishing", "url": "https://www.youtube.com/watch?v=89oYwmzNWcQ"},
        {"title": "Blade Baits Explained: Colors, Gear & Techniques for Winter", "url": "https://www.youtube.com/watch?v=scIGXsWItI8"},
    ],
    "chatterbait": [
        {"title": "How to Fish a Chatterbait - Bass Fishing", "url": "https://www.youtube.com/watch?v=RYikSKT11Qg"},
        {"title": "How To Fish A Chatterbait (Beginner Tips AND Advanced Tricks)", "url": "https://www.youtube.com/watch?v=tej0NsHeT5U"},
    ],
    "squarebill_crankbait": [
        {"title": "NEW Way to Fish Squarebill Crankbaits for Bass (Mark Zona)", "url": "https://www.youtube.com/watch?v=iarou8m-5xw"},
        {"title": "How to Fish a Squarebill Crankbait for Bass", "url": "https://www.youtube.com/watch?v=5t236S94Ico"},
    ],
    "deep_diving_crankbait": [
        {"title": "How to Fish Deep Diving Crankbaits (Scott Martin)", "url": "https://www.youtube.com/watch?v=kCv6eF23eRI"},
        {"title": "How To Fish The DEEP Diving Crankbait!", "url": "https://www.youtube.com/watch?v=z5TIUGNfiJ0"},
    ],
    "texas_rig": [
        {"title": "Texas Rig 101 - How to Fish a Texas Rig Worm and Catch Bass", "url": "https://www.youtube.com/watch?v=aCpi3zzlLIk"},
        {"title": "How to Rig and Fish Texas Rig Worms for Bass", "url": "https://www.youtube.com/watch?v=8BT4f8DsmTU"},
    ],
    "wacky_rig_senko": [
        {"title": "Wacky Rigging a Senko with an O-Ring, Fishing Lure Tutorial", "url": "https://www.youtube.com/watch?v=u8N--D8C--4"},
        {"title": "How to Fish a Wacky Rig and Other Details About a Senko", "url": "https://www.youtube.com/watch?v=zG2xIq1qd3o"},
    ],
    "weightless_soft_plastic": [
        {"title": "Fluke Rigging Tricks to Catch Bass Shallow or Deep", "url": "https://www.youtube.com/watch?v=U3bP0HkJxk0"},
        {"title": "How To Fish A Fluke - An Easy Guide To Catching Bass", "url": "https://www.youtube.com/watch?v=zT_oHqxlfIU"},
    ],
    "spinnerbait": [
        {"title": "How to Slow Roll a Spinnerbait!", "url": "https://www.youtube.com/watch?v=VQp0bsmnBf4"},
        {"title": "How to Fish a Spinnerbait - Basics of Bass Fishing", "url": "https://www.youtube.com/watch?v=DzAvvzxzcNo"},
    ],
    "swim_jig": [
        {"title": "How to Fish Swim Jigs for Bass | When, Where, How, Gear Tips", "url": "https://www.youtube.com/watch?v=ekgbbPIqYmQ"},
        {"title": "Swim Jig Basics for Bass Fishing", "url": "https://www.youtube.com/watch?v=MOC2qje_bS0"},
    ],
    "carolina_rig": [
        {"title": "The Last Carolina Rig Video You'll Ever Need (Masterclass)", "url": "https://www.youtube.com/watch?v=qCNGjKDg8UA"},
        {"title": "Carolina Rig 101 | How to Rig and Fish (Jacob Wheeler)", "url": "https://www.youtube.com/watch?v=LSUcMtyJN44"},
    ],
    "buzzbait": [
        {"title": "How To Fish a Buzzbait, Fishing Lure Tutorial", "url": "https://www.youtube.com/watch?v=t5ioZ_iOBIo"},
        {"title": "Buzzbait Tips That Really Work!", "url": "https://www.youtube.com/watch?v=bvojy2K9G4Q"},
    ],
    "walking_topwater": [
        {"title": "How To Walk The Dog | Topwater Fishing Tips", "url": "https://www.youtube.com/watch?v=h1sewNNLHsk"},
        {"title": "Exclusive Topwater Fishing Tip: How to \"Walk the Dog\" (Scott Martin)", "url": "https://www.youtube.com/watch?v=Sdim6e4HCik"},
    ],
    "popper": [
        {"title": "Topwater Popper Tips & Tricks: Catch More Fish On The Surface", "url": "https://www.youtube.com/watch?v=frXgWsE6uWw"},
        {"title": "How to Fish a Topwater Popper - Bass Fishing", "url": "https://www.youtube.com/watch?v=uDeMi3IdTcQ"},
    ],
    "hollow_body_frog": [
        {"title": "Basics of Frog Fishing and How to Fish Hollow-Body Frog Lures", "url": "https://www.youtube.com/watch?v=czTtqyDKDcA"},
        {"title": "Hollow Body Frog Bass Fishing | Key Rods and Frogs", "url": "https://www.youtube.com/watch?v=EvbWaO8SNNs"},
    ],
}

# Ordered longest/most-specific substring first so e.g. "suspending jerkbait"
# matches before a generic "jig" check would ever get a chance to.
_KEYWORD_MAP = [
    ("football jig", "football_jig"),
    ("suspending jerkbait", "suspending_jerkbait"),
    ("jerkbait", "suspending_jerkbait"),
    ("blade bait", "blade_bait"),
    ("chatterbait", "chatterbait"),
    ("squarebill", "squarebill_crankbait"),
    ("deep-diving crankbait", "deep_diving_crankbait"),
    ("deep diving crankbait", "deep_diving_crankbait"),
    ("lipless crankbait", None),  # no confidently-verified direct link - falls through to search
    ("texas-rigged", "texas_rig"),
    ("texas rig", "texas_rig"),
    ("wacky-rigged senko", "wacky_rig_senko"),
    ("wacky rig", "wacky_rig_senko"),
    ("senko", "wacky_rig_senko"),
    ("weightless soft plastic", "weightless_soft_plastic"),
    ("fluke", "weightless_soft_plastic"),
    ("spinnerbait", "spinnerbait"),
    ("swim jig", "swim_jig"),
    ("carolina-rigged", "carolina_rig"),
    ("carolina rig", "carolina_rig"),
    ("buzzbait", "buzzbait"),
    ("walking topwater", "walking_topwater"),
    ("popper", "popper"),
    ("hollow-body frog", "hollow_body_frog"),
    ("frog", "hollow_body_frog"),
    ("shaky head", None),  # no confidently-verified direct link - falls through to search
    ("finesse worm", None),
    ("jig", "football_jig"),  # generic jig fallback (e.g. "Jig + craw trailer")
    ("crankbait", "squarebill_crankbait"),  # generic crankbait fallback
]


def _search_fallback(query_text: str) -> dict:
    q = quote_plus(f"{query_text} bass fishing how to")
    return {"title": f"Search YouTube for \"{query_text}\"", "url": f"https://www.youtube.com/results?search_query={q}"}


def get_videos_for(lure_text: str) -> list:
    """
    Given a free-text lure/technique string (e.g. "Squarebill crankbait
    (bumping cover)"), return 1-2 video dicts: [{"title":..., "url":...}].
    Falls back to a live YouTube search link if nothing is confidently
    matched/verified.
    """
    text = lure_text.lower()
    for keyword, key in _KEYWORD_MAP:
        if keyword in text:
            if key and key in VIDEO_LIBRARY:
                return VIDEO_LIBRARY[key]
            return [_search_fallback(lure_text.split(" (")[0])]
    return [_search_fallback(lure_text.split(" (")[0])]
