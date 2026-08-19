from __future__ import annotations

from promptgraph.memory.models import Disposition, MemoryCandidate, MemoryType, StorageScope
from promptgraph.models import estimate_token_count
from tests.memory.helpers import failure_candidate


def test_large_vault_bounded_retrieval(memory):
    related = [
        failure_candidate(title="Windows junction escaped containment"),
        MemoryCandidate(
            type=MemoryType.LESSON,
            title="OS-level invariants require real OS-level regression tests",
            body="Use real filesystem objects.",
            scope=StorageScope.SHAREABLE,
            area="filesystem",
            tags=("windows", "containment"),
        ),
        MemoryCandidate(
            type=MemoryType.CONSTRAINT,
            title="Writes must stay inside trusted_root",
            body="No junction escape.",
            scope=StorageScope.SHAREABLE,
            area="filesystem",
            tags=("containment",),
            disposition=Disposition.CANONICAL,
        ),
    ]
    filler = [
        MemoryCandidate(
            type=MemoryType.ASSUMPTION,
            title=f"Unrelated assumption {i:04d} about billing theme {i}",
            body=f"This note is about invoices, taxes, and payroll topic {i}." * 3,
            scope=StorageScope.SHAREABLE,
            area="billing",
            tags=("billing", "unrelated"),
        )
        for i in range(500)
    ]
    memory.writer.persist_many(related + filler)
    pack = memory.build_context_pack("Fix Windows filesystem containment", budget=1800)
    assert pack.total_tokens <= 1800
    assert "FAIL-0001" in pack.selected_ids
    assert "LESSON-0001" in pack.selected_ids
    assert "CON-0001" in pack.selected_ids
    billing = [i for i in pack.selected_ids if i.startswith("ASM-")]
    assert len(billing) < 20
    vault_text = []
    for path in memory.vault.iter_markdown():
        vault_text.append(memory.vault.read_text(path))
    whole = estimate_token_count("\n".join(vault_text))
    assert pack.total_tokens * 4 < whole
    assert memory.retriever.stats.files_opened < 40
    assert memory.retriever.stats.records_considered >= 500
