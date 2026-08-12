"""Path containment validation (PG-04 / P1-02 / P2-01).

Ensures that paths used by persistent writers do not escape their intended
base directory through symlinks, Windows junctions, or reparse points.

Threat model (documented):
  We re-validate containment immediately before creating lock/temp/destination
  artifacts.  A fully race-free guarantee against a privileged concurrent
  attacker swapping directory entries between every syscall is not promised
  on all platforms; the contract is best-effort TOCTOU reduction so that
  rejected operations leave ZERO artifacts outside trusted_root under the
  tested junction/symlink swap scenarios.
"""

from __future__ import annotations

import os
from pathlib import Path

from .exceptions import PathEscapeError


def resolve_canonical(path: str | Path) -> Path:
    """Resolve a path to its canonical form, following symlinks/junctions."""
    p = Path(path)
    resolved = os.path.realpath(str(p))
    return Path(resolved)


def normalize_path_key(path: str | Path) -> str:
    """Normalize for comparison (case on Windows, slash style)."""
    s = os.path.normpath(str(path))
    if os.name == "nt":
        s = os.path.normcase(s)
    return s


def is_project_local_agentops(path: str | Path) -> bool:
    """True if path is a project-local .agentops path (any equivalent spelling).

    Does NOT use naive startswith('.agentops').  Handles:
      .agentops/...
      ./.agentops/...
      .\\.agentops\\...
      absolute .../.agentops/...
    """
    p = Path(path)
    if any(part == ".agentops" for part in p.parts):
        return True
    # Also check normalized string for /.agentops/ or leading .agentops
    norm = p.as_posix()
    if norm == ".agentops" or norm.startswith(".agentops/"):
        return True
    if "/.agentops/" in f"/{norm}/" or norm.endswith("/.agentops"):
        return True
    return False


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

    base_cmp = normalize_path_key(base_canonical)
    tgt_cmp = normalize_path_key(target_canonical)

    try:
        Path(tgt_cmp).relative_to(Path(base_cmp))
    except ValueError as exc:
        raise PathEscapeError(
            f"Path '{target}' resolves to '{target_canonical}' which is "
            f"outside the allowed base '{base_canonical}'."
        ) from exc

    return target_canonical


def assert_path_family_contained(
    *targets: str | Path,
    trusted_root: str | Path,
) -> None:
    """Validate every target (and deepest existing ancestor) stays in root."""
    root = resolve_canonical(trusted_root)
    for target in targets:
        t = Path(target)
        # Walk existing ancestors
        cur = t
        while True:
            if cur.exists():
                validate_contained(cur, root)
                break
            if cur.parent == cur:
                break
            cur = cur.parent
        # Always check resolved form
        resolved = resolve_canonical(t)
        try:
            validate_contained(resolved, root)
        except PathEscapeError:
            raise
        # If nothing existed, ensure resolved string under root
        base_cmp = normalize_path_key(root)
        tgt_cmp = normalize_path_key(resolved)
        try:
            Path(tgt_cmp).relative_to(Path(base_cmp))
        except ValueError as exc:
            raise PathEscapeError(
                f"Path '{target}' resolves to '{resolved}' outside '{root}'."
            ) from exc


def safe_join(base: str | Path, *parts: str) -> Path:
    """Join ``parts`` onto ``base`` and validate the result is contained."""
    base_path = Path(base)
    joined = base_path.joinpath(*parts)
    return validate_contained(joined, base_path)
