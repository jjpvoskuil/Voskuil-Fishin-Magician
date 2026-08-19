"""
Looks up real product data on Cabela's, by text query. Originally built for
the Lure Inventory page's "Scan a lure" flow (see pages/5_Lure_Inventory.py
and core/lure_vision.py); also used by core.ui.render_lure_block (via
core.appstate.get_cabelas_suggestions, which adds caching) to suggest up to
2 real products worth buying whenever a recommended lure category has
nothing color-matched in the angler's own tackle-box inventory - punch-list
#8.

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
lure" form that already exists on that page (core.appstate.
get_cabelas_suggestions layers a curated fallback cache on top of this for
punch-list #8's lure-block suggestions specifically - see
core/cabelas_picks_cache.py).

Punch-list #21/#22: confirmed by calling these same two endpoints directly
from a real browser that they still work exactly as this module expects -
but this app's own deployed server-side calls were coming back empty in
production. Since a plain `requests` call with a browser-like User-Agent
still failed, the next-most-likely cause is TLS/network-level
fingerprinting (bot-mitigation systems commonly check the actual TLS
handshake, not just header content - a `requests`/urllib3 handshake looks
nothing like a real Chrome one no matter what headers are set). This
module now uses `curl_cffi` instead of the plain `requests` library
specifically because it can impersonate a real browser's TLS/JA3
fingerprint (`impersonate=IMPERSONATE_BROWSER` below), not just its
headers - curl_cffi's `requests`-compatible API (get/post, headers, json,
timeout, .raise_for_status(), .json()) is a near drop-in replacement, so
the rest of this module's logic is unchanged. This is still a best-effort
attempt, not a guarantee: if Cabela's/Coveo's blocking is actually IP- or
network-reputation-based (e.g. blocking Streamlit Community Cloud's own
IP ranges outright) rather than fingerprint-based, this change won't fix
it - hence the curated fallback cache existing as a safety net regardless
of whether this works.
"""
from __future__ import annotations
import time
from urllib.parse import quote_plus
from curl_cffi import requests

# A specific recent Chrome version curl_cffi knows how to impersonate the
# TLS/JA3 fingerprint of - kept in sync with the Chrome version claimed in
# _BROWSER_HEADERS' User-Agent below so the TLS handshake and the HTTP
# headers tell a consistent story.
IMPERSONATE_BROWSER = "chrome124"

TOKEN_URL = "https://www.cabelas.com/api/v2/10651/prod/coveo/getCoveoToken"
SEARCH_URL = "https://platform.cloud.coveo.com/rest/search/v2"
COVEO_ORG_ID = "bassproshopsproductionl92epymr"

# A real desktop-browser User-Agent (plus a few other headers a real
# browser tab would always send: Accept, Accept-Language, Referer/Origin
# pointing back at cabelas.com) - both endpoints sit behind Cabela's/
# Coveo's normal bot-mitigation, and an obvious non-browser request (e.g.
# Python's default "python-requests/..." UA, or missing Referer/Origin) is
# the kind of thing that gets filtered before the request is even
# considered. Confirmed via a real browser (punch-list #21 investigation)
# that both endpoints work fine and return real product data when called
# exactly this way from cabelas.com itself - so if this app's own
# server-side calls still get blocked, it's most likely something these
# headers can't fix (e.g. TLS/network-level fingerprinting of the
# underlying HTTP client, not just header content) - see search_lures()'s
# fails-soft contract below for how that's handled either way.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cabelas.com/",
    "Origin": "https://www.cabelas.com",
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
        resp = requests.get(
            TOKEN_URL, headers=_BROWSER_HEADERS, timeout=REQUEST_TIMEOUT_S,
            impersonate=IMPERSONATE_BROWSER,
        )
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
            impersonate=IMPERSONATE_BROWSER,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []
    results = data.get("results") or []
    mapped = [map_result(r.get("raw") or {}) for r in results]
    # A result with no SKU or no name isn't a usable product match.
    return [m for m in mapped if m["sku"] and m["description"]]


def search_page_url(query: str) -> str:
    """Best-effort link to Cabela's own site search for `query` - not a
    specific product page. map_result() above doesn't currently capture a
    stable per-product URL from the Coveo `raw` fields (only sku/brand/
    description/price/image/categories), so rather than fabricate one, this
    links to Cabela's own live search results for the same query text a
    result was found with - the product should be at or near the top of
    that search."""
    return f"https://www.cabelas.com/search?q={quote_plus((query or '').strip())}"
