"""Provider-neutral project-memory facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context_pack import MemoryContextPack, MemoryContextPackBuilder
from .gitinfo import project_git_state
from .index import MemoryIndex
from .models import (
    CompactionManifest,
    MemoryCandidate,
    MemoryRecord,
    MemoryType,
    RetrievalHit,
    ValidationReport,
)
from .retriever import ContextRetriever
from .session import (
    checkpoint_candidate_from_kwargs,
    checkpoint_is_stale,
    plan_compaction,
)
from .validate import validate_vault
from .vault import MemoryVault
from .writer import MemoryWriter


class ProjectMemory:
    def __init__(
        self,
        project_root: str | Path = ".",
        *,
        memory_root: str | Path | None = None,
        trusted_root: str | Path | None = None,
    ) -> None:
        self.vault = MemoryVault(project_root, memory_root=memory_root, trusted_root=trusted_root)
        self.index = MemoryIndex(self.vault)
        self.writer = MemoryWriter(self.vault, self.index)
        self.retriever = ContextRetriever(self.vault, self.index)

    def init(self) -> Path:
        return self.vault.init()

    def record_memory(self, candidate: MemoryCandidate | dict[str, Any]) -> MemoryRecord:
        if isinstance(candidate, MemoryCandidate):
            item = candidate
        else:
            item = MemoryCandidate.from_dict(candidate)
        self.vault.init()
        return self.writer.persist_candidate(item)

    def checkpoint_session(
        self,
        *,
        goal: str,
        current_state: str = "",
        completed: str = "",
        remaining: str = "",
        next_task: str = "",
        related: tuple[str, ...] = (),
        unresolved: tuple[str, ...] = (),
        session: str = "",
        title: str | None = None,
    ) -> MemoryRecord:
        self.vault.init()
        git_state = project_git_state(self.vault.project_root)
        candidate = checkpoint_candidate_from_kwargs(
            goal=goal,
            current_state=current_state,
            completed=completed,
            remaining=remaining,
            next_task=next_task,
            related=related,
            unresolved=unresolved,
            session=session,
            commit=str(git_state.get("commit") or ""),
            title=title,
        )
        return self.writer.persist_candidate(candidate)

    def build_context_pack(
        self,
        task: str,
        *,
        budget: int = 8000,
        paths: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        area: str = "",
        approach_keys: tuple[str, ...] = (),
        include_local: bool = False,
    ) -> MemoryContextPack:
        if not self.vault.exists():
            self.vault.init()
        self.index.invalidate()
        self.index.load()
        return MemoryContextPackBuilder(self.vault, self.retriever).build(
            task,
            budget=budget,
            paths=paths,
            tags=tags,
            area=area,
            approach_keys=approach_keys,
            include_local=include_local,
        )

    def search_memory(
        self,
        query: str,
        *,
        paths: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        area: str = "",
        limit: int = 20,
        include_local: bool = True,
    ) -> list[RetrievalHit]:
        if not self.vault.exists():
            return []
        self.index.invalidate()
        self.index.load()
        return self.retriever.search(
            query,
            paths=paths,
            tags=tags,
            area=area,
            limit=limit,
            include_local=include_local,
        )

    def show(self, record_id: str) -> MemoryRecord:
        self.index.invalidate()
        self.index.load()
        return self.writer.read(record_id)

    def validate_memory(self) -> ValidationReport:
        if not self.vault.exists():
            return validate_vault(self.vault)
        return validate_vault(self.vault)

    def plan_compaction(
        self,
        *,
        session_id: str,
        candidates: list[MemoryCandidate] | None = None,
        checkpoint: MemoryCandidate | None = None,
        task: str = "",
        budget: int = 8000,
        extraction_complete: bool = False,
        source_range: str = "",
    ) -> CompactionManifest:
        self.vault.init()
        return plan_compaction(
            self.vault,
            session_id=session_id,
            candidates=candidates,
            checkpoint=checkpoint,
            task=task,
            budget=budget,
            extraction_complete=extraction_complete,
            source_range=source_range,
        )

    def status(self) -> dict[str, Any]:
        report = self.validate_memory()
        checkpoint = None
        stale = False
        stale_reasons: tuple[str, ...] = ()
        if self.vault.exists():
            try:
                self.index.load()
                checkpoint = self.retriever.latest_checkpoint()
                if checkpoint:
                    stale, stale_reasons = checkpoint_is_stale(checkpoint, self.vault, self.index)
            except Exception:
                pass
        return {
            "root": str(self.vault.root),
            "exists": self.vault.exists(),
            "records": report.record_count,
            "valid": report.ok,
            "status": report.status,
            "unresolved_links": list(report.unresolved_links),
            "corrupt_records": list(report.corrupt_records),
            "checkpoint_id": checkpoint.id if checkpoint else None,
            "checkpoint_stale": stale,
            "checkpoint_stale_reasons": list(stale_reasons),
        }

    def rebuild(self) -> dict[str, Any]:
        self.vault.init()
        index = self.index.rebuild()
        graph = self.writer.graph.rebuild()
        return {"index": index.get("fingerprint"), "edges": len(graph.get("edges") or [])}

    def suggest_consolidation(self) -> list[dict[str, Any]]:
        recs = self.index.records() if self.vault.exists() else {}
        failures = [e for e in recs.values() if e.get("type") == MemoryType.FAILURE.value]
        groups: dict[tuple[str, ...], list[str]] = {}
        for entry in failures:
            tags = {str(t).lower() for t in (entry.get("tags") or [])}
            tags.add(str(entry.get("area") or "").lower())
            key = tuple(sorted(tags))
            if len(key) < 2:
                continue
            groups.setdefault(key, []).append(str(entry["id"]))
        suggestions = []
        for key, ids in sorted(groups.items()):
            if len(ids) < 3:
                continue
            suggestions.append(
                {
                    "source_ids": ids,
                    "shared": list(key),
                    "suggestion": (
                        "Multiple failures share tags/area. Consider a canonical lesson "
                        "linked via LEARNED_FROM. Source failures must be kept."
                    ),
                }
            )
        return suggestions
