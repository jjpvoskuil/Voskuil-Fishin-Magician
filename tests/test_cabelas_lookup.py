from core.cabelas_lookup import map_result, search_lures, _first_number


def test_map_result_pulls_expected_fields_from_coveo_raw():
    raw = {
        "sku": "4500087",
        "ec_brand": "Strike King",
        "ec_name": "Strike King Rattling Thunder Cricket Swim Jig - White - 1/2 oz.",
        "ec_price": 15.99,
        "offerprice": 15.99,
        "listprice": 15.99,
        "fullimage": "https://assets.basspro.com/image/list/.../4500087.json",
        "thumbnail": "https://assets.basspro.com/image/list/.../4500087.json?$Prod_PLPThumb$",
        "ec_category": ["Fishing", "Fishing|Lures", "Jigs", "Jigs|Bladed Jigs"],
    }
    mapped = map_result(raw)
    assert mapped == {
        "sku": "4500087",
        "brand": "Strike King",
        "description": "Strike King Rattling Thunder Cricket Swim Jig - White - 1/2 oz.",
        "price": 15.99,
        "image_url": "https://assets.basspro.com/image/list/.../4500087.json",
        "categories": ["Fishing", "Fishing|Lures", "Jigs", "Jigs|Bladed Jigs"],
    }


def test_map_result_falls_back_to_thumbnail_and_shortdesc():
    raw = {
        "sku": "123",
        "brand": "Berkley",
        "ec_shortdesc": "Some Lure",
        "offerprice": 9.99,
        "thumbnail": "https://example.com/thumb.jpg",
    }
    mapped = map_result(raw)
    assert mapped["description"] == "Some Lure"
    assert mapped["price"] == 9.99
    assert mapped["image_url"] == "https://example.com/thumb.jpg"


def test_map_result_handles_missing_fields():
    mapped = map_result({})
    assert mapped == {
        "sku": "", "brand": "", "description": "", "price": None,
        "image_url": "", "categories": [],
    }


def test_first_number_skips_blanks_and_takes_first_valid():
    assert _first_number(None, "", "9.99", "1.00") == 9.99
    assert _first_number(None, None) is None
    assert _first_number("not-a-number", "5") == 5.0


def test_search_lures_returns_empty_list_for_blank_query():
    assert search_lures("") == []
    assert search_lures("   ") == []
    assert search_lures(None) == []


def test_search_lures_fails_soft_when_token_endpoint_unreachable(monkeypatch):
    # Simulate the token endpoint being unreachable (network error, site
    # change, bot-blocked, etc.) - search_lures() must return [] rather than
    # raising, so the Lure Inventory page's "Scan a lure" flow can fall back
    # to the manual "Add a lure" form cleanly.
    import core.cabelas_lookup as mod

    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(mod.requests, "get", _boom)
    monkeypatch.setattr(mod, "_token_cache", {"token": None, "fetched_at": 0.0})
    assert search_lures("strike king crankbait") == []


def test_search_lures_maps_results_and_drops_unusable_ones(monkeypatch):
    import core.cabelas_lookup as mod

    class _FakeTokenResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"token": "fake-token"}

    class _FakeSearchResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"results": [
                {"raw": {"sku": "111", "ec_brand": "Strike King", "ec_name": "Real Product", "ec_price": 9.99}},
                {"raw": {"sku": "", "ec_brand": "No SKU", "ec_name": "Should be dropped"}},
                {"raw": {"sku": "222", "ec_brand": "No Name"}},  # no description -> dropped
            ]}

    def _fake_get(url, headers=None, timeout=None):
        assert url == mod.TOKEN_URL
        return _FakeTokenResp()

    def _fake_post(url, params=None, headers=None, json=None, timeout=None):
        assert url == mod.SEARCH_URL
        assert params == {"organizationId": mod.COVEO_ORG_ID}
        assert "Authorization" in headers and headers["Authorization"] == "Bearer fake-token"
        assert json["q"] == "strike king"
        return _FakeSearchResp()

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    monkeypatch.setattr(mod.requests, "post", _fake_post)
    monkeypatch.setattr(mod, "_token_cache", {"token": None, "fetched_at": 0.0})

    results = search_lures("strike king")
    assert len(results) == 1
    assert results[0]["sku"] == "111"
    assert results[0]["description"] == "Real Product"
