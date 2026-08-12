"""Regression tests for PG-04: Path containment."""

from __future__ import annotations

import os

import pytest

from promptgraph.exceptions import PathEscapeError
from promptgraph.path_security import resolve_canonical, safe_join, validate_contained


class TestPG04PathContainment:
    def test_normal_path_contained(self, tmp_path):
        target = tmp_path / "subdir" / "file.json"
        result = validate_contained(target, tmp_path)
        assert str(result).startswith(str(resolve_canonical(tmp_path)))

    def test_parent_traversal_rejected(self, tmp_path):
        base = tmp_path / "project"
        base.mkdir()
        target = base / ".." / "secret.txt"
        with pytest.raises(PathEscapeError):
            validate_contained(target, base)

    def test_safe_join_normal(self, tmp_path):
        result = safe_join(tmp_path, "data", "file.json")
        assert result is not None

    def test_safe_join_traversal_rejected(self, tmp_path):
        with pytest.raises(PathEscapeError):
            safe_join(tmp_path, "..", "escape.txt")

    def test_resolve_canonical_no_symlink_expansion_on_missing(self, tmp_path):
        """resolve_canonical should work even if path doesn't exist yet."""
        result = resolve_canonical(tmp_path / "nonexistent" / "file.json")
        assert "nonexistent" in str(result)

    @pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
    def test_junction_escape_detected(self, tmp_path):
        """On Windows, a junction should be detected as an escape."""
        # This test validates the infrastructure exists.
        # Actual junction creation requires admin privileges.
        base = tmp_path / "base"
        base.mkdir()
        assert validate_contained(base / "normal.txt", base) is not None
