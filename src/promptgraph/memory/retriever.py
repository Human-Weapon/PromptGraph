"""Deterministic, explainable retrieval over the memory index."""

from __future__ import annotations

from dataclasses import dataclass

from ..context_selection import tokenize_terms
from .graph import MemoryGraph
from .index import MemoryIndex
from .models import (
    DisclosureLevel,
    Disposition,
    MemoryRecord,
    MemoryType,
    RecordStatus,
    RetrievalHit,
)
from .vault import MemoryVault
from .writer import MemoryWriter


@dataclass
class RetrievalStats:
    index_used: bool = True
    files_opened: int = 0
    records_considered: int = 0
    records_selected: int = 0


class ContextRetriever:
    def __init__(self, vault: MemoryVault, index: MemoryIndex | None = None) -> None:
        self.vault = vault
        self.index = index or MemoryIndex(vault)
        self.graph = MemoryGraph(vault)
        self.writer = MemoryWriter(vault, self.index)
        self.stats = RetrievalStats()

    def search(
        self,
        task: str,
        *,
        paths: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        area: str = "",
        approach_keys: tuple[str, ...] = (),
        limit: int = 32,
        include_local: bool = True,
    ) -> list[RetrievalHit]:
        self.stats = RetrievalStats()
        try:
            records = self.index.records()
        except Exception:
            self.index.invalidate()
            records = self.index.rebuild().get("records") or {}
        self.graph.load()
        self.stats.records_considered = len(records)
        task_terms = tokenize_terms(task)
        path_needles = tuple(p.replace("\\", "/").lower() for p in paths if p)
        tag_needles = {t.lower() for t in tags}
        area_l = area.lower().strip()
        approach_needles = {k.lower() for k in approach_keys if k}
        scored: list[RetrievalHit] = []
        for ident, entry in records.items():
            if not include_local and entry.get("scope") == "local_only":
                continue
            score, reasons, disclosure = self._score(
                entry,
                task_terms=task_terms,
                path_needles=path_needles,
                tag_needles=tag_needles,
                area=area_l,
                approach_needles=approach_needles,
                task=task,
            )
            if score <= 0:
                continue
            scored.append(
                RetrievalHit(
                    record_id=ident,
                    score=score,
                    reasons=tuple(reasons),
                    disclosure=disclosure,
                    summary=str(entry.get("summary") or ""),
                    title=str(entry.get("title") or ident),
                    type=str(entry.get("type") or ""),
                )
            )
        scored.sort(key=lambda h: (-h.score, h.record_id))
        selected = scored[:limit]
        self.stats.records_selected = len(selected)
        return selected

    def load_record(self, record_id: str) -> MemoryRecord:
        self.stats.files_opened += 1
        return self.writer.read(record_id)

    def load_for_hit(self, hit: RetrievalHit) -> MemoryRecord:
        return self.load_record(hit.record_id)

    def latest_checkpoint(self) -> MemoryRecord | None:
        recs = self.index.records()
        cps = [
            (ident, entry)
            for ident, entry in recs.items()
            if entry.get("type") == MemoryType.CHECKPOINT.value
        ]
        if not cps:
            return None
        cps.sort(key=lambda item: item[0], reverse=True)
        try:
            return self.load_record(cps[0][0])
        except Exception:
            return None

    def _score(
        self,
        entry: dict,
        *,
        task_terms: set[str],
        path_needles: tuple[str, ...],
        tag_needles: set[str],
        area: str,
        approach_needles: set[str],
        task: str,
    ) -> tuple[int, list[str], DisclosureLevel]:
        reasons: list[str] = []
        score = 0
        ident = str(entry.get("id") or "")
        title = str(entry.get("title") or "")
        summary = str(entry.get("summary") or "")
        entry_tags = {str(t).lower() for t in (entry.get("tags") or [])}
        entry_paths = [str(p).replace("\\", "/").lower() for p in (entry.get("paths") or [])]
        entry_area = str(entry.get("area") or "").lower()
        entry_keys = {str(k).lower() for k in (entry.get("approach_keys") or [])}
        status = str(entry.get("status") or "")
        importance = str(entry.get("importance") or entry.get("disposition") or "")
        kind = str(entry.get("type") or "")
        task_l = task.lower()

        if ident and ident.lower() in task_l:
            score += 1000
            reasons.append("exact ID mentioned in the task")

        title_terms = tokenize_terms(title)
        summary_terms = tokenize_terms(summary)
        title_hits = task_terms & title_terms
        summary_hits = task_terms & summary_terms
        if title_hits:
            score += 30 * len(title_hits)
            reasons.append("title terms match the task")
        if summary_hits:
            score += 20 * len(summary_hits)
            reasons.append("summary terms match the task")

        if area and area == entry_area:
            score += 50
            reasons.append("area matches")
        elif entry_area and entry_area in task_l:
            score += 35
            reasons.append("area mentioned in the task")

        tag_hits = tag_needles & entry_tags
        if tag_hits:
            score += 40 * len(tag_hits)
            reasons.append("tags match")
        else:
            implied = {t for t in entry_tags if t in task_l}
            if implied:
                score += 25 * len(implied)
                reasons.append("tags mentioned in the task")

        path_hit = False
        for needle in path_needles:
            for ep in entry_paths:
                if needle in ep or ep in needle:
                    path_hit = True
                    break
            if path_hit:
                break
        if not path_hit:
            for ep in entry_paths:
                if ep and ep in task_l:
                    path_hit = True
                    break
        if path_hit:
            score += 80
            reasons.append("affected path matches")

        key_hits = approach_needles & entry_keys
        if key_hits:
            score += 90
            reasons.append("failed-approach signature matches")

        if importance == Disposition.CANONICAL.value and status == RecordStatus.ACTIVE.value:
            score += 25
            reasons.append("active canonical record")
        if status == RecordStatus.SUPERSEDED.value:
            score -= 50
            reasons.append("superseded; historical only")
        if kind == MemoryType.FAILURE.value and score > 0:
            score += 35
            reasons.append("relevant failure")
        if kind == MemoryType.LESSON.value and score > 0:
            score += 30
            reasons.append("persistent lesson")
        if kind == MemoryType.CONSTRAINT.value and score > 0:
            score += 40
            reasons.append("hard constraint")
        if kind == MemoryType.CHECKPOINT.value and score > 0:
            score += 20
            reasons.append("current checkpoint relevance")

        neighbors = self.graph.neighbors(ident)
        if neighbors and score > 0:
            score += min(15, 5 * len(neighbors))
            reasons.append("linked memory neighbors")

        disclosure = DisclosureLevel.TITLE
        if score >= 80:
            disclosure = DisclosureLevel.FULL
        elif score >= 40:
            disclosure = DisclosureLevel.SECTIONS
        if kind == MemoryType.EVIDENCE.value and score < 120:
            disclosure = DisclosureLevel.TITLE
        if kind == MemoryType.CONSTRAINT.value and score > 0:
            disclosure = max(disclosure, DisclosureLevel.SECTIONS)
        return score, reasons, disclosure
