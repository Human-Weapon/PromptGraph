from __future__ import annotations

from pathlib import Path

import pytest

from promptgraph.memory import ProjectMemory


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


@pytest.fixture
def memory(project: Path) -> ProjectMemory:
    mem = ProjectMemory(project, trusted_root=project)
    mem.init()
    return mem
