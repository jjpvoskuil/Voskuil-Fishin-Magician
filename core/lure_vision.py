"""
Identifies a lure from a photo of its packaging using Claude's vision, via
the Anthropic API - the first step of the Tackle Box page's "Scan a
lure" flow (see pages/5_Lure_Inventory.py).

Deliberately kept as two separate steps, not one: this module only reads
whatever brand/product name is legible on the label well enough to build a
search query. core.cabelas_lookup.search_lures() then finds the *real*
product data (exact SKU, current price, category) from Cabela's own catalog
for that query. A vision model's read of a small, possibly glare-y package
photo is a good search query, but isn't a reliable enough source to trust
for exact price/SKU on its own - and the Tackle Box page always shows
the angler the matched candidates to confirm before anything is saved.

Requires an Anthropic API key in Streamlit secrets (ANTHROPIC_API_KEY) -
see core.appstate.anthropic_api_key(). Without one, the "Scan a lure"
section on the Tackle Box page stays hidden and only the existing
manual "Add a lure" form shows - same graceful-degradation pattern already
used for GITHUB_TOKEN elsewhere in this app.
"""
from __future__ import annotations
import base64

# Overridable via the ANTHROPIC_MODEL secret (core.appstate.anthropic_model())
# in case this needs bumping to a newer model without a code change.
DEFAULT_MODEL = "claude-sonnet-4-5"

_TOOL_SCHEMA = {
    "name": "identify_lure",
    "description": (
        "Report what fishing lure/bait is shown in the photo, based on any "
        "text/branding visible on its packaging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "visible": {
                "type": "boolean",
                "description": (
                    "True if the photo clearly shows a fishing lure or its packaging; "
                    "false if it shows something else, or is too blurry/unclear to "
                    "identify anything from."
                ),
            },
            "brand": {
                "type": "string",
                "description": "The brand name printed on the package, e.g. 'Strike King'. Empty string if not legible.",
            },
            "product_name": {
                "type": "string",
                "description": "The specific product/model name, color, and size printed on the package, as close to verbatim as you can read it.",
            },
            "search_query": {
                "type": "string",
                "description": (
                    "A short search-engine-style query (brand + product line name, "
                    "generally without color/size unless it's clearly part of the model "
                    "name) that would find this exact product on a tackle retailer's site."
                ),
            },
            "notes": {
                "type": "string",
                "description": "Anything worth flagging - illegible text, guessing between two similar products, glare/blur, etc. Empty string if nothing to flag.",
            },
        },
        "required": ["visible", "brand", "product_name", "search_query", "notes"],
    },
}

_PROMPT = (
    "This is a photo of a fishing lure, likely still in its retail package. Read any "
    "brand name, product/model name, color, and size printed on the packaging and "
    "report it with the identify_lure tool. If you can't make out enough to identify "
    "it, set visible to false rather than guessing."
)

_MIME_BY_EXT = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}


def identify_lure_photo(image_bytes: bytes, extension: str, api_key: str, model: str = None) -> dict:
    """Send a lure photo to Claude's vision API and return a dict with keys
    visible/brand/product_name/search_query/notes - or a single key `error`
    (with every other key absent) if the call itself failed (missing/bad
    key, network issue, unexpected response shape). Callers should show an
    `error` result as a friendly message and fall back to manual entry,
    same as any other optional-integration failure in this app."""
    if not api_key:
        return {"error": "No ANTHROPIC_API_KEY configured in Streamlit secrets."}
    try:
        import anthropic
    except ImportError:
        return {"error": "The 'anthropic' package isn't installed - add it to requirements.txt."}

    mime = _MIME_BY_EXT.get((extension or "jpg").lower().lstrip("."), "jpeg")
    encoded = base64.b64encode(image_bytes).decode("ascii")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=1024,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "identify_lure"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": f"image/{mime}", "data": encoded}},
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "identify_lure":
                return dict(block.input)
        return {"error": "Claude didn't return a structured answer - try again or add this lure manually."}
    except Exception as e:
        return {"error": f"Lure identification failed: {e}"}
