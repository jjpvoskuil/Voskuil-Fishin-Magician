from core.cabelas_lookup import (
    best_variant_index, group_by_family, map_result, search_lures,
    search_lures_broadening, search_lures_by_group, search_page_url, _first_number,
)


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
        "ec_item_group_id": "7506",
        "product_color": "White",
        "swatchcount": "45",
    }
    mapped = map_result(raw)
    assert mapped == {
        "sku": "4500087",
        "brand": "Strike King",
        "description": "Strike King Rattling Thunder Cricket Swim Jig - White - 1/2 oz.",
        "price": 15.99,
        "image_url": "https://assets.basspro.com/image/list/.../4500087.json",
        "categories": ["Fishing", "Fishing|Lures", "Jigs", "Jigs|Bladed Jigs"],
        "group_id": "7506",
        "color": "White",
        "swatch_count": 45,
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
        "image_url": "", "categories": [], "group_id": "", "color": "", "swatch_count": None,
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


def test_search_lures_dedupes_results_that_share_a_sku(monkeypatch):
    # Punch-list #38: a real crash report - Coveo genuinely can return the
    # same SKU more than once for one query (confirmed live), which crashed
    # pages/5_Lure_Inventory.py's "Scan a lure" results grid with
    # StreamlitDuplicateElementKey since it keys each "Use this" button by
    # SKU. Fixed at the source here so every caller is covered, not just
    # that one page.
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
                {"raw": {"sku": "111", "ec_brand": "Strike King", "ec_name": "First Listing", "ec_price": 9.99}},
                {"raw": {"sku": "111", "ec_brand": "Strike King", "ec_name": "Duplicate SKU Listing", "ec_price": 9.99}},
                {"raw": {"sku": "222", "ec_brand": "Strike King", "ec_name": "Different Product", "ec_price": 4.99}},
            ]}

    def _fake_get(url, headers=None, timeout=None, **kwargs):
        return _FakeTokenResp()

    def _fake_post(url, params=None, headers=None, json=None, timeout=None, **kwargs):
        return _FakeSearchResp()

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    monkeypatch.setattr(mod.requests, "post", _fake_post)
    monkeypatch.setattr(mod, "_token_cache", {"token": None, "fetched_at": 0.0})

    results = search_lures("strike king")
    skus = [r["sku"] for r in results]
    assert skus == ["111", "222"], "expected the duplicate SKU dropped, first occurrence kept, order preserved"
    assert results[0]["description"] == "First Listing"


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
    # Punch-list #36: real route is Cabela's SPA search
    # (/SearchDisplay#q=...), confirmed by actually driving their live
    # search box - the previous /search?q=... guess 404'd unconditionally,
    # even for a single bare word with no special characters at all.
    # Spaces must be %20 (quote()), not literal + (quote_plus()) - a URL
    # FRAGMENT isn't form-urlencoded the way a query string is, so a raw
    # "+" would show up as a literal plus sign in Cabela's own search box
    # instead of being read as a space (reproduced live, see
    # SESSION_NOTES.md).
    url = search_page_url("Strike King 3XD Chartreuse/Black")
    assert url.startswith("https://www.cabelas.com/SearchDisplay#q=")
    assert "Strike%20King%203XD" in url
    assert "+" not in url
    assert " " not in url


def test_search_page_url_handles_blank_query():
    # Shouldn't raise on None/empty - a degenerate but harmless search link
    # rather than an error, matching search_lures()'s own fail-soft contract.
    assert search_page_url("") == "https://www.cabelas.com/SearchDisplay#q="
    assert search_page_url(None) == "https://www.cabelas.com/SearchDisplay#q="


# --- punch-list #83: family grouping / color-picker support -----------------


def test_search_lures_includes_aq_in_request_body_when_given(monkeypatch):
    import core.cabelas_lookup as mod

    captured = {}

    class _FakeTokenResp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"token": "fake-token"}

    class _FakeSearchResp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"results": []}

    def _fake_get(url, headers=None, timeout=None, **kwargs):
        return _FakeTokenResp()

    def _fake_post(url, params=None, headers=None, json=None, timeout=None, **kwargs):
        captured["body"] = json
        return _FakeSearchResp()

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    monkeypatch.setattr(mod.requests, "post", _fake_post)
    monkeypatch.setattr(mod, "_token_cache", {"token": None, "fetched_at": 0.0})

    search_lures("", num_results=60, aq='@ec_item_group_id=="7506"')
    assert captured["body"]["aq"] == '@ec_item_group_id=="7506"'
    assert captured["body"]["q"] == ""


def test_search_lures_by_group_returns_empty_for_blank_or_malformed_group_id():
    assert search_lures_by_group("") == []
    assert search_lures_by_group(None) == []
    # A group id is only ever expected to be alnum/underscore/hyphen (Coveo's
    # own field values look like plain numeric ids in practice) - anything
    # else is refused rather than interpolated into the `aq` filter string
    # unescaped.
    assert search_lures_by_group('7506" or @foo=="bar') == []


def test_search_lures_by_group_filters_on_the_exact_group_id(monkeypatch):
    import core.cabelas_lookup as mod

    captured = {}

    class _FakeTokenResp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"token": "fake-token"}

    class _FakeSearchResp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"results": [
                {"raw": {"sku": "1", "ec_brand": "Zoom", "ec_name": "Zoom Fluke - Albino", "ec_item_group_id": "7506"}},
                {"raw": {"sku": "2", "ec_brand": "Zoom", "ec_name": "Zoom Fluke - White Pearl", "ec_item_group_id": "7506"}},
            ]}

    def _fake_get(url, headers=None, timeout=None, **kwargs):
        return _FakeTokenResp()

    def _fake_post(url, params=None, headers=None, json=None, timeout=None, **kwargs):
        captured["body"] = json
        return _FakeSearchResp()

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    monkeypatch.setattr(mod.requests, "post", _fake_post)
    monkeypatch.setattr(mod, "_token_cache", {"token": None, "fetched_at": 0.0})

    results = search_lures_by_group("7506", num_results=60)
    assert captured["body"]["aq"] == '@ec_item_group_id=="7506"'
    assert captured["body"]["numberOfResults"] == 60
    assert [r["sku"] for r in results] == ["1", "2"]


def test_group_by_family_collapses_shared_group_id():
    results = [
        {"sku": "1", "brand": "Zoom", "description": "Zoom Fluke - Albino", "price": 5.29,
         "image_url": "", "categories": [], "group_id": "7506", "color": "Albino", "swatch_count": 45},
        {"sku": "2", "brand": "Zoom", "description": "Zoom Fluke - White Pearl", "price": 5.29,
         "image_url": "", "categories": [], "group_id": "7506", "color": "White Pearl", "swatch_count": 45},
        {"sku": "3", "brand": "Strike King", "description": "Some Other Lure", "price": 8.99,
         "image_url": "", "categories": [], "group_id": "999", "color": "", "swatch_count": None},
    ]
    families = group_by_family(results)
    assert len(families) == 2
    assert families[0]["sku"] == "1"  # first-seen member represents the family
    assert families[0]["swatch_count"] == 45
    assert families[1]["sku"] == "3"
    assert families[1]["swatch_count"] == 1  # no real swatchcount -> falls back to member count


def test_group_by_family_keeps_ungrouped_results_as_singletons():
    # No group_id at all (grouping wasn't available for this product) -
    # two otherwise-identical-looking results must NOT be merged just
    # because they both lack a group_id.
    results = [
        {"sku": "1", "brand": "Shimano", "description": "A", "price": 1.0,
         "image_url": "", "categories": [], "group_id": "", "color": "", "swatch_count": None},
        {"sku": "2", "brand": "Shimano", "description": "B", "price": 1.0,
         "image_url": "", "categories": [], "group_id": "", "color": "", "swatch_count": None},
    ]
    families = group_by_family(results)
    assert len(families) == 2
    assert {f["sku"] for f in families} == {"1", "2"}
    assert all(f["swatch_count"] == 1 for f in families)


def test_search_lures_broadening_returns_first_try_untouched_when_it_finds_something(monkeypatch):
    import core.cabelas_lookup as mod

    calls = []

    def _fake_search_lures(query, num_results=8, aq=None):
        calls.append(query)
        return [{"sku": "1", "description": query}]

    monkeypatch.setattr(mod, "search_lures", _fake_search_lures)
    results, used = search_lures_broadening("Zoom Super Fluke White Ice", num_results=8)
    assert used == "Zoom Super Fluke White Ice"
    assert calls == ["Zoom Super Fluke White Ice"]  # only one attempt needed
    assert results[0]["sku"] == "1"


def test_search_lures_broadening_drops_trailing_words_until_results_found(monkeypatch):
    import core.cabelas_lookup as mod

    # Simulates the real, reproduced Coveo behavior: the full 6-word query
    # finds nothing, but the first 4 words do.
    WORKS_AT = 4

    def _fake_search_lures(query, num_results=8, aq=None):
        n = len(query.split())
        return [{"sku": "1", "description": query}] if n <= WORKS_AT else []

    monkeypatch.setattr(mod, "search_lures", _fake_search_lures)
    results, used = search_lures_broadening(
        "Strike King 3XD Series Chartreuse Shad", num_results=8, min_words=2,
    )
    assert used == "Strike King 3XD Series"
    assert len(used.split()) == WORKS_AT
    assert results


def test_search_lures_broadening_gives_up_at_min_words(monkeypatch):
    import core.cabelas_lookup as mod

    monkeypatch.setattr(mod, "search_lures", lambda query, num_results=8, aq=None: [])
    results, used = search_lures_broadening("A B C D E", num_results=8, min_words=2)
    assert results == []
    assert used == "A B C D E"  # falls back to the original full query in the message


def test_search_lures_broadening_handles_blank_query():
    assert search_lures_broadening("") == ([], "")
    assert search_lures_broadening(None) == ([], "")


def test_best_variant_index_prefers_word_overlap_match():
    variants = [
        {"color": "Green Pumpkin", "description": "Zoom Fluke - Green Pumpkin - 5-1/4\""},
        {"color": "White Ice", "description": "Zoom Fluke - White Ice - 5-1/4\""},
        {"color": "Albino", "description": "Zoom Fluke - Albino - 5-1/4\""},
    ]
    assert best_variant_index(variants, "Zoom Salty Super Fluke White Ice") == 1
    assert best_variant_index(variants, "looks like the albino one") == 2


def test_best_variant_index_falls_back_to_zero_when_no_hint_or_no_overlap():
    variants = [
        {"color": "Green Pumpkin", "description": "Zoom Fluke - Green Pumpkin"},
        {"color": "White Ice", "description": "Zoom Fluke - White Ice"},
    ]
    assert best_variant_index(variants, "") == 0
    assert best_variant_index([], "White Ice") == 0
    assert best_variant_index(variants, "completely unrelated text") == 0
