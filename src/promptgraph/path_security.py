"""Path containment validation (PG-04).

Ensures that paths used by persistent writers (DecisionLedger,
TechnicalMemory) do not escape their intended base directory through
symlinks, Windows junctions, or resolved parent paths.
"""

from __future__ import annotations

import os
from pathlib import Path

from .exceptions import PathEscapeError


def resolve_canonical(path: str | Path) -> Path:
    """Resolve a path to its canonical form, following symlinks/junctions.

    On Windows this resolves junctions and reparse points.  On POSIX
    this follows symlinks.  ``strict=False`` is used so the path does
    not need to exist yet.
    """
    p = Path(path)
    # os.path.realpath resolves symlinks, junctions, and reparse points
    # on both Windows and POSIX.
    resolved = os.path.realpath(str(p))
    return Path(resolved)


def validate_contained(
    target: str | Path,
    base: str | Path,
) -> Path:
    """Validate that ``target`` resolves to a path inside ``base``.

    Both paths are canonicalised (symlinks/junctions resolved) before
    comparison.  Raises ``PathEscapeError`` if the target escapes.
    Returns the canonical target path on success.
    """
    base_canonical = resolve_canonical(base)
    target_canonical = resolve_canonical(target)

    try:
        target_canonical.relative_to(base_canonical)
    except ValueError as exc:
        raise PathEscapeError(
            f"Path '{target}' resolves to '{target_canonical}' which is "
            f"outside the allowed base '{base_canonical}'."
        ) from exc

    return target_canonical


def safe_join(base: str | Path, *parts: str) -> Path:
    """Join ``parts`` onto ``base`` and validate the result is contained.

    Raises ``PathEscapeError`` if any component escapes via ``..`` or
    symlink resolution.
    """
    base_path = Path(base)
    joined = base_path.joinpath(*parts)
    return validate_contained(joined, base_path)
