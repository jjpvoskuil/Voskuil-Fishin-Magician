import json
from datetime import date

from core.astro import moon_phase
from core.reports import (
    build_reports_dataframe, compute_report, species_options,
    moon_illumination_pct_night_before, _moon_illumination_bin, _pressure_trend_band,
    _water_temp_bucket_label, _water_temp_bucket_axis, WATER_TEMP_BUCKET_FACTOR,
)
import pandas as pd


def _row(trip_id, trip_date, segment="Dawn", angler="John", spot_name="Baby Back Bass",
         structure_type="Rock Face / Bluff", water_clarity="Clear", lure_used="KVD Blade Minnow",
         color_used="Chartreuse", technique_used="Steady retrieve", fish_caught=0, biggest_fish_lb=None,
         fish=None, lure_category="lipless_crankbait", water_temp_f=72.0, pressure_trend_24h=0.0,
         wind_band="Light Ripple", light_condition="Partly Cloudy", precipitation="None",
         fish_activity="Moderate", forage_activity="Moderate", avg_wind_mph=6.0,
         lure_start_time="06:00:00", lure_end_time="07:00:00"):
    cond = {
        "angler": angler, "source": "spot_session", "lure_category": lure_category,
        "water_temp_f": water_temp_f, "pressure_trend_24h": pressure_trend_24h,
        "wind_band": wind_band, "light_condition": light_condition, "precipitation": precipitation,
        "fish_activity": fish_activity, "forage_activity": forage_activity, "avg_wind_mph": avg_wind_mph,
        "lure_start_time": lure_start_time, "lure_end_time": lure_end_time,
    }
    if fish is not None:
        cond["fish"] = fish
    row = {
        "trip_id": trip_id, "trip_date": trip_date, "segment": segment, "spot_id": "s1", "spot_name": spot_name,
        "structure_type": structure_type, "water_clarity": water_clarity, "lure_used": lure_used,
        "color_used": color_used, "technique_used": technique_used, "fish_caught": fish_caught,
        "biggest_fish_lb": biggest_fish_lb, "conditions_json": json.dumps(cond), "notes": "",
    }
    return row


def _fish(species, weight_lb, count=1, length_in=None):
    d = {"species": species, "weight_lb": weight_lb, "count": count}
    if length_in is not None:
        d["length_in"] = length_in
    return d


# --- moon illumination / pressure trend helpers -----------------------------

def test_moon_illumination_night_before_matches_moon_phase_at_6pm_prior_day():
    d = date(2026, 9, 6)
    expected = round(moon_phase(__import__("datetime").datetime(2026, 9, 5, 18, 0)).illumination_pct, 1)
    assert moon_illumination_pct_night_before(d) == expected


def test_moon_illumination_bin_labels_and_edges():
    assert _moon_illumination_bin(0.0) == "0-10%"
    assert _moon_illumination_bin(9.9) == "0-10%"
    assert _moon_illumination_bin(10.0) == "10-20%"
    assert _moon_illumination_bin(99.9) == "90-100%"
    assert _moon_illumination_bin(100.0) == "90-100%"
    assert _moon_illumination_bin(None) is None


def test_pressure_trend_band_thresholds():
    assert _pressure_trend_band(-2.0) == "Falling"
    assert _pressure_trend_band(-1.5) == "Falling"
    assert _pressure_trend_band(-1.0) == "Steady"
    assert _pressure_trend_band(1.9) == "Steady"
    assert _pressure_trend_band(2.0) == "Rising / High"
    assert _pressure_trend_band(5.0) == "Rising / High"
    assert _pressure_trend_band(None) is None


# --- water temp custom bucketing (punch-list #92 follow-up) --------------------

def test_water_temp_bucket_label_floors_to_width_and_formats_cleanly():
    assert _water_temp_bucket_label(83.4, 2) == "82-84°F"
    assert _water_temp_bucket_label(84.0, 2) == "84-86°F"  # exactly on a boundary -> the bucket it starts
    assert _water_temp_bucket_label(72.3, 1) == "72-73°F"
    assert _water_temp_bucket_label(72.3, 5) == "70-75°F"
    assert _water_temp_bucket_label(None, 2) is None
    assert _water_temp_bucket_label(float("nan"), 2) is None  # pandas' missing-value shape, not Python None
    assert _water_temp_bucket_label(72.0, 0) is None  # a bogus non-positive width must not divide-by-zero


def test_water_temp_bucket_axis_fills_every_bucket_between_observed_min_and_max():
    values = pd.Series([82.17, 84.9, 93.0])
    axis = _water_temp_bucket_axis(values, 2)
    assert axis == ["82-84°F", "84-86°F", "86-88°F", "88-90°F", "90-92°F", "92-94°F"]


def test_water_temp_bucket_axis_is_empty_for_no_observed_data():
    assert _water_temp_bucket_axis(pd.Series(dtype=float), 2) == []
    assert _water_temp_bucket_axis(None, 2) == []


# --- build_reports_dataframe --------------------------------------------------

def test_build_reports_dataframe_basic_shape_and_factors():
    rows = [_row("t1", "2026-09-06", fish=[_fish("Largemouth Bass", 3.5)])]
    trips_df, fish_df = build_reports_dataframe(rows)

    assert len(trips_df) == 1
    assert len(fish_df) == 1
    t = trips_df.iloc[0]
    assert t["date"] == date(2026, 9, 6)
    assert t["day_of_week"] == "Sunday"
    assert t["angler"] == "John"
    assert t["spot"] == "Baby Back Bass"
    assert t["lure"] == "KVD Blade Minnow"
    assert t["lure_category"] == "Lipless Crankbait"  # LURE_PROFILES display name
    assert t["water_temp_band"] == "Peak Optimal Prime"  # 72F
    assert t["pressure_trend_band"] == "Steady"
    assert t["fish_caught"] == 1
    assert t["biggest_fish_lb"] is None  # column wasn't set on this row

    f = fish_df.iloc[0]
    assert f["species"] == "Largemouth Bass"
    assert f["weight_lb"] == 3.5
    assert f["count"] == 1
    # factor columns are inherited from the parent trip
    assert f["angler"] == "John"
    assert f["lure_category"] == "Lipless Crankbait"


def test_build_reports_dataframe_group_logged_fish_counts_correctly():
    rows = [_row("t1", "2026-09-06", fish=[_fish("Bluegill", 0.4, count=4)])]
    trips_df, fish_df = build_reports_dataframe(rows)
    assert trips_df.iloc[0]["fish_caught"] == 4
    assert fish_df.iloc[0]["count"] == 4


def test_build_reports_dataframe_legacy_row_falls_back_to_summary_columns():
    rows = [_row("t1", "2026-09-06", fish=None, fish_caught=3, biggest_fish_lb=2.25)]
    trips_df, fish_df = build_reports_dataframe(rows)
    assert len(trips_df) == 1
    assert trips_df.iloc[0]["fish_caught"] == 3
    assert trips_df.iloc[0]["biggest_fish_lb"] == 2.25
    assert fish_df.empty  # no species to attribute a legacy row's catch to


def test_build_reports_dataframe_missing_water_temp_leaves_season_and_band_none():
    rows = [_row("t1", "2026-09-06", water_temp_f=None)]
    trips_df, _ = build_reports_dataframe(rows)
    assert trips_df.iloc[0]["water_temp_band"] is None
    assert trips_df.iloc[0]["season"] is None


def test_build_reports_dataframe_fish_per_hour_uses_calibration_function():
    # a 1-hour window (06:00-07:00) with 2 fish -> 2.0 fish/hour, matching
    # core.calibration.trip_fish_per_hour()'s own math exactly
    rows = [_row("t1", "2026-09-06", fish_caught=2, lure_start_time="06:00:00", lure_end_time="07:00:00")]
    trips_df, _ = build_reports_dataframe(rows)
    assert trips_df.iloc[0]["fish_per_hour"] == 2.0


def test_build_reports_dataframe_empty_input():
    trips_df, fish_df = build_reports_dataframe([])
    assert trips_df.empty
    assert fish_df.empty


# --- compute_report: total_fish -----------------------------------------------

def test_compute_report_total_fish_by_lure_category_no_species_filter():
    rows = [
        _row("t1", "2026-09-06", lure_category="lipless_crankbait", fish=[_fish("Bass", 2.0)]),
        _row("t2", "2026-09-06", lure_category="lipless_crankbait", fish=[_fish("Bass", 1.0)]),
        _row("t3", "2026-09-06", lure_category="football_jig", fish=[_fish("Bass", 3.0)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "lure_category", "total_fish")
    by_cat = dict(zip(report["lure_category"], report["value"]))
    assert by_cat["Lipless Crankbait"] == 2
    assert by_cat["Football Jig"] == 1
    # sorted by value descending (no ORDER_HINTS entry for lure_category)
    assert report.iloc[0]["lure_category"] == "Lipless Crankbait"


def test_compute_report_total_fish_with_species_filter_uses_fish_df():
    rows = [
        _row("t1", "2026-09-06", lure_category="lipless_crankbait",
             fish=[_fish("Largemouth Bass", 2.0), _fish("Bluegill", 0.3, count=3)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report_all = compute_report(trips_df, fish_df, "lure_category", "total_fish")
    assert report_all.iloc[0]["value"] == 4  # 1 bass + 3 bluegill

    report_bass_only = compute_report(trips_df, fish_df, "lure_category", "total_fish", species="Largemouth Bass")
    assert report_bass_only.iloc[0]["value"] == 1


# --- compute_report: fish_per_hour ---------------------------------------------

def test_compute_report_fish_per_hour_pools_across_trips_and_ignores_species():
    rows = [
        _row("t1", "2026-09-06", lure_category="lipless_crankbait", fish_caught=4,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # 4 fish / 1 hr
        _row("t2", "2026-09-06", lure_category="lipless_crankbait", fish_caught=2,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # 2 fish / 1 hr
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "lure_category", "fish_per_hour")
    assert report.iloc[0]["value"] == 3.0  # pooled: (4 + 2) fish / (1 + 1) hours
    assert report.iloc[0]["n"] == 2
    # species is ignored for this metric - same result either way
    report_species = compute_report(trips_df, fish_df, "lure_category", "fish_per_hour", species="Largemouth Bass")
    assert report_species.iloc[0]["value"] == 3.0


def test_compute_report_fish_per_hour_excludes_untrustworthy_rows():
    rows = [
        _row("t1", "2026-09-06", lure_category="lipless_crankbait", fish_caught=1,
             lure_start_time=None, lure_end_time=None),  # no duration - excluded
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "lure_category", "fish_per_hour")
    assert report.empty


def test_compute_report_fish_per_hour_pooling_survives_a_majority_of_skunked_trips():
    # Regression guard for the angler's own live report: "if I pick sky
    # condition and total fish caught, there is something in every bucket,
    # but if I do it as a fish caught rate, only 3 buckets have a number" -
    # a bucket where MOST trustworthy trips got skunked used to read as a
    # flat, misleading 0.0 (the old median-of-per-trip-rates: median of
    # [0, 0, 6] is 0), even though it clearly produced real fish overall.
    # Pooling (sum fish / sum hours) must read as a real, nonzero rate here.
    rows = [
        _row("t1", "2026-09-06", lure_category="lipless_crankbait", fish_caught=0,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # skunked, 1 hr
        _row("t2", "2026-09-06", lure_category="lipless_crankbait", fish_caught=0,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # skunked, 1 hr
        _row("t3", "2026-09-06", lure_category="lipless_crankbait", fish_caught=6,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # 6 fish, 1 hr
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "lure_category", "fish_per_hour")
    assert report.iloc[0]["value"] == 2.0  # pooled: 6 fish / 3 hours, not median([0, 0, 6]) == 0
    assert report.iloc[0]["n"] == 3


# --- compute_report: biggest_fish / trip_count ---------------------------------

def test_compute_report_biggest_fish_by_spot():
    rows = [
        _row("t1", "2026-09-06", spot_name="Spot A", fish=[_fish("Bass", 2.0), _fish("Bass", 5.0)]),
        _row("t2", "2026-09-06", spot_name="Spot B", fish=[_fish("Bass", 1.0)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "spot", "biggest_fish")
    by_spot = dict(zip(report["spot"], report["value"]))
    assert by_spot["Spot A"] == 5.0
    assert by_spot["Spot B"] == 1.0


def test_compute_report_trip_count_by_angler():
    rows = [
        _row("t1", "2026-09-06", angler="Amy"),
        _row("t2", "2026-09-06", angler="Amy"),
        _row("t3", "2026-09-06", angler="Bob"),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "angler", "trip_count")
    by_angler = dict(zip(report["angler"], report["value"]))
    assert by_angler["Amy"] == 2
    assert by_angler["Bob"] == 1


# --- compute_report: ORDER_HINTS factors always show every value -------------

def test_compute_report_segment_factor_shows_all_six_segments_even_at_zero():
    rows = [_row("t1", "2026-09-06", segment="Dawn", fish=[_fish("Bass", 2.0)])]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, "segment", "total_fish")
    assert list(report["segment"]) == ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]
    assert report.iloc[0]["value"] == 1
    assert report.iloc[1]["value"] == 0
    assert report.iloc[1]["n"] == 0


# --- compute_report: date-based factors ---------------------------------------

def test_compute_report_date_daily_factor_fills_every_day_in_range():
    rows = [_row("t1", "2026-09-06", fish=[_fish("Bass", 2.0)])]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, "date", "total_fish",
        date_start=date(2026, 9, 4), date_end=date(2026, 9, 8),
    )
    assert list(report["date"]) == [date(2026, 9, d) for d in range(4, 9)]
    values = dict(zip(report["date"], report["value"]))
    assert values[date(2026, 9, 6)] == 1
    assert values[date(2026, 9, 4)] == 0


def test_compute_report_date_weekly_factor_groups_by_sunday_start_week():
    rows = [
        _row("t1", "2026-09-06", fish=[_fish("Bass", 2.0)]),  # a Sunday
        _row("t2", "2026-09-08", fish=[_fish("Bass", 3.0)]),  # same week, Tuesday
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, "week_start", "total_fish",
        date_start=date(2026, 9, 6), date_end=date(2026, 9, 12),
    )
    assert len(report) == 1
    assert report.iloc[0]["week_start"] == date(2026, 9, 6)
    assert report.iloc[0]["value"] == 2


# --- compute_report: WATER_TEMP_BUCKET_FACTOR (punch-list #92 follow-up) ------
# Angler's report: "Water Temp Band" (5 fixed biological stages) is too
# coarse - a season's worth of trips hasn't been logged yet, so the real
# range so far is only ~10-15°F wide, and nearly every trip lands in just
# one or two of those five bands. This factor lets the bucket width be
# tuned by the caller (pages/9_Reports.py's own number_input) instead.

def test_compute_report_water_temp_bucket_factor_uses_custom_width_and_fills_gaps():
    rows = [
        _row("t1", "2026-09-01", water_temp_f=82.5, fish=[_fish("Bass", 2.0)]),
        _row("t2", "2026-09-02", water_temp_f=83.9, fish=[_fish("Bass", 3.0)]),  # same 2-wide bucket as t1
        _row("t3", "2026-09-03", water_temp_f=93.0, fish=[_fish("Bass", 1.0)]),  # far bucket - gap in between
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, WATER_TEMP_BUCKET_FACTOR, "total_fish", water_temp_bucket_width_f=2,
    )
    assert list(report[WATER_TEMP_BUCKET_FACTOR]) == [
        "82-84°F", "84-86°F", "86-88°F", "88-90°F", "90-92°F", "92-94°F",
    ]
    values = dict(zip(report[WATER_TEMP_BUCKET_FACTOR], report["value"]))
    assert values["82-84°F"] == 2  # t1 + t2 pooled into one bucket
    assert values["84-86°F"] == 0  # a real gap, shown as zero rather than omitted
    assert values["92-94°F"] == 1


def test_compute_report_water_temp_bucket_factor_widening_collapses_buckets():
    rows = [
        _row("t1", "2026-09-01", water_temp_f=82.5, fish=[_fish("Bass", 2.0)]),
        _row("t2", "2026-09-03", water_temp_f=93.0, fish=[_fish("Bass", 1.0)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, WATER_TEMP_BUCKET_FACTOR, "total_fish", water_temp_bucket_width_f=20,
    )
    assert len(report) == 1  # both readings collapse into one wide bucket
    assert report.iloc[0]["value"] == 2  # 1 fish from t1 + 1 fish from t2


def test_compute_report_water_temp_bucket_factor_excludes_missing_water_temp():
    rows = [
        _row("t1", "2026-09-01", water_temp_f=None, fish=[_fish("Bass", 2.0)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, WATER_TEMP_BUCKET_FACTOR, "total_fish", water_temp_bucket_width_f=2,
    )
    assert report.empty


def test_compute_report_water_temp_bucket_factor_defaults_width_when_not_given():
    rows = [_row("t1", "2026-09-01", water_temp_f=72.3, fish=[_fish("Bass", 2.0)])]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(trips_df, fish_df, WATER_TEMP_BUCKET_FACTOR, "total_fish")
    assert list(report[WATER_TEMP_BUCKET_FACTOR]) == ["72-74°F"]  # default 2°F width


def test_compute_report_water_temp_bucket_factor_pools_fish_per_hour_per_bucket():
    # Same masking pattern as the sky-condition regression test above, just
    # bucketed by water temp instead: 2 skunked trips + 1 productive trip,
    # all in the SAME bucket - median([0, 0, 9]) would be 0, pooled must not be.
    rows = [
        _row("t1", "2026-09-01", water_temp_f=82.5, fish_caught=0,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # skunked, 1hr
        _row("t2", "2026-09-02", water_temp_f=82.8, fish_caught=0,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # skunked, 1hr
        _row("t3", "2026-09-03", water_temp_f=83.0, fish_caught=9,
             lure_start_time="06:00:00", lure_end_time="07:00:00"),  # 9 fish, 1hr
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, WATER_TEMP_BUCKET_FACTOR, "fish_per_hour", water_temp_bucket_width_f=2,
    )
    assert report.iloc[0][WATER_TEMP_BUCKET_FACTOR] == "82-84°F"
    assert report.iloc[0]["value"] == 3.0  # pooled: 9 fish / 3 hours, not median([0, 0, 9]) == 0


def test_compute_report_water_temp_bucket_factor_with_empty_data_returns_empty_for_every_metric():
    trips_df, fish_df = build_reports_dataframe([])
    for metric_key in ("total_fish", "fish_per_hour", "biggest_fish", "trip_count"):
        report = compute_report(trips_df, fish_df, WATER_TEMP_BUCKET_FACTOR, metric_key)
        assert report.empty, f"expected an empty report for {metric_key} with no data at all"


# --- compute_report: filters ---------------------------------------------------

def test_compute_report_date_range_filter_excludes_out_of_range_rows():
    rows = [
        _row("t1", "2026-09-01", lure_category="lipless_crankbait", fish=[_fish("Bass", 2.0)]),
        _row("t2", "2026-09-06", lure_category="lipless_crankbait", fish=[_fish("Bass", 3.0)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, "lure_category", "total_fish",
        date_start=date(2026, 9, 5), date_end=date(2026, 9, 10),
    )
    assert report.iloc[0]["value"] == 1


def test_compute_report_angler_and_segment_filters():
    rows = [
        _row("t1", "2026-09-06", angler="Amy", segment="Dawn", lure_category="lipless_crankbait", fish=[_fish("Bass", 2.0)]),
        _row("t2", "2026-09-06", angler="Bob", segment="Dawn", lure_category="lipless_crankbait", fish=[_fish("Bass", 5.0)]),
        _row("t3", "2026-09-06", angler="Amy", segment="Midday", lure_category="lipless_crankbait", fish=[_fish("Bass", 9.0)]),
    ]
    trips_df, fish_df = build_reports_dataframe(rows)
    report = compute_report(
        trips_df, fish_df, "lure_category", "total_fish", anglers=["Amy"], segments=["Dawn"],
    )
    assert report.iloc[0]["value"] == 1


# --- empty input --------------------------------------------------------------

def test_compute_report_empty_dataframes_ordered_factor_still_returns_full_axis():
    trips_df, fish_df = build_reports_dataframe([])
    report = compute_report(trips_df, fish_df, "segment", "total_fish")
    assert list(report["segment"]) == ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Night"]
    assert (report["value"] == 0).all()


def test_compute_report_empty_dataframes_freeform_factor_returns_empty():
    trips_df, fish_df = build_reports_dataframe([])
    report = compute_report(trips_df, fish_df, "spot", "total_fish")
    assert report.empty


# --- species_options -----------------------------------------------------------

def test_species_options_sorted_unique():
    rows = [
        _row("t1", "2026-09-06", fish=[_fish("Largemouth Bass", 2.0), _fish("Bluegill", 0.3)]),
        _row("t2", "2026-09-06", fish=[_fish("Bluegill", 0.4)]),
    ]
    _, fish_df = build_reports_dataframe(rows)
    assert species_options(fish_df) == ["Bluegill", "Largemouth Bass"]


def test_species_options_empty_fish_df():
    assert species_options(build_reports_dataframe([])[1]) == []
