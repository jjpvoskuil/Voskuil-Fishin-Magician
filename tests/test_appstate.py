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


def test_github_connection_status_reports_not_configured_when_token_empty(monkeypatch):
    monkeypatch.setattr(appstate, "github_token", lambda: "")
    configured, preview = appstate.github_connection_status()
    assert configured is False
    assert preview == ""


def test_github_connection_status_masks_a_real_looking_token(monkeypatch):
    # Punch-list #62: enough of the token shown to visually match against
    # what's pasted into Streamlit secrets, never enough to reconstruct it.
    monkeypatch.setattr(appstate, "github_token", lambda: "github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    configured, preview = appstate.github_connection_status()
    assert configured is True
    assert preview == "github_pat...WXYZ"
    assert "ABCDEF" not in preview


def test_github_connection_status_handles_a_short_token_without_crashing(monkeypatch):
    monkeypatch.setattr(appstate, "github_token", lambda: "short")
    configured, preview = appstate.github_connection_status()
    assert configured is True
    assert preview == "(configured)"


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def json(self):
        return self._json_body


def test_test_github_push_access_with_no_token_skips_the_network_call(monkeypatch):
    calls = []
    monkeypatch.setattr(appstate.requests, "get", lambda *a, **k: calls.append(1))
    ok, msg = appstate.test_github_push_access("", "someone/somerepo")
    assert ok is False
    assert "no token" in msg.lower()
    assert calls == []


def test_test_github_push_access_true_when_push_permission_present(monkeypatch):
    monkeypatch.setattr(
        appstate.requests, "get",
        lambda *a, **k: _FakeResponse(200, {"permissions": {"push": True}}),
    )
    ok, msg = appstate.test_github_push_access("faketoken", "someone/somerepo")
    assert ok is True
    assert "push access" in msg.lower()


def test_test_github_push_access_false_when_valid_but_read_only(monkeypatch):
    monkeypatch.setattr(
        appstate.requests, "get",
        lambda *a, **k: _FakeResponse(200, {"permissions": {"push": False}}),
    )
    ok, msg = appstate.test_github_push_access("faketoken", "someone/somerepo")
    assert ok is False
    assert "does not have" in msg.lower() or "does not" in msg.lower()


def test_test_github_push_access_false_on_401_bad_credentials(monkeypatch):
    monkeypatch.setattr(appstate.requests, "get", lambda *a, **k: _FakeResponse(401))
    ok, msg = appstate.test_github_push_access("badtoken", "someone/somerepo")
    assert ok is False
    assert "401" in msg or "bad credentials" in msg.lower()


def test_test_github_push_access_false_on_network_error(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(appstate.requests, "get", _raise)
    ok, msg = appstate.test_github_push_access("sometoken", "someone/somerepo")
    assert ok is False
    assert "couldn't reach github" in msg.lower()


# --- Punch-list #101: stale-bundle fallback when a fresh weather fetch fails --

def test_get_weather_bundle_falls_back_to_last_good_bundle_on_a_transient_failure(monkeypatch):
    from datetime import datetime
    from core.weather import WeatherBundle

    good = WeatherBundle(hourly={"time": ["ok"]}, daily={}, fetched_at=datetime.utcnow())
    calls = {"n": 0}

    def _fake_fetch(days=7):
        calls["n"] += 1
        if calls["n"] == 1:
            return good
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(appstate, "fetch_forecast", _fake_fetch)
    appstate._weather_bundle_fallback_store.clear()
    appstate.get_weather_bundle.clear()

    first = appstate.get_weather_bundle(7)
    assert first is good
    appstate.get_weather_bundle.clear()  # force past the st.cache_data TTL for this test
    second = appstate.get_weather_bundle(7)
    assert second is good, "a transient failure should silently serve the last successful bundle"


def test_get_weather_bundle_still_raises_with_nothing_good_on_hand(monkeypatch):
    def _always_fails(days=7):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(appstate, "fetch_forecast", _always_fails)
    appstate._weather_bundle_fallback_store.clear()
    appstate.get_weather_bundle.clear()

    try:
        appstate.get_weather_bundle(7)
        assert False, "expected the failure to propagate with no prior good bundle to fall back on"
    except RuntimeError:
        pass


def test_get_weather_bundle_does_not_serve_a_too_stale_fallback(monkeypatch):
    from datetime import datetime, timedelta
    from core.weather import WeatherBundle

    stale = WeatherBundle(
        hourly={"time": ["old"]}, daily={},
        fetched_at=datetime.utcnow() - appstate.WEATHER_STALE_FALLBACK_MAX_AGE - timedelta(minutes=1),
    )
    calls = {"n": 0}

    def _fake_fetch(days=7):
        calls["n"] += 1
        if calls["n"] == 1:
            return stale
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(appstate, "fetch_forecast", _fake_fetch)
    appstate._weather_bundle_fallback_store.clear()
    appstate.get_weather_bundle.clear()

    appstate.get_weather_bundle(7)
    appstate.get_weather_bundle.clear()
    try:
        appstate.get_weather_bundle(7)
        assert False, "a fallback bundle older than the staleness cap should not be served"
    except RuntimeError:
        pass
