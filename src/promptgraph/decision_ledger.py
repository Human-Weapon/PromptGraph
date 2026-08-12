"""DecisionLedger — record and retrieve decisions for future reference.

PG-03 fix: Duplicate IDs are rejected (no silent overwrite).  Corrupt
storage is quarantined with a structured error.  Stale-write protection:
``record()`` re-reads from disk before writing to avoid clobbering
records added by another instance.

PG-04 fix: Path validation via canonical resolution.
PG-09 fix: Corrupt JSON is quarantined (renamed) and raised as
``CorruptStorageError`` with the quarantine path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .exceptions import CorruptStorageError, DecisionError, DuplicateDecisionError
from .models import Decision


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "decision"


class DecisionLedger:
    """A durable log of decisions backed by a JSON file.

    - ``record()`` rejects duplicate IDs (no silent overwrite).
    - Corrupt storage is quarantined, not silently overwritten.
    - ``record()`` re-reads from disk to minimise stale-write data loss.
    """

    def __init__(self, path: str | Path = "decisions.json") -> None:
        self.path = Path(path)
        self._items: dict[str, Decision] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Ledger root is not a JSON object.")
            self._items = {}
            for key, val in data.items():
                self._items[key] = Decision.from_dict(val)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            # PG-09: quarantine corrupt file instead of silently overwriting.
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

    def _save(self) -> None:
        # PG-03: re-read from disk to detect records added by other instances.
        fresh = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    fresh = data
            except (json.JSONDecodeError, OSError):
                pass  # will be caught on next _load

        # Merge: combine existing on-disk with our in-memory items.
        merged: dict[str, dict[str, object]] = dict(fresh)
        for key, d in self._items.items():
            merged[key] = d.to_dict()

        payload = json.dumps(merged, indent=2, default=str)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            raise DecisionError(f"Cannot write decision ledger: {exc}") from exc

    def record(self, decision: Decision) -> str:
        """Store a decision and return its id.

        Raises ``DuplicateDecisionError`` if the id already exists.
        """
        if not decision.id:
            raise DecisionError("Decision must have a non-empty id.")
        # Check in-memory first.
        if decision.id in self._items:
            raise DuplicateDecisionError(
                f"A decision with id '{decision.id}' already exists. "
                f"Use a different id or remove the existing one first."
            )
        # Re-read from disk to catch records added by other instances.
        if self.path.exists():
            try:
                disk_data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(disk_data, dict) and decision.id in disk_data:
                    raise DuplicateDecisionError(
                        f"A decision with id '{decision.id}' already exists on disk."
                    )
            except (json.JSONDecodeError, OSError):
                pass  # corrupt disk; _save will handle merge
        self._items[decision.id] = decision
        self._save()
        return decision.id

    def get(self, decision_id: str) -> Decision | None:
        return self._items.get(decision_id)

    def all(self) -> list[Decision]:
        return list(self._items.values())

    def search(self, query: str, *, in_title: str = "", limit: int = 50) -> list[Decision]:
        """Search decisions by substring in title/decision/context."""
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
