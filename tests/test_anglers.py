"""Tests for core/anglers.py - punch-list #26's "who's fishing" roster."""
from core import anglers


def test_ensure_anglers_exists_seeds_defaults(tmp_path):
    path = tmp_path / "anglers.csv"
    anglers.ensure_anglers_exists(path)
    assert path.exists()
    assert anglers.read_anglers(path) == anglers.DEFAULT_ANGLERS


def test_read_anglers_missing_file_bootstraps(tmp_path):
    path = tmp_path / "anglers.csv"
    assert not path.exists()
    result = anglers.read_anglers(path)
    assert result == anglers.DEFAULT_ANGLERS
    assert path.exists()


def test_read_anglers_dedupes_case_insensitively_keeping_first_spelling(tmp_path):
    path = tmp_path / "anglers.csv"
    path.write_text("name\nJohn\nMatthew\njohn\nAlex\n")
    assert anglers.read_anglers(path) == ["John", "Matthew", "Alex"]


def test_add_angler_appends_new_name(tmp_path):
    path = tmp_path / "anglers.csv"
    anglers.ensure_anglers_exists(path)
    added = anglers.add_angler("Grandpa", path)
    assert added is True
    assert anglers.read_anglers(path) == anglers.DEFAULT_ANGLERS + ["Grandpa"]


def test_add_angler_blank_or_whitespace_does_not_touch_file(tmp_path):
    path = tmp_path / "anglers.csv"
    assert anglers.add_angler("", path) is False
    assert anglers.add_angler("   ", path) is False
    assert not path.exists()  # never even created - a no-op should touch nothing


def test_add_angler_rejects_case_insensitive_duplicate(tmp_path):
    path = tmp_path / "anglers.csv"
    anglers.ensure_anglers_exists(path)
    added = anglers.add_angler("matthew", path)
    assert added is False
    assert anglers.read_anglers(path) == anglers.DEFAULT_ANGLERS


def test_add_angler_strips_whitespace(tmp_path):
    path = tmp_path / "anglers.csv"
    anglers.ensure_anglers_exists(path)
    assert anglers.add_angler("  Grandpa  ", path) is True
    assert "Grandpa" in anglers.read_anglers(path)
