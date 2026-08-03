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
    # All three seasonal picks bracket 18 ft, so each should reference the 18 ft reading
    # (bottom baits get count-down guidance, column baits get the above-target offset).
    assert all("18 ft" in b.depth for b in rec.first_choice)
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


def test_column_lure_targets_above_marked_fish_depth():
    rec = recommend("summer_peak", 84, "Dawn", -1.0, "Flat", "Stained", fish_depth_ft=7)
    jig_block = next(b for b in rec.first_choice + rec.second_choice if b.key == "swim_jig")
    assert "target ~5-6 ft" in jig_block.depth
    assert "above the 7 ft" in jig_block.depth
    assert "strike up" in jig_block.depth


def test_bottom_lure_gets_countdown_guidance_not_offset():
    rec = recommend("summer_peak", 84, "Midday", -1.0, "Creek channel / ledge", "Stained", fish_depth_ft=7)
    jig_block = next(b for b in rec.first_choice + rec.second_choice if b.key == "football_jig")
    assert "1-2 ft above" not in jig_block.depth  # bottom baits shouldn't get the reaction-bait offset phrasing
    assert "7 ft" in jig_block.depth


def test_rationale_explains_strike_up_bias_when_fish_depth_given():
    rec = recommend("summer_peak", 84, "Midday", -1.0, "Flat", "Stained", fish_depth_ft=10)
    assert any("strike up" in r for r in rec.rationale)


def test_forage_adds_matched_lure_and_rationale():
    # Winter pattern doesn't naturally include a crawfish-imitating lure in
    # either list (football_jig/suspending_jerkbait/blade_bait first,
    # deep_diving_crankbait second) - selecting Crawfish forage should pull
    # one of the crawfish-boost lures in as a second choice and explain why.
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", forage=["Crawfish"])
    keys = {b.key for b in rec.first_choice + rec.second_choice}
    from core.lures import FORAGE_LURE_BOOST
    assert keys & set(FORAGE_LURE_BOOST["Crawfish"])
    assert any("Crawfish" in r or "craw" in r.lower() for r in rec.rationale)


def test_forage_none_adds_no_forage_rationale():
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear")
    assert not any("forage" in r.lower() or "shad are in play" in r.lower() for r in rec.rationale)


def test_forage_does_not_duplicate_already_covered_lure():
    # Gizzard Shad boost list includes lipless_crankbait, which is already the
    # first pick in fall_turnover - forage nudge should not add a duplicate.
    rec = recommend("fall_turnover", 60, "Midday", 0.0, "Creek channel / ledge", "Clear", forage=["Gizzard Shad"])
    all_keys = [b.key for b in rec.first_choice] + [b.key for b in rec.second_choice]
    assert len(all_keys) == len(set(all_keys))


def test_thermocline_caveat_appears_when_fish_depth_below_input():
    rec = recommend("summer_peak", 84, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     fish_depth_ft=25, thermocline_ft=15.0)
    assert any("below the thermocline depth you've set" in r for r in rec.rationale)


def test_thermocline_caveat_absent_when_fish_depth_above_input():
    rec = recommend("summer_peak", 84, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     fish_depth_ft=10, thermocline_ft=15.0)
    assert not any("below the thermocline depth you've set" in r for r in rec.rationale)


def test_thermocline_caveat_absent_when_no_thermocline_value_given():
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     fish_depth_ft=30, thermocline_ft=None)
    assert not any("below the thermocline depth you've set" in r for r in rec.rationale)
