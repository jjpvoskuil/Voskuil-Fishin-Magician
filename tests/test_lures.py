import json

from core.lures import (
    recommend, STRUCTURE_TYPES, WATER_CLARITY_OPTIONS, LURE_PROFILES, guess_category_from_text,
    is_trailer_eligible, TRAILER_ELIGIBLE_CATEGORIES, find_inventory_gaps,
    curate_recommendation, MAX_RECOMMENDED_DISPLAY, MAX_GAP_DISPLAY,
    STRONG_HISTORY_MIN_TRIPS, STRONG_HISTORY_CATCH_RATE,
)


def _history_trip(lure_category, structure_type="Main-lake point", water_clarity="Green stained",
                   segment="Midday", spot_id="spot1", fish_caught=1, biggest_fish_lb=1.5, water_temp_f=45.0):
    # Punch-list #37 test helper - matches core.storage's real row shape
    # (dict with a conditions_json string), same as tests/test_lure_history.py's
    # own helper, duplicated here to keep this file's recommend()-focused
    # tests self-contained rather than reaching into another test module.
    return {
        "spot_id": spot_id,
        "structure_type": structure_type,
        "water_clarity": water_clarity,
        "segment": segment,
        "fish_caught": fish_caught,
        "biggest_fish_lb": biggest_fish_lb,
        "conditions_json": json.dumps({"lure_category": lure_category, "water_temp_f": water_temp_f}),
    }


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
        {"item_id": "jig-1", "brand": "Strike King", "description": "Tour Grade Football Jig - Green Pumpkin",
         "category": "football_jig", "quantity": "2", "sku": "1534654",
         "image_url": "https://example.com/jig.jpg", "image_filename": ""},
    ]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    jig_block = next(b for b in rec.first_choice if b.key == "football_jig")
    assert jig_block.owned is True
    assert jig_block.owned_items[0]["item_id"] == "jig-1"
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
    # Punch-list #37: winter first-choice keys (unsorted by depth since no
    # fish_depth_ft given) are now suspending_jerkbait, medium_diving_crankbait,
    # football_jig (Nolin-documented pattern - see core.lures.recommend()'s
    # winter branch) - own only football_jig (last in the list) and confirm it
    # moves to the front once inventory is supplied. football_jig's "Clear"
    # water color suggestion is "Green pumpkin/Watermelon red", so the
    # description needs to share one of those words to pass the color-match gate.
    inventory = [
        {"brand": "Strike King", "description": "Hack Attack Jig - Green Pumpkin", "category": "football_jig",
         "quantity": "1", "sku": ""},
    ]
    rec_plain = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear")
    assert [b.key for b in rec_plain.first_choice][0] == "suspending_jerkbait"
    assert [b.key for b in rec_plain.first_choice][-1] == "football_jig"

    rec_owned = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    assert rec_owned.first_choice[0].key == "football_jig"
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


def test_owned_items_are_capped_at_top_2_in_original_order_when_no_track_record():
    # Punch-list #8: "only show the top 2 recommendations in each category...
    # with a #1 and a #2 choice" - even with 3 color-matched items on hand,
    # only 2 should come back. Punch-list #88: with no trip_history passed
    # (as here), none of these items has a catch-success rate, so there's
    # no signal to rank them by - quantity on hand is deliberately NOT used
    # as a fallback (real angler feedback: "the qty on hand is irrelevant
    # for this"), so ties simply keep the order they arrived in
    # (inventory's own row order), regardless of how much of each is in
    # stock - note "most stock"/"low stock" in the descriptions below are
    # red herrings, kept from this test's original quantity-ranked version,
    # deliberately NOT reflected in the expected order.
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
    assert [it["sku"] for it in block.owned_items] == ["a", "b"]


def test_owned_items_with_no_track_record_and_equal_quantity_keep_original_order():
    # Same-quantity items used to be an explicit tie-on-quantity case; now
    # that quantity isn't part of the ranking at all (punch-list #88), this
    # is really just another no-track-record tie - kept as its own test
    # since equal quantity was the original reported scenario.
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


def _item_history_trip(lure_used, structure_type="Main-lake point", spot_id="spot1", fish_caught=1,
                        lure_start_time="08:00:00", lure_end_time="09:00:00"):
    # Punch-list #88 test helper - same shape as tests/test_lure_history.py's
    # own _item_trip(), duplicated here for the same "keep this file's
    # recommend()/_build_block()-focused tests self-contained" reason
    # _history_trip() above already gives for punch-list #37's helper.
    return {
        "spot_id": spot_id,
        "structure_type": structure_type,
        "lure_used": lure_used,
        "fish_caught": fish_caught,
        "conditions_json": json.dumps({
            "lure_category": "medium_diving_crankbait",
            "lure_start_time": lure_start_time,
            "lure_end_time": lure_end_time,
        }),
    }


def test_owned_items_rank_by_catch_success_ahead_of_quantity():
    # Punch-list #88: the angler's real complaint - a KVD-like crankbait with
    # more quantity on hand was outranking a lower-quantity item that had
    # actually caught more fish. With a trustworthy per-item track record,
    # the higher-quantity item should no longer automatically win.
    from core.lures import _build_block
    owned = [
        {"brand": "Strike King", "description": "3XD Chartreuse Shad - most stock",
         "quantity": 5, "sku": "high_qty_low_catch", "item_id": "a",
         "image_url": "", "image_filename": ""},
        {"brand": "Rapala", "description": "DT Green Shad - low stock",
         "quantity": 1, "sku": "low_qty_high_catch", "item_id": "b",
         "image_url": "", "image_filename": ""},
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    trip_history = [
        # "Strike King - 3XD Chartreuse Shad - most stock": 1 fish/hr, twice.
        _item_history_trip("Strike King - 3XD Chartreuse Shad - most stock", fish_caught=1),
        _item_history_trip("Strike King - 3XD Chartreuse Shad - most stock", fish_caught=1),
        # "Rapala - DT Green Shad - low stock": 4 fish/hr, twice - the real
        # producer, despite only 1 on hand.
        _item_history_trip("Rapala - DT Green Shad - low stock", fish_caught=4),
        _item_history_trip("Rapala - DT Green Shad - low stock", fish_caught=4),
    ]
    block = _build_block("medium_diving_crankbait", "Green stained", owned_items=owned,
                          trip_history=trip_history, situation=situation)
    assert [it["sku"] for it in block.owned_items] == ["low_qty_high_catch", "high_qty_low_catch"]
    assert block.owned_items[0]["_item_fish_per_hour"] == 4.0
    assert block.owned_items[1]["_item_fish_per_hour"] == 1.0


def test_owned_items_without_track_record_do_not_rank_by_quantity():
    # No trip_history/situation passed at all - no item has a catch-success
    # rate, so nothing distinguishes them for ranking purposes. Real angler
    # feedback: "the qty on hand is irrelevant for this" - so even though
    # "b" has 5x the stock of "a", quantity must NOT decide the order;
    # items should simply keep the order they arrived in.
    from core.lures import _build_block
    owned = [
        {"brand": "Strike King", "description": "3XD Chartreuse Shad - low stock",
         "quantity": 1, "sku": "a", "item_id": "a", "image_url": "", "image_filename": ""},
        {"brand": "Rapala", "description": "DT Green Shad - most stock",
         "quantity": 5, "sku": "b", "item_id": "b", "image_url": "", "image_filename": ""},
    ]
    block = _build_block("medium_diving_crankbait", "Green stained", owned_items=owned)
    assert [it["sku"] for it in block.owned_items] == ["a", "b"]
    assert all(it["_item_fish_per_hour"] is None for it in block.owned_items)


def test_owned_items_with_a_proven_rate_outrank_an_unproven_higher_quantity_item():
    # An item with a real (if modest) track record should still rank ahead
    # of one with none at all, however much more of it is in the tackle box.
    from core.lures import _build_block
    owned = [
        {"brand": "Strike King", "description": "3XD Chartreuse Shad - most stock, never logged",
         "quantity": 10, "sku": "unproven", "item_id": "a", "image_url": "", "image_filename": ""},
        {"brand": "Rapala", "description": "DT Green Shad - one on hand, proven",
         "quantity": 1, "sku": "proven", "item_id": "b", "image_url": "", "image_filename": ""},
    ]
    situation = {"structure_type": "Main-lake point", "spot_id": "spot1"}
    trip_history = [
        _item_history_trip("Rapala - DT Green Shad - one on hand, proven", fish_caught=1),
        _item_history_trip("Rapala - DT Green Shad - one on hand, proven", fish_caught=1),
    ]
    block = _build_block("medium_diving_crankbait", "Green stained", owned_items=owned,
                          trip_history=trip_history, situation=situation)
    assert [it["sku"] for it in block.owned_items] == ["proven", "unproven"]


def test_owned_off_color_item_populates_off_color_list_not_owned_items():
    # Punch-list #48: reproduces the exact user-reported case - a Heddon
    # Super Spook Jr. in "Blue Chrome" is correctly categorized as
    # walking_topwater, but "Chrome/blue" is only a suggested color under
    # "Clear" water clarity (see LURE_PROFILES["walking_topwater"]["colors"]).
    # Under Nolin's more typical "Green stained" water, it should NOT show
    # as a color-matched owned_items pick, but SHOULD show up in the new
    # owned_off_color_items list so the UI can say "you own one, wrong
    # color" instead of the misleading "not in your inventory yet."
    from core.lures import _build_block
    owned = [
        {"item_id": "82ac5107", "brand": "Heddon",
         "description": "Heddon Super Spook Jr. - Blue Chrome",
         "quantity": 1, "sku": "", "image_url": "", "image_filename": ""},
    ]
    block = _build_block("walking_topwater", "Green stained", owned_items=owned)
    assert block.owned is False
    assert block.owned_items == []
    assert len(block.owned_off_color_items) == 1
    assert block.owned_off_color_items[0]["item_id"] == "82ac5107"

    # Under "Clear" water, the very same item DOES match ("Chrome/blue" is
    # a suggested color there), so it should show as owned and NOT appear
    # in the off-color list.
    clear_block = _build_block("walking_topwater", "Clear", owned_items=owned)
    assert clear_block.owned is True
    assert clear_block.owned_items[0]["item_id"] == "82ac5107"
    assert clear_block.owned_off_color_items == []


def test_owned_off_color_items_empty_when_nothing_owned_in_category():
    # No owned_items at all (the true "you don't own this lure type yet"
    # case) should leave BOTH lists empty, not just owned_items.
    from core.lures import _build_block
    block = _build_block("walking_topwater", "Green stained", owned_items=None)
    assert block.owned is False
    assert block.owned_items == []
    assert block.owned_off_color_items == []

    empty_block = _build_block("walking_topwater", "Green stained", owned_items=[])
    assert empty_block.owned is False
    assert empty_block.owned_items == []
    assert empty_block.owned_off_color_items == []


def test_owned_off_color_items_excludes_color_matched_items():
    # A mix of one color-matched and one off-color item in the same
    # category: the matched one should appear only in owned_items, and the
    # off-color one should appear only in owned_off_color_items - no
    # duplication across the two lists.
    from core.lures import _build_block
    owned = [
        {"item_id": "matched-1", "brand": "Heddon",
         "description": "Heddon Super Spook - Bone/white",
         "quantity": 1, "sku": "", "image_url": "", "image_filename": ""},
        {"item_id": "off-color-1", "brand": "Heddon",
         "description": "Heddon Super Spook Jr. - Blue Chrome",
         "quantity": 1, "sku": "", "image_url": "", "image_filename": ""},
    ]
    block = _build_block("walking_topwater", "Green stained", owned_items=owned)
    assert [it["item_id"] for it in block.owned_items] == ["matched-1"]
    assert [it["item_id"] for it in block.owned_off_color_items] == ["off-color-1"]


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
        # Punch-list #37: "swimbait" now routes to the new dedicated
        # soft_swimbait category instead of weightless_soft_plastic (which
        # stays fluke/soft-jerkbait-only, a genuinely different presentation).
        ("Bass Pro Shops Paddle Tail Shad Swimbait - White Pearl", "soft_swimbait"),
        ("Zoom Super Fluke - Pearl", "weightless_soft_plastic"),
        ("VMC Spinshot Drop Shot Hook Rig", "drop_shot"),
    ]
    for text, expected in cases:
        assert guess_category_from_text(text) == expected, text


def test_guess_category_from_text_every_returned_key_is_real():
    # Every non-blank key this function can ever return must be a real
    # LURE_PROFILES key, or the Tackle Box page's category dropdown
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


# --- find_inventory_gaps (punch-list #14) -------------------------------

def test_find_inventory_gaps_returns_every_category_for_empty_inventory():
    assert find_inventory_gaps([]) == list(LURE_PROFILES.keys())


def test_find_inventory_gaps_excludes_owned_categories():
    inventory = [
        {"brand": "Strike King", "description": "Football Jig", "category": "football_jig", "quantity": "3"},
        {"brand": "Rapala", "description": "Jerkbait", "category": "suspending_jerkbait", "quantity": "1"},
    ]
    gaps = find_inventory_gaps(inventory)
    assert "football_jig" not in gaps
    assert "suspending_jerkbait" not in gaps
    assert len(gaps) == len(LURE_PROFILES) - 2


def test_find_inventory_gaps_treats_zero_quantity_as_still_a_gap():
    inventory = [
        {"brand": "Strike King", "description": "Football Jig", "category": "football_jig", "quantity": "0"},
    ]
    assert "football_jig" in find_inventory_gaps(inventory)


def test_find_inventory_gaps_ignores_unrecognized_categories():
    inventory = [
        {"brand": "No Name", "description": "Mystery bait", "category": "not_a_real_category", "quantity": "5"},
    ]
    assert find_inventory_gaps(inventory) == list(LURE_PROFILES.keys())


def test_find_inventory_gaps_includes_trailer_eligible_categories_when_unowned():
    # texas_rig_creature/weightless_soft_plastic are themselves LURE_PROFILES
    # entries (the app's two trailer types) - confirms the gap check covers
    # "trailers" without any separate trailer-specific logic.
    gaps = find_inventory_gaps([])
    assert TRAILER_ELIGIBLE_CATEGORIES.issubset(set(gaps))


def test_find_inventory_gaps_returns_no_gaps_when_everything_is_owned():
    inventory = [
        {"brand": "Brand", "description": "Item", "category": key, "quantity": "1"}
        for key in LURE_PROFILES
    ]
    assert find_inventory_gaps(inventory) == []


def test_find_inventory_gaps_preserves_lure_profiles_order():
    inventory = [
        {"brand": "Brand", "description": "Item", "category": "suspending_jerkbait", "quantity": "1"},
    ]
    gaps = find_inventory_gaps(inventory)
    expected = [k for k in LURE_PROFILES if k != "suspending_jerkbait"]
    assert gaps == expected


# --- Punch-list #37: personal trip-history nudge -----------------------------

def test_recommend_without_trip_history_behaves_exactly_as_before():
    # No trip_history/spot_id passed - every block's note should stay empty,
    # confirming this is a purely additive, opt-in feature.
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear")
    assert all(b.note == "" for b in rec.first_choice + rec.second_choice)


def test_recommend_attaches_a_note_to_an_already_picked_lure_with_matching_history():
    # football_jig is already a winter first-choice pick - give it a real,
    # situation-matched track record and confirm the note lands on that
    # exact block rather than changing which lures are picked.
    history = [_history_trip("football_jig", structure_type="Creek channel / ledge", spot_id="spot1", fish_caught=1)] * 2
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    jig_block = next(b for b in rec.first_choice if b.key == "football_jig")
    assert "Your own history" in jig_block.note
    assert "2 of 2" in jig_block.note
    # Didn't change which lures are recommended, just annotated one.
    assert {b.key for b in rec.first_choice} == {"suspending_jerkbait", "medium_diving_crankbait", "football_jig"}


def test_recommend_injects_a_fish_producing_lure_not_in_the_seasonal_pattern():
    # carolina_rig isn't part of winter's picks at all - a real, matching,
    # fish-producing history on it should surface it as an extra second-choice
    # option (the "even if it's not in your tackle box" case), not silently
    # get ignored just because the season/structure rules didn't pick it.
    history = [_history_trip("carolina_rig", structure_type="Creek channel / ledge", spot_id="spot1", fish_caught=1)] * 2
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    injected = next((b for b in rec.second_choice if b.key == "carolina_rig"), None)
    assert injected is not None
    assert "Your own history" in injected.note
    assert "tackle box" in injected.note.lower()


def test_recommend_never_injects_a_lure_with_zero_matching_catches():
    # Real matching history, but never actually caught anything on it - this
    # should never get promoted as a "proven" suggestion just because it was
    # tried enough times to clear the minimum-sample gate.
    history = [_history_trip("chatterbait", structure_type="Creek channel / ledge", spot_id="spot1", fish_caught=0)] * 3
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    assert not any(b.key == "chatterbait" for b in rec.first_choice + rec.second_choice)


def test_recommend_ignores_history_from_a_dissimilar_spot_and_structure():
    # Same lure, but every trip was at a different spot/structure than the
    # CURRENT situation - shouldn't be similar enough to inject or annotate.
    history = [_history_trip("carolina_rig", structure_type="Flat", spot_id="some-other-spot", fish_caught=1)] * 3
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    assert not any(b.key == "carolina_rig" for b in rec.first_choice + rec.second_choice)


# --- Punch-list #49: per-lure "why" reasoning ---------------------------------

def test_every_block_has_a_why_ending_in_a_color_reason():
    rec = recommend("spawn", 65, "Midday", 0.0, "Main-lake point", "Green stained")
    for block in rec.first_choice + rec.second_choice:
        assert block.why, f"{block.key} has no why at all"
        assert "green stained" in block.why[-1].lower()
        assert "colors shown" in block.why[-1].lower()


def test_season_pick_why_mentions_the_documented_pattern():
    rec = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear")
    block = next(b for b in rec.first_choice if b.key == "suspending_jerkbait")
    assert any("winter pattern" in reason.lower() for reason in block.why)


def test_structure_crank_nudge_why_names_the_structure():
    # post_spawn_summer's own picks (finesse_shaky_head/walking_topwater/
    # soft_swimbait first, spinnerbait/swim_jig/texas_rig_worm second) have
    # no crankbait at all - "Creek channel / ledge" is on the crank-ensure
    # nudge's structure list, so a squarebill crank (water temp >= 60)
    # should get added by the nudge alone, tagged with why it's there.
    rec = recommend("post_spawn_summer", 65, "Midday", 0.0, "Creek channel / ledge", "Clear")
    block = next(b for b in rec.second_choice if b.key == "squarebill_crankbait")
    assert any("creek channel / ledge" in reason.lower() for reason in block.why)


def test_fish_activity_very_active_promotes_a_reaction_bait_to_first_choice():
    # Winter's default picks (suspending_jerkbait/medium_diving_crankbait/
    # football_jig first, soft_swimbait/blade_bait/deep_diving_crankbait
    # second) have no REACTION_BAIT_KEYS member anywhere - a clean case to
    # confirm the nudge inserts a brand-new pick at the very front.
    rec = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear", fish_activity="Very active")
    assert rec.first_choice[0].key in ("walking_topwater", "chatterbait")
    assert any("very active" in reason.lower() for reason in rec.first_choice[0].why)


def test_fish_activity_promotion_survives_a_fish_depth_reorder():
    # Regression test: an earlier version of this nudge ran BEFORE the
    # depth-based reorder step, which silently re-sorted the promoted pick
    # right back out of first position. Passing both fish_activity and
    # fish_depth_ft together must still leave the promoted reaction bait at
    # the front.
    rec = recommend("summer_peak", 80, "Midday", 0.0, "Main-lake point", "Green stained",
                     fish_depth_ft=15, fish_activity="Very active")
    assert rec.first_choice[0].key == "lipless_crankbait"


def test_forage_activity_frenzied_also_promotes_a_reaction_bait():
    rec = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear",
                     forage_activity="Frenzied (busting bait)")
    assert any("forage activity" in reason.lower() and "frenzied" in reason.lower()
               for reason in rec.first_choice[0].why)


def test_windy_conditions_promote_a_reaction_bait_independent_of_activity():
    rec = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear", wind_mph=14)
    assert any("wind" in reason.lower() for reason in rec.first_choice[0].why)
    # Below the 10 mph threshold, no promotion should happen.
    rec_calm = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear", wind_mph=4)
    assert not any("wind is up" in reason.lower() for reason in rec_calm.first_choice[0].why)


def test_sluggish_fish_activity_promotes_a_finesse_bait_with_reason():
    # summer_peak's non-low-light picks (football_jig/deep_diving_crankbait/
    # carolina_rig first, drop_shot/suspending_jerkbait/lipless_crankbait
    # second) already have finesse baits present (football_jig, drop_shot) -
    # the nudge should tag the existing one rather than adding a duplicate.
    rec = recommend("summer_peak", 80, "Midday", 0.0, "Main-lake point", "Green stained",
                     fish_activity="Inactive / shut down")
    tagged = [b for b in rec.first_choice + rec.second_choice
              if any("inactive / shut down" in reason.lower() for reason in b.why)]
    assert len(tagged) == 1
    assert tagged[0].key in ("football_jig", "drop_shot")


def test_no_activity_or_wind_params_leaves_picks_unchanged():
    # The 7-Day Forecast page never passes fish_activity/forage_activity/
    # wind_mph - confirms the whole nudge is a true no-op without them,
    # same picks/order as before this feature existed.
    baseline = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear")
    explicit_none = recommend("winter", 45, "Midday", 0.0, "Main-lake point", "Clear",
                               fish_activity=None, forage_activity=None, wind_mph=None)
    assert [b.key for b in baseline.first_choice] == [b.key for b in explicit_none.first_choice]
    assert [b.key for b in baseline.second_choice] == [b.key for b in explicit_none.second_choice]


# --- Punch-list #82: strong personal history can promote the #1 pick ---------
# Winter's own picks: first = [suspending_jerkbait, medium_diving_crankbait,
# football_jig], second = [soft_swimbait, blade_bait, deep_diving_crankbait] -
# carolina_rig is in neither, so it's a clean case to prove a strong track
# record can promote a lure the season pattern never even considered.

def test_strong_personal_history_promotes_lure_to_the_very_top():
    history = [_history_trip("carolina_rig", structure_type="Creek channel / ledge",
                              spot_id="spot1", fish_caught=1)] * STRONG_HISTORY_MIN_TRIPS
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    assert rec.first_choice[0].key == "carolina_rig"
    assert "promoted" in rec.first_choice[0].note.lower()
    assert any("promoted" in reason.lower() for reason in rec.first_choice[0].why)


def test_personal_history_below_strong_trip_count_does_not_promote():
    # One trip short of STRONG_HISTORY_MIN_TRIPS - still gets injected as a
    # second-choice option (existing punch-list #37 behavior) but shouldn't
    # jump to the very front of first choice.
    history = [_history_trip("carolina_rig", structure_type="Creek channel / ledge",
                              spot_id="spot1", fish_caught=1)] * (STRONG_HISTORY_MIN_TRIPS - 1)
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    assert rec.first_choice[0].key != "carolina_rig"
    assert any(b.key == "carolina_rig" for b in rec.second_choice)


def test_personal_history_below_strong_catch_rate_does_not_promote():
    # Enough trips, but well under STRONG_HISTORY_CATCH_RATE - a real but
    # weak signal, injected as a second-choice option, not promoted to #1.
    history = (
        [_history_trip("carolina_rig", structure_type="Creek channel / ledge", spot_id="spot1", fish_caught=1)]
        + [_history_trip("carolina_rig", structure_type="Creek channel / ledge", spot_id="spot1", fish_caught=0)] * 2
    )
    assert len(history) >= STRONG_HISTORY_MIN_TRIPS
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    assert rec.first_choice[0].key != "carolina_rig"


def test_strong_history_already_in_top_spot_is_not_relabeled_as_promoted():
    # suspending_jerkbait is already winter's own #1 pick - a strong record
    # on it shouldn't be reworded as "promoted" since nothing moved.
    history = [_history_trip("suspending_jerkbait", structure_type="Creek channel / ledge",
                              spot_id="spot1", fish_caught=1)] * STRONG_HISTORY_MIN_TRIPS
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear",
                     trip_history=history, spot_id="spot1")
    assert rec.first_choice[0].key == "suspending_jerkbait"
    assert "promoted" not in rec.first_choice[0].note.lower()
    assert f"{STRONG_HISTORY_MIN_TRIPS} of {STRONG_HISTORY_MIN_TRIPS}" in rec.first_choice[0].note


# --- Punch-list #82: curate_recommendation() (top-3 owned + gaps) ------------

def test_curate_recommendation_splits_owned_vs_gaps_and_caps_each():
    # Own only football_jig (a first-choice pick) and deep_diving_crankbait
    # (a second-choice pick) - curation should keep both of those, in their
    # original relative rank order, as `recommended`, and the top
    # MAX_GAP_DISPLAY non-owned keys (in rank order) as `gaps`.
    inventory = [
        {"brand": "Strike King", "description": "Hack Attack Jig", "category": "football_jig", "quantity": "1"},
        {"brand": "Storm", "description": "Wiggle Wart", "category": "deep_diving_crankbait", "quantity": "1"},
    ]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    curated = curate_recommendation(rec, inventory)
    assert [b.key for b in curated.recommended] == ["football_jig", "deep_diving_crankbait"]
    assert [b.key for b in curated.gaps] == ["suspending_jerkbait", "medium_diving_crankbait", "soft_swimbait"]
    assert len(curated.recommended) <= MAX_RECOMMENDED_DISPLAY
    assert len(curated.gaps) <= MAX_GAP_DISPLAY


def test_curate_recommendation_caps_recommended_even_when_everything_is_owned():
    owned_keys = ["suspending_jerkbait", "medium_diving_crankbait", "football_jig",
                  "soft_swimbait", "blade_bait", "deep_diving_crankbait"]
    inventory = [{"brand": "B", "description": "D", "category": k, "quantity": "1"} for k in owned_keys]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    curated = curate_recommendation(rec, inventory)
    assert len(curated.recommended) == MAX_RECOMMENDED_DISPLAY
    assert [b.key for b in curated.recommended] == ["suspending_jerkbait", "medium_diving_crankbait", "football_jig"]
    assert curated.gaps == []


def test_curate_recommendation_with_no_inventory_is_all_gaps():
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear")
    curated = curate_recommendation(rec, inventory=None)
    assert curated.recommended == []
    assert [b.key for b in curated.gaps] == ["suspending_jerkbait", "medium_diving_crankbait", "football_jig"]


def test_curate_recommendation_treats_off_color_ownership_as_owned_not_a_gap():
    # Own a football_jig, but in a color that doesn't match "Clear" water's
    # suggested colors - LureBlock.owned is False (wrong color for TODAY),
    # but you still genuinely own the lure TYPE, so curation should treat it
    # as "in your tackle box" (recommended), not a gap - see
    # find_inventory_gaps()'s own color-agnostic definition of "owned".
    inventory = [
        {"brand": "Strike King", "description": "Firetiger Football Jig", "category": "football_jig", "quantity": "1"},
    ]
    rec = recommend("winter", 45, "Midday", 0.0, "Creek channel / ledge", "Clear", inventory=inventory)
    jig_block = next(b for b in rec.first_choice if b.key == "football_jig")
    assert jig_block.owned is False
    assert jig_block.owned_off_color_items
    curated = curate_recommendation(rec, inventory)
    assert "football_jig" in [b.key for b in curated.recommended]
    assert "football_jig" not in [b.key for b in curated.gaps]
