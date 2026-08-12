"""PersistentTechnicalMemory — durable storage of technical facts.

PG-04: path containment via trusted_root.
PG-09: corrupt JSON quarantined as CorruptStorageError.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .decision_ledger import DecisionLedger
from .exceptions import CorruptStorageError
from .path_security import resolve_canonical, validate_contained


class TechnicalMemory:
    """Persistent technical memory storing notes and decisions by key."""

    def __init__(
        self,
        path: str | Path = "memory.json",
        *,
        trusted_root: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.trusted_root = Path(trusted_root) if trusted_root is not None else None
        if self.trusted_root is not None:
            self._assert_contained(self.path)
        self._notes: dict[str, dict[str, Any]] = {}
        self.ledger: DecisionLedger | None = None
        self._load()

    def _assert_contained(self, target: Path) -> None:
        if self.trusted_root is None:
            return
        root = resolve_canonical(self.trusted_root)
        cur = target
        while True:
            if cur.exists():
                validate_contained(cur, root)
                break
            if cur == cur.parent:
                break
            cur = cur.parent
        # Also check final resolved path
        validate_contained(resolve_canonical(target if target.exists() else target.parent), root)

    def _load(self) -> None:
        if not self.path.exists():
            return
        if self.trusted_root is not None:
            self._assert_contained(self.path)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Memory root is not a JSON object.")
            self._notes = dict(data.get("notes", {}))
        except (json.JSONDecodeError, ValueError) as exc:
            quarantined = self.path.with_suffix(self.path.suffix + ".corrupt")
            try:
                self.path.rename(quarantined)
            except OSError:
                quarantined = None  # type: ignore[assignment]
            self._notes = {}
            raise CorruptStorageError(
                f"Technical memory at {self.path} is corrupt: {exc}. "
                f"The corrupt file has been quarantined.",
                quarantined_path=str(quarantined) if quarantined else None,
            ) from exc

    def _save(self) -> None:
        if self.trusted_root is not None:
            self._assert_contained(self.path)
        payload = {"notes": self._notes}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import os
        import tempfile

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=f".{os.getpid()}.tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2, default=str))
                fh.flush()
                os.fsync(fh.fileno())
            Path(tmp_name).replace(self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def with_decision_ledger(self, ledger: DecisionLedger) -> TechnicalMemory:
        self.ledger = ledger
        return self

    def record_note(self, key: str, content: str, tags: list[str] | None = None) -> str:
        if not key or not content:
            raise ValueError("key and content must be non-empty.")
        self._notes[key] = {
            "key": key,
            "content": content,
            "tags": list(tags or []),
        }
        self._save()
        return key

    def get_note(self, key: str) -> dict[str, Any] | None:
        return self._notes.get(key)

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        results: list[dict[str, Any]] = []
        for key, note in self._notes.items():
            if (
                q in note["content"].lower()
                or q in " ".join(note["tags"]).lower()
                or q in key.lower()
            ):
                results.append({**note, "kind": "note"})
        if self.ledger is not None:
            for d in self.ledger.search(query, limit=len(self.ledger)):
                results.append(
                    {
                        "key": d.id,
                        "content": d.decision,
                        "tags": [],
                        "kind": "decision",
                        "title": d.title,
                    }
                )
        results = results[:limit]
        return sorted(results, key=lambda r: r.get("kind", ""))
