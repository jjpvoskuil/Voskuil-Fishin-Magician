from core.lures import LURE_PROFILES
from core.videos import get_videos_for, get_videos_by_key, VIDEO_LIBRARY


def test_every_lure_profile_video_key_has_curated_videos():
    # Punch-list #82: real angler feedback - "it would be great to have at
    # least one [video] for every true lure ... in our tackle box." A gap
    # check found 6 of 23 categories silently falling back to a generic
    # search link (get_videos_by_key only returns a curated pick when the
    # key is actually in VIDEO_LIBRARY). This locks in that every category
    # the recommendation engine can ever suggest has a real, curated entry,
    # so a future new LURE_PROFILES addition that forgets a video fails a
    # test instead of shipping silently.
    missing = [
        key for key, profile in LURE_PROFILES.items()
        if profile["video_key"] not in VIDEO_LIBRARY
    ]
    assert missing == [], f"LURE_PROFILES categories with no curated video: {missing}"


def test_get_videos_by_key_never_falls_back_to_search_for_a_real_lure_profile():
    for key, profile in LURE_PROFILES.items():
        videos = get_videos_by_key(profile["video_key"], profile["name"])
        for v in videos:
            assert "results?search_query=" not in v["url"], (
                f"{key} ({profile['video_key']}) fell back to a search link instead of a curated video"
            )


def test_known_lures_return_curated_youtube_links():
    for lure in ["Football jig + craw trailer", "Squarebill crankbait", "Suspending jerkbait",
                 "Chatterbait", "Wacky-rigged senko", "Buzzbait", "Hollow-body frog"]:
        videos = get_videos_for(lure)
        assert len(videos) >= 1
        for v in videos:
            assert v["url"].startswith("https://www.youtube.com/")
            assert v["title"]


def test_unmatched_text_falls_back_to_search_link():
    videos = get_videos_for("Some made-up lure name xyz")
    assert len(videos) == 1
    assert "results?search_query=" in videos[0]["url"]
