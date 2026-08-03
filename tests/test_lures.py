from core.lures import recommend, WATER_CLARITY_OPTIONS, STRUCTURE_TYPES


def test_recommend_returns_valid_structure():
    rec = recommend("summer_peak", 85, "Midday", -1.0, "Creek channel / ledge", "Stained")
    assert len(rec.primary_lures) >= 2
    assert len(rec.colors) >= 2
    assert rec.technique
    assert rec.target_depth


def test_all_seasons_and_segments_produce_recommendations():
    seasons = ["winter", "pre_spawn", "spawn", "post_spawn_summer", "summer_peak", "fall_feed_up", "fall_turnover"]
    segments = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]
    for season in seasons:
        for seg in segments:
            for structure in STRUCTURE_TYPES:
                for clarity in WATER_CLARITY_OPTIONS:
                    rec = recommend(season, 70, seg, 0.0, structure, clarity)
                    assert rec.primary_lures and rec.colors
