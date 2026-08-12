"""
Looks up real product data on Cabela's, by text query, for the Lure
Inventory page's "Scan a lure" flow (see pages/5_Lure_Inventory.py and
core/lure_vision.py).

Cabela's search results are populated client-side by JavaScript, so a plain
HTML fetch of a search-results page wouldn't see any products - this
instead calls the same two JSON endpoints the site's own search box calls
under the hood:

1. GET a short-lived, anonymous, read-only search token from Cabela's own
   site (the same token any visitor's browser gets, logged in or not -
   confirmed via the site's own network traffic, not a documented/public
   API, so there's no login or account involved).
2. POST that token to Coveo's public search REST API (the third-party
   search platform Cabela's/Bass Pro's site search runs on) with a plain
   text query, and get back real product data - brand, name, price, SKU,
   category, photo - as JSON.

This is best-effort, not a guaranteed-stable integration: it depends on
Cabela's continuing to serve their public site search via these same
endpoints. If Cabela's changes their search implementation or starts
blocking non-browser traffic, these calls will start failing - every
function here fails soft (returns [] rather than raising), so a lookup
failure just means the "Scan a lure" flow falls back to the manual "Add a
lure" form that already exists on that page.
"""
from __future__ import annotations
import time
import requests

TOKEN_URL = "https://www.cabelas.com/api/v2/10651/prod/coveo/getCoveoToken"
SEARCH_URL = "https://platform.cloud.coveo.com/rest/search/v2"
COVEO_ORG_ID = "bassproshopsproductionl92epymr"

# A real desktop-browser User-Agent - both endpoints sit behind Cabela's/
# Coveo's normal bot-mitigation, and an obvious non-browser UA (e.g.
# Python's default "python-requests/...") is the kind of thing that gets
# filtered before the request is even considered.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}
REQUEST_TIMEOUT_S = 10

# In-memory token cache (per Streamlit server process) - the token itself is
# valid for hours, so there's no need to fetch a new one on every search;
# this just avoids one extra round-trip per keystroke/search.
_TOKEN_TTL_S = 60 * 30
_token_cache = {"token": None, "fetched_at": 0.0}


def _get_token() -> str | None:
    now = time.time()
    cached = _token_cache["token"]
    if cached and (now - _token_cache["fetched_at"]) < _TOKEN_TTL_S:
        return cached
    try:
        resp = requests.get(TOKEN_URL, headers=_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        token = resp.json().get("token")
    except Exception:
        return None
    if token:
        _token_cache["token"] = token
        _token_cache["fetched_at"] = now
    return token


def _first_number(*values):
    for v in values:
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def map_result(raw: dict) -> dict:
    """Turn one Coveo result's `raw` fields into the shape the Lure
    Inventory page works with (a subset of core.lure_inventory.LureItem's
    fields, plus `categories` for core.lures.guess_category_from_text()).
    A pure function (no I/O) so it's unit-testable against fixture data
    without hitting the network."""
    return {
        "sku": str(raw.get("sku") or "").strip(),
        "brand": (raw.get("ec_brand") or raw.get("brand") or "").strip(),
        "description": (raw.get("ec_name") or raw.get("ec_shortdesc") or "").strip(),
        "price": _first_number(raw.get("ec_price"), raw.get("offerprice"), raw.get("listprice")),
        "image_url": raw.get("fullimage") or raw.get("thumbnail") or "",
        "categories": raw.get("ec_category") or [],
    }


def search_lures(query: str, num_results: int = 8) -> list:
    """Search Cabela's for products matching `query`. Returns a list of
    dicts (sku/brand/description/price/image_url/categories), best matches
    first - or [] if the query is empty or the lookup fails for any reason
    (network error, expired/rejected token, unexpected response shape).
    Callers should treat [] the same as "no matches found", not as an
    error to surface differently."""
    query = (query or "").strip()
    if not query:
        return []
    token = _get_token()
    if not token:
        return []
    try:
        resp = requests.post(
            SEARCH_URL,
            params={"organizationId": COVEO_ORG_ID},
            headers={
                **_BROWSER_HEADERS,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"q": query, "numberOfResults": num_results, "firstResult": 0},
            timeout=REQUEST_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    results = data.get("results") or []
    mapped = [map_result(r.get("raw") or {}) for r in results]
    # A result with no SKU or no name isn't a usable product match.
    return [m for m in mapped if m["sku"] and m["description"]]
