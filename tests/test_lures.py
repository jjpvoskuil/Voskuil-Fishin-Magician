from core.lures import (
    recommend, STRUCTURE_TYPES, WATER_CLARITY_OPTIONS, LURE_PROFILES, guess_category_from_text,
    is_trailer_eligible, TRAILER_ELIGIBLE_CATEGORIES,
)


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


def test_threadfin_shad_and_stonerollers_are_valid_forage_options():
    from core.lures import FORAGE_OPTIONS, FORAGE_NOTES, FORAGE_LURE_BOOST
    for forage_type in ("Threadfin Shad", "Stonerollers"):
        assert forage_type in FORAGE_OPTIONS
        assert forage_type in FORAGE_NOTES
        assert forage_type in FORAGE_LURE_BOOST
        rec = recommend("summer_peak", 84, "Midday", 0.0, "Flat", "Clear", forage=[forage_type])
        assert any(FORAGE_NOTES[forage_type].split(" - ")[0] in r for r in rec.rationale)


def test_no_inventory_leaves_blocks_unowned():
    rec = recommend("summer_peak", 84, "Midday", -1.0, "Creek channel / ledge", "Clear")
    for block in rec.first_choice + rec.second_choice:
        assert block.owned is False
        assert block.owned_items == []


def test_inventory_annotates_owned_lure_block():
    # football_jig is a first-choice pick for winter conditions; football_jig's
    # "Clear" water color suggestion is "Green pumpkin"/"Watermelon red", so the
    # owned item's description needs to share one of those color words to be
    # surfaced (see the color-match gate added after user feedback).
    inventory = [
        {"brand": "Strike King", "description": "Tour Grade Football Jig - Green Pumpkin",
         "category": "football_jig", "quantity": "2", "sku": "1534654",
         "image_url": "https://example.com/jig.jpg", "image_filename": ""},
    ]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    jig_block = next(b for b in rec.first_choice if b.key == "football_jig")
    assert jig_block.owned is True
    assert jig_block.owned_items[0]["brand"] == "Strike King"
    assert jig_block.owned_items[0]["quantity"] == 2
    assert jig_block.owned_items[0]["image_url"] == "https://example.com/jig.jpg"
    assert jig_block.owned_items[0]["image_filename"] == ""
    # Nothing else in this recommendation was tagged as owned.
    other_blocks = [b for b in rec.first_choice + rec.second_choice if b.key != "football_jig"]
    assert all(not b.owned for b in other_blocks)


def test_inventory_zero_quantity_is_not_owned():
    inventory = [
        {"brand": "Strike King", "description": "Tour Grade Football Jig - Black/Blue",
         "category": "football_jig", "quantity": "0", "sku": "1534654"},
    ]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    jig_block = next(b for b in rec.first_choice if b.key == "football_jig")
    assert jig_block.owned is False


def test_inventory_unrecognized_category_is_ignored():
    inventory = [
        {"brand": "No Name", "description": "Mystery bait", "category": "not_a_real_category",
         "quantity": "5", "sku": ""},
    ]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    assert all(not b.owned for b in rec.first_choice + rec.second_choice)


def test_owned_lures_sort_before_unowned_within_each_tier():
    # winter first-choice keys (unsorted by depth since no fish_depth_ft given) are
    # football_jig, suspending_jerkbait, blade_bait - own only blade_bait and confirm
    # it moves to the front of the list once inventory is supplied. blade_bait's
    # "Clear" water color suggestion is "Silver/natural shad", so the description
    # needs to share one of those words to pass the color-match gate.
    inventory = [
        {"brand": "Rapala", "description": "Rippin Rap - Silver", "category": "blade_bait",
         "quantity": "1", "sku": ""},
    ]
    rec_plain = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear")
    assert [b.key for b in rec_plain.first_choice][0] == "football_jig"

    rec_owned = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    assert rec_owned.first_choice[0].key == "blade_bait"
    assert rec_owned.first_choice[0].owned is True
    # same set of lures either way - inventory only reorders, never adds/removes
    assert {b.key for b in rec_owned.first_choice} == {b.key for b in rec_plain.first_choice}


def test_medium_diving_crankbait_profile_is_complete():
    from core.lures import LURE_PROFILES, WATER_CLARITY_OPTIONS
    profile = LURE_PROFILES["medium_diving_crankbait"]
    assert profile["name"]
    assert profile["depth_range_ft"] == (6, 12)
    for clarity in WATER_CLARITY_OPTIONS:
        assert clarity in profile["colors"]


def test_medium_diving_crankbait_preferred_when_fish_depth_matches():
    # "Boat dock" isn't in the crank-ensure nudge's structure list, so use one that is,
    # with a season/segment combo that doesn't already include a crank pick, and a fish
    # depth reading squarely in the medium-diving zone.
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Clear", fish_depth_ft=9)
    keys = {b.key for b in rec.first_choice + rec.second_choice}
    assert "medium_diving_crankbait" in keys


def test_color_tokens_extracts_meaningful_words_and_drops_stopwords():
    from core.lures import _color_tokens
    assert _color_tokens("Chartreuse/black back") == {"chartreuse", "black"}
    assert _color_tokens("Craw pattern") == {"craw"}
    assert _color_tokens("") == set()
    assert _color_tokens(None) == set()


def test_owned_item_matching_suggested_color_is_shown():
    # medium_diving_crankbait in "Green stained" water suggests "Chartreuse/black
    # back" and "Green shad" - an owned item described with either color word
    # should show up as owned.
    inventory = [
        {"brand": "Strike King", "description": "3XD Chartreuse Shad",
         "category": "medium_diving_crankbait", "quantity": "1", "sku": ""},
    ]
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Green stained", fish_depth_ft=9,
                     inventory=inventory)
    block = next(b for b in rec.first_choice + rec.second_choice if b.key == "medium_diving_crankbait")
    assert block.owned is True
    assert block.owned_items[0]["description"] == "3XD Chartreuse Shad"


def test_owned_item_not_matching_suggested_color_is_hidden():
    # Reproduces the user-reported case: the suggestion is chartreuse/green
    # shad, but the owned item is a craw pattern - per follow-up feedback,
    # non-matching owned items are no longer shown at all, so this block
    # should fall back to the plain "not owned" state.
    inventory = [
        {"brand": "Strike King", "description": "3XD Chili Craw",
         "category": "medium_diving_crankbait", "quantity": "1", "sku": ""},
    ]
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Green stained", fish_depth_ft=9,
                     inventory=inventory)
    block = next(b for b in rec.first_choice + rec.second_choice if b.key == "medium_diving_crankbait")
    assert block.owned is False
    assert block.owned_items == []


def test_only_color_matched_owned_items_are_shown_others_dropped():
    inventory = [
        {"brand": "Strike King", "description": "3XD Chili Craw",
         "category": "medium_diving_crankbait", "quantity": "1", "sku": ""},
        {"brand": "Rapala", "description": "DT Dives-To Bluegill",
         "category": "medium_diving_crankbait", "quantity": "1", "sku": ""},
        {"brand": "Bandit", "description": "300 Green Shad",
         "category": "medium_diving_crankbait", "quantity": "1", "sku": ""},
    ]
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Green stained", fish_depth_ft=9,
                     inventory=inventory)
    block = next(b for b in rec.first_choice + rec.second_choice if b.key == "medium_diving_crankbait")
    assert len(block.owned_items) == 1
    assert block.owned_items[0]["description"] == "300 Green Shad"


def test_owned_items_are_capped_at_top_2_ranked_by_quantity():
    # Punch-list #8: "only show the top 2 recommendations in each category...
    # with a #1 and a #2 choice" - even with 3 color-matched items on hand,
    # only the 2 with the most quantity in reserve should come back, most
    # in-stock first.
    inventory = [
        {"brand": "Strike King", "description": "3XD Chartreuse Shad - low stock",
         "category": "medium_diving_crankbait", "quantity": "1", "sku": "a"},
        {"brand": "Rapala", "description": "DT Green Shad - most stock",
         "category": "medium_diving_crankbait", "quantity": "5", "sku": "b"},
        {"brand": "Bandit", "description": "300 Green Shad - mid stock",
         "category": "medium_diving_crankbait", "quantity": "3", "sku": "c"},
    ]
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Green stained", fish_depth_ft=9,
                     inventory=inventory)
    block = next(b for b in rec.first_choice + rec.second_choice if b.key == "medium_diving_crankbait")
    assert len(block.owned_items) == 2
    assert [it["sku"] for it in block.owned_items] == ["b", "c"]


def test_owned_items_tie_on_quantity_keeps_original_order():
    inventory = [
        {"brand": "Strike King", "description": "3XD Chartreuse Shad - first",
         "category": "medium_diving_crankbait", "quantity": "2", "sku": "a"},
        {"brand": "Rapala", "description": "DT Green Shad - second",
         "category": "medium_diving_crankbait", "quantity": "2", "sku": "b"},
        {"brand": "Bandit", "description": "300 Green Shad - third",
         "category": "medium_diving_crankbait", "quantity": "2", "sku": "c"},
    ]
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Green stained", fish_depth_ft=9,
                     inventory=inventory)
    block = next(b for b in rec.first_choice + rec.second_choice if b.key == "medium_diving_crankbait")
    assert [it["sku"] for it in block.owned_items] == ["a", "b"]


def test_guess_category_from_text_matches_known_product_names():
    cases = [
        ("Strike King Rattling Thunder Cricket Swim Jig - White", "chatterbait"),
        ("Strike King 3XD Series Pro-Model Crankbait - Powder Blue", "medium_diving_crankbait"),
        ("Strike King Pro-Model XD Crankbait (5XD) - Tennessee Shad", "deep_diving_crankbait"),
        ("Strike King KVD Elite Double-Willow Spinnerbait", "spinnerbait"),
        ("Strike King Red Eyed Shad Tungsten 2 Tap Lipless Crankbait", "lipless_crankbait"),
        ("Strike King Tour Grade Football Jig - Black/Blue", "football_jig"),
        ("Z-Man Finesse TRD - Green Pumpkin", "finesse_shaky_head"),
        ("Roboworm FAT Straight Worm - Margarita Mutilator", "wacky_rig_senko"),
        ("Strike King KVD Rattling Square Bill Crankbait", "squarebill_crankbait"),
        ("Strike King Rage Tail Craw Soft Bait - Fire Craw", "texas_rig_creature"),
        ("Booyah Poppin' Pad Crasher Frog", "hollow_body_frog"),
        ("Some Unbranded Doohickey", ""),
    ]
    for text, expected in cases:
        assert guess_category_from_text(text) == expected, text


def test_guess_category_from_text_every_returned_key_is_real():
    # Every non-blank key this function can ever return must be a real
    # LURE_PROFILES key, or the Lure Inventory page's category dropdown
    # (built from LURE_CATEGORY_OPTIONS) wouldn't recognize it.
    from core.lures import _CATEGORY_KEYWORD_RULES
    for key, _phrases in _CATEGORY_KEYWORD_RULES:
        assert key in LURE_PROFILES, key


def test_guess_category_from_text_blank_input():
    assert guess_category_from_text("") == ""
    assert guess_category_from_text() == ""


# --- is_trailer_eligible / TRAILER_ELIGIBLE_CATEGORIES -----------------------

def _inv_item(**kwargs):
    base = {"item_id": "abc123", "brand": "Strike King", "description": "Test Lure", "category": ""}
    base.update(kwargs)
    return base


def test_trailer_eligible_categories_are_all_real_lure_profiles():
    for key in TRAILER_ELIGIBLE_CATEGORIES:
        assert key in LURE_PROFILES, key


def test_is_trailer_eligible_true_for_craw_and_swimbait_style_categories():
    assert is_trailer_eligible(_inv_item(category="texas_rig_creature")) is True
    assert is_trailer_eligible(_inv_item(category="weightless_soft_plastic")) is True


def test_is_trailer_eligible_false_for_worm_style_categories():
    # These are the exact categories the angler asked to exclude ("not for
    # worms or TRD's") - Texas-rigged worms, wacky senkos, finesse worms,
    # and Carolina-rigged worms aren't trailers, they're standalone rigs.
    for category in ("texas_rig_worm", "wacky_rig_senko", "finesse_shaky_head", "carolina_rig"):
        assert is_trailer_eligible(_inv_item(category=category)) is False, category


def test_is_trailer_eligible_false_for_host_bait_categories():
    # A jig/chatterbait/spinnerbait/swim_jig/buzzbait is what a trailer gets
    # ADDED to - it isn't itself a trailer.
    for category in ("football_jig", "chatterbait", "spinnerbait", "swim_jig", "buzzbait"):
        assert is_trailer_eligible(_inv_item(category=category)) is False, category


def test_is_trailer_eligible_keyword_safety_net_excludes_trd_even_if_miscategorized():
    # Z-Man's TRD line is a finesse worm - explicitly called out by the
    # angler. Even if it were (incorrectly) tagged as a trailer-eligible
    # category, the brand/description keyword check should still exclude it.
    item = _inv_item(category="texas_rig_creature", brand="Z-Man", description="Finesse TRD - Green Pumpkin")
    assert is_trailer_eligible(item) is False


def test_is_trailer_eligible_matches_real_logged_trailer_uses():
    # Every trailer the angler has actually logged so far is a Strike King
    # Rage Tail Craw (texas_rig_creature) or a KVD Blade Minnow
    # (weightless_soft_plastic) - confirms the filter doesn't regress real
    # historical usage.
    craw = _inv_item(category="texas_rig_creature", brand="Strike King",
                      description='Rage Tail Craw Soft Bait - Fire Craw, 4", 7-pack')
    blade_minnow = _inv_item(category="weightless_soft_plastic", brand="Strike King",
                              description='KVD Perfect Plastics Blade Minnow - Key Lime Pie, 4-1/2", 8-pack')
    assert is_trailer_eligible(craw) is True
    assert is_trailer_eligible(blade_minnow) is True
