"""Shared pytest fixtures for this test suite.

Punch-list #101: core.weather.fetch_forecast() now retries a transient
429/5xx a couple times with a real time.sleep() backoff (1.5s, then 3s) -
the right thing for the deployed app, but this sandbox's own outbound
network to api.open-meteo.com is blocked (see SESSION_NOTES.md's standing
Open-Meteo network note), so EVERY test that renders a page calling
core.appstate.get_weather_bundle() for real (Trip History, Spot Session,
7-Day Forecast, Reports, home.py - none of them mock it, since a blocked-
network failure is itself the scenario several of those pages are already
tested against) hits that failure and, without this fixture, would burn
the real ~4.5s backoff on every single one of them - dozens of tests times
several seconds each, which is exactly what turned a normal ~13s full-suite
run into a run that no longer finished inside a 170s budget the first time
this retry logic was added. Autouse + session-scoped so it's applied once
for the whole run without every test file needing its own monkeypatch."""
import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep_in_weather_retries(monkeypatch):
    import core.weather as weather_mod
    monkeypatch.setattr(weather_mod.time, "sleep", lambda seconds: None)
