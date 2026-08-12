"""Optional sibling integration helpers.

Implements the ecosystem's "BETTER TOGETHER" pattern with graceful degradation:
each integration is discovered at import-time via importlib.util and is
completely optional. PromptGraph works fully standalone.
"""

from __future__ import annotations

import importlib.util
from typing import Any


def is_installed(name: str) -> bool:
    """Return True if the named package is importable (installed)."""
    return importlib.util.find_spec(name) is not None


def load_sibling(name: str) -> Any | None:
    """Import and return a sibling package, or None if not installed.

    Never raises due to a missing sibling.
    """
    if not is_installed(name):
        return None
    try:
        return importlib.import_module(name)
    except (ImportError, Exception):  # noqa: BLE001 - degrade gracefully on any failure
        return None


def sibling_versions() -> dict[str, str | None]:
    """Report which ecosystem siblings are installed and their versions."""
    out: dict[str, str | None] = {}
    for name in ("agentgear", "agentbench", "projectkaizen", "skillguard", "promptgraph"):
        mod = load_sibling(name)
        if mod is not None:
            out[name] = getattr(mod, "__version__", "unknown")
        else:
            out[name] = None
    return out
