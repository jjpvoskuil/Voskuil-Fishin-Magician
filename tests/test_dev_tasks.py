import csv

from core.dev_tasks import (
    DevTask, FIELDNAMES, PAGE_OPTIONS, STATUS_DONE, STATUS_OPEN, append_task,
    delete_task, mark_done, read_all_tasks, reopen_task, update_task,
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
    task = append_task("Some issue", "Tackle Box", path)
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


def test_delete_task_removes_row(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    task1 = append_task("Item one", "Lake Map", path)
    task2 = append_task("Item two", "Lake Map", path)
    assert delete_task(task1.task_no, path) is True
    rows = read_all_tasks(path)
    assert len(rows) == 1
    assert rows[0]["task_no"] == str(task2.task_no)


def test_delete_task_missing_task_no_returns_false(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    assert delete_task(999, path) is False


def test_deleting_the_highest_numbered_task_does_not_reuse_its_number(tmp_path):
    # The whole point of a small human-friendly task_no (vs. every other id
    # in this app, which is a uuid) is that it's memorized and referenced by
    # number - so unlike a uuid, silently reusing #5 for a brand-new,
    # unrelated item after the original #5 was deleted would be genuinely
    # confusing. The sidecar counter file (see core/dev_tasks.py's module
    # docstring) is what prevents that.
    path = tmp_path / "dev_tasks.csv"
    append_task("Item one", "Lake Map", path)
    second = append_task("Item two", "Lake Map", path)
    assert second.task_no == 2
    assert delete_task(second.task_no, path) is True
    third = append_task("Item three", "Lake Map", path)
    assert third.task_no == 3  # not 2 - the deleted number is never reissued


def test_deleting_a_middle_task_does_not_reuse_its_number_either(tmp_path):
    path = tmp_path / "dev_tasks.csv"
    append_task("Item one", "Lake Map", path)
    append_task("Item two", "Lake Map", path)
    append_task("Item three", "Lake Map", path)
    assert delete_task(2, path) is True
    fourth = append_task("Item four", "Lake Map", path)
    assert fourth.task_no == 4
    assert [r["task_no"] for r in read_all_tasks(path)] == ["1", "3", "4"]


def test_next_task_no_bootstraps_from_existing_rows_when_counter_file_missing(tmp_path):
    # Simulates data/dev_tasks.csv as it existed before the counter file was
    # introduced (or a hand-edited file with no counter alongside it) - the
    # next append should still continue past whatever's already there.
    path = tmp_path / "dev_tasks.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow({
            "task_no": "1", "created_at": "2026-08-15T00:00:00", "description": "Pre-existing item",
            "page": "Spot Session", "status": STATUS_OPEN, "completed_at": "",
        })
    assert not path.with_name("dev_tasks_counter.txt").exists()
    task = append_task("New item after bootstrap", "Lake Map", path)
    assert task.task_no == 2


def test_page_options_include_every_real_page():
    # Keep in sync with app.py's st.navigation titles - a stale list here
    # would mean the dropdown can't tag an item against a page that exists.
    for title in [
        "Today (Home)", "7 Day Forecast", "Lake Map", "Trip History",
        "Tackle Box", "Spot Session", "Development",
    ]:
        assert title in PAGE_OPTIONS


def test_dev_task_dataclass_to_row_matches_fieldnames():
    task = DevTask(description="x", page="Lake Map", task_no=5)
    assert set(task.to_row().keys()) == set(FIELDNAMES)
