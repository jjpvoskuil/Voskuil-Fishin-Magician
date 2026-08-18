import pytest

from core.lake_level import fetch_lake_level, USGS_SITE_ID, USGS_LAKE_ELEVATION_PARAM_CD


def _fake_usgs_payload(value="515.34", date_time="2026-08-18T14:10:00.000-05:00", site_name="NOLIN LAKE NEAR KYROCK, KY"):
    # Real shape confirmed against the live USGS Water Services API before
    # wiring this in - see SESSION_NOTES.md's punch-list #7 entry.
    return {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {"siteName": site_name},
                    "values": [{"value": [{"value": value, "qualifiers": ["P"], "dateTime": date_time}]}],
                }
            ]
        }
    }


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"simulated HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_fetch_lake_level_requests_the_right_site_and_parameter(monkeypatch):
    import core.lake_level as mod

    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResp(_fake_usgs_payload())

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    fetch_lake_level()
    assert captured["params"]["sites"] == USGS_SITE_ID
    assert captured["params"]["parameterCd"] == USGS_LAKE_ELEVATION_PARAM_CD
    assert captured["params"]["format"] == "json"


def test_fetch_lake_level_parses_the_most_recent_reading(monkeypatch):
    import core.lake_level as mod

    monkeypatch.setattr(
        mod.requests, "get",
        lambda url, params=None, timeout=None: _FakeResp(_fake_usgs_payload(value="515.34")),
    )
    result = fetch_lake_level()
    assert result.elevation_ft == 515.34
    assert result.site_name == "NOLIN LAKE NEAR KYROCK, KY"
    assert result.observed_at.year == 2026 and result.observed_at.month == 8 and result.observed_at.day == 18


def test_fetch_lake_level_takes_the_last_value_when_multiple_readings_present(monkeypatch):
    import core.lake_level as mod

    payload = _fake_usgs_payload()
    # Two readings, oldest first (as USGS actually returns them) - must take
    # the LAST one (most recent), not the first.
    payload["value"]["timeSeries"][0]["values"][0]["value"] = [
        {"value": "515.20", "qualifiers": ["P"], "dateTime": "2026-08-18T13:55:00.000-05:00"},
        {"value": "515.34", "qualifiers": ["P"], "dateTime": "2026-08-18T14:10:00.000-05:00"},
    ]
    monkeypatch.setattr(mod.requests, "get", lambda url, params=None, timeout=None: _FakeResp(payload))
    result = fetch_lake_level()
    assert result.elevation_ft == 515.34


def test_fetch_lake_level_raises_on_zero_readings(monkeypatch):
    import core.lake_level as mod

    payload = _fake_usgs_payload()
    payload["value"]["timeSeries"][0]["values"][0]["value"] = []
    monkeypatch.setattr(mod.requests, "get", lambda url, params=None, timeout=None: _FakeResp(payload))
    with pytest.raises(ValueError):
        fetch_lake_level()


def test_fetch_lake_level_raises_on_network_failure(monkeypatch):
    # Callers (home.py) are expected to catch and degrade gracefully - this
    # just confirms the failure actually propagates rather than being
    # silently swallowed here, same convention as core.weather.fetch_forecast().
    import core.lake_level as mod

    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(mod.requests, "get", _boom)
    with pytest.raises(ConnectionError):
        fetch_lake_level()
