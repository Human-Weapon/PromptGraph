from __future__ import annotations

from promptgraph.core import PromptGraph
from promptgraph.memory.models import MemoryCandidate, MemoryType, StorageScope
from promptgraph.memory.session import checkpoint_candidate_from_kwargs, plan_compaction
from tests.memory.helpers import failure_candidate


def test_failure_repetition_across_sessions(project):
    session_a = PromptGraph(project_root=project, trusted_root=project)
    fail = session_a.record_memory(failure_candidate())
    session_a.record_memory(
        {
            "type": "lesson",
            "title": "OS-level invariants require real OS-level regression tests",
            "body": "Do not treat mocked junction tests as proof.",
            "scope": "shareable",
            "related": [fail.id],
            "area": "filesystem",
            "tags": ["windows", "containment"],
        }
    )
    session_a.checkpoint_session(
        goal="Record the containment failure",
        related=(fail.id,),
    )

    session_b = PromptGraph(project_root=project, trusted_root=project)
    pack = session_b.build_context_pack("Fix Windows filesystem containment", budget=2000)
    assert fail.id in pack.selected_ids
    assert "LESSON-0001" in pack.selected_ids
    assert "string-only path normalization" in pack.markdown
    assert "User:" not in pack.markdown
    assert "Assistant:" not in pack.markdown


def test_safe_compaction_end_to_end(memory):
    candidates = [
        failure_candidate(),
        MemoryCandidate(
            type=MemoryType.LESSON,
            title="Real OS tests",
            body="Use real junctions.",
            scope=StorageScope.SHAREABLE,
            area="filesystem",
            tags=("windows",),
        ),
    ]
    checkpoint = checkpoint_candidate_from_kwargs(goal="Persist then compact")
    ok = plan_compaction(
        memory.vault,
        session_id="s-ok",
        candidates=candidates,
        checkpoint=checkpoint,
        task="Fix Windows filesystem containment",
        budget=2000,
        extraction_complete=True,
    )
    assert ok.safe_to_compact is True
    assert ok.declared_status == "SAFE_TO_COMPACT_DECLARED_CONTEXT"
    assert ok.host_chat_deletion == "NOT_PERFORMED"
    assert ok.persistence_verified is True
    assert ok.retrieval_verified is True
    assert ok.checkpoint_id
    assert ok.context_pack_id

    blocked = plan_compaction(
        memory.vault,
        session_id="s-no",
        candidates=[
            MemoryCandidate(
                type=MemoryType.CONSTRAINT,
                title="Keep writes contained",
                body="trusted_root is mandatory.",
                scope=StorageScope.SHAREABLE,
            )
        ],
        checkpoint=checkpoint_candidate_from_kwargs(goal="second"),
        task="containment",
        budget=2000,
        extraction_complete=False,
    )
    assert blocked.safe_to_compact is False
    assert any("extraction_complete" in r for r in blocked.reasons)

    broken = plan_compaction(
        memory.vault,
        session_id="s-bad",
        candidates=[
            MemoryCandidate(
                type=MemoryType.FAILURE,
                title="dup",
                id="FAIL-0001",
                scope=StorageScope.SHAREABLE,
            )
        ],
        checkpoint=checkpoint_candidate_from_kwargs(goal="will fail persist"),
        task="containment",
        budget=2000,
        extraction_complete=True,
    )
    assert broken.safe_to_compact is False
    assert broken.reasons


def test_host_api_on_promptgraph(project):
    pg = PromptGraph(project_root=project, trusted_root=project)
    rec = pg.record_memory(failure_candidate())
    hits = pg.search_memory("windows junction")
    assert rec.id in [h.record_id for h in hits]
    report = pg.validate_memory()
    assert report.record_count >= 1
    pack = pg.build_context_pack("windows containment", budget=1500)
    assert pack.total_tokens <= 1500
