import pytest

from core.lake_water_quality import fetch_surface_water_quality, SURFACE_STATION_NAME

# Real HTML shape confirmed against the live USACE report
# (lrl-wc.usace.army.mil/reports/wq/NRR.html) via a real browser before
# wiring this in - see SESSION_NOTES.md for the full investigation writeup.
_REAL_REPORT_HTML = """
<img src="NRR%20P.jpg" alt="Plot of temperature and desolved oxygen data from table below."><table border="1" cellpadding="15">
<caption>TEMPERATURE AND DISSOLVED OXYGEN REPORT<br>Nolin River LAKE, KY</caption>
<tbody><tr><th>Station</th>
<th>Date, Time</th>
<th>Depth (ft)</th>
<th>Water Temperature (deg C)</th>
<th>Dissolved Oxygen (mg/l)</th>
</tr><tr><td>Tailwater</td><td>20260806, 1200</td><td>0</td><td>23.6</td><td>8.76</td></tr>
<tr></tr>
<tr><td>Dam Site</td><td>20260806, 1400</td><td>0</td><td>30.3</td><td>10.66</td></tr>
<tr><td>Dam Site</td><td>20260806, 1400</td><td>5</td><td>29.1</td><td>10.81</td></tr>
<tr><td>Dam Site</td><td>20260806, 1400</td><td>10</td><td>28.2</td><td>8.15</td></tr>
<tr><td>Dam Site</td><td>20260806, 1400</td><td>90</td><td>20.8</td><td>0.07</td></tr>
</tbody></table>
"""


class _FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"simulated HTTP {self.status_code}")


def test_fetch_surface_water_quality_requests_the_right_url(monkeypatch):
    import core.lake_water_quality as mod

    captured = {}

    def _fake_get(url, timeout=None):
        captured["url"] = url
        return _FakeResp(_REAL_REPORT_HTML)

    monkeypatch.setattr(mod.requests, "get", _fake_get)
    fetch_surface_water_quality()
    assert captured["url"] == mod.USACE_WQ_REPORT_URL


def test_fetch_surface_water_quality_picks_the_dam_site_surface_row_not_tailwater_or_deep(monkeypatch):
    # Tailwater (river water below the dam) and deeper Dam Site rows must
    # NOT be picked - only the Dam Site row at depth 0 is the lake surface.
    import core.lake_water_quality as mod

    monkeypatch.setattr(mod.requests, "get", lambda url, timeout=None: _FakeResp(_REAL_REPORT_HTML))
    result = fetch_surface_water_quality()
    assert result.station == SURFACE_STATION_NAME
    # 30.3 deg C -> 86.5 deg F, not the Tailwater's 23.6 C (74.5F) or any
    # deeper/colder Dam Site reading.
    assert result.water_temp_f == 86.5
    assert result.do_mg_l == 10.66


def test_fetch_surface_water_quality_parses_the_observation_datetime(monkeypatch):
    import core.lake_water_quality as mod

    monkeypatch.setattr(mod.requests, "get", lambda url, timeout=None: _FakeResp(_REAL_REPORT_HTML))
    result = fetch_surface_water_quality()
    assert (result.observed_at.year, result.observed_at.month, result.observed_at.day) == (2026, 8, 6)
    assert (result.observed_at.hour, result.observed_at.minute) == (14, 0)


def test_fetch_surface_water_quality_computes_a_plausible_supersaturation_pct(monkeypatch):
    # Hand-checked during development: 30.3C / 10.66 mg/l / 515 ft elevation
    # works out to ~147% - plausible afternoon photosynthetic
    # supersaturation for a warm, productive summer reservoir surface, not a
    # sign of a broken formula.
    import core.lake_water_quality as mod

    monkeypatch.setattr(mod.requests, "get", lambda url, timeout=None: _FakeResp(_REAL_REPORT_HTML))
    result = fetch_surface_water_quality()
    assert 140.0 <= result.do_saturation_pct <= 155.0


def test_fetch_surface_water_quality_raises_when_no_dam_site_surface_row_found(monkeypatch):
    import core.lake_water_quality as mod

    html_without_dam_site = """
    <table><tbody><tr><th>Station</th><th>Date, Time</th><th>Depth (ft)</th>
    <th>Water Temperature (deg C)</th><th>Dissolved Oxygen (mg/l)</th></tr>
    <tr><td>Tailwater</td><td>20260806, 1200</td><td>0</td><td>23.6</td><td>8.76</td></tr>
    </tbody></table>
    """
    monkeypatch.setattr(mod.requests, "get", lambda url, timeout=None: _FakeResp(html_without_dam_site))
    with pytest.raises(ValueError):
        fetch_surface_water_quality()


def test_fetch_surface_water_quality_raises_on_network_failure(monkeypatch):
    # Callers (home.py) are expected to catch and degrade gracefully - this
    # just confirms the failure actually propagates, same convention as
    # core.lake_level.fetch_lake_level() and core.weather.fetch_forecast().
    import core.lake_water_quality as mod

    def _boom(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(mod.requests, "get", _boom)
    with pytest.raises(ConnectionError):
        fetch_surface_water_quality()
