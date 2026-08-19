"""Best-effort local Git metadata. Never required, never networked."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def project_git_state(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    commit = _run(root, "rev-parse", "HEAD")
    porcelain = _run(root, "status", "--porcelain")
    dirty = None if porcelain is None else bool(porcelain)
    return {
        "commit": commit,
        "dirty": dirty,
        "available": commit is not None,
    }
