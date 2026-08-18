from core.lures import FORAGE_OPTIONS
from core.activity_log import (
    OTHER_LABEL, DEPTH_MODES, FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS,
    RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
    inventory_item_label, lure_can_take_trailer, lure_picker_options,
    format_weight_lb_oz, parse_weight_lb_oz,
)


def _item(**kwargs):
    base = {"item_id": "abc123", "brand": "Strike King", "description": "Test Lure", "category": ""}
    base.update(kwargs)
    return base


def test_inventory_item_label_combines_brand_and_description():
    assert inventory_item_label(_item()) == "Strike King - Test Lure"


def test_inventory_item_label_falls_back_when_brand_or_description_missing():
    assert inventory_item_label(_item(brand="", description="Just A Description")) == "Just A Description"
    assert inventory_item_label(_item(brand="OnlyBrand", description="")) == "OnlyBrand"
    assert inventory_item_label({"item_id": "xyz"}) == "xyz"


def test_lure_picker_options_starts_with_other_label():
    items = [_item(item_id="1"), _item(item_id="2", description="Second Lure")]
    labels, out_items = lure_picker_options(items)
    assert labels[0] == OTHER_LABEL
    assert out_items[0] is None
    assert len(labels) == len(out_items) == len(items) + 1
    assert out_items[1:] == items


def test_lure_picker_options_handles_empty_inventory():
    labels, out_items = lure_picker_options([])
    assert labels == [OTHER_LABEL]
    assert out_items == [None]


def test_lure_can_take_trailer_true_for_manual_entry_and_unknown_category():
    assert lure_can_take_trailer(None) is True
    assert lure_can_take_trailer(_item(category="Not categorized / other")) is True
    assert lure_can_take_trailer(_item(category="")) is True


def test_lure_can_take_trailer_true_for_a_category_with_a_trailer_profile():
    # football_jig and chatterbait both carry a real "trailer" colors dict.
    assert lure_can_take_trailer(_item(category="football_jig")) is True
    assert lure_can_take_trailer(_item(category="chatterbait")) is True


def test_lure_can_take_trailer_false_for_a_category_with_no_trailer():
    # weightless_soft_plastic and finesse_shaky_head are explicitly trailer=None.
    assert lure_can_take_trailer(_item(category="weightless_soft_plastic")) is False
    assert lure_can_take_trailer(_item(category="finesse_shaky_head")) is False


def test_log_vocabulary_lists_are_nonempty_and_string_only():
    for options in (DEPTH_MODES, FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS,
                    RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS):
        assert len(options) >= 2
        assert all(isinstance(o, str) and o for o in options)
        assert len(set(options)) == len(options)  # no duplicates


def test_forage_options_still_importable_for_the_log_forms_forage_multiselect():
    # activity_log.py doesn't define its own forage vocabulary - it reuses
    # core.lures.FORAGE_OPTIONS for both the conditions form and the log form.
    assert len(FORAGE_OPTIONS) > 0


# --- format_weight_lb_oz / parse_weight_lb_oz --------------------------------

def test_format_weight_lb_oz_whole_pounds():
    assert format_weight_lb_oz(3.0) == "3 lb"
    assert format_weight_lb_oz(1.0) == "1 lb"


def test_format_weight_lb_oz_pounds_and_ounces():
    assert format_weight_lb_oz(3.5) == "3 lb 8 oz"
    assert format_weight_lb_oz(3.53) == "3 lb 8 oz"  # rounds to nearest ounce


def test_format_weight_lb_oz_under_one_pound_shows_ounces_only():
    assert format_weight_lb_oz(0.5) == "8 oz"
    assert format_weight_lb_oz(0.0625) == "1 oz"


def test_format_weight_lb_oz_rounds_up_to_next_pound_at_16_oz():
    # 3.99 lb rounds to 16 oz, which should carry over to a whole 4 lb, not
    # display as "3 lb 16 oz".
    assert format_weight_lb_oz(3.99) == "4 lb"


def test_format_weight_lb_oz_blank_for_none_zero_or_unparseable():
    assert format_weight_lb_oz(None) == ""
    assert format_weight_lb_oz(0) == ""
    assert format_weight_lb_oz("") == ""
    assert format_weight_lb_oz(float("nan")) == ""


def test_parse_weight_lb_oz_full_format():
    assert parse_weight_lb_oz("3 lb 8 oz") == 3.5
    assert parse_weight_lb_oz("3lb8oz") == 3.5


def test_parse_weight_lb_oz_lb_only_or_oz_only():
    assert parse_weight_lb_oz("4 lb") == 4.0
    assert parse_weight_lb_oz("8 oz") == 0.5


def test_parse_weight_lb_oz_plain_decimal_fallback():
    assert parse_weight_lb_oz("3.5") == 3.5
    assert parse_weight_lb_oz("2") == 2.0


def test_parse_weight_lb_oz_dash_separated_format():
    # The Spot Session "Add fish" form's own manual weight field (punch-list
    # item #2) uses this "lb - oz" shorthand, dash pre-filled as "0 - 0".
    assert parse_weight_lb_oz("3 - 8") == 3.5
    assert parse_weight_lb_oz("3-8") == 3.5
    assert parse_weight_lb_oz("0 - 0") == 0.0
    assert parse_weight_lb_oz("3 8") == 3.5  # space-separated, no dash, same idea


def test_parse_weight_lb_oz_dash_format_rejects_invalid_ounces():
    # 20 isn't a valid oz value (>= 16) - falls through to the plain-decimal
    # fallback, which can't parse "3 - 20" either, so this is None rather
    # than silently misinterpreting it.
    assert parse_weight_lb_oz("3 - 20") is None


def test_parse_weight_lb_oz_blank_or_unparseable_returns_none():
    assert parse_weight_lb_oz(None) is None
    assert parse_weight_lb_oz("") is None
    assert parse_weight_lb_oz("   ") is None
    assert parse_weight_lb_oz("not a weight") is None


def test_format_and_parse_weight_round_trip_on_whole_ounces():
    for lb in (0.0625, 0.5, 1.0, 3.5, 4.0, 7.9375):
        assert parse_weight_lb_oz(format_weight_lb_oz(lb)) == lb
