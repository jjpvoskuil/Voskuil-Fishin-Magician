from core.lures import recommend, STRUCTURE_TYPES, WATER_CLARITY_OPTIONS, LURE_PROFILES


def test_recommend_returns_valid_blocks():
    rec = recommend("summer_peak", 85, "Midday", -1.0, "Creek channel / ledge", "Stained")
    assert len(rec.first_choice) >= 2
    for block in rec.first_choice + rec.second_choice:
        assert block.name
        assert len(block.colors) >= 1
        assert block.depth
        assert block.presentation
        assert len(block.videos) >= 1
        assert block.videos[0]["url"].startswith("https://www.youtube.com/")


def test_no_lure_appears_in_both_lists():
    rec = recommend("fall_feed_up", 68, "Dawn", -2.0, "Flat", "Muddy")
    first_keys = {b.key for b in rec.first_choice}
    second_keys = {b.key for b in rec.second_choice}
    assert not (first_keys & second_keys)


def test_all_seasons_and_segments_produce_recommendations():
    seasons = ["winter", "pre_spawn", "spawn", "post_spawn_summer", "summer_peak", "fall_feed_up", "fall_turnover"]
    segments = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]
    for season in seasons:
        for seg in segments:
            for structure in STRUCTURE_TYPES:
                for clarity in WATER_CLARITY_OPTIONS:
                    rec = recommend(season, 70, seg, 0.0, structure, clarity)
                    assert rec.first_choice


def test_crankbait_jerkbait_topwater_show_up_broadly():
    seasons = ["winter", "pre_spawn", "spawn", "post_spawn_summer", "summer_peak", "fall_feed_up", "fall_turnover"]
    segments = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]
    crank_hits = jerk_hits = topwater_hits = total = 0
    for season in seasons:
        for seg in segments:
            rec = recommend(season, 70, seg, 0.0, "Flat", "Stained")
            keys = {b.key for b in rec.first_choice + rec.second_choice}
            total += 1
            if keys & {"squarebill_crankbait", "lipless_crankbait", "deep_diving_crankbait"}:
                crank_hits += 1
            if "suspending_jerkbait" in keys:
                jerk_hits += 1
            if keys & {"buzzbait", "walking_topwater", "popper", "hollow_body_frog"}:
                topwater_hits += 1
    assert crank_hits / total > 0.5
    assert jerk_hits / total > 0.3
    assert topwater_hits / total > 0.3


def test_trailer_only_present_where_defined():
    for key, profile in LURE_PROFILES.items():
        if profile["trailer"] is None:
            continue
        assert "type" in profile["trailer"]
        for clarity in WATER_CLARITY_OPTIONS:
            assert clarity in profile["trailer"]["colors"]


def test_fish_depth_reorders_by_match_quality():
    rec = recommend("summer_peak", 84, "Midday", -1.0, "Creek channel / ledge", "Stained", fish_depth_ft=18)
    # All three seasonal picks bracket 18 ft, so order should be unchanged and each annotated.
    assert all("dialed in" in b.depth for b in rec.first_choice)
    assert any("marking fish" in r for r in rec.rationale)


def test_fish_depth_flags_mismatch_without_dropping_lure():
    rec = recommend("summer_peak", 84, "Midday", -1.0, "Creek channel / ledge", "Stained", fish_depth_ft=3)
    all_blocks = rec.first_choice + rec.second_choice
    keys = {b.key for b in all_blocks}
    # same lure set as without a reading - nothing added or removed, just reordered/annotated
    rec_plain = recommend("summer_peak", 84, "Midday", -1.0, "Creek channel / ledge", "Stained")
    plain_keys = {b.key for b in rec_plain.first_choice + rec_plain.second_choice}
    assert keys == plain_keys
    assert any("marking fish shallower" in b.depth for b in all_blocks)


def test_no_fish_depth_reading_omits_depth_annotation():
    rec = recommend("summer_peak", 84, "Midday", -1.0, "Creek channel / ledge", "Stained")
    assert not any("marking fish" in b.depth for b in rec.first_choice + rec.second_choice)
    assert not any("marking fish" in r for r in rec.rationale)
