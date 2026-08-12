"""DecisionLedger — record and retrieve decisions for future reference.

Persists decisions to a JSON file so future sessions can consult prior decisions
without being told again (persistent technical memory primitive).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .exceptions import DecisionError
from .models import Decision


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "decision"


class DecisionLedger:
    """A lightweight, append-only log of decisions backed by a JSON file.

    Decisions are keyed by a stable id. The ledger is safe to use standalone
    (no integration required).
    """

    def __init__(self, path: str | Path = "decisions.json") -> None:
        self.path = Path(path)
        self._items: dict[str, Decision] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for key, val in data.items():
                    self._items[key] = Decision.from_dict(val)
            except (json.JSONDecodeError, OSError) as exc:
                raise DecisionError(f"Cannot read decision ledger at {self.path}: {exc}") from exc

    def _save(self) -> None:
        payload = {key: d.to_dict() for key, d in self._items.items()}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            raise DecisionError(f"Cannot write decision ledger: {exc}") from exc

    def record(self, decision: Decision) -> str:
        """Store a decision and return its id."""
        if not decision.id:
            raise DecisionError("Decision must have a non-empty id.")
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
