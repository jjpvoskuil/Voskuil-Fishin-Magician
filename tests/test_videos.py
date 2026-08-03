from core.videos import get_videos_for


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
