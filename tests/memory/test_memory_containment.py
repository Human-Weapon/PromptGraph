from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tests.memory.conftest import failure_candidate

from promptgraph.exceptions import PathEscapeError
from promptgraph.memory import ProjectMemory
from promptgraph.memory.models import MemoryType
from promptgraph.path_security import validate_contained


def _junction_or_symlink(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace")
            pytest.skip(f"Cannot create junction: {err}")
    else:
        os.symlink(target, link, target_is_directory=True)


def test_relative_escape_rejected(memory):
    with pytest.raises(PathEscapeError):
        memory.vault.resolve_rel("../secret.md")
    with pytest.raises(PathEscapeError):
        memory.vault.resolve_rel("..\\secret.md")


def test_absolute_escape_rejected(memory, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(PathEscapeError):
        memory.vault._assert_contained(outside)


def test_invalid_filename_rejected(memory):
    from promptgraph.exceptions import MemoryValidationError
    from promptgraph.memory.models import MemoryRecord

    with pytest.raises(MemoryValidationError):
        MemoryRecord(id="FAIL-0001/../x", type=MemoryType.FAILURE, title="bad")


def test_symlink_or_junction_escape_rejected(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    agentops = project / ".agentops"
    _junction_or_symlink(agentops, outside)
    with pytest.raises(PathEscapeError):
        mem = ProjectMemory(project, trusted_root=project)
        mem.init()
        mem.record_memory(failure_candidate())
    leaked = list(outside.rglob("*.md"))
    assert not leaked


def test_nested_link_escape(tmp_path):
    if os.name == "nt":
        pytest.skip("nested POSIX symlink test")
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    vault = project / ".agentops" / "promptgraph"
    vault.mkdir(parents=True)
    link = vault / "local"
    os.symlink(outside, link, target_is_directory=True)
    mem = ProjectMemory(project, trusted_root=project)
    mem.vault.init()
    with pytest.raises(PathEscapeError):
        mem.record_memory(failure_candidate())


def test_validate_contained_used():
    root = Path.cwd()
    validate_contained(root, root)
