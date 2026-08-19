"""Validate a memory vault without inventing missing content."""

from __future__ import annotations

from ..contradiction_detection import ContradictionDetector
from ..models import PackageStatus, Requirement
from .index import MemoryIndex
from .models import Disposition, MemoryType, RecordStatus, ValidationReport
from .serialize import markdown_to_record, parse_frontmatter
from .vault import MemoryVault


def validate_vault(vault: MemoryVault) -> ValidationReport:
    messages: list[str] = []
    unresolved: list[str] = []
    corrupt: list[str] = []
    contradictions: list[str] = []
    records = []
    seen_ids: dict[str, str] = {}
    if not vault.exists():
        return ValidationReport(
            ok=False,
            status=PackageStatus.ANALYSIS_INCOMPLETE.value,
            messages=("Memory vault does not exist. Run promptgraph memory init.",),
        )

    for path in vault.iter_markdown():
        rel = vault.relpath(path)
        try:
            text = vault.read_text(path)
            parse_frontmatter(text)
            record = markdown_to_record(text)
        except Exception as exc:
            corrupt.append(f"{rel}: {exc}")
            continue
        if record.id in seen_ids:
            corrupt.append(f"{rel}: duplicate id {record.id} (also {seen_ids[record.id]})")
            continue
        seen_ids[record.id] = rel
        records.append(record)

    index = MemoryIndex(vault)
    index_current = True
    try:
        data = index.load(rebuild_if_missing=False)
        indexed = set(data.get("records") or {})
        live = set(seen_ids)
        if indexed != live:
            index_current = False
            messages.append("index is stale relative to Markdown records")
    except Exception:
        index_current = False
        messages.append("index missing or unreadable; rebuild required")

    graph_current = True
    graph_path = vault.root / "graph.json"
    if not graph_path.exists():
        graph_current = False
        messages.append("graph.json missing; rebuild required")

    live_ids = set(seen_ids)
    for record in records:
        for ident in (*record.related, *record.supersedes):
            if ident not in live_ids:
                unresolved.append(f"{record.id} -> {ident}")

    actives = [
        r
        for r in records
        if r.disposition is Disposition.CANONICAL and r.status is RecordStatus.ACTIVE
    ]
    if len(actives) >= 2:
        detector = ContradictionDetector()
        reqs = [
            Requirement(id=r.id, description=f"{r.title}. {r.body or r.summary or r.problem}")
            for r in actives
            if r.type in {MemoryType.DECISION, MemoryType.CONSTRAINT, MemoryType.REQUIREMENT}
        ]
        if len(reqs) >= 2:
            for finding in detector.detect(reqs):
                if finding.confidence == "strong":
                    contradictions.append(
                        f"{finding.requirement_a} conflicts with "
                        f"{finding.requirement_b}: {finding.reason}"
                    )

    status = PackageStatus.READY.value
    ok = not corrupt
    if corrupt:
        status = PackageStatus.ANALYSIS_INCOMPLETE.value
        ok = False
    if contradictions:
        messages.append("active canonical records conflict")
    return ValidationReport(
        ok=ok and index_current and not contradictions,
        record_count=len(records),
        unresolved_links=tuple(unresolved),
        corrupt_records=tuple(corrupt),
        contradictions=tuple(contradictions),
        index_current=index_current,
        graph_current=graph_current,
        status=status,
        messages=tuple(messages),
    )
