from core.lures import WATER_CLARITY_OPTIONS
from core.onwater import (
    LIGHT_CONDITIONS, PRECIPITATION_OPTIONS, STAIN_COLOR_OPTIONS, WIND_BAND_LABELS, WIND_BANDS,
    WIND_DIRECTIONS,
    cloud_proxy_for_light_condition, light_condition_for_cloud_pct, precipitation_option_for_forecast,
    precipitation_proxy, resolve_water_clarity, visibility_band, water_temp_band, wind_band,
    wind_direction_for_degrees, wind_mph_for_band,
)


def test_wind_band_boundaries():
    assert wind_band(0)["label"] == "Glassy"
    assert wind_band(3)["label"] == "Glassy"
    assert wind_band(4)["label"] == "Light Ripple"
    assert wind_band(9)["label"] == "Light Ripple"
    assert wind_band(10)["label"] == "Moderate Chop / Action Trigger"
    assert wind_band(16)["label"] == "Moderate Chop / Action Trigger"
    assert wind_band(17)["label"] == "Heavy / Turbulent"
    assert wind_band(40)["label"] == "Heavy / Turbulent"


def test_visibility_band_boundaries():
    assert visibility_band(5.0)["label"] == "Clear"
    assert visibility_band(4.0)["label"] == "Clear"
    assert visibility_band(3.99)["label"] == "Stained"
    assert visibility_band(1.5)["label"] == "Stained"
    assert visibility_band(1.49)["label"] == "Dirty / Muddy"
    assert visibility_band(0.0)["label"] == "Dirty / Muddy"


def test_water_temp_band_boundaries():
    assert water_temp_band(49.9)["label"] == "Cold / Lethargic"
    assert water_temp_band(50.0)["label"] == "Pre-Spawn Transition"
    assert water_temp_band(62.0)["label"] == "Pre-Spawn Transition"
    assert water_temp_band(63.0)["label"] == "Peak Optimal Prime"
    assert water_temp_band(76.0)["label"] == "Peak Optimal Prime"
    assert water_temp_band(77.0)["label"] == "Summer Stratified"
    assert water_temp_band(84.0)["label"] == "Summer Stratified"
    assert water_temp_band(84.5)["label"] == "Extreme Thermal Load"
    assert water_temp_band(95.0)["label"] == "Extreme Thermal Load"


def test_resolve_water_clarity_clear_and_muddy_need_no_stain_color():
    assert resolve_water_clarity(5.0) == "Clear"
    assert resolve_water_clarity(0.5) == "Muddy"


def test_resolve_water_clarity_stained_uses_supplied_stain_color():
    assert resolve_water_clarity(2.0, "Green stained") == "Green stained"
    assert resolve_water_clarity(2.0, "Brown stained") == "Brown stained"


def test_resolve_water_clarity_stained_defaults_to_brown_without_a_stain_color():
    assert resolve_water_clarity(2.0) == "Brown stained"


def test_resolve_water_clarity_always_returns_a_valid_lure_engine_option():
    for secchi in (0.2, 1.0, 1.5, 2.5, 4.0, 6.0):
        for stain in (None, "Green stained", "Brown stained"):
            assert resolve_water_clarity(secchi, stain) in WATER_CLARITY_OPTIONS


def test_resolve_water_clarity_stirred_up_overrides_everything():
    # A clear-water Secchi reading plus an explicit stain color would normally
    # resolve to Clear/the stain color - the stirred-up flag should win regardless,
    # since it represents newer information than the Secchi/stain reading.
    assert resolve_water_clarity(6.0, stirred_up=True) == "Muddy"
    assert resolve_water_clarity(2.0, "Green stained", stirred_up=True) == "Muddy"
    assert resolve_water_clarity(0.5, stirred_up=False) == "Muddy"  # unaffected either way


def test_wind_mph_for_band_covers_every_label_within_its_own_range():
    for lo, hi, label, _ in WIND_BANDS:
        proxy = wind_mph_for_band(label)
        assert lo <= proxy <= (hi if hi != float("inf") else proxy)
        assert wind_band(proxy)["label"] == label  # round-trips back to the same band


def test_wind_band_labels_matches_wind_bands_order():
    assert WIND_BAND_LABELS == [label for _, _, label, _ in WIND_BANDS]


def test_cloud_proxy_for_light_condition_covers_every_condition():
    for lc in LIGHT_CONDITIONS:
        proxy = cloud_proxy_for_light_condition(lc)
        assert 0.0 <= proxy <= 100.0


def test_cloud_proxy_for_light_condition_straddles_the_scoring_thresholds_correctly():
    # core.scoring._segment_score() reacts to avg_cloud >= 60 (overcast bonus)
    # and avg_cloud <= 25 (clear/bright bluebird penalty) - punch-list #10's
    # NWS-sourced sky-condition bands need to land on the correct side of
    # both, with "Partly Cloudy" deliberately in the untouched neutral middle.
    assert cloud_proxy_for_light_condition("Clear / Sunny") <= 25.0
    assert cloud_proxy_for_light_condition("Mostly Clear") <= 25.0
    assert 25.0 < cloud_proxy_for_light_condition("Partly Cloudy") < 60.0
    assert cloud_proxy_for_light_condition("Mostly Cloudy") >= 60.0
    assert cloud_proxy_for_light_condition("Overcast") >= 60.0


def test_cloud_proxy_for_light_condition_falls_back_to_neutral_for_unrecognized_value():
    # Older logged trips (pre-#10) stored values from the retired Night/
    # Crepuscular/Overcast-Diffuse-Day/Direct-High-Sun vocabulary - a lookup
    # against the current bands shouldn't raise or silently return 0.
    assert cloud_proxy_for_light_condition("Crepuscular (Dawn/Dusk)") == 40.0
    assert cloud_proxy_for_light_condition("") == 40.0
    assert cloud_proxy_for_light_condition(None) == 40.0


def test_precipitation_proxy_heavy_rain_crosses_storm_thresholds():
    total_precip, max_prob = precipitation_proxy("Heavy rain / storm")
    assert total_precip > 1.0 or max_prob > 85
    total_precip_none, max_prob_none = precipitation_proxy("None")
    assert total_precip_none == 0.0
    assert max_prob_none == 0.0


def test_precipitation_proxy_covers_every_option():
    for p in PRECIPITATION_OPTIONS:
        total_precip, max_prob = precipitation_proxy(p)
        assert total_precip >= 0.0
        assert max_prob >= 0.0


def test_stain_color_options_are_valid_lure_engine_clarities():
    for s in STAIN_COLOR_OPTIONS:
        assert s in WATER_CLARITY_OPTIONS


# --- Spot Session weather auto-fill reverse mappings -------------------------

def test_light_condition_for_cloud_pct_round_trips_each_bands_own_proxy():
    # Each band's own proxy value (see _LIGHT_CONDITION_CLOUD_PROXY) should
    # bucket back to that same band.
    for label in LIGHT_CONDITIONS:
        proxy = cloud_proxy_for_light_condition(label)
        assert light_condition_for_cloud_pct(proxy) == label


def test_light_condition_for_cloud_pct_boundaries():
    assert light_condition_for_cloud_pct(0) == "Clear / Sunny"
    assert light_condition_for_cloud_pct(12.5) == "Clear / Sunny"
    assert light_condition_for_cloud_pct(12.6) == "Mostly Clear"
    assert light_condition_for_cloud_pct(32.5) == "Mostly Clear"
    assert light_condition_for_cloud_pct(32.6) == "Partly Cloudy"
    assert light_condition_for_cloud_pct(60.0) == "Partly Cloudy"
    assert light_condition_for_cloud_pct(60.1) == "Mostly Cloudy"
    assert light_condition_for_cloud_pct(85.0) == "Mostly Cloudy"
    assert light_condition_for_cloud_pct(85.1) == "Overcast"
    assert light_condition_for_cloud_pct(100) == "Overcast"


def test_light_condition_for_cloud_pct_handles_missing_reading():
    assert light_condition_for_cloud_pct(None) in LIGHT_CONDITIONS


def test_precipitation_option_for_forecast_round_trips_each_options_own_proxy():
    for label in PRECIPITATION_OPTIONS:
        precip_in, precip_prob_pct = precipitation_proxy(label)
        assert precipitation_option_for_forecast(precip_in, precip_prob_pct) == label


def test_precipitation_option_for_forecast_either_signal_can_trigger_a_bucket():
    # A confident probability with a near-zero modeled amount should still
    # bump the bucket, and vice versa.
    assert precipitation_option_for_forecast(0.0, 90.0) == "Heavy rain / storm"
    assert precipitation_option_for_forecast(1.5, 0.0) == "Heavy rain / storm"
    assert precipitation_option_for_forecast(0.0, 0.0) == "None"


def test_precipitation_option_for_forecast_handles_missing_readings():
    assert precipitation_option_for_forecast(None, None) == "None"


def test_wind_direction_for_degrees_compass_points():
    assert wind_direction_for_degrees(0) == "N"
    assert wind_direction_for_degrees(360) == "N"
    assert wind_direction_for_degrees(45) == "NE"
    assert wind_direction_for_degrees(90) == "E"
    assert wind_direction_for_degrees(135) == "SE"
    assert wind_direction_for_degrees(180) == "S"
    assert wind_direction_for_degrees(225) == "SW"
    assert wind_direction_for_degrees(270) == "W"
    assert wind_direction_for_degrees(315) == "NW"


def test_wind_direction_for_degrees_boundary_wraps_correctly():
    assert wind_direction_for_degrees(22.4) == "N"
    assert wind_direction_for_degrees(22.6) == "NE"
    assert wind_direction_for_degrees(348.0) == "N"


def test_wind_direction_for_degrees_handles_missing_reading():
    assert wind_direction_for_degrees(None) == "Variable"


def test_wind_direction_for_degrees_only_returns_documented_compass_points():
    for deg in range(0, 360, 5):
        assert wind_direction_for_degrees(deg) in WIND_DIRECTIONS
