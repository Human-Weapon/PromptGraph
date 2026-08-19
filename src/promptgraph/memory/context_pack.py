"""Bounded context packages compiled from persistent memory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from ..exceptions import BudgetExceededError, TokenBudgetError
from ..models import estimate_token_count
from .gitinfo import project_git_state
from .index import MemoryIndex
from .models import (
    DisclosureLevel,
    MemoryRecord,
    MemoryType,
    RecordStatus,
    RetrievalHit,
    StorageScope,
)
from .retriever import ContextRetriever
from .vault import MemoryVault


@dataclass
class MemoryContextPack:
    pack_id: str
    task: str
    markdown: str
    selected_ids: tuple[str, ...]
    omitted: int
    token_budget: int
    total_tokens: int
    fingerprint: str
    stale: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    explanations: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "task": self.task,
            "markdown": self.markdown,
            "selected_ids": list(self.selected_ids),
            "omitted": self.omitted,
            "token_budget": self.token_budget,
            "total_tokens": self.total_tokens,
            "fingerprint": self.fingerprint,
            "stale": self.stale,
            "metadata": dict(self.metadata),
            "explanations": {k: list(v) for k, v in self.explanations.items()},
        }


def _render_record(record: MemoryRecord, disclosure: DisclosureLevel) -> str:
    if disclosure is DisclosureLevel.TITLE:
        return f"- **{record.id}** {record.title} — {record.one_line_summary()}"
    parts = [f"### {record.id} — {record.title}"]
    if record.one_line_summary():
        parts.append(record.one_line_summary())
    if disclosure is DisclosureLevel.SECTIONS:
        for label, value in (
            ("Constraint", record.body if record.type is MemoryType.CONSTRAINT else ""),
            ("Problem", record.problem),
            ("Lesson", record.lesson),
            ("Decision", record.body if record.type is MemoryType.DECISION else ""),
            ("Solution", record.solution),
        ):
            if value.strip():
                parts.append(f"**{label}:** {value.strip()[:600]}")
        return "\n".join(parts)
    if record.problem:
        parts.append(f"**Problem:** {record.problem}")
    if record.symptom:
        parts.append(f"**Symptom:** {record.symptom}")
    if record.root_cause:
        status = record.root_cause_status.value
        parts.append(f"**Root cause ({status}):** {record.root_cause}")
    elif record.type is MemoryType.FAILURE:
        parts.append("**Root cause:** unknown")
    if record.failed_attempts:
        parts.append("**Failed attempts:**")
        for attempt in record.failed_attempts:
            parts.append(f"- {attempt.title}: {attempt.result} — {attempt.why}")
    if record.solution:
        parts.append(f"**Correct solution:** {record.solution}")
    if record.lesson:
        parts.append(f"**Lesson:** {record.lesson}")
    if record.body.strip() and record.type not in {MemoryType.FAILURE}:
        parts.append(record.body.strip()[:2000])
    if record.evidence_status.value != "verified":
        status = record.evidence_status.value
        parts.append(f"_Evidence status: {status} (not independently verified)._")
    return "\n".join(parts)


def _failed_approach_lines(records: list[MemoryRecord]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for record in records:
        for attempt in record.failed_attempts:
            key = attempt.approach_key or attempt.title
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {attempt.title}: {attempt.why}")
    return lines


class MemoryContextPackBuilder:
    def __init__(self, vault: MemoryVault, retriever: ContextRetriever | None = None) -> None:
        self.vault = vault
        self.retriever = retriever or ContextRetriever(vault)
        self.index = self.retriever.index

    def build(
        self,
        task: str,
        *,
        budget: int = 8000,
        paths: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        area: str = "",
        approach_keys: tuple[str, ...] = (),
        include_local: bool = False,
        pack_id: str | None = None,
        persist: bool = True,
    ) -> MemoryContextPack:
        if budget < 0:
            raise TokenBudgetError("budget must be non-negative.")
        hits = self.retriever.search(
            task,
            paths=paths,
            tags=tags,
            area=area,
            approach_keys=approach_keys,
            limit=64,
            include_local=include_local,
        )
        loaded: dict[str, MemoryRecord] = {}
        for hit in hits:
            try:
                loaded[hit.record_id] = self.retriever.load_for_hit(hit)
            except Exception:
                continue
        checkpoint = self.retriever.latest_checkpoint()
        if checkpoint and checkpoint.id not in loaded:
            loaded[checkpoint.id] = checkpoint

        grouped = self._group(hits, loaded)
        selected: list[str] = []
        explanations: dict[str, tuple[str, ...]] = {}
        omitted_ids: list[str] = []

        def take(items: list[tuple[RetrievalHit, MemoryRecord]], heading_budget: int) -> list[str]:
            blocks: list[str] = []
            for hit, record in items:
                block = _render_record(record, hit.disclosure)
                if heading_budget <= 0:
                    omitted_ids.append(record.id)
                    continue
                probe = "\n".join(blocks + [block])
                if estimate_token_count(probe) > heading_budget and blocks:
                    omitted_ids.append(record.id)
                    continue
                blocks.append(block)
                selected.append(record.id)
                explanations[record.id] = hit.reasons
            return blocks

        reserve = 80
        remaining = budget
        sections: list[tuple[str, list[str]]] = []

        task_block = [task.strip() or "(unspecified task)"]
        remaining = self._fit_mandatory("Current task", task_block, remaining, reserve)

        constraints = grouped[MemoryType.CONSTRAINT]
        if constraints:
            blocks = take(constraints, max(0, remaining - reserve))
            if blocks:
                sections.append(("Hard constraints", blocks))
                remaining = budget  # recomputed later from full render

        for heading, kind in (
            ("Relevant requirements", MemoryType.REQUIREMENT),
            ("Active decisions", MemoryType.DECISION),
            ("Relevant architecture", MemoryType.ARCHITECTURE),
            ("Known failures", MemoryType.FAILURE),
            ("Persistent lessons", MemoryType.LESSON),
            ("Assumptions", MemoryType.ASSUMPTION),
        ):
            items = grouped[kind]
            if not items:
                continue
            # critical kinds first: already added constraints
            blocks = take(items, 10**9)
            if blocks:
                sections.append((heading, blocks))

        failure_records = [rec for hit, rec in grouped[MemoryType.FAILURE] if rec.id in selected]
        approach_lines = _failed_approach_lines(failure_records)
        if approach_lines:
            sections.append(("Known failed approaches / do not repeat", approach_lines))

        if checkpoint:
            hit = next(
                (h for h, _ in grouped[MemoryType.CHECKPOINT] if h.record_id == checkpoint.id),
                None,
            )
            disclosure = hit.disclosure if hit else DisclosureLevel.SECTIONS
            sections.append(
                (
                    "Current checkpoint",
                    [_render_record(checkpoint, disclosure)],
                )
            )
            if checkpoint.id not in selected:
                selected.append(checkpoint.id)
            if hit:
                explanations[checkpoint.id] = hit.reasons

        file_lines = []
        seen_paths: set[str] = set()
        for rec in loaded.values():
            if rec.id not in selected:
                continue
            for p in rec.paths:
                if p not in seen_paths:
                    seen_paths.add(p)
                    file_lines.append(f"- {p}")
        if file_lines:
            sections.append(("Relevant files", file_lines))

        unresolved = []
        for rec in loaded.values():
            if rec.id not in selected:
                continue
            unresolved.extend(f"- {item} (from {rec.id})" for item in rec.unresolved)
            if rec.status is RecordStatus.OPEN and rec.type is not MemoryType.CHECKPOINT:
                unresolved.append(f"- {rec.id} is still open")
        if unresolved:
            sections.append(("Unresolved questions", unresolved))

        evidence = grouped[MemoryType.EVIDENCE] + grouped[MemoryType.AUDIT]
        if evidence:
            lines = [
                f"- {rec.id}: {rec.title} (available on demand)"
                for hit, rec in evidence
                if rec.id not in selected
            ]
            if lines:
                sections.append(("Evidence available on demand", lines))

        markdown = self._render(task, sections, omitted=0)
        # Drop lowest-priority optional sections until budget fits.
        drop_order = [
            "Evidence available on demand",
            "Assumptions",
            "Relevant files",
            "Relevant architecture",
            "Current checkpoint",
        ]
        while estimate_token_count(markdown) > budget:
            dropped = False
            for name in drop_order:
                kept = [(h, b) for h, b in sections if h != name]
                if len(kept) != len(sections):
                    for _, _blocks in sections:
                        if name == "Current checkpoint" and checkpoint:
                            if checkpoint.id in selected:
                                selected.remove(checkpoint.id)
                    sections = kept
                    markdown = self._render(task, sections, omitted=len(omitted_ids))
                    dropped = True
                    break
            if not dropped:
                # drop trailing non-constraint selected records
                if len(selected) <= 1:
                    break
                removed = selected.pop()
                omitted_ids.append(removed)
                new_sections: list[tuple[str, list[str]]] = []
                for heading, blocks in sections:
                    filtered = [b for b in blocks if removed not in b]
                    if filtered:
                        new_sections.append((heading, filtered))
                sections = new_sections
                markdown = self._render(task, sections, omitted=len(omitted_ids))
        omitted_total = len(omitted_ids) + max(0, len(hits) - len(selected))
        markdown = self._render(task, sections, omitted=omitted_total)
        tokens = estimate_token_count(markdown)
        if tokens > budget:
            raise BudgetExceededError(
                f"Memory context pack requires {tokens} tokens, exceeding budget {budget}."
            )

        git_state = project_git_state(self.vault.project_root)
        index_fp = ""
        try:
            index_fp = MemoryIndex(self.vault).fingerprint()
        except Exception:
            index_fp = ""
        assigned_id = pack_id or self._next_pack_id()
        meta = {
            "git_commit": git_state.get("commit"),
            "dirty_worktree": git_state.get("dirty"),
            "memory_index_fingerprint": index_fp,
            "checkpoint_id": checkpoint.id if checkpoint else None,
            "memory_ids": list(dict.fromkeys(selected)),
            "generation": {"task": task, "budget": budget, "include_local": include_local},
            "files_opened": self.retriever.stats.files_opened,
            "records_considered": self.retriever.stats.records_considered,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                {"ids": meta["memory_ids"], "task": task, "budget": budget, "index": index_fp},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        pack = MemoryContextPack(
            pack_id=assigned_id,
            task=task,
            markdown=markdown,
            selected_ids=tuple(meta["memory_ids"]),
            omitted=len(omitted_ids) + max(0, len(hits) - len(selected)),
            token_budget=budget,
            total_tokens=tokens,
            fingerprint=fingerprint,
            stale=False,
            metadata=meta,
            explanations=explanations,
        )
        if persist:
            self._persist(pack)
        return pack

    def _group(
        self, hits: list[RetrievalHit], loaded: dict[str, MemoryRecord]
    ) -> dict[MemoryType, list[tuple[RetrievalHit, MemoryRecord]]]:
        grouped: dict[MemoryType, list[tuple[RetrievalHit, MemoryRecord]]] = {
            kind: [] for kind in MemoryType
        }
        for hit in hits:
            record = loaded.get(hit.record_id)
            if record is None:
                continue
            if record.scope is StorageScope.LOCAL_ONLY:
                pass
            grouped[record.type].append((hit, record))
        return grouped

    def _fit_mandatory(self, heading: str, blocks: list[str], remaining: int, reserve: int) -> int:
        text = f"# Context Package\n\n## {heading}\n\n" + "\n".join(blocks) + "\n"
        used = estimate_token_count(text)
        if used > remaining:
            raise BudgetExceededError(
                f"Mandatory context ({heading}) requires {used} tokens, exceeding budget."
            )
        return remaining

    def _render(self, task: str, sections: list[tuple[str, list[str]]], omitted: int) -> str:
        task_text = task.strip() or "(unspecified task)"
        lines = ["# Context Package", "", "## Current task", "", task_text, ""]
        for heading, blocks in sections:
            if heading == "Current task":
                continue
            lines.append(f"## {heading}")
            lines.append("")
            lines.extend(blocks)
            lines.append("")
        lines.append("## Omitted context")
        lines.append("")
        lines.append(
            f"{omitted} additional records were not included because they were not "
            "relevant enough or did not fit the context budget."
        )
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _next_pack_id(self) -> str:
        folder = self.vault.root / "context-packs"
        highest = 0
        if folder.exists():
            for path in folder.glob("PACK-*.md"):
                try:
                    num = int(path.stem.split("-")[1])
                except (IndexError, ValueError):
                    continue
                highest = max(highest, num)
        return f"PACK-{highest + 1:04d}"

    def _persist(self, pack: MemoryContextPack) -> None:
        folder = self.vault.root / "context-packs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{pack.pack_id}.md"
        header = {
            "id": pack.pack_id,
            "fingerprint": pack.fingerprint,
            "token_budget": pack.token_budget,
            "total_tokens": pack.total_tokens,
            "stale": pack.stale,
            "selected_ids": list(pack.selected_ids),
        }
        body = json.dumps(pack.metadata, indent=2, sort_keys=True) + "\n\n" + pack.markdown
        meta = "\n".join(f"{k}: {json.dumps(v)}" for k, v in header.items())
        text = f"---\n{meta}\n---\n{body}"
        self.vault.write_text(path, text)

    def mark_stale_if_needed(self, pack: MemoryContextPack) -> MemoryContextPack:
        current = MemoryIndex(self.vault)
        try:
            current.load()
            fp = current.fingerprint()
        except Exception:
            pack.stale = True
            return pack
        if fp != pack.metadata.get("memory_index_fingerprint"):
            pack.stale = True
        git_state = project_git_state(self.vault.project_root)
        if git_state.get("commit") and git_state.get("commit") != pack.metadata.get("git_commit"):
            pack.stale = True
        return pack
