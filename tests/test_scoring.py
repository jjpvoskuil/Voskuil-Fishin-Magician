from datetime import date, timedelta, datetime
from core.weather import WeatherBundle, WATER_TEMP_TREND_PAST_DAYS
from core.scoring import (
    score_week, score_day, manual_segment_score, realtime_context_from_bundle,
    segment_time_ranges, lake_now_naive, SEGMENTS, _segment_windows,
)
from core import onwater
from core import astro


def _fake_bundle_with_air_temp(air_temp_f: float, d: date, days=9):
    """Same shape as _fake_bundle(), but every hourly reading is a fixed air
    temp and the window is anchored around `d` - used to force
    estimate_water_temp_f() toward a specific, deterministic metabolic band
    regardless of what day the test suite happens to run on. `daily` starts
    WATER_TEMP_TREND_PAST_DAYS before `d`, not at `d` itself - matching a
    real Open-Meteo response now that fetch_forecast() requests
    `past_days`, and needed so estimate_water_temp_f()'s trailing daily-high
    average actually has real days to average for `d` (a bundle whose daily
    array only started at `d` itself, like this fixture used to build,
    would leave that average permanently empty and silently fall through to
    the seasonal-only branch - not what these tests are meant to exercise)."""
    times, temps, pres, cloud, wind, wdir, pprob, precip = [], [], [], [], [], [], [], []
    t0 = datetime(d.year, d.month, d.day) - timedelta(days=6)
    for h in range(24 * days):
        dt = t0 + timedelta(hours=h)
        times.append(dt.isoformat())
        temps.append(air_temp_f)
        pres.append(1015 - 0.05 * h)
        cloud.append(40)
        wind.append(7)
        wdir.append(180)
        pprob.append(10)
        precip.append(0)
    hourly = {"time": times, "temperature_2m": temps, "surface_pressure": pres, "cloudcover": cloud,
              "windspeed_10m": wind, "winddirection_10m": wdir, "precipitation_probability": pprob,
              "precipitation": precip}
    daily_start = d - timedelta(days=WATER_TEMP_TREND_PAST_DAYS)
    daily_days = WATER_TEMP_TREND_PAST_DAYS + 7
    daily = {
        "time": [(daily_start + timedelta(days=i)).isoformat() for i in range(daily_days)],
        "sunrise": [
            (datetime(d.year, d.month, d.day) + timedelta(days=i - WATER_TEMP_TREND_PAST_DAYS, hours=6, minutes=20)).isoformat()
            for i in range(daily_days)
        ],
        "sunset": [
            (datetime(d.year, d.month, d.day) + timedelta(days=i - WATER_TEMP_TREND_PAST_DAYS, hours=20, minutes=15)).isoformat()
            for i in range(daily_days)
        ],
        "temperature_2m_max": [air_temp_f + 10] * daily_days,
        "temperature_2m_min": [air_temp_f - 10] * daily_days,
    }
    return WeatherBundle(hourly=hourly, daily=daily)


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
    # daily starts WATER_TEMP_TREND_PAST_DAYS before today, not at today itself -
    # see _fake_bundle_with_air_temp()'s docstring for why this matters now.
    daily_start = today - timedelta(days=WATER_TEMP_TREND_PAST_DAYS)
    daily_days = WATER_TEMP_TREND_PAST_DAYS + 7
    daily = {
        "time": [(daily_start + timedelta(days=i)).isoformat() for i in range(daily_days)],
        "sunrise": [
            (datetime(today.year, today.month, today.day) + timedelta(days=i - WATER_TEMP_TREND_PAST_DAYS, hours=6, minutes=20)).isoformat()
            for i in range(daily_days)
        ],
        "sunset": [
            (datetime(today.year, today.month, today.day) + timedelta(days=i - WATER_TEMP_TREND_PAST_DAYS, hours=20, minutes=15)).isoformat()
            for i in range(daily_days)
        ],
        "temperature_2m_max": [90] * daily_days,
        "temperature_2m_min": [72] * daily_days,
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


def test_lake_now_naive_returns_naive_datetime():
    now = lake_now_naive()
    assert isinstance(now, datetime)
    assert now.tzinfo is None


def test_manual_segment_score_returns_score_in_range_with_notes_and_moon():
    result = manual_segment_score(
        "Dawn", "spawn", avg_cloud_pct=75, avg_wind_mph=8, total_precip_in=0.0, max_precip_prob_pct=0.0,
    )
    assert 1 <= result.score <= 10
    assert result.notes  # overcast + wind sweet spot should both fire
    assert result.moon is not None
    assert result.warnings == []


def test_manual_segment_score_flags_storm_warning_for_heavy_precip():
    result = manual_segment_score(
        "Midday", "summer_peak", avg_cloud_pct=50, avg_wind_mph=5,
        total_precip_in=1.5, max_precip_prob_pct=95,
    )
    assert result.warnings
    assert "storm" in result.warnings[0].lower() or "rain" in result.warnings[0].lower()


def test_manual_segment_score_matches_score_day_for_equivalent_inputs():
    # If the same underlying pressure/moon/cloud/wind/season/precip/water-temp
    # values are fed to both the bundle-driven score_day() and the hand-entered
    # manual_segment_score(), they should agree - they share the same
    # _segment_score() formula, just different sources for the inputs. Passing
    # day.water_temp_f explicitly here matters now that estimate_water_temp_f()
    # produces realistic (not artificially neutral-banded) estimates - without
    # it, this would be comparing score_day()'s water-temp-aware score against
    # manual_segment_score()'s water-temp-blind default, which aren't actually
    # "equivalent inputs" at all.
    bundle = _fake_bundle()
    day = score_day(bundle, date.today())
    dawn = next(s for s in day.segments if s.name == "Dawn")

    result = manual_segment_score(
        "Dawn", day.season, avg_cloud_pct=40, avg_wind_mph=7,
        total_precip_in=0.0, max_precip_prob_pct=10,
        pressure_trend_24h=day.pressure_trend_24h, solunar_overlap=dawn.solunar_overlap,
        moon=day.moon, water_temp_f=day.water_temp_f,
    )
    assert result.score == dawn.score


def test_realtime_context_from_bundle_returns_neutral_defaults_when_bundle_is_none():
    ctx = realtime_context_from_bundle(None, "Dawn", date.today())
    assert ctx == {"pressure_trend_24h": 0.0, "solunar_overlap": None}


def test_realtime_context_from_bundle_resolves_pressure_trend_from_a_real_bundle():
    bundle = _fake_bundle()
    ctx = realtime_context_from_bundle(bundle, "Dawn", date.today())
    assert isinstance(ctx["pressure_trend_24h"], float)
    # This synthetic bundle's pressure falls steadily, so the trend should be negative.
    assert ctx["pressure_trend_24h"] < 0


def test_realtime_context_from_bundle_degrades_gracefully_outside_coverage():
    bundle = _bundle_with_partial_daily_coverage(daily_days=0)
    ctx = realtime_context_from_bundle(bundle, "Dawn", date.today())
    assert ctx["solunar_overlap"] is None


def test_realtime_context_from_bundle_pressure_trend_uses_at_time_not_wall_clock_now():
    # _fake_bundle()'s pressure falls at a perfectly constant rate per hour, so its
    # 24h trend is identical no matter which hour you anchor it to - not a useful
    # bundle for telling "used at_time" apart from "used wall-clock now". Build a
    # bundle with a kink instead: flat for the first half, then falling - so the
    # 24h-trend as of a morning anchor (still flat) differs from as of an evening
    # anchor (now includes the falling stretch) - proving at_time (the angler's
    # entered session-start time), not lake_now_naive(), drives the lookup.
    today = date.today()
    t0 = datetime(today.year, today.month, today.day) - timedelta(days=2)
    times, pres = [], []
    for h in range(24 * 4):
        dt = t0 + timedelta(hours=h)
        times.append(dt.isoformat())
        pres.append(1015.0 if h < 24 * 2 else 1015.0 - 0.3 * (h - 24 * 2))
    hourly = {"time": times, "surface_pressure": pres}
    bundle = WeatherBundle(hourly=hourly, daily={})

    morning = datetime(today.year, today.month, today.day, 1, 0)
    evening = datetime(today.year, today.month, today.day, 20, 0)
    ctx_morning = realtime_context_from_bundle(bundle, "Dawn", today, at_time=morning)
    ctx_evening = realtime_context_from_bundle(bundle, "Dawn", today, at_time=evening)
    assert ctx_morning["pressure_trend_24h"] != ctx_evening["pressure_trend_24h"]


def test_manual_segment_score_at_time_drives_moon_phase_not_wall_clock_now():
    # Moon phase is a function of the timestamp passed in - two at_time values far
    # enough apart (say, ~10 days) land in different phases, proving manual_segment_
    # score() actually used at_time rather than silently falling back to "now".
    today = date.today()
    t1 = datetime(today.year, today.month, today.day, 12, 0)
    t2 = t1 + timedelta(days=10)
    r1 = manual_segment_score("Dawn", "summer_peak", 40, 7, at_time=t1)
    r2 = manual_segment_score("Dawn", "summer_peak", 40, 7, at_time=t2)
    assert r1.moon.name != r2.moon.name or r1.moon.is_new_or_full_window != r2.moon.is_new_or_full_window


def test_segment_time_ranges_returns_none_without_a_bundle():
    assert segment_time_ranges(None, date.today()) is None


def test_segment_time_ranges_covers_every_segment_with_a_real_bundle():
    bundle = _fake_bundle()
    ranges = segment_time_ranges(bundle, date.today())
    assert ranges is not None
    assert set(ranges) == set(SEGMENTS)
    for name, (start, end) in ranges.items():
        assert start < end


def test_segment_time_ranges_degrades_gracefully_outside_coverage():
    bundle = _bundle_with_partial_daily_coverage(daily_days=0)
    assert segment_time_ranges(bundle, date.today()) is None


def test_segment_windows_dawn_dusk_are_a_real_hour_either_side_of_sun_times():
    d = date(2026, 8, 18)
    sunrise = datetime(2026, 8, 18, 6, 20)
    sunset = datetime(2026, 8, 18, 20, 15)
    windows = {name: (s, e) for name, s, e in _segment_windows(sunrise, sunset, d)}
    assert windows["Dawn"] == (sunrise - timedelta(hours=1), sunrise + timedelta(hours=1))
    assert windows["Dusk"] == (sunset - timedelta(hours=1), sunset + timedelta(hours=1))
    assert windows["Night"] == (sunset + timedelta(hours=1), (sunrise - timedelta(hours=1)) + timedelta(days=1))


def test_segment_windows_morning_midday_afternoon_are_equal_daylight_thirds():
    d = date(2026, 8, 18)
    sunrise = datetime(2026, 8, 18, 6, 20)
    sunset = datetime(2026, 8, 18, 20, 15)
    windows = {name: (s, e) for name, s, e in _segment_windows(sunrise, sunset, d)}
    morning, midday, afternoon = windows["Morning"], windows["Midday"], windows["Afternoon"]
    # Contiguous: Morning starts right where Dawn ends, Afternoon ends right where Dusk starts.
    assert morning[0] == sunrise + timedelta(hours=1)
    assert afternoon[1] == sunset - timedelta(hours=1)
    assert morning[1] == midday[0]
    assert midday[1] == afternoon[0]
    # Equal thirds of the daytime interior (within a second, for float/rounding slop).
    interior = afternoon[1] - morning[0]
    third = interior / 3
    assert abs((morning[1] - morning[0]) - third) < timedelta(seconds=1)
    assert abs((midday[1] - midday[0]) - third) < timedelta(seconds=1)
    assert abs((afternoon[1] - afternoon[0]) - third) < timedelta(seconds=1)


def test_segment_windows_daytime_thirds_shrink_on_a_short_winter_day():
    d_summer = date(2026, 8, 18)
    summer = {
        name: (s, e) for name, s, e in
        _segment_windows(datetime(2026, 8, 18, 6, 20), datetime(2026, 8, 18, 20, 15), d_summer)
    }
    d_winter = date(2026, 12, 15)
    winter = {
        name: (s, e) for name, s, e in
        _segment_windows(datetime(2026, 12, 15, 7, 50), datetime(2026, 12, 15, 17, 30), d_winter)
    }
    for name in ("Morning", "Midday", "Afternoon"):
        summer_len = summer[name][1] - summer[name][0]
        winter_len = winter[name][1] - winter[name][0]
        assert winter_len < summer_len
    # Night correctly runs longer on the shorter winter day.
    assert (winter["Night"][1] - winter["Night"][0]) > (summer["Night"][1] - summer["Night"][0])


# --- New "beyond pressure trend and moon phase" manual-only factors --------------

def test_manual_segment_score_breakdown_starts_with_base_and_sums_to_raw_score():
    result = manual_segment_score("Dawn", "summer_peak", 40, 7)
    assert result.breakdown[0][0] == "Base"
    assert result.breakdown[0][1] == 5.0
    raw_total = sum(delta for _, delta, _ in result.breakdown)
    # Nothing here should clamp, so the breakdown's own arithmetic should match the
    # returned score exactly - this is the "how was this derived" tooltip's whole
    # premise, so it needs to actually add up.
    assert round(raw_total, 1) == result.score


def test_manual_segment_score_water_temp_prime_band_gives_a_bonus():
    cold = manual_segment_score("Dawn", "winter", 40, 7, water_temp_f=45.0)
    prime = manual_segment_score("Dawn", "winter", 40, 7, water_temp_f=70.0)
    extreme = manual_segment_score("Dawn", "winter", 40, 7, water_temp_f=90.0)
    assert prime.score > cold.score
    assert any(label == "Water temperature" for label, _, _ in prime.breakdown)
    assert any(label == "Water temperature" and delta < 0 for label, delta, _ in cold.breakdown)
    assert any(label == "Water temperature" and delta < 0 for label, delta, _ in extreme.breakdown)


def test_manual_segment_score_water_temp_summer_stratified_band_is_neutral():
    # 77-84F ("Summer Stratified") intentionally has no dedicated weight - it's
    # already partially covered by the season_summer_midday_penalty factor.
    result = manual_segment_score("Midday", "summer_peak", 40, 7, water_temp_f=80.0)
    assert not any(label == "Water temperature" for label, _, _ in result.breakdown)


def test_manual_segment_score_water_clarity_stained_bonus_and_muddy_penalty():
    stained = manual_segment_score("Dawn", "summer_peak", 40, 7, water_clarity="Green stained")
    muddy = manual_segment_score("Dawn", "summer_peak", 40, 7, water_clarity="Muddy")
    clear = manual_segment_score("Dawn", "summer_peak", 40, 7, water_clarity="Clear")
    assert stained.score > clear.score > muddy.score
    assert not any(label == "Water clarity" for label, _, _ in clear.breakdown)


def test_manual_segment_score_forage_present_gives_a_small_bonus():
    seen = manual_segment_score("Dawn", "summer_peak", 40, 7, forage_present=True)
    not_seen = manual_segment_score("Dawn", "summer_peak", 40, 7, forage_present=False)
    neither = manual_segment_score("Dawn", "summer_peak", 40, 7)
    assert seen.score > not_seen.score
    assert not_seen.score == neither.score  # absence isn't scored as a penalty


def test_manual_segment_score_without_the_new_extras_is_unaffected():
    # None of the new manual-only factors should fire when the caller doesn't pass
    # them, same as before they existed.
    result = manual_segment_score("Dawn", "summer_peak", 40, 7)
    labels = {label for label, _, _ in result.breakdown}
    assert not labels & {"Water temperature", "Water clarity", "Forage"}


def test_manual_segment_score_light_rain_gives_a_small_bonus_short_of_storm():
    dry = manual_segment_score("Dawn", "summer_peak", 40, 7, total_precip_in=0.0, max_precip_prob_pct=0.0)
    light_rain = manual_segment_score("Dawn", "summer_peak", 40, 7, total_precip_in=0.3, max_precip_prob_pct=40.0)
    storm = manual_segment_score("Dawn", "summer_peak", 40, 7, total_precip_in=1.5, max_precip_prob_pct=95.0)
    assert light_rain.score > dry.score
    assert storm.score < dry.score
    assert any(label == "Precipitation" for label, _, _ in light_rain.breakdown)


def test_manual_segment_score_moon_is_now_genuinely_two_sided():
    # 2026 rebalance: moon phase went from a one-way "bonus near new/full,
    # nothing otherwise" to a real two-sided nudge with a matching penalty
    # near the quarter moons - see core/scoring.py's module docstring for why.
    near_full = astro.MoonPhase(14.5, 0.5, 100.0, "Full Moon", is_new_or_full_window=True, is_quarter_window=False)
    near_quarter = astro.MoonPhase(7.4, 0.25, 50.0, "First Quarter", is_new_or_full_window=False, is_quarter_window=True)
    neither = astro.MoonPhase(11.0, 0.37, 75.0, "Waxing Gibbous", is_new_or_full_window=False, is_quarter_window=False)
    bonus_result = manual_segment_score("Dawn", "summer_peak", 40, 7, moon=near_full)
    penalty_result = manual_segment_score("Dawn", "summer_peak", 40, 7, moon=near_quarter)
    neutral_result = manual_segment_score("Dawn", "summer_peak", 40, 7, moon=neither)
    assert bonus_result.score > neutral_result.score > penalty_result.score
    assert any(label == "Moon phase" and delta > 0 for label, delta, _ in bonus_result.breakdown)
    assert any(label == "Moon phase" and delta < 0 for label, delta, _ in penalty_result.breakdown)
    assert not any(label == "Moon phase" for label, _, _ in neutral_result.breakdown)


def test_manual_segment_score_cloud_cover_is_now_genuinely_two_sided():
    # 2026 rebalance: clear/bright ("bluebird") skies now score an explicit
    # penalty instead of just missing out on the overcast bonus.
    overcast = manual_segment_score("Dawn", "summer_peak", 70, 7)
    clear = manual_segment_score("Dawn", "summer_peak", 10, 7)
    partly = manual_segment_score("Dawn", "summer_peak", 40, 7)
    assert overcast.score > partly.score > clear.score
    assert any(label == "Cloud cover" and delta > 0 for label, delta, _ in overcast.breakdown)
    assert any(label == "Cloud cover" and delta < 0 for label, delta, _ in clear.breakdown)
    assert not any(label == "Cloud cover" for label, _, _ in partly.breakdown)


def test_score_day_still_never_applies_water_clarity_or_forage():
    # water_clarity/forage_present stay manual-entry-only (no forecast-API
    # equivalent for either) - score_day() never supplies them, so those two
    # labels should never show up in its per-segment breakdown.
    bundle = _fake_bundle()
    day = score_day(bundle, date.today())
    for seg in day.segments:
        labels = {label for label, _, _ in seg.breakdown}
        assert not labels & {"Water clarity", "Forage"}
        assert seg.breakdown[0] == ("Base", 5.0, "Starting point before any factors below.")


def test_score_day_now_applies_water_temp_band_scoring():
    # Unlike water_clarity/forage_present, water_temp_f IS now a shared
    # enhancement - score_day() passes its own estimated water temp through
    # to _segment_score(), same as manual_segment_score() always has (a real
    # study found temperature to be the one environmental factor that
    # actually predicted catch rate - see core/scoring.py's module docstring).
    # Force a cold-water estimate (well below the Peak Optimal Prime band) so
    # the penalty branch is deterministically exercised regardless of what
    # date the test suite happens to run on.
    d = date(2026, 1, 15)
    bundle = _fake_bundle_with_air_temp(28.0, d)
    day = score_day(bundle, d)
    assert onwater.water_temp_band(day.water_temp_f)["label"] == "Cold / Lethargic"
    for seg in day.segments:
        labels_and_deltas = {label: delta for label, delta, _ in seg.breakdown}
        assert "Water temperature" in labels_and_deltas
        assert labels_and_deltas["Water temperature"] < 0


def test_score_day_water_temp_summer_stratified_band_stays_neutral():
    # 77-84F intentionally has no dedicated weight (already partially covered
    # by season_summer_midday_penalty) - confirm score_day() respects that too,
    # not just manual_segment_score(). 66.0 (not a hotter value) is deliberate:
    # estimate_water_temp_f() now weights each day's actual HIGH
    # (_fake_bundle_with_air_temp sets temperature_2m_max to air_temp_f + 10),
    # not a flat all-hours average, so a cooler input air temp is what lands
    # the resulting estimate in the 77-84F Summer Stratified band now.
    d = date(2026, 7, 15)
    bundle = _fake_bundle_with_air_temp(66.0, d)
    day = score_day(bundle, d)
    assert onwater.water_temp_band(day.water_temp_f)["label"] == "Summer Stratified"
    for seg in day.segments:
        labels = {label for label, _, _ in seg.breakdown}
        assert "Water temperature" not in labels


def test_score_day_light_rain_bonus_is_a_shared_enhancement():
    # Unlike the manual-only factors, light rain is meant to apply to BOTH paths -
    # build a bundle with a burst of light (not stormy) rain and confirm at least
    # one segment picks up the bonus.
    bundle = _fake_bundle()
    for i in range(len(bundle.hourly["precipitation"])):
        bundle.hourly["precipitation"][i] = 0.02  # ~0.5in/day-ish, short of storm level
        bundle.hourly["precipitation_probability"][i] = 40
    day = score_day(bundle, date.today())
    assert any(
        any(label == "Precipitation" and delta > 0 for label, delta, _ in seg.breakdown)
        for seg in day.segments
    )
