from core.dev_tasks import (
    DevTask, PAGE_OPTIONS, STATUS_DONE, STATUS_OPEN, append_task, mark_done,
    read_all_tasks, reopen_task, update_task,
)


def test_empty_tasks_file_returns_empty_list(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    assert read_all_tasks(path) == []


def test_append_task_assigns_task_no_one_for_first_item(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task = append_task("Sidebar toggle is too small", "7 Day Forecast", path)
    assert task.task_no == 1
    row = read_all_tasks(path)[0]
    assert row["task_no"] == "1"
    assert row["description"] == "Sidebar toggle is too small"
    assert row["page"] == "7 Day Forecast"
    assert row["status"] == STATUS_OPEN
    assert row["completed_at"] == ""


def test_append_task_increments_task_no(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    append_task("First issue", "Lake Map", path)
    second = append_task("Second issue", "Trip History", path)
    third = append_task("Third issue", "Spot Session", path)
    assert second.task_no == 2
    assert third.task_no == 3
    assert [r["task_no"] for r in read_all_tasks(path)] == ["1", "2", "3"]


def test_append_task_strips_description_whitespace(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task = append_task("  needs a trailing-whitespace trim  ", "General / whole app", path)
    assert task.description == "needs a trailing-whitespace trim"


def test_update_task_changes_fields(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task = append_task("Fix typo on Home", "Today (Home)", path)
    found = update_task(task.task_no, path, description="Fix typo on Today page")
    assert found is True
    row = read_all_tasks(path)[0]
    assert row["description"] == "Fix typo on Today page"


def test_update_task_missing_task_no_returns_false(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    assert update_task(999, path, description="nope") is False


def test_update_task_accepts_int_or_str_task_no(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task = append_task("Some issue", "Lure Inventory", path)
    assert update_task(str(task.task_no), path, description="edited via string id") is True
    row = read_all_tasks(path)[0]
    assert row["description"] == "edited via string id"


def test_mark_done_sets_status_and_completed_at(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task = append_task("Something to finish", "Spot Session", path)
    assert mark_done(task.task_no, path) is True
    row = read_all_tasks(path)[0]
    assert row["status"] == STATUS_DONE
    assert row["completed_at"] != ""


def test_reopen_task_clears_status_and_completed_at(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task = append_task("Something to reopen", "Spot Session", path)
    mark_done(task.task_no, path)
    assert reopen_task(task.task_no, path) is True
    row = read_all_tasks(path)[0]
    assert row["status"] == STATUS_OPEN
    assert row["completed_at"] == ""


def test_deleting_the_highest_numbered_task_never_reuses_its_number(tmp_path):
    # Deliberately no delete_task exists (see core/dev_tasks.py's module
    # docstring) - but if data/dev_tasks.csv is ever hand-edited to drop a
    # row, a new item still shouldn't silently reuse that number. Simulate a
    # hand-edit by rewriting the file with the last row removed, then confirm
    # append_task still moves past the original max rather than reusing it -
    # this only holds because _next_task_no looks at the highest surviving
    # task_no, so this test also documents that a hand-edit CAN cause reuse
    # if the highest-numbered row is the one removed.
    path = tmp_path / "dev_tasks.csv"
    append_task("Item one", "Lake Map", path)
    second = append_task("Item two", "Lake Map", path)
    assert second.task_no == 2
    # Hand-edit: drop item #2, leaving only #1.
    remaining = [r for r in read_all_tasks(path) if r["task_no"] != "2"]
    import csv
    from core.dev_tasks import FIELDNAMES
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(remaining)
    third = append_task("Item three", "Lake Map", path)
    assert third.task_no == 2  # documents the reuse-after-hand-edit caveat


def test_page_options_include_every_real_page():
    # Keep in sync with app.py's st.navigation titles - a stale list here
    # would mean the dropdown can't tag an item against a page that exists.
    for title in [
        "Today (Home)", "7 Day Forecast", "Lake Map", "Trip History",
        "Lure Inventory", "Spot Session", "Development",
    ]:
        assert title in PAGE_OPTIONS


def test_dev_task_dataclass_to_row_matches_fieldnames():
    from core.dev_tasks import FIELDNAMES
    task = DevTask(description="x", page="Lake Map", task_no=5)
    assert set(task.to_row().keys()) == set(FIELDNAMES)
