import core.appstate as appstate


def _patch_search_lures(monkeypatch, fn):
    monkeypatch.setattr(appstate, "search_lures", fn)


def _patch_get_cached_picks(monkeypatch, fn):
    monkeypatch.setattr(appstate, "get_cached_picks", fn)


def test_get_cabelas_suggestions_returns_live_results_and_is_live_true(monkeypatch):
    live_item = {"sku": "1", "brand": "B", "description": "D", "price": 1.0, "image_url": "", "categories": []}
    _patch_search_lures(monkeypatch, lambda query, num_results=8: [live_item])

    suggestions, is_live = appstate.get_cabelas_suggestions("query one - live hit", num_results=2)
    assert suggestions == [live_item]
    assert is_live is True


def test_get_cabelas_suggestions_falls_back_to_cache_when_live_lookup_is_empty(monkeypatch):
    # Punch-list #22: an empty live result (search_lures() fails soft and
    # returns [] on any problem, including this app's own server-side calls
    # getting blocked) should fall back to the curated cache rather than
    # surfacing as "nothing found" outright.
    cached_item = {"sku": "2", "brand": "B2", "description": "D2", "price": 2.0, "image_url": "", "categories": []}
    _patch_search_lures(monkeypatch, lambda query, num_results=8: [])
    _patch_get_cached_picks(monkeypatch, lambda query: [cached_item])

    suggestions, is_live = appstate.get_cabelas_suggestions("query two - live miss", num_results=2)
    assert suggestions == [cached_item]
    assert is_live is False


def test_get_cabelas_suggestions_returns_empty_and_is_live_false_when_both_miss(monkeypatch):
    _patch_search_lures(monkeypatch, lambda query, num_results=8: [])
    _patch_get_cached_picks(monkeypatch, lambda query: [])

    suggestions, is_live = appstate.get_cabelas_suggestions("query three - both miss", num_results=2)
    assert suggestions == []
    assert is_live is False


def test_get_cabelas_suggestions_caps_cached_results_to_num_results(monkeypatch):
    cached_items = [
        {"sku": str(i), "brand": "B", "description": f"D{i}", "price": 1.0, "image_url": "", "categories": []}
        for i in range(5)
    ]
    _patch_search_lures(monkeypatch, lambda query, num_results=8: [])
    _patch_get_cached_picks(monkeypatch, lambda query: cached_items)

    suggestions, is_live = appstate.get_cabelas_suggestions("query four - cap test", num_results=2)
    assert len(suggestions) == 2
    assert is_live is False


def test_get_anglers_passes_through_read_anglers(monkeypatch):
    monkeypatch.setattr(appstate, "read_anglers", lambda: ["Test Angler One", "Test Angler Two"])
    assert appstate.get_anglers() == ["Test Angler One", "Test Angler Two"]


def test_get_trip_history_is_cached_until_cleared(monkeypatch):
    # Punch-list #61: get_trip_history()/get_calibrated_weights() (below) are
    # the two cached getters in this app that used to never get a .clear()
    # call anywhere after a trip write - unlike get_lake_spots, get_inventory,
    # and get_dev_tasks, which every write site for THEIR data clears right
    # after saving. This proves both halves of that fix: the getter really is
    # cached (repeat calls don't re-read the CSV), and calling .clear() - what
    # every trip-log write site now does via pages/6_Spot_Session.py's
    # _push_or_toast(), or directly in pages/4_Trip_History.py and
    # pages/8_Leaderboard.py - really does force a fresh read on the next call.
    calls = {"n": 0}

    def _fake_read_all_trips():
        calls["n"] += 1
        return [{"trip_id": f"row-{calls['n']}"}]

    monkeypatch.setattr(appstate, "read_all_trips", _fake_read_all_trips)
    appstate.get_trip_history.clear()

    first = appstate.get_trip_history()
    assert calls["n"] == 1
    assert first == [{"trip_id": "row-1"}]

    # A second call with no clear() in between must hit the cache, not
    # re-read - if a new trip was logged in the meantime, this call would
    # otherwise (wrongly) still see the old rows for up to 5 more minutes.
    second = appstate.get_trip_history()
    assert calls["n"] == 1
    assert second == first

    appstate.get_trip_history.clear()
    third = appstate.get_trip_history()
    assert calls["n"] == 2
    assert third == [{"trip_id": "row-2"}]


def test_get_calibrated_weights_is_cached_until_cleared(monkeypatch):
    calls = {"n": 0}

    def _fake_read_all_trips():
        calls["n"] += 1
        return [{"trip_id": f"row-{calls['n']}", "fish_caught": "0", "conditions_json": "{}"}] * calls["n"]

    monkeypatch.setattr(appstate, "read_all_trips", _fake_read_all_trips)
    appstate.get_calibrated_weights.clear()

    _, first_count = appstate.get_calibrated_weights()
    assert calls["n"] == 1
    assert first_count == 1

    _, second_count = appstate.get_calibrated_weights()
    assert calls["n"] == 1
    assert second_count == first_count

    appstate.get_calibrated_weights.clear()
    _, third_count = appstate.get_calibrated_weights()
    assert calls["n"] == 2
    assert third_count == 2
