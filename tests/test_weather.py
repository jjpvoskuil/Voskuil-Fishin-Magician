from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.weather import lake_today, LAKE_TZ, LAKE_ZONEINFO


def test_lake_today_returns_a_date():
    assert isinstance(lake_today(), date)


def test_lake_zoneinfo_matches_lake_tz_constant():
    assert LAKE_TZ == "America/Chicago"
    assert LAKE_ZONEINFO.key == "America/Chicago"


def test_lake_today_matches_independently_computed_chicago_date():
    # Not a tautology on the implementation - re-derives the value via a fresh
    # ZoneInfo lookup rather than importing LAKE_ZONEINFO, so it'd catch
    # lake_today() drifting to the wrong zone (e.g. back to server-local time).
    assert lake_today() == datetime.now(ZoneInfo("America/Chicago")).date()
