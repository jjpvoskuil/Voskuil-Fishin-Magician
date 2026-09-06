import json

import pytest

from core.calibration import (
    calibrate_weights, calibration_summary, location_adjustments, moon_illumination_dawn_rates,
    daily_dawn_morning_catch, trip_fish_per_hour, DAYS_IN_LUNAR_CYCLE, MIN_SAMPLES_PER_SIDE,
    LOCATION_MIN_SAMPLES,
)
from core.scoring import DEFAULT_WEIGHTS


def _row(pressure_trend_24h=0.0, fish_caught=1, conditions_json=None):
    if conditions_json is None:
        conditions_json = json.dumps({"pressure_trend_24h": pressure_trend_24h})
    return {"conditions_json": conditions_json, "fish_caught": fish_caught}


def _timed_row(
    pressure_trend_24h=0.0, fish_caught=1, hours=1.0,
    spot_id=None, spot_name=None, segment=None, extra_conditions=None, trip_date=None,
):
    """A row with a real lure_start_time/lure_end_time window (punch-list
    #81) - the shape trip_fish_per_hour()/calibrate_weights()/
    location_adjustments() all actually key off of, unlike _row() above
    (which predates fish-per-hour and has no timing at all - kept as-is for
    the pre-#81 tests that only care about the JSON-shape edge cases)."""
    start = "06:00:00"
    end_seconds = int(hours * 3600)
    end_h, rem = divmod(end_seconds, 3600)
    end_m, end_s = divmod(rem, 60)
    end = f"{6 + end_h:02d}:{end_m:02d}:{end_s:02d}"
    cond = {"pressure_trend_24h": pressure_trend_24h, "lure_start_time": start, "lure_end_time": end}
    if extra_conditions:
        cond.update(extra_conditions)
    row = {"conditions_json": json.dumps(cond), "fish_caught": fish_caught}
    if spot_id is not None:
        row["spot_id"] = spot_id
    if spot_name is not None:
        row["spot_name"] = spot_name
    if segment is not None:
        row["segment"] = segment
    if trip_date is not None:
        row["trip_date"] = trip_date
    return row


def test_calibrate_weights_ignores_rows_where_conditions_json_is_not_an_object():
    # Same latent bug class as core.lure_history: conditions_json can be
    # valid JSON that isn't a dict (a bare number/string/list/null) - this
    # used to crash _factor_flags()'s conditions.get(...) call with an
    # uncaught AttributeError instead of just skipping the row.
    rows = [_row(conditions_json="7"), _row(conditions_json='"oops"'), _row(conditions_json="[1]")]
    rows += [_row(pressure_trend_24h=-2.0, fish_caught=1) for _ in range(MIN_SAMPLES_PER_SIDE)]
    rows += [_row(pressure_trend_24h=0.0, fish_caught=0) for _ in range(MIN_SAMPLES_PER_SIDE)]
    weights = calibrate_weights(rows)  # must not raise
    assert isinstance(weights, dict)


def test_calibration_summary_ignores_rows_where_conditions_json_is_not_an_object():
    rows = [_row(conditions_json="null"), _row(conditions_json="24")]
    summary = calibration_summary(rows)  # must not raise
    assert isinstance(summary, dict)


# --- Punch-list #81: fish-per-hour replaces the old binary success flag ----

def test_trip_fish_per_hour_computes_rate_from_lure_start_and_end_time():
    row = _timed_row(fish_caught=2, hours=1.0)
    assert trip_fish_per_hour(row) == 2.0


def test_trip_fish_per_hour_a_scoreless_but_validly_timed_trip_is_zero_not_excluded():
    # Fishing for a real hour and catching nothing is a real, informative
    # data point - distinct from "we don't know how long this took" (None).
    row = _timed_row(fish_caught=0, hours=1.0)
    assert trip_fish_per_hour(row) == 0.0


def test_trip_fish_per_hour_excludes_missing_timing():
    row = _row(fish_caught=1)  # no lure_start_time/lure_end_time at all
    assert trip_fish_per_hour(row) is None


def test_trip_fish_per_hour_excludes_implausibly_short_or_long_durations():
    # A punch-list #81 guardrail against the "sketchy" batch-reconstructed
    # sessions the angler flagged - see core/calibration.py's module
    # docstring for why there's no way to positively identify those rows,
    # only filter out the most implausible-looking durations.
    too_short = _timed_row(fish_caught=1, hours=1 / 120)  # 30 seconds
    too_long = _timed_row(fish_caught=1, hours=9.0)
    assert trip_fish_per_hour(too_short) is None
    assert trip_fish_per_hour(too_long) is None


def test_trip_fish_per_hour_parses_microsecond_suffixed_timestamps():
    # Real live bug (angler noticed the moon-illumination "last 14 days"
    # chart undercounting, "I think this might be the 8/23/26 split
    # again"): pages/6_Spot_Session.py stamps lure_start_time/lure_end_time
    # via `time.isoformat()` on a real live timestamp, which appends
    # microseconds whenever they're non-zero ("06:06:37.576926") - true of
    # virtually every genuinely live-timed entry, as opposed to a
    # manually-backfilled whole-second one. The old strict
    # `datetime.strptime(start, "%H:%M:%S")` couldn't parse that suffix and
    # silently excluded the row - meaning almost every real live-timed
    # session was quietly dropped from every calibration function in this
    # module, not just this one test's row.
    row = {
        "conditions_json": '{"lure_start_time": "06:06:37.576926", "lure_end_time": "07:24:07.255807"}',
        "fish_caught": 3,
    }
    rate = trip_fish_per_hour(row)
    assert rate is not None
    assert rate == pytest.approx(2.3227, rel=1e-3)  # 3 fish / ~1.2916 hours


def test_trip_fish_per_hour_still_parses_whole_second_timestamps():
    # Manually-backfilled/historical rows (no fractional part) must keep
    # working exactly as before this fix.
    row = _timed_row(fish_caught=2, hours=1.0)
    assert trip_fish_per_hour(row) == 2.0


def test_calibrate_weights_stays_at_defaults_with_no_trustworthy_duration_data():
    # Every row here has a real pressure signal but NO timing at all (the
    # pre-#81 _row() helper) - the old binary-success calibration would have
    # happily nudged pressure_falling from this; the rewrite must not, since
    # none of it can be trusted as a real rate.
    rows = [_row(pressure_trend_24h=-2.0, fish_caught=1) for _ in range(10)]
    rows += [_row(pressure_trend_24h=0.0, fish_caught=0) for _ in range(10)]
    weights = calibrate_weights(rows)
    assert weights == DEFAULT_WEIGHTS


def test_calibrate_weights_moves_on_fish_per_hour_even_when_binary_success_is_identical():
    # The core punch-list #81 behavior change: "on" and "off" here both hit
    # fish_caught >= 1 on every single row (100% success either way, which
    # is what the OLD calibration compared) - only the rate differs. If
    # calibration were still binary-success-based, this would produce zero
    # lift and leave pressure_falling untouched.
    on_rows = [_timed_row(pressure_trend_24h=-2.0, fish_caught=1, hours=0.25) for _ in range(4)]   # 4.0 fish/hr
    off_rows = [_timed_row(pressure_trend_24h=0.0, fish_caught=1, hours=2.0) for _ in range(4)]    # 0.5 fish/hr
    weights = calibrate_weights(on_rows + off_rows)
    assert weights["pressure_falling"] > DEFAULT_WEIGHTS["pressure_falling"]


def test_calibration_summary_reports_trustworthy_duration_count():
    rows = [_timed_row(fish_caught=1, hours=1.0) for _ in range(3)]
    rows += [_row(fish_caught=1)]  # no timing - not trustworthy
    summary = calibration_summary(rows)
    assert summary["total_trips"] == 4
    assert summary["trustworthy_duration_trips"] == 3


# --- Punch-list #81: location_adjustments() ---------------------------------

def test_location_adjustments_rewards_a_spot_segment_that_outperforms_its_segment_baseline():
    # Spot A crushes it at Dawn; Spot B is ordinary at Dawn - enough samples
    # at both to compare, and enough total Dawn samples to have a baseline.
    rows = []
    rows += [_timed_row(fish_caught=3, hours=1.0, spot_id="A", spot_name="Spot A", segment="Dawn") for _ in range(6)]
    rows += [_timed_row(fish_caught=1, hours=1.0, spot_id="B", spot_name="Spot B", segment="Dawn") for _ in range(6)]
    adjustments = location_adjustments(rows)
    assert ("A", "Dawn") in adjustments
    assert adjustments[("A", "Dawn")]["adjustment"] > 0
    assert adjustments[("A", "Dawn")]["n"] == 6
    assert adjustments[("A", "Dawn")]["spot_name"] == "Spot A"
    assert ("B", "Dawn") in adjustments
    assert adjustments[("B", "Dawn")]["adjustment"] < 0


def test_location_adjustments_requires_minimum_samples_per_cell():
    rows = [_timed_row(fish_caught=5, hours=1.0, spot_id="A", spot_name="Spot A", segment="Dawn")
            for _ in range(LOCATION_MIN_SAMPLES - 1)]
    rows += [_timed_row(fish_caught=1, hours=1.0, spot_id="B", spot_name="Spot B", segment="Dawn")
             for _ in range(LOCATION_MIN_SAMPLES)]
    adjustments = location_adjustments(rows)
    assert ("A", "Dawn") not in adjustments  # too few trips at A itself


def test_location_adjustments_shrinks_small_samples_toward_zero():
    # Same relative outperformance at both spots (1.5x the segment baseline
    # rate), but Spot Big has far more logged trips than Spot Small - the
    # small sample's adjustment should be damped harder (n / (n + K)
    # shrinkage), not treated as equally confident. The baseline population
    # is deliberately large (50) so it isn't itself swamped by "big"'s own
    # 30 rows - if the baseline sample were small, the segment median would
    # just track "big" and wash out its own relative lift to zero.
    rows = []
    rows += [_timed_row(fish_caught=2, hours=1.0, spot_id="baseline", spot_name="Baseline", segment="Dawn")
             for _ in range(50)]
    rows += [_timed_row(fish_caught=3, hours=1.0, spot_id="big", spot_name="Big", segment="Dawn") for _ in range(30)]
    rows += [_timed_row(fish_caught=3, hours=1.0, spot_id="small", spot_name="Small", segment="Dawn")
             for _ in range(LOCATION_MIN_SAMPLES)]
    adjustments = location_adjustments(rows)
    assert adjustments[("big", "Dawn")]["adjustment"] > adjustments[("small", "Dawn")]["adjustment"] > 0


# --- Punch-list #89 (revised): moon_illumination_dawn_rates() ---------------
#
# core.astro's own reference new moon is 2000-01-06 18:14 UTC (REF_NEW_MOON_JD)
# - 2000-01-07 was a real, easy-to-reason-about New Moon day (age ~0), so
# every test date below is picked as an exact multiple of the synodic month
# (~29.53 days) offset from that date, landing near age 0 (new), ~7.4
# (waxing, ~50%) or ~14.8 (full, ~100%) predictably instead of needing a
# live ephemeris lookup to know what day-of-cycle/illumination a given
# calendar date should produce.

def test_days_in_lunar_cycle_is_30():
    # int(SYNODIC_MONTH) + 1 = int(29.53...) + 1 - age_days is always
    # < SYNODIC_MONTH, so int(age_days) only ever lands in 0-29.
    assert DAYS_IN_LUNAR_CYCLE == 30


def test_moon_illumination_dawn_rates_covers_all_30_days_even_with_no_data():
    rates = moon_illumination_dawn_rates([])
    assert len(rates) == 30
    assert [d["day_of_cycle"] for d in rates] == list(range(30))
    for d in rates:
        assert d["median"] is None
        assert d["n"] == 0
        assert 0.0 <= d["illumination_pct"] <= 100.0


def test_moon_illumination_dawn_rates_new_moon_day_is_near_0_pct_illumination():
    # A Dawn trip on 2000-01-07 - the morning right after the reference new
    # moon (core.astro.REF_NEW_MOON_JD, 2000-01-06 18:14 UTC) - has its
    # "night before" (18:00 on 2000-01-06) at age ~0.15 days: day_of_cycle
    # 0, illumination near 0% (verified directly against core.astro.moon_phase()).
    rows = [_timed_row(fish_caught=3, hours=1.0, segment="Dawn", trip_date="2000-01-07")]
    rates = moon_illumination_dawn_rates(rows)
    day0 = rates[0]
    assert day0["n"] == 1
    assert day0["median"] == 3.0
    assert day0["illumination_pct"] < 5.0


def test_moon_illumination_dawn_rates_full_moon_day_is_near_100_pct_illumination():
    # ~14.77 days (half a synodic month) after the reference new moon lands
    # right on a full moon - 2000-01-21 (13 days later) is close enough to
    # land in the high-illumination days near day_of_cycle 14.
    rows = [_timed_row(fish_caught=2, hours=1.0, segment="Morning", trip_date="2000-01-21")]
    rates = moon_illumination_dawn_rates(rows)
    matching = [d for d in rates if d["n"] == 1]
    assert len(matching) == 1
    assert matching[0]["illumination_pct"] > 85.0


def test_moon_illumination_dawn_rates_only_counts_dawn_and_morning_segments():
    rows = [
        _timed_row(fish_caught=8, hours=1.0, segment="Night", trip_date="2000-01-08"),
        _timed_row(fish_caught=8, hours=1.0, segment="Dusk", trip_date="2000-01-08"),
        _timed_row(fish_caught=8, hours=1.0, segment="Afternoon", trip_date="2000-01-08"),
    ]
    rates = moon_illumination_dawn_rates(rows)
    assert all(d["n"] == 0 for d in rates)  # none of these are Dawn/Morning


def test_moon_illumination_dawn_rates_uses_the_night_before_trip_date_not_trip_date_itself():
    # The whole point of the rewrite: a Dawn/Morning trip's relevant moon
    # state is the night that already passed, not core.scoring's own
    # same-day-18:00 convention (which is the UPCOMING night for that
    # date - a full calendar day later than what a Dawn trip experienced).
    # 2000-01-08 (night-before-relative age ~0.2, day 0) vs. 2000-01-09
    # (night-before-relative age ~1.2, day 1) must land in DIFFERENT
    # buckets, one calendar day apart, exactly tracking trip_date.
    day0_rows = moon_illumination_dawn_rates(
        [_timed_row(fish_caught=1, hours=1.0, segment="Dawn", trip_date="2000-01-08")]
    )
    day1_rows = moon_illumination_dawn_rates(
        [_timed_row(fish_caught=1, hours=1.0, segment="Dawn", trip_date="2000-01-09")]
    )
    bucket0 = next(d["day_of_cycle"] for d in day0_rows if d["n"] == 1)
    bucket1 = next(d["day_of_cycle"] for d in day1_rows if d["n"] == 1)
    assert bucket1 == bucket0 + 1


def test_moon_illumination_dawn_rates_excludes_untrustworthy_duration_rows():
    untimed = _row(fish_caught=99)
    untimed["segment"] = "Dawn"
    untimed["trip_date"] = "2000-01-08"
    rows = [
        _timed_row(fish_caught=2, hours=1.0, segment="Dawn", trip_date="2000-01-08"),
        untimed,  # no timing at all - must not pollute the median
    ]
    rates = moon_illumination_dawn_rates(rows)
    day0 = next(d for d in rates if d["n"] > 0)
    assert day0["n"] == 1
    assert day0["median"] == 2.0


def test_moon_illumination_dawn_rates_ignores_rows_missing_trip_date():
    rows = [_timed_row(fish_caught=1, hours=1.0, segment="Dawn")]  # no trip_date at all
    rates = moon_illumination_dawn_rates(rows)
    assert all(d["n"] == 0 for d in rates)


def test_moon_illumination_dawn_rates_since_filters_out_older_trips():
    # Punch-list #89 (2nd follow-up): "just the last two weeks as a
    # separate chart" - since= lets home.py reuse this same function for
    # both the all-time and the recent-only view.
    import datetime as dt

    rows = [
        _timed_row(fish_caught=5, hours=1.0, segment="Dawn", trip_date="2000-01-07"),  # old
        _timed_row(fish_caught=1, hours=1.0, segment="Dawn", trip_date="2000-02-07"),  # recent
    ]
    all_time = moon_illumination_dawn_rates(rows)
    recent = moon_illumination_dawn_rates(rows, since=dt.date(2000, 2, 1))
    assert sum(d["n"] for d in all_time) == 2
    assert sum(d["n"] for d in recent) == 1
    recent_day = next(d for d in recent if d["n"] > 0)
    assert recent_day["median"] == 1.0


def test_moon_illumination_dawn_rates_since_none_keeps_every_trip():
    import datetime as dt

    rows = [_timed_row(fish_caught=1, hours=1.0, segment="Dawn", trip_date="2000-01-07")]
    assert moon_illumination_dawn_rates(rows, since=None) == moon_illumination_dawn_rates(rows)
    # Sanity: a since far in the future excludes it, proving since is really applied.
    excluded = moon_illumination_dawn_rates(rows, since=dt.date(2099, 1, 1))
    assert sum(d["n"] for d in excluded) == 0


# --- Punch-list #89 (3rd follow-up): since+until restricts the BUCKETS ------
# too, not just which trips count - "the 14 day chart should only show the
# last 14 days not all 30 days of the lunar cycle."

def test_moon_illumination_dawn_rates_since_alone_still_returns_all_30_buckets():
    # since alone (no until) keeps the pre-existing "all 30 buckets, just
    # filter which trips count" behavior - only since+until together
    # restricts which buckets are returned at all.
    import datetime as dt

    rows = [_timed_row(fish_caught=1, hours=1.0, segment="Dawn", trip_date="2000-01-07")]
    assert len(moon_illumination_dawn_rates(rows, since=dt.date(2000, 1, 1))) == 30


def test_moon_illumination_dawn_rates_since_and_until_only_returns_that_windows_days():
    import datetime as dt

    # A 14-day window (inclusive both ends) can only ever touch 14 distinct
    # lunar-cycle days - not all 30.
    since = dt.date(2000, 1, 7)
    until = since + dt.timedelta(days=13)
    rates = moon_illumination_dawn_rates([], since=since, until=until)
    assert len(rates) == 14


def test_moon_illumination_dawn_rates_since_and_until_keeps_calendar_order_not_numeric():
    # Picking a window that straddles the lunar-cycle wrap (day 29 -> day 0)
    # would come out numerically out of order (e.g. ...,28,29,0,1,...) if
    # sorted 0-29 - it must instead follow calendar date order.
    import datetime as dt

    since = dt.date(2000, 1, 1)  # a few days before the reference new moon
    until = since + dt.timedelta(days=6)
    rates = moon_illumination_dawn_rates([], since=since, until=until)
    days = [d["day_of_cycle"] for d in rates]
    assert len(days) == 7
    assert days != sorted(days)  # genuinely wraps, not coincidentally ascending


def test_moon_illumination_dawn_rates_since_and_until_excludes_trips_outside_the_window():
    import datetime as dt

    rows = [
        _timed_row(fish_caught=9, hours=1.0, segment="Dawn", trip_date="2000-01-06"),  # 1 day too early
        _timed_row(fish_caught=3, hours=1.0, segment="Dawn", trip_date="2000-01-10"),  # inside
        _timed_row(fish_caught=9, hours=1.0, segment="Dawn", trip_date="2000-01-21"),  # 1 day too late
    ]
    since = dt.date(2000, 1, 7)
    until = dt.date(2000, 1, 20)
    rates = moon_illumination_dawn_rates(rows, since=since, until=until)
    assert sum(d["n"] for d in rates) == 1
    matching = next(d for d in rates if d["n"] > 0)
    assert matching["median"] == 3.0


# --- daily_dawn_morning_catch() (punch-list #89, further follow-up): the ---
# angler compared moon_illumination_dawn_rates()'s "last 14 days" chart
# against a real session (13 fish over ~3 hours) that showed up as a
# lunar-cycle bucket reading 0.2 fish/hour - a real median-of-per-lure-
# segment artifact, not a bug (see trip_fish_per_hour()'s docstring and
# core.calibration.daily_dawn_morning_catch()'s own docstring above). These
# tests use plain dicts (no _timed_row()) since this function never reads
# lure_start_time/lure_end_time at all - that independence from duration
# data is the entire point.

def test_daily_dawn_morning_catch_returns_one_entry_per_calendar_day_in_window():
    import datetime as dt

    since = dt.date(2000, 1, 7)
    until = since + dt.timedelta(days=6)
    days = daily_dawn_morning_catch([], since=since, until=until)
    assert len(days) == 7
    assert [d["date"] for d in days] == [since + dt.timedelta(days=i) for i in range(7)]


def test_daily_dawn_morning_catch_sums_fish_caught_per_day():
    import datetime as dt

    rows = [
        {"segment": "Dawn", "trip_date": "2000-01-08", "fish_caught": 10},
        {"segment": "Morning", "trip_date": "2000-01-08", "fish_caught": 1},
        {"segment": "Dawn", "trip_date": "2000-01-08", "fish_caught": 0},
        {"segment": "Dawn", "trip_date": "2000-01-08", "fish_caught": 1},
        {"segment": "Dawn", "trip_date": "2000-01-08", "fish_caught": 1},
    ]
    days = daily_dawn_morning_catch(
        rows, since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 9),
    )
    by_date = {d["date"]: d["fish"] for d in days}
    assert by_date[dt.date(2000, 1, 8)] == 13  # matches the angler's real 13-fish report


def test_daily_dawn_morning_catch_ignores_non_dawn_morning_segments():
    import datetime as dt

    rows = [
        {"segment": "Dawn", "trip_date": "2000-01-08", "fish_caught": 3},
        {"segment": "Night", "trip_date": "2000-01-08", "fish_caught": 9},
        {"segment": "Midday", "trip_date": "2000-01-08", "fish_caught": 9},
    ]
    days = daily_dawn_morning_catch(
        rows, since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 9),
    )
    by_date = {d["date"]: d["fish"] for d in days}
    assert by_date[dt.date(2000, 1, 8)] == 3


def test_daily_dawn_morning_catch_ignores_rows_outside_the_window():
    import datetime as dt

    rows = [
        {"segment": "Dawn", "trip_date": "2000-01-06", "fish_caught": 9},  # 1 day too early
        {"segment": "Dawn", "trip_date": "2000-01-08", "fish_caught": 3},  # inside
        {"segment": "Dawn", "trip_date": "2000-01-10", "fish_caught": 9},  # 1 day too late
    ]
    days = daily_dawn_morning_catch(
        rows, since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 9),
    )
    assert sum(d["fish"] for d in days) == 3


def test_daily_dawn_morning_catch_day_with_no_trips_is_a_real_zero_not_missing():
    import datetime as dt

    days = daily_dawn_morning_catch([], since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 9))
    assert all(d["fish"] == 0 for d in days)


def test_daily_dawn_morning_catch_ignores_rows_missing_trip_date():
    import datetime as dt

    rows = [{"segment": "Dawn", "fish_caught": 9}]  # no trip_date at all
    days = daily_dawn_morning_catch(rows, since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 9))
    assert sum(d["fish"] for d in days) == 0


def test_daily_dawn_morning_catch_counts_rows_with_no_duration_data_at_all():
    # The entire point: unlike moon_illumination_dawn_rates()/
    # trip_fish_per_hour(), a row with no lure_start_time/lure_end_time (or
    # an implausible one) still counts in full - there's no rate to trust
    # or distrust here, just a fish count.
    import datetime as dt

    rows = [{"segment": "Morning", "trip_date": "2000-01-08", "fish_caught": 13}]
    days = daily_dawn_morning_catch(rows, since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 9))
    by_date = {d["date"]: d["fish"] for d in days}
    assert by_date[dt.date(2000, 1, 8)] == 13


def test_daily_dawn_morning_catch_label_matches_this_apps_day_date_format():
    import datetime as dt

    # 2000-01-08 was a Saturday - label format matches this app's other
    # trend-chart date labels ("%a %-m/%d", e.g. home.py's trend_idx).
    days = daily_dawn_morning_catch([], since=dt.date(2000, 1, 8), until=dt.date(2000, 1, 8))
    assert days[0]["label"] == "Sat 1/08"


def test_daily_dawn_morning_catch_illumination_pct_uses_the_night_before():
    # Same reference dates as moon_illumination_dawn_rates()'s own tests
    # above - 2000-01-07 (new moon morning) near 0%, 2000-01-21 (full moon
    # morning) near 100%.
    import datetime as dt

    days = daily_dawn_morning_catch([], since=dt.date(2000, 1, 7), until=dt.date(2000, 1, 21))
    by_date = {d["date"]: d["illumination_pct"] for d in days}
    assert by_date[dt.date(2000, 1, 7)] < 5.0
    assert by_date[dt.date(2000, 1, 21)] > 95.0
