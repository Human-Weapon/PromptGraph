"""PersistentTechnicalMemory — durable storage of technical facts.

PG-09 fix: Corrupt JSON is now quarantined and raised as
``CorruptStorageError`` instead of silently starting fresh.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .decision_ledger import DecisionLedger
from .exceptions import CorruptStorageError


class TechnicalMemory:
    """Persistent technical memory storing notes and decisions by key."""

    def __init__(self, path: str | Path = "memory.json") -> None:
        self.path = Path(path)
        self._notes: dict[str, dict[str, Any]] = {}
        self.ledger: DecisionLedger | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Memory root is not a JSON object.")
            self._notes = dict(data.get("notes", {}))
        except (json.JSONDecodeError, ValueError) as exc:
            # PG-09: quarantine corrupt file with structured error.
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
        payload = {"notes": self._notes}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            raise

    def with_decision_ledger(self, ledger: DecisionLedger) -> TechnicalMemory:
        """Attach an optional DecisionLedger for combined search."""
        self.ledger = ledger
        return self

    def record_note(self, key: str, content: str, tags: list[str] | None = None) -> str:
        """Store a technical note under a stable key."""
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
        """Search notes (and, if a ledger is attached, decisions) by substring."""
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
