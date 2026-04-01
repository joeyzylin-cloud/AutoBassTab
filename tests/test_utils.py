"""Tests for shared utility functions."""

from pathlib import Path

from src.utils import ensure_dir


class TestEnsureDir:
    """Tests for ensure_dir()."""

    def test_creates_missing_directory(self, tmp_path: Path) -> None:
        """Creates a new directory if it does not exist."""
        new_dir = tmp_path / "new_dir"
        result = ensure_dir(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result == new_dir

    def test_idempotent_on_existing_directory(self, tmp_path: Path) -> None:
        """Does not raise if the directory already exists."""
        existing = tmp_path / "existing"
        existing.mkdir()
        result = ensure_dir(existing)
        assert existing.exists()
        assert result == existing

    def test_returns_same_path(self, tmp_path: Path) -> None:
        """Return value is identical to the input path."""
        path = tmp_path / "returned"
        result = ensure_dir(path)
        assert result == path

    def test_creates_deep_nested_parents(self, tmp_path: Path) -> None:
        """Creates all intermediate parent directories."""
        deep = tmp_path / "a" / "b" / "c" / "d"
        ensure_dir(deep)
        assert deep.exists()
        assert (tmp_path / "a" / "b").exists()
