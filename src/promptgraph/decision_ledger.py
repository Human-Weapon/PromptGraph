"""DecisionLedger — durable decision storage via SafeJsonStore."""

from __future__ import annotations

from pathlib import Path

from .exceptions import CorruptStorageError, DecisionError, DuplicateDecisionError
from .models import Decision
from .safe_json_store import SafeJsonStore


def _validate_ledger_schema(data: object) -> dict:
    """Validate DecisionLedger JSON shape; raise ValueError if invalid."""
    if not isinstance(data, dict):
        raise ValueError("Ledger root must be a JSON object.")
    for key, val in data.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"Invalid decision id key: {key!r}")
        if not isinstance(val, dict):
            raise ValueError(f"Decision record {key!r} must be an object.")
        for field in ("id", "title", "context", "decision"):
            if field not in val:
                raise ValueError(f"Decision {key!r} missing required field {field!r}.")
            if not isinstance(val[field], str):
                raise ValueError(f"Decision {key!r} field {field!r} must be a string.")
        if val["id"] != key:
            # allow but require id present; id should match key ideally
            if not val["id"]:
                raise ValueError(f"Decision {key!r} has empty id.")
        if (
            "rationale" in val
            and val["rationale"] is not None
            and not isinstance(val["rationale"], str)
        ):
            raise ValueError(f"Decision {key!r} rationale must be a string.")
    return data


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
        self._store = SafeJsonStore(
            self.path,
            trusted_root=self.trusted_root,
            default=dict,
            validator=_validate_ledger_schema,
        )
        self._items: dict[str, Decision] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = self._store.read()
            data = _validate_ledger_schema(data)
            self._items = {}
            for key, val in data.items():
                self._items[key] = Decision.from_dict(val)
        except CorruptStorageError:
            self._items = {}
            raise
        except (ValueError, KeyError, TypeError) as exc:
            self._items = {}
            # Quarantine invalid schema
            self._store.quarantine_invalid(str(exc))

    def record(self, decision: Decision) -> str:
        if not decision.id:
            raise DecisionError("Decision must have a non-empty id.")

        def mutator(disk: object) -> dict:
            if disk is None or disk == {}:
                disk = {}
            try:
                disk = _validate_ledger_schema(disk) if disk else {}
            except ValueError as exc:
                raise CorruptStorageError(str(exc)) from exc
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
        except CorruptStorageError:
            raise
        except Exception:
            if decision.id in self._items:
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
