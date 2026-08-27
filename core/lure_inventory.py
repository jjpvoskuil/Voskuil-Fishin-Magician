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

The `package_qty` field (punch-list #43) is a purely informational count of
how many individual lures come in one retail package (e.g. 8 for an
"8-pack", 1 - the default - for something sold as a single lure). It's
intentionally NOT multiplied into `quantity` anywhere in this app -
`quantity` keeps meaning exactly what it always has (however many units
this row represents on hand), and `package_qty` just lets an angler note
what size package that came in, so a single "6-pack" bought once can be
told apart from six lures bought individually. Every existing row was
backfilled to `package_qty=1` (see `_migrate_add_package_qty_column()`)
since prior to this field existing, `quantity` was always tracked as
individual-unit counts, not package counts.
"""
from __future__ import annotations
import base64
import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

from core.storage import data_write_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = REPO_ROOT / "data" / "lure_inventory.csv"
IMAGES_DIR = REPO_ROOT / "data" / "lure_images"

FIELDNAMES = [
    "item_id", "added_at", "updated_at", "brand", "description", "category", "sku",
    "price", "quantity", "package_qty", "image_url", "image_filename", "source",
]


@dataclass
class LureItem:
    brand: str
    description: str
    price: Optional[float]
    quantity: int
    category: str = ""  # one of core.lures.LURE_PROFILES' keys, or "" if not (yet) categorized
    package_qty: int = 1  # how many individual lures come in one package - see module docstring
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


def _migrate_add_package_qty_column(path: Path):
    """One-time migration (punch-list #43): back-fills `package_qty=1` on
    every row of an inventory CSV written before that column existed, and
    rewrites the header to match. Same approach used when the `category`
    column was added - a plain rewrite, since this file has no flexible/
    JSON column (unlike core.storage.TripEntry's conditions_json) to tuck
    a new field into without a header change. Safe to call on a file that
    already has the column (no-op) or doesn't exist yet (no-op - callers
    only invoke this after confirming the file exists)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        existing_fieldnames = reader.fieldnames or []
        rows = list(reader)
    if "package_qty" in existing_fieldnames:
        return
    for row in rows:
        row["package_qty"] = 1
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})


def ensure_inventory_exists(path: Path = INVENTORY_PATH, images_dir: Path = IMAGES_DIR):
    path.parent.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
    else:
        _migrate_add_package_qty_column(path)


def read_all_items(path: Path = INVENTORY_PATH) -> list:
    ensure_inventory_exists(path)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def append_item(item: LureItem, path: Path = INVENTORY_PATH):
    # Punch-list #68: see core.storage.data_write_lock's docstring - the
    # same unlocked-concurrent-write mechanism that corrupted trip_log.csv
    # applies to every git-backed CSV this app writes, this one included.
    with data_write_lock():
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
    """Update fields on an existing item by item_id. Returns True if found.

    Punch-list #68: read-modify-write now guarded by data_write_lock() -
    see core.storage's docstring for why."""
    with data_write_lock():
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
    """Punch-list #68: read-modify-write now guarded by data_write_lock() -
    see core.storage's docstring for why."""
    with data_write_lock():
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


def resolve_image_source(item: dict, images_dir: Path = IMAGES_DIR) -> Optional[str]:
    """Given an inventory row/dict (with image_filename/image_url keys), return
    whatever st.image() should be pointed at: a local file path if the user's
    own uploaded/captured photo exists on disk, else the vendor's linked CDN
    URL, else None if there's no photo at all. Shared by the Tackle Box
    page and the forecast/map "owned lure" rendering (core/ui.py) so both
    follow the exact same local-photo-wins-over-link rule."""
    filename = item.get("image_filename")
    if filename:
        path = images_dir / filename
        if path.exists():
            return str(path)
    return item.get("image_url") or None


_MIME_BY_EXTENSION = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}


def image_data_uri_or_url(image_source: Optional[str]) -> Optional[str]:
    """Turn whatever resolve_image_source() returned into something directly
    usable as an HTML <img> tag's src attribute (core.ui's fixed-size square
    thumbnail rendering needs raw HTML/CSS to crop-and-fit consistently,
    since st.image() has no crop-to-square option). A remote vendor URL is
    passed through unchanged - the browser fetches it itself, exactly like
    st.image() would, so this never adds a new server-side network call. A
    local file path can't be reached by the browser directly (it only knows
    the Streamlit server's rendered page, not its filesystem), so it's
    base64-encoded into an inline `data:` URI instead - still just reading
    bytes we already have on disk, no extra network or image-processing
    dependency. Returns None for a falsy/missing source or an unreadable
    local file."""
    if not image_source:
        return None
    if image_source.startswith("http://") or image_source.startswith("https://"):
        return image_source
    path = Path(image_source)
    if not path.exists() or not path.is_file():
        return None
    extension = path.suffix.lstrip(".").lower()
    mime = _MIME_BY_EXTENSION.get(extension, "jpeg")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"
