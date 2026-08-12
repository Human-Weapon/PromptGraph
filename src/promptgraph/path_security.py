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


def is_project_local_agentops(path: str | Path, *, project_root: str | Path | None = None) -> bool:
    """True if path is beneath this project's ``.agentops`` directory.

    Does NOT use naive ``startswith('.agentops')``. Handles:
      .agentops/...
      ./.agentops/...
      .\\.agentops\\...
      absolute <project>/.agentops/...

    An unrelated absolute path that merely contains a directory named
    ``.agentops`` is caller-configured storage, not this project's default
    storage, and must not silently inherit this project's trusted root.
    """
    root = Path.cwd() if project_root is None else Path(project_root)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate

    root_key = Path(normalize_path_key(os.path.abspath(root)))
    candidate_key = Path(normalize_path_key(os.path.abspath(candidate)))
    try:
        relative = candidate_key.relative_to(root_key)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == ".agentops"


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
