from pathlib import Path

import streamlit as st

from core.appstate import anthropic_api_key, anthropic_model, get_inventory, github_token, repo_slug
from core.cabelas_lookup import search_lures
from core.lure_inventory import (
    IMAGES_DIR, INVENTORY_PATH, LureItem, append_item, delete_item, save_image, update_item,
)
from core.lure_vision import identify_lure_photo
from core.lures import LURE_CATEGORY_OPTIONS, LURE_PROFILES, find_inventory_gaps, guess_category_from_text
from core.storage import commit_and_push_data
from core.ui import render_cabelas_suggestions, render_square_thumbnail, inject_mobile_css

CARD_THUMBNAIL_PX = 160
SCAN_THUMBNAIL_PX = 110

st.set_page_config(page_title="Tackle Box - Nolin Lake", page_icon="🧰", layout="wide")
inject_mobile_css()
st.title("🧰 Tackle Box")
st.caption(
    "Your tackle box, tracked: brand, full description, a photo, the last price you paid, and "
    "how many you currently have on hand. Seeded from a Cabela's order, and grows as you add "
    "more by hand or with a photo."
)
st.caption(
    "🎣 Tag each lure with a **Category** matching how it's fished - the 7-Day Forecast and Lake "
    "Map pages use it to flag which of their lure suggestions you already own. Auto-imported items "
    "were tagged with a best guess; double-check/correct them below if one looks off."
)

CATEGORY_LABELS = ["Not categorized / other"] + [name for _, name in LURE_CATEGORY_OPTIONS]
CATEGORY_KEYS = [""] + [key for key, _ in LURE_CATEGORY_OPTIONS]
CATEGORY_NAME_BY_KEY = dict(LURE_CATEGORY_OPTIONS)


def _category_index(category_key: str) -> int:
    return CATEGORY_KEYS.index(category_key) if category_key in CATEGORY_KEYS else 0


def _render_candidate_grid(candidates: list, session_key: str, key_prefix: str) -> None:
    """Shared Cabela's-results grid, used by both the photo-scan flow above
    and the type-a-description search flow below (punch-list #41) - picking
    a card stores that candidate dict at `st.session_state[session_key]`
    and reruns so a confirm form can render underneath."""
    st.write(f"Found {len(candidates)} possible match(es) on Cabela's - pick one:")
    cols_per_row = 4
    for row_start in range(0, len(candidates), cols_per_row):
        row_candidates = list(enumerate(candidates[row_start:row_start + cols_per_row], start=row_start))
        cand_cols = st.columns(cols_per_row)
        for col, (idx, cand) in zip(cand_cols, row_candidates):
            with col:
                with st.container(border=True):
                    if not render_square_thumbnail(cand, size_px=SCAN_THUMBNAIL_PX):
                        st.caption("No photo")
                    st.caption(f"**{cand['brand']}**  \n{cand['description']}"[:110])
                    price_txt = f"${cand['price']:,.2f}" if cand["price"] is not None else "price n/a"
                    st.caption(f"SKU {cand['sku']} · {price_txt}")
                    # Punch-list #38: core.cabelas_lookup.search_lures() now dedupes by
                    # SKU at the source (the real cause of the crash this fixed), but this
                    # index in the key is still worth keeping as cheap defense-in-depth -
                    # a key collision here means a full-page crash, not just a cosmetic bug.
                    if st.button("Use this", key=f"{key_prefix}_{idx}_{cand['sku']}", width='stretch'):
                        st.session_state[session_key] = cand
                        st.rerun()


def _render_confirm_form(selected: dict, form_key: str, source_label: str, cleanup_keys: tuple) -> None:
    """Shared 'confirm before saving' form, used by both the photo-scan
    flow above and the type-a-description search flow below (punch-list
    #41) - editable brand/price/description/qty/category, bumps an
    existing matching-SKU row's quantity instead of duplicating it,
    otherwise appends a new LureItem sourced from the Cabela's lookup."""
    st.divider()
    st.markdown("#### Confirm details")
    existing_match = next((r for r in items if r.get("sku") and r["sku"] == selected["sku"]), None)
    if existing_match:
        st.info(
            f"You already have this in inventory (qty {existing_match['quantity']}) - "
            "confirming below adds to that quantity instead of creating a duplicate entry."
        )
    guessed_category = guess_category_from_text(selected["brand"], selected["description"]) or (
        existing_match.get("category", "") if existing_match else ""
    )
    with st.form(form_key):
        sc1, sc2 = st.columns(2)
        confirm_brand = sc1.text_input("Brand", value=selected["brand"])
        confirm_price = sc2.number_input(
            "Price ($)", min_value=0.0, step=0.01, value=float(selected["price"] or 0.0),
        )
        confirm_description = st.text_area("Full description", value=selected["description"])
        sc3, sc4 = st.columns(2)
        confirm_qty = sc3.number_input("Quantity to add", min_value=1, step=1, value=1)
        confirm_category_choice = sc4.selectbox(
            "Category (matches it to forecast lure suggestions)", CATEGORY_LABELS,
            index=_category_index(guessed_category),
            key=f"{form_key}_category",
        )
        confirm_package_qty = st.number_input(
            "Package qty (lures per package)", min_value=1, step=1, value=1,
            help="How many individual lures come in one package - e.g. 8 for an 8-pack, "
                 "or 1 if it's sold individually.",
            key=f"{form_key}_package_qty",
        )
        confirm_submitted = st.form_submit_button("✅ Add to inventory", width='stretch')

    if confirm_submitted:
        category_key = CATEGORY_KEYS[CATEGORY_LABELS.index(confirm_category_choice)]
        if existing_match:
            new_qty = int(existing_match["quantity"] or 0) + int(confirm_qty)
            update_item(
                existing_match["item_id"],
                quantity=new_qty,
                price=float(confirm_price) if confirm_price else existing_match.get("price"),
                category=category_key or existing_match.get("category", ""),
            )
            saved_desc = (
                f"{confirm_brand} - {confirm_description[:50]} "
                f"(qty {existing_match['quantity']} -> {new_qty})"
            )
        else:
            new_item = LureItem(
                brand=confirm_brand.strip(),
                description=confirm_description.strip(),
                price=float(confirm_price) if confirm_price else None,
                quantity=int(confirm_qty),
                category=category_key,
                package_qty=int(confirm_package_qty),
                sku=selected["sku"],
                image_url=selected["image_url"],
                source=source_label,
            )
            append_item(new_item)
            saved_desc = f"{new_item.brand} - {new_item.description[:50]}"

        get_inventory.clear()
        token = github_token()
        if token:
            ok, msg = commit_and_push_data(
                [INVENTORY_PATH], token, repo_slug(),
                f"Add lure to inventory: {saved_desc}",
            )
            (st.success if ok else st.warning)(msg)
        else:
            st.success("Added locally.")
            st.info(
                "No GITHUB_TOKEN configured in Streamlit secrets, so this entry wasn't pushed "
                "to GitHub and won't survive an app restart. See README for how to add it."
            )
        for key in cleanup_keys:
            st.session_state.pop(key, None)
        st.rerun()


items = get_inventory()

with st.expander("📷 Scan a lure", expanded=False, key="scan_expander", on_change="rerun"):
    api_key = anthropic_api_key()
    if not api_key:
        st.info(
            "Photo scanning isn't set up yet - add an `ANTHROPIC_API_KEY` to this app's "
            "Streamlit secrets to enable it (see `secrets.toml.example` in the repo for the "
            "exact key name). You can still add lures manually below."
        )
    elif not st.session_state.get("scan_expander"):
        # Collapsed - render nothing below, in particular no camera_input. Streamlit
        # still runs a collapsed expander's `with` block on every rerun (it only
        # hides the result with CSS), so a widget with a real hardware side effect -
        # camera_input requests the webcam the moment it's created, whether or not
        # it's actually visible - has to be skipped explicitly like this rather than
        # relying on the collapsed state to do it for us. Also drop the camera-on
        # flag so re-expanding this section always starts with the camera off,
        # requiring an explicit "Turn on camera" click again rather than resuming
        # wherever it was left.
        st.session_state["scan_camera_active"] = False
    else:
        st.caption(
            "Take or upload a photo of the lure's package. Claude reads the brand/product name "
            "off the label, looks it up on Cabela's for the real product details, and shows you "
            "candidate matches to confirm before anything is added - nothing saves automatically."
        )
        photo_mode = st.radio(
            "Photo", ["Upload a photo", "Take a photo"], horizontal=True, key="scan_photo_mode",
        )

        if photo_mode == "Upload a photo":
            st.session_state["scan_camera_active"] = False
            uploaded = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"], key="scan_upload")
            if uploaded is not None:
                st.session_state["scan_photo_bytes"] = uploaded.getvalue()
                st.session_state["scan_photo_ext"] = (
                    Path(getattr(uploaded, "name", "photo.jpg")).suffix.lstrip(".") or "jpg"
                )
        elif not st.session_state.get("scan_camera_active"):
            # Camera stays off until explicitly turned on - this is the actual fix
            # for the camera activating just from opening this page: it's now
            # impossible for st.camera_input to even be created without this
            # button click first, regardless of expander state or widget defaults.
            st.caption("Camera is off.")
            if st.button("📷 Turn on camera", key="scan_camera_on_btn"):
                st.session_state["scan_camera_active"] = True
                st.rerun()
            st.caption(
                "On some phones, this in-browser camera can come out blurrier than a normal "
                "photo - it also opens your front-facing (selfie) camera by default, which is "
                "lower-resolution than your back camera on almost every phone. If a shot looks "
                "soft, try 'Upload a photo' instead and choose 'Take Photo' from your phone's "
                "own camera app - that uses your phone's full rear camera, not the browser's."
            )
        else:
            cam_photo = st.camera_input(
                "Take a picture of the lure/package", key="scan_camera", resolution="1080p",
            )
            st.caption(
                "📷 This opens your front (selfie) camera by default - tap the flip/"
                "switch-camera icon in the camera view above to switch to your back camera "
                "before shooting. It's much sharper for reading small print on packaging."
            )
            if cam_photo is not None:
                st.session_state["scan_photo_bytes"] = cam_photo.getvalue()
                st.session_state["scan_photo_ext"] = (
                    Path(getattr(cam_photo, "name", "photo.jpg")).suffix.lstrip(".") or "jpg"
                )
                # Release the camera the instant a shot is captured, rather than
                # leaving it running while the angler reviews/identifies the photo.
                st.session_state["scan_camera_active"] = False
                st.rerun()
            if st.button("Turn off camera", key="scan_camera_off_btn"):
                st.session_state["scan_camera_active"] = False
                st.rerun()

        photo_bytes = st.session_state.get("scan_photo_bytes")
        if photo_bytes is not None:
            st.image(photo_bytes, width=220)
            pc1, pc2 = st.columns(2)
            identify_clicked = pc1.button("🔍 Identify this lure", key="scan_identify_btn", width='stretch')
            if pc2.button("Remove photo", key="scan_remove_photo_btn", width='stretch'):
                st.session_state.pop("scan_photo_bytes", None)
                st.session_state.pop("scan_photo_ext", None)
                st.rerun()
            if identify_clicked:
                with st.spinner("Reading the label..."):
                    scan_result = identify_lure_photo(
                        photo_bytes, st.session_state.get("scan_photo_ext", "jpg"),
                        api_key=api_key, model=anthropic_model(),
                    )
                st.session_state["scan_result"] = scan_result
                st.session_state["scan_candidates"] = None
                st.session_state["scan_selected"] = None
                if not scan_result.get("error") and scan_result.get("visible") and scan_result.get("search_query"):
                    with st.spinner("Searching Cabela's..."):
                        st.session_state["scan_candidates"] = search_lures(scan_result["search_query"])

        scan_result = st.session_state.get("scan_result")
        if scan_result:
            if scan_result.get("error"):
                st.error(scan_result["error"])
            elif not scan_result.get("visible"):
                st.warning(
                    "Couldn't make out a lure in that photo"
                    + (f" - {scan_result['notes']}" if scan_result.get("notes") else "")
                    + ". Try a clearer photo, or add it manually below."
                )
            else:
                read_as = " ".join(p for p in [scan_result.get("brand"), scan_result.get("product_name")] if p)
                notes_line = f"  \n_{scan_result['notes']}_" if scan_result.get("notes") else ""
                st.caption(f"📖 Claude read: **{read_as or '(nothing legible)'}**{notes_line}")

                candidates = st.session_state.get("scan_candidates")
                if not candidates:
                    st.warning(
                        "No matches found on Cabela's for that. Try a different search below, "
                        "or add it manually further down."
                    )
                    manual_query = st.text_input(
                        "Search Cabela's yourself", value=scan_result.get("search_query", ""),
                        key="scan_manual_query",
                    )
                    if st.button("Search", key="scan_manual_search_btn") and manual_query.strip():
                        with st.spinner("Searching Cabela's..."):
                            st.session_state["scan_candidates"] = search_lures(manual_query)
                        st.rerun()
                else:
                    _render_candidate_grid(candidates, "scan_selected", "scan_pick")

        selected = st.session_state.get("scan_selected")
        if selected:
            _render_confirm_form(
                selected, "scan_confirm_form", "Scanned photo -> Cabela's lookup",
                ("scan_result", "scan_candidates", "scan_selected", "scan_photo_bytes", "scan_photo_ext"),
            )

        if st.session_state.get("scan_result"):
            if st.button("Start over", key="scan_reset_btn"):
                for key in ("scan_result", "scan_candidates", "scan_selected", "scan_photo_bytes", "scan_photo_ext"):
                    st.session_state.pop(key, None)
                st.rerun()

with st.expander("🔍 Search Cabela's by description", expanded=False, key="text_search_expander"):
    # Punch-list #41: no photo needed - type what you know about the lure
    # (brand, name, color, size) and search Cabela's directly, reusing the
    # exact same "pick a match -> confirm details" flow as the photo-scan
    # section above (_render_candidate_grid/_render_confirm_form), just
    # skipping the photo + Claude-vision step entirely.
    st.caption(
        "Type a description of the lure - brand, name, color, size, whatever you know - and "
        "search Cabela's directly. Pick a match below to confirm details before it's added to "
        "your tackle box."
    )
    ts1, ts2 = st.columns([4, 1])
    text_query = ts1.text_input(
        "Search Cabela's", placeholder='e.g. Strike King KVD 1.5 crankbait chartreuse',
        key="text_search_query", label_visibility="collapsed",
    )
    search_clicked = ts2.button("🔍 Search", key="text_search_btn", width='stretch')
    if search_clicked and text_query.strip():
        with st.spinner("Searching Cabela's..."):
            st.session_state["text_search_candidates"] = search_lures(text_query)
        st.session_state["text_search_selected"] = None
        st.rerun()

    text_candidates = st.session_state.get("text_search_candidates")
    if text_candidates is not None:
        if not text_candidates:
            st.warning(
                "No matches found on Cabela's for that search. Try different wording, or add it "
                "manually below."
            )
        else:
            _render_candidate_grid(text_candidates, "text_search_selected", "text_search_pick")

    text_selected = st.session_state.get("text_search_selected")
    if text_selected:
        _render_confirm_form(
            text_selected, "text_search_confirm_form", "Cabela's search",
            ("text_search_candidates", "text_search_selected", "text_search_query"),
        )

with st.expander("➕ Add a lure", expanded=len(items) == 0):
    # Punch-list #40: the photo controls used to live INSIDE the st.form
    # below. Streamlit forms only rerun the script when their submit button
    # is clicked - a radio button changed inside a form doesn't trigger a
    # rerun the way it normally would, so picking "Take a photo" never
    # actually revealed the camera widget (it silently took effect only on
    # submit, by which point the lure had already been added with no
    # photo). Moving the photo radio + the upload/camera widgets outside
    # the form fixes this the same way the "Scan a lure" section above
    # already works: these are ordinary reactive widgets now, so selecting
    # "Take a photo" reruns the page immediately and the camera turns on
    # right away. `uploaded_file`/`camera_file` are still plain Python
    # variables in scope when the form below is submitted, so the rest of
    # the add-lure logic is unchanged.
    photo_mode = st.radio(
        "Photo", ["Upload a photo", "Take a photo", "No photo"], horizontal=True,
        key="add_lure_photo_mode",
    )
    uploaded_file = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"], key="add_lure_upload") \
        if photo_mode == "Upload a photo" else None
    camera_file = st.camera_input("Take a picture", resolution="1080p", key="add_lure_camera") \
        if photo_mode == "Take a photo" else None
    if photo_mode == "Take a photo":
        st.caption(
            "📷 This opens your front (selfie) camera by default - tap the flip/switch-camera "
            "icon above to use your back camera for a sharper photo."
        )

    with st.form("add_lure_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        brand = c1.text_input("Brand", placeholder="e.g. Strike King")
        price = c2.number_input("Last price paid ($)", min_value=0.0, step=0.01, value=0.0)
        description = st.text_area(
            "Full description",
            placeholder='e.g. KVD Perfect Plastics Blade Minnow - KVD Magic, 4-1/2", 8-pack',
        )
        c3, c4 = st.columns(2)
        quantity = c3.number_input("Quantity in inventory", min_value=0, step=1, value=1)
        category_choice = c4.selectbox(
            "Category (matches it to forecast lure suggestions)", CATEGORY_LABELS,
            help="Which of the forecast engine's lure types this is/works as - lets the 7-Day "
                 "Forecast and Lake Map pages flag this as something you already have.",
        )
        package_qty = st.number_input(
            "Package qty (lures per package)", min_value=1, step=1, value=1,
            help="How many individual lures come in one package - e.g. 8 for an 8-pack, or 1 "
                 "if it's sold individually.",
        )
        if photo_mode == "Take a photo" and camera_file is not None:
            st.caption("📷 Photo captured above - will attach when you submit.")
        elif photo_mode == "Upload a photo" and uploaded_file is not None:
            st.caption("🖼️ Photo selected above - will attach when you submit.")

        submitted = st.form_submit_button("Add to inventory", width='stretch')

    if submitted:
        if not brand.strip() or not description.strip():
            st.warning("Brand and description are required.")
        else:
            item = LureItem(
                brand=brand.strip(),
                description=description.strip(),
                price=float(price) if price else None,
                quantity=int(quantity),
                category=CATEGORY_KEYS[CATEGORY_LABELS.index(category_choice)],
                package_qty=int(package_qty),
                source="Manual",
            )
            photo_file = uploaded_file or camera_file
            if photo_file is not None:
                ext = Path(getattr(photo_file, "name", "photo.jpg")).suffix or ".jpg"
                item.image_filename = save_image(item.item_id, photo_file.getvalue(), ext)

            append_item(item)
            get_inventory.clear()

            # The photo controls live outside add_lure_form now (see comment
            # above), so clear_on_submit=True doesn't reset them - do it
            # explicitly so the next "Add a lure" doesn't start with a stale
            # photo/mode left over from this one. This has to be a pop(), not
            # an assignment - Streamlit raises StreamlitAPIException if you
            # assign to a widget's session_state key after that widget has
            # already been instantiated in the current script run (which the
            # radio/uploader/camera above always have been by this point).
            # Popping the key removes it entirely, so on the rerun below the
            # widget falls back to its own default (the radio's first option,
            # "Upload a photo") with no forbidden assignment involved.
            st.session_state.pop("add_lure_upload", None)
            st.session_state.pop("add_lure_camera", None)
            st.session_state.pop("add_lure_photo_mode", None)

            token = github_token()
            paths = [INVENTORY_PATH, IMAGES_DIR] if photo_file is not None else [INVENTORY_PATH]
            if token:
                ok, msg = commit_and_push_data(
                    paths, token, repo_slug(),
                    f"Add lure to inventory: {item.brand} - {item.description[:50]}",
                )
                (st.success if ok else st.warning)(msg)
            else:
                st.success("Added locally.")
                st.info(
                    "No GITHUB_TOKEN configured in Streamlit secrets, so this entry wasn't pushed "
                    "to GitHub and won't survive an app restart. See README for how to add it."
                )
            st.rerun()

with st.expander("🎯 Fill your tackle gaps", expanded=False):
    st.caption(
        "Every lure type (and trailer style - craw/creature and paddle-tail swimbait trailers are "
        "their own types below, same as any other lure) this app knows how to suggest for Nolin "
        "Lake, cross-checked against your inventory above. A \"Search Cabela's\" link opens that "
        "product's real search results in a new tab - there's no way for this app to add something "
        "to your cart for you (that needs your own logged-in session on their site), so one more "
        "click there finishes it."
    )
    gap_categories = find_inventory_gaps(items)
    if not gap_categories:
        st.success("✅ You've got at least one of every lure type this app suggests for Nolin Lake - nothing to fill.")
    else:
        st.write(f"**{len(gap_categories)} of {len(LURE_PROFILES)}** lure types have nothing in your inventory yet:")
        for category_key in gap_categories:
            profile = LURE_PROFILES[category_key]
            with st.container(border=True):
                st.markdown(f"**{profile['name']}**")
                render_cabelas_suggestions(
                    profile["name"],
                    found_caption="🛒 Worth considering from Cabela's:",
                    empty_caption="🛒 No Cabela's matches found for this one right now - try searching manually.",
                )

st.divider()

if not items:
    st.info("No lures in inventory yet - add one above.")
else:
    brands = sorted({row["brand"] for row in items if row["brand"]})
    categories_present = sorted({row.get("category", "") for row in items}, key=lambda k: CATEGORY_NAME_BY_KEY.get(k, "Not categorized / other"))
    fc1, fc2, fc3 = st.columns([2, 1, 1])
    search = fc1.text_input("Search description or brand", placeholder="e.g. crankbait, chartreuse, Strike King")
    brand_filter = fc2.multiselect("Filter by brand", brands)
    category_filter = fc3.multiselect(
        "Filter by category",
        categories_present,
        format_func=lambda k: CATEGORY_NAME_BY_KEY.get(k, "Not categorized / other"),
    )

    filtered = items
    if search:
        s = search.lower()
        filtered = [r for r in filtered if s in r["description"].lower() or s in r["brand"].lower()]
    if brand_filter:
        filtered = [r for r in filtered if r["brand"] in brand_filter]
    if category_filter:
        filtered = [r for r in filtered if r.get("category", "") in category_filter]

    total_qty = sum(int(r["quantity"] or 0) for r in filtered)
    total_value = sum(float(r["price"] or 0) * int(r["quantity"] or 0) for r in filtered)
    st.caption(f"{len(filtered)} lure(s) shown - {total_qty} total on hand - roughly ${total_value:,.2f} in tackle")

    cols_per_row = 6
    for i in range(0, len(filtered), cols_per_row):
        row_items = filtered[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, row in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    if not render_square_thumbnail(row, size_px=CARD_THUMBNAIL_PX):
                        st.caption("No photo yet")

                    st.markdown(f"**{row['brand']}**")
                    st.write(row["description"])
                    price_val = float(row["price"]) if row["price"] else 0.0
                    package_qty_val = int(row.get("package_qty") or 1)
                    package_note = f" ({package_qty_val}-pack)" if package_qty_val > 1 else ""
                    st.caption(f"Last price: ${price_val:,.2f}  ·  Qty: {row['quantity']}{package_note}")
                    st.caption(f"Category: {CATEGORY_NAME_BY_KEY.get(row.get('category', ''), 'Not categorized / other')}")

                    with st.expander("Edit"):
                        new_qty = st.number_input(
                            "Quantity", min_value=0, step=1,
                            value=int(row["quantity"] or 0), key=f"qty_{row['item_id']}",
                        )
                        new_price = st.number_input(
                            "Last price ($)", min_value=0.0, step=0.01,
                            value=price_val, key=f"price_{row['item_id']}",
                        )
                        new_category_choice = st.selectbox(
                            "Category", CATEGORY_LABELS,
                            index=_category_index(row.get("category", "")), key=f"cat_{row['item_id']}",
                        )
                        new_package_qty = st.number_input(
                            "Package qty (lures per package)", min_value=1, step=1,
                            value=package_qty_val, key=f"pkgqty_{row['item_id']}",
                        )
                        ec1, ec2 = st.columns(2)
                        if ec1.button("Save", key=f"save_{row['item_id']}", width='stretch'):
                            new_category = CATEGORY_KEYS[CATEGORY_LABELS.index(new_category_choice)]
                            update_item(
                                row["item_id"], quantity=new_qty, price=new_price, category=new_category,
                                package_qty=new_package_qty,
                            )
                            get_inventory.clear()
                            token = github_token()
                            if token:
                                commit_and_push_data(
                                    [INVENTORY_PATH], token, repo_slug(),
                                    f"Update lure inventory item {row['item_id']}",
                                )
                            st.rerun()
                        if ec2.button("Delete", key=f"del_{row['item_id']}", width='stretch'):
                            delete_item(row["item_id"])
                            get_inventory.clear()
                            token = github_token()
                            if token:
                                commit_and_push_data(
                                    [INVENTORY_PATH, IMAGES_DIR], token, repo_slug(),
                                    f"Remove lure inventory item {row['item_id']}",
                                )
                            st.rerun()
