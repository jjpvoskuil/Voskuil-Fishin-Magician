from pathlib import Path

import streamlit as st

from core.appstate import get_inventory, github_token, repo_slug
from core.lure_inventory import (
    IMAGES_DIR, INVENTORY_PATH, LureItem, append_item, delete_item, save_image, update_item,
)
from core.lures import LURE_CATEGORY_OPTIONS
from core.storage import commit_and_push
from core.ui import render_square_thumbnail

CARD_THUMBNAIL_PX = 160

st.set_page_config(page_title="Lure Inventory - Nolin Lake", page_icon="🧰", layout="wide")
st.title("🧰 Lure Inventory")
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


items = get_inventory()

with st.expander("➕ Add a lure", expanded=len(items) == 0):
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

        photo_mode = st.radio("Photo", ["Upload a photo", "Take a photo", "No photo"], horizontal=True)
        uploaded_file = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png"]) \
            if photo_mode == "Upload a photo" else None
        camera_file = st.camera_input("Take a picture") if photo_mode == "Take a photo" else None

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
                source="Manual",
            )
            photo_file = uploaded_file or camera_file
            if photo_file is not None:
                ext = Path(getattr(photo_file, "name", "photo.jpg")).suffix or ".jpg"
                item.image_filename = save_image(item.item_id, photo_file.getvalue(), ext)

            append_item(item)
            get_inventory.clear()

            token = github_token()
            paths = [INVENTORY_PATH, IMAGES_DIR] if photo_file is not None else [INVENTORY_PATH]
            if token:
                ok, msg = commit_and_push(
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
                    st.caption(f"Last price: ${price_val:,.2f}  ·  Qty: {row['quantity']}")
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
                        ec1, ec2 = st.columns(2)
                        if ec1.button("Save", key=f"save_{row['item_id']}", width='stretch'):
                            new_category = CATEGORY_KEYS[CATEGORY_LABELS.index(new_category_choice)]
                            update_item(row["item_id"], quantity=new_qty, price=new_price, category=new_category)
                            get_inventory.clear()
                            token = github_token()
                            if token:
                                commit_and_push(
                                    [INVENTORY_PATH], token, repo_slug(),
                                    f"Update lure inventory item {row['item_id']}",
                                )
                            st.rerun()
                        if ec2.button("Delete", key=f"del_{row['item_id']}", width='stretch'):
                            delete_item(row["item_id"])
                            get_inventory.clear()
                            token = github_token()
                            if token:
                                commit_and_push(
                                    [INVENTORY_PATH, IMAGES_DIR], token, repo_slug(),
                                    f"Remove lure inventory item {row['item_id']}",
                                )
                            st.rerun()
