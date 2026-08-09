from core.lures import FORAGE_OPTIONS
from core.activity_log import (
    OTHER_LABEL, DEPTH_MODES, FISH_ACTIVITY_OPTIONS, FORAGE_ACTIVITY_OPTIONS,
    RETRIEVE_SPEED_OPTIONS, RETRIEVE_STYLE_OPTIONS,
    inventory_item_label, lure_can_take_trailer, lure_picker_options,
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
