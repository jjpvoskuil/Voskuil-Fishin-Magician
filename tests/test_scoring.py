from datetime import date, timedelta, datetime
from core.weather import WeatherBundle
from core.scoring import score_week, score_day


def _fake_bundle(days=9):
    today = date.today()
    times, temps, pres, cloud, wind, wdir, pprob, precip = [], [], [], [], [], [], [], []
    t0 = datetime(today.year, today.month, today.day) - timedelta(days=1)
    for h in range(24 * days):
        dt = t0 + timedelta(hours=h)
        times.append(dt.isoformat())
        temps.append(78 + 6 * ((h % 24) - 12) / 12)
        pres.append(1015 - 0.05 * h)
        cloud.append(40)
        wind.append(7)
        wdir.append(180)
        pprob.append(10)
        precip.append(0)
    hourly = {"time": times, "temperature_2m": temps, "surface_pressure": pres, "cloudcover": cloud,
              "windspeed_10m": wind, "winddirection_10m": wdir, "precipitation_probability": pprob,
              "precipitation": precip}
    daily = {
        "time": [(today + timedelta(days=i)).isoformat() for i in range(7)],
        "sunrise": [(datetime(today.year, today.month, today.day) + timedelta(days=i, hours=6, minutes=20)).isoformat() for i in range(7)],
        "sunset": [(datetime(today.year, today.month, today.day) + timedelta(days=i, hours=20, minutes=15)).isoformat() for i in range(7)],
        "temperature_2m_max": [90] * 7,
        "temperature_2m_min": [72] * 7,
    }
    return WeatherBundle(hourly=hourly, daily=daily)


def test_score_week_returns_seven_days_in_range():
    bundle = _fake_bundle()
    week = score_week(bundle, date.today(), 7)
    assert len(week) == 7
    for day in week:
        assert 1 <= day.overall_score <= 10
        assert len(day.segments) == 6
        for seg in day.segments:
            assert 1 <= seg.score <= 10


def test_score_day_raises_outside_window():
    bundle = _fake_bundle()
    try:
        score_day(bundle, date.today() + timedelta(days=30))
        assert False, "expected ValueError"
    except ValueError:
        pass


def _bundle_with_partial_daily_coverage(full_days=9, daily_days=5):
    # Same hourly shape as _fake_bundle, but daily/sunrise/sunset only cover
    # the first `daily_days` days - simulates a cached weather bundle that's
    # briefly a day (or more) short at the tail of the requested window (e.g.
    # right at the lake's local-day rollover, or an Open-Meteo hiccup).
    today = date.today()
    bundle = _fake_bundle(days=full_days)
    bundle.daily = {
        "time": [(today + timedelta(days=i)).isoformat() for i in range(daily_days)],
        "sunrise": [(datetime(today.year, today.month, today.day) + timedelta(days=i, hours=6, minutes=20)).isoformat() for i in range(daily_days)],
        "sunset": [(datetime(today.year, today.month, today.day) + timedelta(days=i, hours=20, minutes=15)).isoformat() for i in range(daily_days)],
        "temperature_2m_max": [90] * daily_days,
        "temperature_2m_min": [72] * daily_days,
    }
    return bundle


def test_score_week_skips_days_missing_from_the_bundle_instead_of_raising():
    bundle = _bundle_with_partial_daily_coverage(daily_days=5)
    week = score_week(bundle, date.today(), 7)
    assert len(week) == 5
    for day in week:
        assert 1 <= day.overall_score <= 10


def test_score_week_returns_empty_list_when_nothing_is_available():
    bundle = _bundle_with_partial_daily_coverage(daily_days=0)
    week = score_week(bundle, date.today(), 7)
    assert week == []
