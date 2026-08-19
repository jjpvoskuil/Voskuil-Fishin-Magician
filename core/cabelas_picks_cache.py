"""
Punch-list #22's safety net for punch-list #8's "not in your inventory"
Cabela's suggestions (see core.ui.render_cabelas_suggestions and
core.appstate.get_cabelas_suggestions).

core.cabelas_lookup.search_lures() calls Cabela's/Coveo live - confirmed
working from a real browser, but confirmed *failing* from this app's own
deployed server (SESSION_NOTES.md punch-list #21/#22 entries have the full
investigation). core/cabelas_lookup.py now also tries impersonating a real
browser's TLS fingerprint (punch-list #22) to work around that, but there's
no guarantee that fixes it - Cabela's/Coveo could just as easily be
blocking by IP/network reputation instead, which no amount of header or
TLS spoofing gets around.

This module is the fallback for when the live lookup keeps failing anyway:
a small, curated data/cabelas_picks_cache.csv with up to 2 real Cabela's
products per lure category, captured via a real browser the same way the
punch-list #21/#22 investigation confirmed the live lookup itself still
works. Unlike the live lookup, this only covers a fixed, closed vocabulary
- the 20 category names in core.lures.LURE_PROFILES (that's literally
every `LureBlock.name` this app's recommendation engine ever produces) -
not arbitrary free text, so it's meaningless for the Lure Inventory page's
"Scan a lure" flow (core.cabelas_lookup.search_lures() is called directly
there, by a vision-model-guessed query that isn't from this fixed
vocabulary, and intentionally doesn't use this fallback - that flow
already has its own fallback, the manual "Add a lure" form).

Not live: prices/stock can go stale between refreshes of this file (there
is no automatic refresh - a future session re-running the same browser-
based capture and overwriting data/cabelas_picks_cache.csv is how this
gets updated). core.ui.render_cabelas_suggestions() shows a note whenever
this fallback (rather than a live result) is what's actually on screen, so
the angler isn't misled into thinking it's a live price/availability check.
"""
from __future__ import annotations
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data" / "cabelas_picks_cache.csv"


def _load_all(path: Path = CACHE_PATH) -> dict:
    """Reads the whole cache file and groups rows by category, each list
    already sorted by `rank`. Returns {} if the file is missing (e.g. a
    fresh checkout before it's ever been captured) rather than raising -
    same fails-soft contract as the rest of this Cabela's integration."""
    if not path.exists():
        return {}
    grouped: dict = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            category = (row.get("category") or "").strip()
            if not category:
                continue
            try:
                rank = int(row.get("rank") or 0)
                price = float(row["price"]) if row.get("price") not in (None, "") else None
            except (TypeError, ValueError):
                continue
            grouped.setdefault(category, []).append({
                "rank": rank,
                "sku": (row.get("sku") or "").strip(),
                "brand": (row.get("brand") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "price": price,
                "image_url": (row.get("image_url") or "").strip(),
                "categories": [],
            })
    for rows in grouped.values():
        rows.sort(key=lambda r: r["rank"])
    return grouped


def get_cached_picks(category: str, path: Path = CACHE_PATH) -> list:
    """Up to 2 curated picks for `category` (must match a
    core.lures.LURE_PROFILES `name` exactly - this is an exact-match
    lookup, not a text search), in the same dict shape
    core.cabelas_lookup.map_result() produces (sku/brand/description/
    price/image_url/categories) so callers can treat live and cached
    results identically. Returns [] for an unrecognized category or a
    missing/empty cache file - never raises."""
    category = (category or "").strip()
    if not category:
        return []
    rows = _load_all(path).get(category, [])
    return [{k: v for k, v in row.items() if k != "rank"} for row in rows]
