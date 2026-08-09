from core.lures import WATER_CLARITY_OPTIONS
from core.onwater import (
    LIGHT_CONDITIONS, PRECIPITATION_OPTIONS, STAIN_COLOR_OPTIONS,
    cloud_proxy_for_light_condition, precipitation_proxy, resolve_water_clarity,
    visibility_band, water_temp_band, wind_band,
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


def test_cloud_proxy_for_light_condition_covers_every_condition():
    for lc in LIGHT_CONDITIONS:
        proxy = cloud_proxy_for_light_condition(lc)
        assert 0.0 <= proxy <= 100.0
    assert cloud_proxy_for_light_condition("Overcast / Diffuse Day") >= 60.0
    assert cloud_proxy_for_light_condition("Direct High Sun") < 60.0


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
