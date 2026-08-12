"""Atomic locked JSON store — shared persistence primitive.

Used by DecisionLedger and TechnicalMemory so concurrency / path /
corruption guarantees are implemented once (NEW-01 architectural lesson).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .exceptions import CorruptStorageError, DecisionError, PathEscapeError
from .path_security import resolve_canonical, validate_contained

_LOCK_TIMEOUT_S = 10.0
_LOCK_POLL_S = 0.05


class FileLock:
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
                self._fh = open(self.lock_path, "a+b")  # noqa: SIM115
                if os.name == "nt":
                    import msvcrt

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

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


class SafeJsonStore:
    """Process-safe JSON document store with path containment."""

    def __init__(
        self,
        path: str | Path,
        *,
        trusted_root: str | Path | None = None,
        default: Callable[[], Any] | None = None,
    ) -> None:
        self.path = Path(path)
        self.trusted_root = Path(trusted_root) if trusted_root is not None else None
        self._default = default or (lambda: {})
        if self.trusted_root is not None:
            self.assert_contained(self.path)

    def assert_contained(self, target: Path) -> None:
        if self.trusted_root is None:
            return
        root = resolve_canonical(self.trusted_root)
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
        resolved = resolve_canonical(target)
        try:
            validate_contained(resolved, root)
        except PathEscapeError:
            raise
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

    def read(self) -> Any:
        """Read JSON from disk (no lock). Returns default if missing."""
        if not self.path.exists():
            return self._default()
        if self.trusted_root is not None:
            self.assert_contained(self.path)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            quarantined = self.path.with_suffix(self.path.suffix + ".corrupt")
            try:
                self.path.rename(quarantined)
            except OSError:
                quarantined = None  # type: ignore[assignment]
            raise CorruptStorageError(
                f"JSON store at {self.path} is corrupt: {exc}. Quarantined.",
                quarantined_path=str(quarantined) if quarantined else None,
            ) from exc

    def write_atomic(self, data: Any) -> None:
        """Write JSON atomically with unique temp (caller must hold lock)."""
        if self.trusted_root is not None:
            self.assert_contained(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, default=str)
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

    def update(self, mutator: Callable[[Any], Any]) -> Any:
        """Lock → read → mutator(data) → write. Returns new data."""
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with FileLock(lock_path):
            try:
                current = self.read()
            except CorruptStorageError:
                raise
            new_data = mutator(current)
            try:
                self.write_atomic(new_data)
            except OSError as exc:
                raise DecisionError(f"Cannot write store {self.path}: {exc}") from exc
            return new_data
