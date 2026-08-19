from __future__ import annotations

from tests.memory.conftest import failure_candidate

from promptgraph.memory.graph import MemoryGraph
from promptgraph.memory.models import RelationType


def test_graph_roundtrip_and_supersession(memory):
    fail = memory.record_memory(failure_candidate())
    lesson = memory.record_memory(
        {
            "type": "lesson",
            "title": "Keep source failures",
            "body": "LEARNED_FROM the original failure.",
            "scope": "shareable",
            "related": [fail.id],
            "relations": [
                {
                    "source": "LESSON-0001",
                    "target": fail.id,
                    "relation": "learned_from",
                }
            ],
        }
    )
    old = memory.record_memory(
        {
            "type": "decision",
            "title": "Old rule",
            "body": "Allow public cache.",
            "scope": "shareable",
            "disposition": "canonical",
        }
    )
    memory.record_memory(
        {
            "type": "decision",
            "title": "New rule",
            "body": "Deny public cache.",
            "scope": "shareable",
            "disposition": "canonical",
            "supersedes": [old.id],
        }
    )
    graph = MemoryGraph(memory.vault)
    graph.rebuild()
    neighbors = graph.neighbors(fail.id)
    assert lesson.id in neighbors
    assert any(e.relation is RelationType.SUPERSEDES for e in graph.edges)


def test_contradictory_canonical_decisions(memory):
    memory.record_memory(
        {
            "type": "decision",
            "title": "Public API",
            "body": "The API must remain public and allow anonymous access.",
            "scope": "shareable",
            "disposition": "canonical",
        }
    )
    memory.record_memory(
        {
            "type": "decision",
            "title": "Private API",
            "body": "The API must remain private and deny anonymous access.",
            "scope": "shareable",
            "disposition": "canonical",
        }
    )
    report = memory.validate_memory()
    assert report.contradictions or not report.ok


def test_constraint_survives_small_budget(memory):
    memory.record_memory(
        {
            "type": "constraint",
            "title": "Writes must stay inside trusted_root",
            "body": "Never follow a junction out of the project.",
            "scope": "shareable",
            "area": "filesystem",
            "tags": ["containment", "windows"],
            "disposition": "canonical",
        }
    )
    memory.record_memory(failure_candidate())
    for i in range(8):
        memory.record_memory(
            {
                "type": "assumption",
                "title": f"Historical note {i} windows containment narrative",
                "body": "old history " * 40,
                "scope": "shareable",
                "area": "filesystem",
                "tags": ["windows", "containment"],
            }
        )
    pack = memory.build_context_pack("Fix Windows filesystem containment", budget=700)
    assert pack.total_tokens <= 700
    assert "CON-0001" in pack.selected_ids or "trusted_root" in pack.markdown
