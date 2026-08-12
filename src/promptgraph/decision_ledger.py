"""DecisionLedger — durable decision storage via SafeJsonStore."""

from __future__ import annotations

from pathlib import Path

from .exceptions import CorruptStorageError, DecisionError, DuplicateDecisionError
from .models import Decision
from .safe_json_store import SafeJsonStore


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
        self._store = SafeJsonStore(self.path, trusted_root=self.trusted_root, default=dict)
        self._items: dict[str, Decision] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = self._store.read()
            if not isinstance(data, dict):
                raise ValueError("Ledger root is not a JSON object.")
            self._items = {}
            for key, val in data.items():
                self._items[key] = Decision.from_dict(val)
        except CorruptStorageError:
            self._items = {}
            raise

    def record(self, decision: Decision) -> str:
        if not decision.id:
            raise DecisionError("Decision must have a non-empty id.")

        def mutator(disk: object) -> dict:
            if not isinstance(disk, dict):
                disk = {}
            # Merge disk into memory view
            for key, val in disk.items():
                if key not in self._items:
                    try:
                        self._items[key] = Decision.from_dict(val)
                    except (KeyError, TypeError, ValueError):
                        pass
            if decision.id in disk or decision.id in self._items:
                raise DuplicateDecisionError(f"A decision with id '{decision.id}' already exists.")
            self._items[decision.id] = decision
            return {k: d.to_dict() for k, d in self._items.items()}

        try:
            self._store.update(mutator)
        except DuplicateDecisionError:
            raise
        except Exception:
            # Only roll back a newly added id if write failed after insert
            if decision.id in self._items:
                # If disk still has it, keep memory; if we added only in memory, drop
                try:
                    disk = self._store.read()
                    if isinstance(disk, dict) and decision.id not in disk:
                        self._items.pop(decision.id, None)
                except Exception:
                    self._items.pop(decision.id, None)
            raise
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
