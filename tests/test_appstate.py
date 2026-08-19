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
