"""
Looks up real product data on Cabela's, by text query. Originally built for
the Tackle Box page's "Scan a lure" flow (see pages/5_Lure_Inventory.py
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
import re
import time
from urllib.parse import quote
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
    without hitting the network.

    Punch-list #83: `group_id`/`color`/`swatch_count` are new - Coveo's
    `ec_item_group_id`/`product_color`/`swatchcount` raw fields, confirmed
    live to be the exact mechanism Cabela's own site uses to cluster every
    color/size of one product line (e.g. all ~45 colors of "Zoom Salty
    Super Fluke" share one `ec_item_group_id`) - see group_by_family()
    and search_lures_by_group() below for what these enable. Blank/missing
    on a result just means grouping wasn't available for that product;
    every caller treats such a result as its own singleton family rather
    than erroring."""
    return {
        "sku": str(raw.get("sku") or "").strip(),
        "brand": (raw.get("ec_brand") or raw.get("brand") or "").strip(),
        "description": (raw.get("ec_name") or raw.get("ec_shortdesc") or "").strip(),
        "price": _first_number(raw.get("ec_price"), raw.get("offerprice"), raw.get("listprice")),
        "image_url": raw.get("fullimage") or raw.get("thumbnail") or "",
        "categories": raw.get("ec_category") or [],
        "group_id": str(raw.get("ec_item_group_id") or "").strip(),
        "color": (raw.get("product_color") or "").strip(),
        "swatch_count": int(raw["swatchcount"]) if str(raw.get("swatchcount") or "").strip().isdigit() else None,
    }


def search_lures(query: str, num_results: int = 8, aq: str = None) -> list:
    """Search Cabela's for products matching `query`. Returns a list of
    dicts (sku/brand/description/price/image_url/categories/group_id/
    color/swatch_count), best matches first - or [] if the query is empty
    (and no `aq` filter is given either) or the lookup fails for any
    reason (network error, expired/rejected token, unexpected response
    shape). Callers should treat [] the same as "no matches found", not
    as an error to surface differently.

    `aq` (Coveo's "advanced query" field filter syntax, e.g.
    `'@ec_item_group_id=="7506"'`) is an optional precise filter layered
    on top of `query`'s free-text relevance search - punch-list #83's
    search_lures_by_group() below is the one real caller, passing an empty
    `query` with just this filter to fetch every color/size in one exact
    product family rather than relying on free-text relevance at all."""
    query = (query or "").strip()
    if not query and not aq:
        return []
    token = _get_token()
    if not token:
        return []
    try:
        body = {"q": query, "numberOfResults": num_results, "firstResult": 0}
        if aq:
            body["aq"] = aq
        resp = requests.post(
            SEARCH_URL,
            params={"organizationId": COVEO_ORG_ID},
            headers={
                **_BROWSER_HEADERS,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
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
    usable = [m for m in mapped if m["sku"] and m["description"]]
    # Punch-list #38: Coveo can genuinely return the same SKU twice for one
    # query (confirmed live - not a caller bug) - e.g. the same product
    # showing up under more than one matched facet/variant grouping. A
    # caller that keys UI elements by SKU (Lure Inventory's "Scan a lure"
    # results grid, pages/5_Lure_Inventory.py) would otherwise crash with
    # Streamlit's StreamlitDuplicateElementKey the moment that happened, so
    # this dedupes by SKU here, once, for every caller - not just the one
    # that happened to surface it - keeping first-occurrence order (best
    # match first, per this function's own docstring).
    seen_skus = set()
    deduped = []
    for m in usable:
        if m["sku"] in seen_skus:
            continue
        seen_skus.add(m["sku"])
        deduped.append(m)
    return deduped


_GROUP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def search_lures_by_group(group_id: str, num_results: int = 60) -> list:
    """Punch-list #83: fetch every color/size in one exact product family,
    identified by Coveo's `ec_item_group_id` field (see map_result()'s
    `group_id`) - e.g. every one of "Zoom Salty Super Fluke"'s ~45 colors,
    confirmed live to share `group_id == "7506"` regardless of color or
    the two sizes it's sold in. Uses `aq` (a precise field filter), not
    free-text relevance, so it doesn't share search_lures()'s occasional
    zero-result fragility on a long, specific query (see
    search_lures_broadening()'s docstring for that story) - once a family
    is known, this reliably returns everything in it. `num_results`
    defaults to 60 - comfortably above every family size seen so far
    (Coveo's own `swatchcount` field tells a caller the real total, so
    pass `max(swatchcount, 60)` if a specific family is ever bigger).
    Returns [] for a blank/malformed group_id, same fails-soft contract as
    search_lures()."""
    group_id = (group_id or "").strip()
    if not group_id or not _GROUP_ID_RE.match(group_id):
        return []
    return search_lures("", num_results=num_results, aq=f'@ec_item_group_id=="{group_id}"')


def group_by_family(results: list) -> list:
    """Collapse a flat list of search_lures() results (which can contain
    several color/size variants of the very same product line, e.g.
    searching "zoom super fluke" surfaces many of its ~45 colors directly)
    into one entry per real product family - punch-list #83's "just show
    me the product, then let me pick a color" redesign of the Tackle Box
    page's Cabela's-lookup flow.

    Grouped on `group_id` (Coveo's `ec_item_group_id`, see map_result()).
    Each returned dict is the first-seen variant in that family (used as
    the representative brand/description/photo/price shown on the family
    card) with one added key, `swatch_count`: the family's real total
    color/size count, taken from whichever member result carried Coveo's
    own `swatchcount` field (should be the same on every member; falls
    back to how many of THIS list's own results shared the group if none
    did). A result with no `group_id` (grouping wasn't available for it)
    is kept as its own singleton family rather than merged with anything -
    every caller treats `swatch_count <= 1` as "no color picker needed,
    just use this," so an ungrouped result behaves exactly like it did
    before this existed. Order is preserved (first-seen family first),
    matching search_lures()'s own best-match-first ordering. A pure
    function (no I/O) so it's unit-testable against fixture data."""
    families: dict[str, dict] = {}
    order: list[str] = []
    for r in results:
        key = r.get("group_id") or f"__ungrouped_{r['sku']}"
        if key not in families:
            families[key] = dict(r)
            families[key]["_member_count"] = 0
            order.append(key)
        families[key]["_member_count"] += 1
        # A later member might be the one that actually carries a real
        # swatch_count (Coveo doesn't always populate every raw field on
        # every result) - keep the first non-None one seen.
        if families[key].get("swatch_count") is None and r.get("swatch_count") is not None:
            families[key]["swatch_count"] = r["swatch_count"]
    out = []
    for key in order:
        fam = families[key]
        if fam.get("swatch_count") is None:
            fam["swatch_count"] = fam["_member_count"]
        del fam["_member_count"]
        out.append(fam)
    return out


def search_lures_broadening(query: str, num_results: int = 8, min_words: int = 2) -> tuple:
    """Punch-list #83: search_lures(), but automatically retries with a
    shorter version of `query` if the full text comes back with zero
    results, instead of the caller just being told "no matches found."
    Returns `(results, query_used)` - `query_used` is the exact text that
    actually found something (== `query` itself if the first try worked,
    which is the common case), so a caller can tell the angler when it had
    to broaden ("Showing results for 'X' - your exact description had no
    matches").

    This exists because of a real, reproducible Coveo relevance quirk,
    confirmed live against Cabela's own search: a long, highly specific
    query - exactly the kind Scan-a-lure's vision-generated search_query,
    or a manual "brand + full description" search, naturally produces -
    can come back with ZERO results even though a shorter prefix of the
    very same words finds the right product immediately. E.g. "Strike
    King 3XD Series Pro-Model Crankbait Chartreuse Sexy Shad 2-3/4 5XD"
    (11 words) -> 0 results, but the first 9 of those same 11 words -> 2
    results, an exact match. Confirmed this isn't a hyphen/slash escaping
    bug (rewriting "2-3/4" as "2 3/4", or the whole phrase as all spaces,
    failed identically) - it's Coveo's own relevance ranking dropping
    below its return threshold once a query gets this specific, which
    this app's query text can't reason about or fix character-by-character.
    Dropping trailing words and retrying is a generic workaround for that
    class of failure, not a fix aimed at any one phrase - the trailing
    words are also, not coincidentally, usually where a vision/manual
    description's extra color/size detail (beyond brand + product line)
    lives, so this naturally broadens toward the same "brand + product
    line" query core/lure_vision.py already asks Claude's vision to
    prefer in the first place.

    Stops at the first non-empty result (usually the very first, full-text
    try), so a query that already works pays no extra latency; only a
    genuinely over-specific query pays for the extra round-trip(s), down
    to `min_words` words minimum (never broadens past that, so a short
    query is at most tried once)."""
    words = (query or "").split()
    if not words:
        return [], (query or "")
    floor = min(min_words, len(words))
    for end in range(len(words), floor - 1, -1):
        candidate = " ".join(words[:end])
        results = search_lures(candidate, num_results=num_results)
        if results:
            return results, candidate
    return [], query


def search_page_url(query: str) -> str:
    """Best-effort link to Cabela's own site search for `query` - not a
    specific product page. map_result() above doesn't currently capture a
    stable per-product URL from the Coveo `raw` fields (only sku/brand/
    description/price/image/categories), so rather than fabricate one, this
    links to Cabela's own live search results for the same query text a
    result was found with - the product should be at or near the top of
    that search.

    Punch-list #36: this used to build a `/search?q=...` URL (a real-
    looking, but wrong, guess at Cabela's search route) with `quote_plus()`
    (spaces encoded as literal `+`), which 404'd on Cabela's own site no
    matter how the query was encoded - confirmed live: `/search?q=Gambler`
    alone 404s, `+`-vs-`%20`-vs-raw `/` in "5/16 oz." made no difference.
    Cabela's real site search, confirmed by actually driving their live
    search box and watching where it navigates to, is a single-page-app
    route: `/SearchDisplay#q=<query>` - a URL FRAGMENT (`#...`), not a
    query string (`?...`), which is also why `+` was never going to be
    read as a space here even with correct encoding (fragments aren't
    form-urlencoded the way `application/x-www-form-urlencoded` query
    strings are - only `%20` reliably means space in one). `quote()`
    (percent-encodes spaces as `%20`, matching what a real click through
    their own search box produces) replaces `quote_plus()` accordingly."""
    return f"https://www.cabelas.com/SearchDisplay#q={quote((query or '').strip())}"


def best_variant_index(variants: list, hint_text: str) -> int:
    """Punch-list #83: given a family's full list of color/size variants
    (search_lures_by_group()'s result) and free text that might already
    name a specific one (a vision scan's own product_name, or whatever the
    angler typed to search), returns the index of whichever variant's
    color/description shares the most words with `hint_text` - so "the
    app got the name of the lure right" (a real angler quote about the
    Scan-a-lure flow) actually pre-selects the right color in the picker
    instead of always defaulting to the first one and making the angler
    hunt for it again by hand. Falls back to 0 (first/best-ranked variant)
    if `hint_text` is blank or shares no real word with anything - a
    word-overlap heuristic deliberately kept simple (no fuzzy/typo
    tolerance) since it only ever affects a *default*, never hides or
    excludes an option, and every variant is always still pickable from
    the dropdown regardless. A pure function (no I/O), unit-testable
    against fixture data."""
    if not variants:
        return 0
    hint_words = {w for w in re.findall(r"[a-z0-9]+", (hint_text or "").lower()) if len(w) > 2}
    if not hint_words:
        return 0
    best_idx, best_score = 0, -1
    for i, v in enumerate(variants):
        text = f"{v.get('color') or ''} {v.get('description') or ''}".lower()
        words = set(re.findall(r"[a-z0-9]+", text))
        score = len(hint_words & words)
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx
