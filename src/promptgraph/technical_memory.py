"""PersistentTechnicalMemory — durable notes via SafeJsonStore (NEW-01)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .decision_ledger import DecisionLedger
from .exceptions import CorruptStorageError
from .safe_json_store import SafeJsonStore


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
        self._store = SafeJsonStore(
            self.path,
            trusted_root=self.trusted_root,
            default=lambda: {"notes": {}},
        )
        self._notes: dict[str, dict[str, Any]] = {}
        self.ledger: DecisionLedger | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = self._store.read()
            if not isinstance(data, dict):
                raise ValueError("Memory root is not a JSON object.")
            self._notes = dict(data.get("notes", {}))
        except CorruptStorageError:
            self._notes = {}
            raise

    def with_decision_ledger(self, ledger: DecisionLedger) -> TechnicalMemory:
        self.ledger = ledger
        return self

    def record_note(self, key: str, content: str, tags: list[str] | None = None) -> str:
        if not key or not content:
            raise ValueError("key and content must be non-empty.")
        note = {
            "key": key,
            "content": content,
            "tags": list(tags or []),
        }

        def mutator(disk: object) -> dict:
            if not isinstance(disk, dict):
                disk = {"notes": {}}
            notes = dict(disk.get("notes", {}))
            # Merge disk notes into memory
            for k, v in notes.items():
                if k not in self._notes:
                    self._notes[k] = v
            self._notes[key] = note
            return {"notes": dict(self._notes)}

        self._store.update(mutator)
        return key

    def get_note(self, key: str) -> dict[str, Any] | None:
        # Prefer fresh disk view for concurrent readers
        if self.path.exists():
            try:
                data = self._store.read()
                if isinstance(data, dict):
                    notes = data.get("notes", {})
                    if key in notes:
                        return notes[key]
            except CorruptStorageError:
                pass
        return self._notes.get(key)

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        # Refresh notes from disk
        if self.path.exists():
            try:
                data = self._store.read()
                if isinstance(data, dict):
                    self._notes = dict(data.get("notes", {}))
            except CorruptStorageError:
                pass
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
