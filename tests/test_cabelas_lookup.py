from core.cabelas_lookup import map_result, search_lures, search_page_url, _first_number


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
    # raising, so the Tackle Box page's "Scan a lure" flow can fall back
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

    def _fake_get(url, headers=None, timeout=None, **kwargs):
        # **kwargs absorbs curl_cffi-specific args (e.g. impersonate=...,
        # punch-list #22) this fake doesn't need to assert on.
        assert url == mod.TOKEN_URL
        return _FakeTokenResp()

    def _fake_post(url, params=None, headers=None, json=None, timeout=None, **kwargs):
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


def test_search_lures_impersonates_a_real_browser_tls_fingerprint(monkeypatch):
    # Punch-list #22: the actual point of switching to curl_cffi - both the
    # token GET and the search POST must pass impersonate=IMPERSONATE_BROWSER
    # so curl_cffi spoofs a real Chrome TLS/JA3 handshake, not just headers
    # (a plain `requests` call with a browser User-Agent was still coming
    # back empty from this app's own deployed server).
    import core.cabelas_lookup as mod

    captured = {}

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
            return {"results": []}

    def _fake_get(url, headers=None, timeout=None, **kwargs):
        captured["get_impersonate"] = kwargs.get("impersonate")
        return _FakeTokenResp()

    def _fake_post(url, params=None, headers=None, json=None, timeout=None, **kwargs):
        captured["post_impersonate"] = kwargs.get("impersonate")
        return _FakeSearchResp()

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    monkeypatch.setattr(mod.requests, "post", _fake_post)
    monkeypatch.setattr(mod, "_token_cache", {"token": None, "fetched_at": 0.0})

    search_lures("strike king")
    assert captured["get_impersonate"] == mod.IMPERSONATE_BROWSER
    assert captured["post_impersonate"] == mod.IMPERSONATE_BROWSER
    assert mod.IMPERSONATE_BROWSER  # non-empty - a real curl_cffi browser token


def test_search_page_url_url_encodes_the_query():
    url = search_page_url("Strike King 3XD Chartreuse/Black")
    assert url.startswith("https://www.cabelas.com/search?q=")
    assert "Strike+King+3XD" in url or "Strike%20King%203XD" in url
    assert " " not in url


def test_search_page_url_handles_blank_query():
    # Shouldn't raise on None/empty - a degenerate but harmless search link
    # rather than an error, matching search_lures()'s own fail-soft contract.
    assert search_page_url("") == "https://www.cabelas.com/search?q="
    assert search_page_url(None) == "https://www.cabelas.com/search?q="
