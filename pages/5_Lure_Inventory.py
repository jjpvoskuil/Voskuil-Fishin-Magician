from pathlib import Path

import streamlit as st

from core.appstate import get_inventory, github_token, repo_slug
from core.lure_inventory import (
    IMAGES_DIR, INVENTORY_PATH, LureItem, append_item, delete_item, save_image, update_item,
)
from core.storage import commit_and_push

st.set_page_config(page_title="Lure Inventory - Nolin Lake", page_icon="🧰", layout="wide")
st.title("🧰 Lure Inventory")
st.caption(
    "Your tackle box, tracked: brand, full description, a photo, the last price you paid, and "
    "how many you currently have on hand. Seeded from a Cabela's order, and grows as you add "
    "more by hand or with a photo."
)

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
        quantity = st.number_input("Quantity in inventory", min_value=0, step=1, value=1)

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
    fc1, fc2 = st.columns([2, 1])
    search = fc1.text_input("Search description or brand", placeholder="e.g. crankbait, chartreuse, Strike King")
    brand_filter = fc2.multiselect("Filter by brand", brands)

    filtered = items
    if search:
        s = search.lower()
        filtered = [r for r in filtered if s in r["description"].lower() or s in r["brand"].lower()]
    if brand_filter:
        filtered = [r for r in filtered if r["brand"] in brand_filter]

    total_qty = sum(int(r["quantity"] or 0) for r in filtered)
    total_value = sum(float(r["price"] or 0) * int(r["quantity"] or 0) for r in filtered)
    st.caption(f"{len(filtered)} lure(s) shown - {total_qty} total on hand - roughly ${total_value:,.2f} in tackle")

    cols_per_row = 3
    for i in range(0, len(filtered), cols_per_row):
        row_items = filtered[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, row in zip(cols, row_items):
            with col:
                with st.container(border=True):
                    shown = False
                    if row.get("image_filename"):
                        img_path = IMAGES_DIR / row["image_filename"]
                        if img_path.exists():
                            st.image(str(img_path), width='stretch')
                            shown = True
                    if not shown and row.get("image_url"):
                        st.image(row["image_url"], width='stretch')
                        shown = True
                    if not shown:
                        st.caption("No photo yet")

                    st.markdown(f"**{row['brand']}**")
                    st.write(row["description"])
                    price_val = float(row["price"]) if row["price"] else 0.0
                    st.caption(f"Last price: ${price_val:,.2f}  ·  Qty: {row['quantity']}")

                    with st.expander("Edit"):
                        new_qty = st.number_input(
                            "Quantity", min_value=0, step=1,
                            value=int(row["quantity"] or 0), key=f"qty_{row['item_id']}",
                        )
                        new_price = st.number_input(
                            "Last price ($)", min_value=0.0, step=0.01,
                            value=price_val, key=f"price_{row['item_id']}",
                        )
                        ec1, ec2 = st.columns(2)
                        if ec1.button("Save", key=f"save_{row['item_id']}", width='stretch'):
                            update_item(row["item_id"], quantity=new_qty, price=new_price)
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
