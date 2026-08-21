import csv

from core.lure_inventory import (
    FIELDNAMES, LureItem, append_item, delete_item, ensure_inventory_exists,
    image_data_uri_or_url, read_all_items, resolve_image_source, save_image, update_item,
)


def test_empty_inventory_returns_empty_list(tmp_path):
    path = tmp_path / "inv.csv"
    assert read_all_items(path) == []


def test_append_and_read_item(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Strike King", description="Test crankbait", price=8.99, quantity=2)
    append_item(item, path)
    rows = read_all_items(path)
    assert len(rows) == 1
    assert rows[0]["brand"] == "Strike King"
    assert rows[0]["description"] == "Test crankbait"
    assert rows[0]["price"] == "8.99"
    assert rows[0]["quantity"] == "2"
    assert rows[0]["item_id"] == item.item_id


def test_append_and_read_item_with_category(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Strike King", description="Test crankbait", price=8.99, quantity=2,
                     category="squarebill_crankbait")
    append_item(item, path)
    rows = read_all_items(path)
    assert rows[0]["category"] == "squarebill_crankbait"


def test_item_defaults_to_uncategorized(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="No Name", description="Mystery bait", price=1.0, quantity=1)
    append_item(item, path)
    rows = read_all_items(path)
    assert rows[0]["category"] == ""


def test_item_package_qty_defaults_to_one(tmp_path):
    # Punch-list #43: a lure with no package_qty specified is assumed to be
    # sold individually, same reasoning as the pre-#43 data (see the
    # migration test below).
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Zoom", description="Trick Worm", price=4.99, quantity=3)
    append_item(item, path)
    rows = read_all_items(path)
    assert rows[0]["package_qty"] == "1"


def test_item_package_qty_can_be_set_explicitly(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(
        brand="Strike King", description="KVD Perfect Plastics - 8-pack", price=6.99,
        quantity=1, package_qty=8,
    )
    append_item(item, path)
    rows = read_all_items(path)
    assert rows[0]["package_qty"] == "8"


def test_update_item_changes_package_qty(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Zoom", description="Trick Worm", price=4.99, quantity=1)
    append_item(item, path)

    found = update_item(item.item_id, path, package_qty=6)
    assert found is True
    rows = read_all_items(path)
    assert rows[0]["package_qty"] == "6"


def test_ensure_inventory_exists_migrates_a_csv_written_before_package_qty(tmp_path):
    # Punch-list #43: data/lure_inventory.csv already had real rows (from
    # the Cabela's order-history import and manual adds) written before
    # this column existed - ensure_inventory_exists() has to rewrite that
    # header and back-fill package_qty=1 on every existing row, the same
    # approach used when the `category` column was added, rather than
    # silently dropping/misaligning those rows.
    path = tmp_path / "inv.csv"
    old_fieldnames = [f for f in FIELDNAMES if f != "package_qty"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fieldnames)
        writer.writeheader()
        writer.writerow({
            "item_id": "abc123", "added_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
            "brand": "Strike King", "description": "Old row from before package_qty existed",
            "category": "squarebill_crankbait", "sku": "9999", "price": "5.99", "quantity": "2",
            "image_url": "", "image_filename": "", "source": "Manual",
        })

    ensure_inventory_exists(path)

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["package_qty"] == "1"
    # Nothing else about the pre-existing row should have changed.
    assert rows[0]["brand"] == "Strike King"
    assert rows[0]["quantity"] == "2"
    assert rows[0]["sku"] == "9999"


def test_ensure_inventory_exists_is_a_no_op_on_an_already_migrated_file(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Zoom", description="Trick Worm", price=4.99, quantity=1, package_qty=4)
    append_item(item, path)

    ensure_inventory_exists(path)  # should not touch the file a second time

    rows = read_all_items(path)
    assert len(rows) == 1
    assert rows[0]["package_qty"] == "4"


def test_update_item_changes_category(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Strike King", description="Swim jig", price=7.99, quantity=1)
    append_item(item, path)

    found = update_item(item.item_id, path, category="swim_jig")
    assert found is True
    rows = read_all_items(path)
    assert rows[0]["category"] == "swim_jig"


def test_update_item_changes_quantity_and_price(tmp_path):
    path = tmp_path / "inv.csv"
    item = LureItem(brand="Zoom", description="Worm", price=5.49, quantity=1)
    append_item(item, path)

    found = update_item(item.item_id, path, quantity=5, price=4.99)
    assert found is True

    rows = read_all_items(path)
    assert rows[0]["quantity"] == "5"
    assert rows[0]["price"] == "4.99"


def test_update_item_missing_id_returns_false(tmp_path):
    path = tmp_path / "inv.csv"
    assert update_item("nonexistent", path, quantity=9) is False


def test_delete_item_removes_row(tmp_path):
    path = tmp_path / "inv.csv"
    item1 = LureItem(brand="Rapala", description="Jerkbait", price=10.99, quantity=1)
    item2 = LureItem(brand="Z-Man", description="Jighead", price=6.99, quantity=2)
    append_item(item1, path)
    append_item(item2, path)

    assert delete_item(item1.item_id, path) is True
    rows = read_all_items(path)
    assert len(rows) == 1
    assert rows[0]["item_id"] == item2.item_id


def test_delete_item_missing_id_returns_false(tmp_path):
    path = tmp_path / "inv.csv"
    assert delete_item("nonexistent", path) is False


def test_delete_item_removes_associated_local_image(tmp_path):
    path = tmp_path / "inv.csv"
    images_dir = tmp_path / "images"
    item = LureItem(brand="Strike King", description="Swimjig", price=13.99, quantity=1)
    filename = save_image(item.item_id, b"fake-bytes", "jpg", images_dir)
    item.image_filename = filename
    append_item(item, path)

    img_path = images_dir / filename
    assert img_path.exists()

    delete_item(item.item_id, path, images_dir)
    assert not img_path.exists()


def test_save_image_writes_file_and_returns_filename(tmp_path):
    images_dir = tmp_path / "images"
    filename = save_image("abc123", b"\x89PNG-fake", "PNG", images_dir)
    assert filename == "abc123.png"
    assert (images_dir / filename).read_bytes() == b"\x89PNG-fake"


def test_save_image_defaults_to_jpg_when_no_extension(tmp_path):
    images_dir = tmp_path / "images"
    filename = save_image("xyz", b"data", "", images_dir)
    assert filename == "xyz.jpg"


def test_resolve_image_source_prefers_local_file_over_url(tmp_path):
    images_dir = tmp_path / "images"
    filename = save_image("abc", b"fake-bytes", "jpg", images_dir)
    item = {"image_filename": filename, "image_url": "https://example.com/product.jpg"}
    assert resolve_image_source(item, images_dir) == str(images_dir / filename)


def test_resolve_image_source_falls_back_to_url_when_local_missing(tmp_path):
    images_dir = tmp_path / "images"
    item = {"image_filename": "does_not_exist.jpg", "image_url": "https://example.com/product.jpg"}
    assert resolve_image_source(item, images_dir) == "https://example.com/product.jpg"


def test_resolve_image_source_none_when_no_photo(tmp_path):
    images_dir = tmp_path / "images"
    item = {"image_filename": "", "image_url": ""}
    assert resolve_image_source(item, images_dir) is None


def test_image_data_uri_or_url_passes_through_remote_urls_unchanged():
    url = "https://example.com/product.jpg"
    assert image_data_uri_or_url(url) == url


def test_image_data_uri_or_url_encodes_local_file_as_data_uri(tmp_path):
    images_dir = tmp_path / "images"
    filename = save_image("abc", b"\x89PNG-fake-bytes", "png", images_dir)
    local_path = str(images_dir / filename)
    result = image_data_uri_or_url(local_path)
    assert result.startswith("data:image/png;base64,")
    import base64
    encoded_part = result.split(",", 1)[1]
    assert base64.b64decode(encoded_part) == b"\x89PNG-fake-bytes"


def test_image_data_uri_or_url_none_for_missing_local_file(tmp_path):
    assert image_data_uri_or_url(str(tmp_path / "nope.jpg")) is None


def test_image_data_uri_or_url_none_for_empty_input():
    assert image_data_uri_or_url("") is None
    assert image_data_uri_or_url(None) is None
