"""
Development - a punch list of things to adjust or fix in the app itself.

Purpose: give the angler a place to jot down anything they want changed
(a bug, a tweak, an idea) as soon as they notice it, tagged with a stable
`task_no` and the page it's mainly about. In a future Claude session, the
angler can just say "let's do #7" (or Claude can read this list and ask
which number to work on) instead of re-describing the issue from memory or
digging through SESSION_NOTES.md's open-items section. Deliberately kept
to the three fields the angler asked for - description, page, done/not -
plus the auto-assigned number; see core/dev_tasks.py for why this is
append-only (no delete).
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from core.appstate import get_dev_tasks, github_token, repo_slug
from core.dev_tasks import (
    DEV_TASKS_PATH, PAGE_OPTIONS, STATUS_DONE, STATUS_OPEN, append_task, update_task,
)
from core.storage import commit_and_push
from core.ui import inject_mobile_css

st.set_page_config(page_title="Development - Nolin Lake", page_icon="🛠️", layout="wide")
inject_mobile_css()
st.title("🛠️ Development")
st.caption(
    "Your punch list for this app. Jot down anything you want adjusted or fixed as soon as "
    "you notice it - each item gets its own number. Next session, just reference a number "
    "(\"let's do #7\") or ask me to look at this list and suggest what's next."
)

with st.expander("➕ Add an item", expanded=True):
    with st.form("add_dev_task_form", clear_on_submit=True):
        description = st.text_area(
            "What needs adjusting or fixing?",
            placeholder="e.g. Trip History date filter doesn't reset when I clear the other filters",
        )
        page = st.selectbox("Mainly associated with", PAGE_OPTIONS)
        submitted = st.form_submit_button("Add to punch list", width="stretch")

    if submitted:
        if not description.strip():
            st.warning("Add a description before saving.")
        else:
            task = append_task(description, page)
            get_dev_tasks.clear()
            token = github_token()
            if token:
                ok, msg = commit_and_push(
                    [DEV_TASKS_PATH], token, repo_slug(),
                    f"Add dev punch-list item #{task.task_no}: {task.description[:50]}",
                )
                (st.success if ok else st.warning)(f"#{task.task_no} added. {msg}")
            else:
                st.success(f"#{task.task_no} added locally.")
                st.info(
                    "No GITHUB_TOKEN configured in Streamlit secrets, so this entry wasn't pushed "
                    "to GitHub and won't survive an app restart. See README for how to add it."
                )
            st.rerun()

st.divider()

rows = get_dev_tasks()

if not rows:
    st.info("No punch-list items yet - add your first one above.")
    st.stop()

show_completed = st.checkbox("Show completed items", value=False)

df = pd.DataFrame(rows)
df["task_no"] = pd.to_numeric(df["task_no"], errors="coerce").fillna(0).astype(int)
df["_done"] = df["status"] == STATUS_DONE

open_count = int((~df["_done"]).sum())
done_count = int(df["_done"].sum())
st.caption(f"{open_count} open · {done_count} completed")

visible = df if show_completed else df[~df["_done"]]

if visible.empty:
    st.info("Nothing open right now - nice work. Check \"Show completed items\" to see finished ones.")
else:
    st.caption(
        "Check \"Done\" off as you finish something - saves automatically. Description and "
        "page are editable too, in case you want to fix a typo or re-tag an item."
    )

    grid_sorted = visible.sort_values("task_no")
    grid_display = grid_sorted.set_index("task_no")[["_done", "description", "page", "created_at"]].copy()
    grid_display = grid_display.rename(columns={"created_at": "added"})

    # Options must already include every value actually present in the data
    # (SelectboxColumn errors otherwise) - matches the canonical-plus-observed
    # pattern used by Trip History's grid.
    page_options = sorted(set(PAGE_OPTIONS) | set(v for v in grid_display["page"].dropna().unique().tolist() if v))

    edited_grid = st.data_editor(
        grid_display,
        key="dev_tasks_grid_editor",
        width="stretch",
        hide_index=False,
        num_rows="fixed",
        disabled=["added"],
        column_config={
            "_done": st.column_config.CheckboxColumn("Done"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "page": st.column_config.SelectboxColumn("Page", options=page_options),
            "added": st.column_config.TextColumn("Added"),
        },
    )

    # Auto-save: st.data_editor commits (and reruns) as soon as a cell edit is
    # confirmed, so diffing the just-rendered edited copy against grid_display
    # on every run is enough - no separate "Save" button, matching Trip
    # History's grid.
    changed_ids = []
    for task_no in grid_display.index:
        if task_no not in edited_grid.index:
            continue
        old_done = bool(grid_display.loc[task_no, "_done"])
        new_done = bool(edited_grid.loc[task_no, "_done"])
        old_desc = str(grid_display.loc[task_no, "description"]).strip()
        new_desc = str(edited_grid.loc[task_no, "description"]).strip()
        old_page = str(grid_display.loc[task_no, "page"]).strip()
        new_page = str(edited_grid.loc[task_no, "page"]).strip()
        if (old_done, old_desc, old_page) == (new_done, new_desc, new_page):
            continue
        changes = {"description": new_desc, "page": new_page}
        if new_done != old_done:
            changes["status"] = STATUS_DONE if new_done else STATUS_OPEN
            changes["completed_at"] = datetime.utcnow().isoformat() if new_done else ""
        if update_task(int(task_no), **changes):
            changed_ids.append(int(task_no))

    if changed_ids:
        get_dev_tasks.clear()
        token = github_token()
        if token:
            plural = "s" if len(changed_ids) != 1 else ""
            commit_and_push(
                [DEV_TASKS_PATH], token, repo_slug(),
                f"Update dev punch-list item{plural} #{', #'.join(str(i) for i in changed_ids)}",
            )
        st.toast(f"Saved #{', #'.join(str(i) for i in changed_ids)}.", icon="✅")
        st.rerun()
