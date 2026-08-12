"""DecisionLedger — durable decision storage with process-safe writes.

PG-03 (round 2): process-level integrity
  - exclusive file lock across processes
  - unique temp files (no shared decisions.json.tmp)
  - re-read after lock, merge, atomic replace
  - duplicate IDs rejected under lock

PG-04 (round 2): path containment wired
  - optional trusted_root; when set, path must stay inside it
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from .exceptions import (
    CorruptStorageError,
    DecisionError,
    DuplicateDecisionError,
    PathEscapeError,
)
from .models import Decision
from .path_security import resolve_canonical, validate_contained

_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.05


class _FileLock:
    """Cross-platform exclusive file lock (Windows msvcrt / POSIX fcntl)."""

    def __init__(self, lock_path: Path, timeout: float = _LOCK_TIMEOUT_S) -> None:
        self.lock_path = lock_path
        self.timeout = timeout
        self._fh = None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                # Open/create lock file
                self._fh = open(self.lock_path, "a+b")  # noqa: SIM115
                if os.name == "nt":
                    import msvcrt

                    # Lock one byte
                    self._fh.seek(0)
                    if self._fh.tell() == 0:
                        self._fh.write(b"\0")
                        self._fh.flush()
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                if self._fh is not None:
                    try:
                        self._fh.close()
                    except OSError:
                        pass
                    self._fh = None
                if time.monotonic() >= deadline:
                    raise DecisionError(
                        f"Could not acquire lock on {self.lock_path} within {self.timeout}s"
                    ) from None
                time.sleep(_LOCK_POLL_S)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None

    def __enter__(self) -> _FileLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


class DecisionLedger:
    """A durable log of decisions backed by a JSON file."""

    def __init__(
        self,
        path: str | Path = "decisions.json",
        *,
        trusted_root: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.trusted_root = Path(trusted_root) if trusted_root is not None else None
        if self.trusted_root is not None:
            # Validate the intended path stays inside trusted root (PG-04).
            # Parent may not exist yet — validate the resolved path.
            self._assert_contained(self.path)
        self._items: dict[str, Decision] = {}
        self._load()

    def _assert_contained(self, target: Path) -> None:
        if self.trusted_root is None:
            return
        root = resolve_canonical(self.trusted_root)
        # Walk up to the deepest existing path component and validate it.
        cur = Path(target)
        checked = False
        while True:
            if cur.exists():
                validate_contained(cur, root)
                checked = True
                break
            if cur.parent == cur:
                break
            cur = cur.parent
        # Always validate the fully resolved form of the target path.
        # realpath resolves junctions/symlinks in existing prefixes.
        resolved = resolve_canonical(target)
        try:
            validate_contained(resolved if resolved.exists() else resolved, root)
        except PathEscapeError:
            raise
        # If nothing existed yet, still ensure resolved string is under root
        if not checked:
            base_cmp = str(root)
            tgt_cmp = str(resolved)
            if os.name == "nt":
                base_cmp = os.path.normcase(base_cmp)
                tgt_cmp = os.path.normcase(tgt_cmp)
            try:
                Path(tgt_cmp).relative_to(Path(base_cmp))
            except ValueError as exc:
                raise PathEscapeError(
                    f"Path '{target}' resolves to '{resolved}' outside '{root}'."
                ) from exc

    def _load(self) -> None:
        if not self.path.exists():
            return
        if self.trusted_root is not None:
            self._assert_contained(self.path)
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Ledger root is not a JSON object.")
            self._items = {}
            for key, val in data.items():
                self._items[key] = Decision.from_dict(val)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            quarantined = self.path.with_suffix(self.path.suffix + ".corrupt")
            try:
                self.path.rename(quarantined)
            except OSError:
                quarantined = None  # type: ignore[assignment]
            self._items = {}
            raise CorruptStorageError(
                f"Decision ledger at {self.path} is corrupt or malformed: {exc}. "
                f"The corrupt file has been quarantined.",
                quarantined_path=str(quarantined) if quarantined else None,
            ) from exc

    def _read_disk(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _save_locked(self, items: dict[str, Decision]) -> None:
        """Write items under lock using a unique temp file + atomic replace."""
        if self.trusted_root is not None:
            self._assert_contained(self.path)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Re-read AFTER lock held by caller
        disk = self._read_disk()
        merged: dict[str, dict] = dict(disk)
        for key, d in items.items():
            merged[key] = d.to_dict()

        payload = json.dumps(merged, indent=2, default=str)
        # Unique temp in same directory for atomic replace on same volume
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=f".{os.getpid()}.tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            Path(tmp_name).replace(self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def record(self, decision: Decision) -> str:
        """Store a decision and return its id. Process-safe."""
        if not decision.id:
            raise DecisionError("Decision must have a non-empty id.")

        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with _FileLock(lock_path):
            # Re-load disk under lock
            disk = self._read_disk()
            if decision.id in disk or decision.id in self._items:
                raise DuplicateDecisionError(f"A decision with id '{decision.id}' already exists.")
            # Merge memory with disk
            for key, val in disk.items():
                if key not in self._items:
                    try:
                        self._items[key] = Decision.from_dict(val)
                    except (KeyError, TypeError, ValueError):
                        pass
            self._items[decision.id] = decision
            try:
                self._save_locked(self._items)
            except OSError as exc:
                # roll back in-memory add
                self._items.pop(decision.id, None)
                raise DecisionError(f"Cannot write decision ledger: {exc}") from exc
        return decision.id

    def get(self, decision_id: str) -> Decision | None:
        return self._items.get(decision_id)

    def all(self) -> list[Decision]:
        return list(self._items.values())

    def search(self, query: str, *, in_title: str = "", limit: int = 50) -> list[Decision]:
        q = query.lower()
        hits: list[tuple[float, Decision]] = []
        for d in self._items.values():
            score = 0.0
            if q and q in d.title.lower():
                score += 3
            if q and q in d.decision.lower():
                score += 2
            if q and q in d.context.lower():
                score += 1
            if in_title and in_title.lower() not in d.title.lower():
                score = -1.0
            if score > 0:
                hits.append((score, d))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in hits[:limit]]

    def __len__(self) -> int:
        return len(self._items)
