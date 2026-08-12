"""PersistentTechnicalMemory — durable notes via SafeJsonStore (NEW-01)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .decision_ledger import DecisionLedger
from .exceptions import CorruptStorageError
from .safe_json_store import SafeJsonStore


def _validate_memory_schema(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Memory root must be a JSON object.")
    notes = data.get("notes", {})
    if notes is None:
        notes = {}
    if not isinstance(notes, dict):
        raise ValueError("Memory 'notes' must be an object.")
    for key, note in notes.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"Invalid note key: {key!r}")
        if not isinstance(note, dict):
            raise ValueError(f"Note {key!r} must be an object.")
        if "key" not in note or not isinstance(note["key"], str) or not note["key"]:
            raise ValueError(f"Note {key!r} missing string 'key'.")
        if "content" not in note or not isinstance(note["content"], str):
            raise ValueError(f"Note {key!r} missing string 'content'.")
        if "tags" in note and note["tags"] is not None:
            if not isinstance(note["tags"], list) or not all(
                isinstance(t, str) for t in note["tags"]
            ):
                raise ValueError(f"Note {key!r} tags must be a list of strings.")
    return data


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
            data = _validate_memory_schema(data)
            self._notes = dict(data.get("notes", {}))
        except CorruptStorageError:
            self._notes = {}
            raise
        except (ValueError, KeyError, TypeError) as exc:
            self._notes = {}
            self._store.quarantine_invalid(str(exc))

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
            try:
                disk = _validate_memory_schema(disk)
            except ValueError as exc:
                raise CorruptStorageError(str(exc)) from exc
            notes = dict(disk.get("notes", {}))
            for k, v in notes.items():
                if k not in self._notes:
                    self._notes[k] = v
            self._notes[key] = note
            return {"notes": dict(self._notes)}

        self._store.update(mutator)
        return key

    def get_note(self, key: str) -> dict[str, Any] | None:
        if self.path.exists():
            try:
                data = self._store.read()
                data = _validate_memory_schema(data)
                notes = data.get("notes", {})
                if key in notes:
                    return notes[key]
            except CorruptStorageError:
                pass
            except ValueError:
                pass
        return self._notes.get(key)

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        if self.path.exists():
            try:
                data = self._store.read()
                data = _validate_memory_schema(data)
                self._notes = dict(data.get("notes", {}))
            except (CorruptStorageError, ValueError):
                pass
        results: list[dict[str, Any]] = []
        for key, note in self._notes.items():
            if (
                q in note["content"].lower()
                or q in " ".join(note.get("tags") or []).lower()
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
