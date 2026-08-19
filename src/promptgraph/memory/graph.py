"""Persistent memory relationships, rebuilt from Markdown + explicit edges."""

from __future__ import annotations

import json
from typing import Any

from ..context_graph import ContextGraph
from ..exceptions import CycleError, MemoryValidationError
from ..models import ContextNode, Priority
from .models import (
    Disposition,
    MemoryEdge,
    MemoryRecord,
    RecordStatus,
    RelationType,
)
from .serialize import markdown_to_record
from .vault import MemoryVault

GRAPH_VERSION = 1
DEPENDENCY_RELATIONS = {RelationType.DEPENDS_ON, RelationType.CONSTRAINS}


def _priority_for(record: MemoryRecord) -> Priority:
    if record.disposition is Disposition.CANONICAL:
        return Priority.P0
    if record.type.value in {"constraint", "failure"}:
        return Priority.P1
    if record.status is RecordStatus.SUPERSEDED:
        return Priority.P5
    return Priority.P2


def record_to_node(record: MemoryRecord) -> ContextNode:
    return ContextNode(
        id=record.id,
        title=record.title,
        content=record.one_line_summary(),
        kind=record.type.value,
        tags=list(record.tags),
        priority=_priority_for(record),
        metadata={
            "area": record.area,
            "status": record.status.value,
            "disposition": record.disposition.value,
            "paths": list(record.paths),
        },
    )


class MemoryGraph:
    def __init__(self, vault: MemoryVault) -> None:
        self.vault = vault
        self.path = vault.root / "graph.json"
        self.context_graph = ContextGraph()
        self.edges: list[MemoryEdge] = []

    def load(self, *, rebuild_if_missing: bool = True) -> dict[str, Any]:
        if not self.path.exists():
            if rebuild_if_missing:
                return self.rebuild()
            return {"version": GRAPH_VERSION, "edges": []}
        try:
            data = json.loads(self.vault.read_text(self.path))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            if rebuild_if_missing:
                return self.rebuild()
            raise
        self.edges = [
            MemoryEdge(
                source=str(item["source"]),
                target=str(item["target"]),
                relation=RelationType(item["relation"]),
            )
            for item in data.get("edges") or []
            if isinstance(item, dict)
        ]
        return data

    def neighbors(self, record_id: str) -> set[str]:
        found: set[str] = set()
        for edge in self.edges:
            if edge.source == record_id:
                found.add(edge.target)
            elif edge.target == record_id:
                found.add(edge.source)
        return found

    def rebuild(self, records: dict[str, MemoryRecord] | None = None) -> dict[str, Any]:
        loaded = records if records is not None else self._scan_records()
        edges: list[MemoryEdge] = []
        seen: set[tuple[str, str, str]] = set()
        self.context_graph = ContextGraph()
        for record in loaded.values():
            self.context_graph.add_node(record_to_node(record))
        for record in loaded.values():
            candidates = list(record.relations)
            for ident in record.related:
                candidates.append(
                    MemoryEdge(source=record.id, target=ident, relation=RelationType.RELATES_TO)
                )
            for ident in record.supersedes:
                candidates.append(
                    MemoryEdge(source=record.id, target=ident, relation=RelationType.SUPERSEDES)
                )
            for attempt in record.failed_attempts:
                if attempt.approach_key:
                    candidates.append(
                        MemoryEdge(
                            source=record.id,
                            target=record.id,
                            relation=RelationType.ATTEMPTED,
                        )
                    )
            for edge in candidates:
                self_link = edge.target == edge.source
                if not edge.target or (self_link and edge.relation is RelationType.RELATES_TO):
                    continue
                if edge.relation is RelationType.ATTEMPTED and edge.target == edge.source:
                    continue
                key = (edge.source, edge.target, edge.relation.value)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(edge)
                if edge.relation in DEPENDENCY_RELATIONS and edge.target in loaded:
                    try:
                        self.context_graph.add_dependency(edge.source, edge.target)
                    except (CycleError, KeyError):
                        pass
        edges.sort(key=lambda e: (e.source, e.relation.value, e.target))
        payload = {
            "version": GRAPH_VERSION,
            "edges": [e.to_dict() for e in edges],
        }
        self.vault.dump_json(self.path, payload)
        self.edges = edges
        return payload

    def _scan_records(self) -> dict[str, MemoryRecord]:
        out: dict[str, MemoryRecord] = {}
        for path in self.vault.iter_markdown():
            try:
                record = markdown_to_record(self.vault.read_text(path))
            except (MemoryValidationError, OSError, UnicodeDecodeError):
                continue
            out[record.id] = record
        return out
