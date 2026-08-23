"""
Development - a punch list of things to adjust or fix in the app itself.

Purpose: give the angler a place to jot down anything they want changed
(a bug, a tweak, an idea) as soon as they notice it, tagged with a stable
`task_no` and the page it's mainly about. In a future Claude session, the
angler can just say "let's do #7" (or Claude can read this list and ask
which number to work on) instead of re-describing the issue from memory or
digging through SESSION_NOTES.md's open-items section.

Deliberately built with plain widgets (checkbox/text_area/selectbox/button)
rather than st.data_editor - this page is exactly the kind of thing the
angler would use standing at the lake to jot something down, and Trip
History's data_editor grid (glide-data-grid under the hood) has real,
still-unverified touch/swipe behavior on a phone (see SESSION_NOTES.md
entry 57); plain widgets are the same pattern already proven to work well
on mobile elsewhere in this app (Spot Session's live-conditions inputs).
Each item has its own explicit Edit (description/page, with a Save button)
and Delete (two-step confirm, matching Trip History's delete pattern -
deleting a punch-list item is as permanent as deleting a trip) controls,
plus an immediate Done/reopen checkbox that saves the moment it's toggled.
See core/dev_tasks.py for why numbers are never reused, even after delete.
"""
import streamlit as st

from core.appstate import get_dev_tasks, github_token, repo_slug
from core.dev_tasks import (
    DEV_TASKS_COUNTER_PATH, DEV_TASKS_PATH, PAGE_OPTIONS, STATUS_DONE,
    append_task, delete_task, mark_done, reopen_task, update_task,
)
from core.storage import commit_and_push_data
from core.ui import inject_mobile_css

st.set_page_config(page_title="Development - Nolin Lake", page_icon="🛠️", layout="wide")
inject_mobile_css()
st.title("🛠️ Development")
st.caption(
    "Your punch list for this app. Jot down anything you want adjusted or fixed as soon as "
    "you notice it - each item gets its own number. Next session, just reference a number "
    "(\"let's do #7\") or ask me to look at this list and suggest what's next."
)

COMMIT_PATHS = [DEV_TASKS_PATH, DEV_TASKS_COUNTER_PATH]


def _push(message: str):
    token = github_token()
    if token:
        return commit_and_push_data(COMMIT_PATHS, token, repo_slug(), message)
    return True, None


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
            ok, msg = _push(f"Add dev punch-list item #{task.task_no}: {task.description[:50]}")
            if msg:
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

open_count = sum(1 for r in rows if r["status"] != STATUS_DONE)
done_count = len(rows) - open_count
st.caption(f"{open_count} open · {done_count} completed")

visible = [r for r in rows if show_completed or r["status"] != STATUS_DONE]
visible.sort(key=lambda r: int(r["task_no"]))

if not visible:
    st.info("Nothing open right now - nice work. Check \"Show completed items\" to see finished ones.")

for row in visible:
    task_no = row["task_no"]
    is_done = row["status"] == STATUS_DONE

    with st.container(border=True):
        check_col, body_col = st.columns([1, 10])
        new_done = check_col.checkbox(
            "Done", value=is_done, key=f"done_{task_no}", label_visibility="collapsed",
        )
        label = f"~~#{task_no} · {row['description']}~~" if is_done else f"**#{task_no}** · {row['description']}"
        body_col.markdown(label)
        body_col.caption(f"Page: {row['page']}" + (f" · Completed {row['completed_at'][:10]}" if row.get("completed_at") else ""))

        if new_done != is_done:
            ok = mark_done(task_no) if new_done else reopen_task(task_no)
            if ok:
                get_dev_tasks.clear()
                _push(f"Mark dev punch-list item #{task_no} as {'Done' if new_done else 'Open'}")
                st.toast(f"#{task_no} marked {'Done' if new_done else 'Open'}.", icon="✅")
            st.rerun()

        with st.expander("✏️ Edit or delete"):
            edit_desc = st.text_area("Description", value=row["description"], key=f"edit_desc_{task_no}")
            page_options = sorted(set(PAGE_OPTIONS) | {row["page"]}) if row["page"] not in PAGE_OPTIONS else PAGE_OPTIONS
            edit_page = st.selectbox(
                "Mainly associated with", page_options,
                index=page_options.index(row["page"]) if row["page"] in page_options else 0,
                key=f"edit_page_{task_no}",
            )
            save_col, delete_col = st.columns(2)
            if save_col.button("💾 Save changes", key=f"save_{task_no}", width="stretch"):
                if not edit_desc.strip():
                    st.warning("Description can't be empty.")
                else:
                    update_task(task_no, description=edit_desc.strip(), page=edit_page)
                    get_dev_tasks.clear()
                    _push(f"Edit dev punch-list item #{task_no}")
                    st.toast(f"#{task_no} saved.", icon="✅")
                    st.rerun()

            delete_pending_key = f"dev_task_delete_confirm_{task_no}"
            if not st.session_state.get(delete_pending_key):
                if delete_col.button("🗑️ Delete", key=f"delete_{task_no}", width="stretch"):
                    st.session_state[delete_pending_key] = True
                    st.rerun()
            else:
                st.warning(f"Delete #{task_no} permanently? This can't be undone.")
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button("Yes, delete it", key=f"confirm_delete_{task_no}", type="primary", width="stretch"):
                    if delete_task(task_no):
                        get_dev_tasks.clear()
                        _push(f"Delete dev punch-list item #{task_no}")
                        st.session_state.pop(delete_pending_key, None)
                        st.toast(f"#{task_no} deleted.", icon="✅")
                    else:
                        st.session_state.pop(delete_pending_key, None)
                        st.toast("Couldn't find that item - it may have already been removed.", icon="⚠️")
                    st.rerun()
                if cancel_col.button("Cancel", key=f"cancel_delete_{task_no}", width="stretch"):
                    st.session_state.pop(delete_pending_key, None)
                    st.rerun()
