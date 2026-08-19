import csv
import tempfile
from pathlib import Path

from core.cabelas_picks_cache import get_cached_picks


def _tmp_cache_path() -> Path:
    d = tempfile.mkdtemp()
    return Path(d) / "cabelas_picks_cache.csv"


def _write_cache(path: Path, rows: list):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["category", "rank", "sku", "brand", "description", "price", "image_url", "captured_at"]
        )
        writer.writeheader()
        writer.writerows(rows)


def test_get_cached_picks_returns_empty_list_when_file_is_missing():
    path = _tmp_cache_path()
    assert not path.exists()
    assert get_cached_picks("Squarebill Crankbait", path) == []


def test_get_cached_picks_returns_empty_list_for_unrecognized_category():
    path = _tmp_cache_path()
    _write_cache(path, [
        {"category": "Squarebill Crankbait", "rank": 1, "sku": "111", "brand": "BOOYAH",
         "description": "XCS Squarebill", "price": "6.99", "image_url": "https://example.com/1.json",
         "captured_at": "2026-08-19T01:09:50"},
    ])
    assert get_cached_picks("Some Lure Nobody Recommends", path) == []


def test_get_cached_picks_returns_picks_sorted_by_rank_in_the_mapped_shape():
    path = _tmp_cache_path()
    _write_cache(path, [
        {"category": "Squarebill Crankbait", "rank": 2, "sku": "222", "brand": "BOOYAH",
         "description": "Citrus Shad", "price": "6.99", "image_url": "https://example.com/2.json",
         "captured_at": "2026-08-19T01:09:50"},
        {"category": "Squarebill Crankbait", "rank": 1, "sku": "111", "brand": "BOOYAH",
         "description": "Tennessee Special", "price": "6.99", "image_url": "https://example.com/1.json",
         "captured_at": "2026-08-19T01:09:50"},
    ])
    picks = get_cached_picks("Squarebill Crankbait", path)
    assert len(picks) == 2
    # Rank 1 first, regardless of file order.
    assert picks[0] == {
        "sku": "111", "brand": "BOOYAH", "description": "Tennessee Special",
        "price": 6.99, "image_url": "https://example.com/1.json", "categories": [],
    }
    assert picks[1]["sku"] == "222"


def test_get_cached_picks_skips_rows_with_unparseable_price_or_rank():
    path = _tmp_cache_path()
    _write_cache(path, [
        {"category": "Squarebill Crankbait", "rank": "not-a-number", "sku": "111", "brand": "BOOYAH",
         "description": "Bad rank", "price": "6.99", "image_url": "", "captured_at": ""},
        {"category": "Squarebill Crankbait", "rank": 1, "sku": "222", "brand": "BOOYAH",
         "description": "Bad price", "price": "not-a-number", "image_url": "", "captured_at": ""},
        {"category": "Squarebill Crankbait", "rank": 1, "sku": "333", "brand": "BOOYAH",
         "description": "Fine", "price": "6.99", "image_url": "", "captured_at": ""},
    ])
    picks = get_cached_picks("Squarebill Crankbait", path)
    assert [p["sku"] for p in picks] == ["333"]


def test_get_cached_picks_handles_blank_query():
    path = _tmp_cache_path()
    assert get_cached_picks("", path) == []
    assert get_cached_picks(None, path) == []


def test_real_cache_file_has_two_picks_for_every_lure_profile_category():
    # Guards against the shipped data/cabelas_picks_cache.csv silently
    # losing coverage for a category (e.g. a future core.lures.LURE_PROFILES
    # addition not getting a matching row) - every category this app's
    # recommendation engine can actually produce should have a real
    # fallback available.
    from core.lures import LURE_PROFILES

    for profile in LURE_PROFILES.values():
        picks = get_cached_picks(profile["name"])
        assert len(picks) == 2, f"expected 2 cached picks for {profile['name']!r}, got {len(picks)}"
        for pick in picks:
            assert pick["sku"], profile["name"]
            assert pick["description"], profile["name"]
