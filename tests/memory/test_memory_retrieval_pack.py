from __future__ import annotations

import pytest

from promptgraph.exceptions import TokenBudgetError
from tests.memory.helpers import failure_candidate


def _seed(memory):
    fail = memory.record_memory(failure_candidate())
    lesson = memory.record_memory(
        {
            "type": "lesson",
            "title": "OS-level invariants require real OS-level regression tests",
            "body": "Mocked filesystem tests are not proof.",
            "scope": "shareable",
            "related": [fail.id],
            "area": "filesystem",
            "tags": ["windows", "containment"],
            "disposition": "canonical",
        }
    )
    constraint = memory.record_memory(
        {
            "type": "constraint",
            "title": "Writes must stay inside trusted_root",
            "body": "Junctions and symlinks must not escape containment.",
            "scope": "shareable",
            "area": "filesystem",
            "tags": ["containment"],
            "disposition": "canonical",
        }
    )
    memory.record_memory(
        {
            "type": "failure",
            "title": "Unrelated billing timeout",
            "body": "Stripe webhook lagged.",
            "scope": "shareable",
            "area": "billing",
            "tags": ["payments"],
        }
    )
    memory.record_memory(
        {
            "type": "decision",
            "title": "Use string-only path normalization",
            "body": "Old approach, now superseded.",
            "scope": "shareable",
            "status": "superseded",
            "area": "filesystem",
        }
    )
    memory.checkpoint_session(
        goal="Fix Windows filesystem containment",
        remaining="add real junction regression",
        related=(fail.id, lesson.id, constraint.id),
    )
    return fail, lesson, constraint


def test_relevant_failure_retrieved_unrelated_omitted(memory):
    fail, lesson, _ = _seed(memory)
    hits = memory.search_memory("Fix Windows filesystem containment")
    ids = [h.record_id for h in hits]
    assert fail.id in ids
    assert lesson.id in ids
    assert "FAIL-0002" not in ids


def test_canonical_and_active_preferred(memory):
    _seed(memory)
    hits = memory.search_memory("filesystem containment trusted_root")
    kinds = {h.record_id: h for h in hits}
    assert "CON-0001" in kinds
    superseded = [h for h in hits if h.record_id.startswith("DEC-")]
    if superseded:
        assert kinds["CON-0001"].score > superseded[0].score


def test_approach_key_boost(memory):
    fail, _, _ = _seed(memory)
    hits = memory.retriever.search(
        "retry containment",
        approach_keys=("filesystem:string-normalization-only",),
    )
    assert hits[0].record_id == fail.id
    assert any("failed-approach" in r for r in hits[0].reasons)


def test_deterministic_ties(memory):
    memory.record_memory(
        {
            "type": "assumption",
            "title": "Alpha",
            "body": "windows containment",
            "scope": "shareable",
            "area": "filesystem",
        }
    )
    memory.record_memory(
        {
            "type": "assumption",
            "title": "Beta",
            "body": "windows containment",
            "scope": "shareable",
            "area": "filesystem",
        }
    )
    a = [h.record_id for h in memory.search_memory("windows containment")]
    b = [h.record_id for h in memory.search_memory("windows containment")]
    assert a == b


def test_context_pack_surfaces_failed_approach(memory):
    fail, lesson, constraint = _seed(memory)
    pack = memory.build_context_pack("Fix Windows filesystem containment", budget=2500)
    assert fail.id in pack.selected_ids
    assert lesson.id in pack.selected_ids
    assert constraint.id in pack.selected_ids
    assert "Known failed approaches / do not repeat" in pack.markdown
    assert "string-only path normalization" in pack.markdown
    assert "Stripe" not in pack.markdown
    assert pack.total_tokens <= 2500
    assert pack.explanations[fail.id]


def test_hard_budget_and_negative(memory):
    _seed(memory)
    with pytest.raises(TokenBudgetError):
        memory.build_context_pack("task", budget=-1)
    pack = memory.build_context_pack("Fix Windows filesystem containment", budget=400)
    assert pack.total_tokens <= 400
    assert "Hard constraints" in pack.markdown or "trusted_root" in pack.markdown


def test_local_only_not_in_shareable_pack(memory):
    memory.record_memory(
        {
            "type": "failure",
            "title": "Secret local note about windows containment",
            "body": "do not share",
            "scope": "local_only",
            "area": "filesystem",
            "tags": ["windows", "containment"],
        }
    )
    pack = memory.build_context_pack("windows containment", budget=1500, include_local=False)
    assert "FAIL-0001" not in pack.selected_ids
    assert "do not share" not in pack.markdown
