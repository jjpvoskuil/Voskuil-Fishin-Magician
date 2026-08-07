"""
Lure/tackle inventory storage + optional git commit-back.

Mirrors core/storage.py's trip-log pattern: inventory rows live in
data/lure_inventory.csv inside the repo, and any photos the user manually
uploads or takes live as image files in data/lure_images/. When a
GITHUB_TOKEN is configured, changes are committed and pushed back to the
repo (via core.storage.commit_and_push) so the inventory survives
Streamlit Cloud restarts/redeploys; without one it still works, just for
the current session.

Two ways a photo gets attached to an item:
- image_url: a link to an existing product photo (e.g. the vendor's own
  CDN, used for items seeded from an order-history import). Not stored in
  the repo, just linked at render time - these are the vendor's own
  copyrighted product photography, and displaying via a link avoids
  keeping a redistributed copy, same reasoning already applied elsewhere
  in this app to third-party map/chart data.
- image_filename: a photo the user uploaded or took themselves, stored
  under data/lure_images/ and committed to the repo like any other
  user-owned data (same treatment as Quickdraw survey CSVs).

The `category` field (added when the 7-Day Forecast/Lake Map ownership
feature was built) is a free-form string that, when it matches one of
core.lures.LURE_PROFILES' keys, lets the recommendation engine
(core.lures.recommend()) know you already own tackle that fits a given
lure suggestion. It's intentionally just a plain string column here (not
an enum/foreign key) so this module stays independent of core.lures - the
matching happens on the lures.py side via
core.lures._group_owned_by_category(). Blank/unrecognized values just mean
"not matched to a forecast category," not an error.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = REPO_ROOT / "data" / "lure_inventory.csv"
IMAGES_DIR = REPO_ROOT / "data" / "lure_images"

FIELDNAMES = [
    "item_id", "added_at", "updated_at", "brand", "description", "category", "sku",
    "price", "quantity", "image_url", "image_filename", "source",
]


@dataclass
class LureItem:
    brand: str
    description: str
    price: Optional[float]
    quantity: int
    category: str = ""  # one of core.lures.LURE_PROFILES' keys, or "" if not (yet) categorized
    sku: str = ""
    image_url: str = ""
    image_filename: str = ""
    source: str = "Manual"
    item_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    added_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_row(self) -> dict:
        d = asdict(self)
        return {k: d.get(k, "") for k in FIELDNAMES}


def ensure_inventory_exists(path: Path = INVENTORY_PATH, images_dir: Path = IMAGES_DIR):
    path.parent.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def read_all_items(path: Path = INVENTORY_PATH) -> list:
    ensure_inventory_exists(path)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append_item(item: LureItem, path: Path = INVENTORY_PATH):
    ensure_inventory_exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(item.to_row())


def _write_rows(rows: list, path: Path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def update_item(item_id: str, path: Path = INVENTORY_PATH, **changes) -> bool:
    """Update fields on an existing item by item_id. Returns True if found."""
    rows = read_all_items(path)
    found = False
    for row in rows:
        if row["item_id"] == item_id:
            row.update({k: v for k, v in changes.items() if k in FIELDNAMES})
            row["updated_at"] = datetime.utcnow().isoformat()
            found = True
            break
    if found:
        _write_rows(rows, path)
    return found


def delete_item(item_id: str, path: Path = INVENTORY_PATH, images_dir: Path = IMAGES_DIR) -> bool:
    rows = read_all_items(path)
    remaining = [r for r in rows if r["item_id"] != item_id]
    deleted = len(remaining) != len(rows)
    if deleted:
        removed_img = next((r["image_filename"] for r in rows if r["item_id"] == item_id and r["image_filename"]), "")
        _write_rows(remaining, path)
        if removed_img:
            img_path = images_dir / removed_img
            if img_path.exists():
                img_path.unlink()
    return deleted


def save_image(item_id: str, file_bytes: bytes, extension: str, images_dir: Path = IMAGES_DIR) -> str:
    """Write an uploaded/captured photo to the images dir and return its filename."""
    images_dir.mkdir(parents=True, exist_ok=True)
    extension = (extension or "jpg").lower().lstrip(".") or "jpg"
    filename = f"{item_id}.{extension}"
    with open(images_dir / filename, "wb") as f:
        f.write(file_bytes)
    return filename
