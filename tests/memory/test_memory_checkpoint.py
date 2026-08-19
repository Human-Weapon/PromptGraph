from __future__ import annotations

from promptgraph.memory.session import checkpoint_is_stale
from tests.memory.helpers import failure_candidate


def test_checkpoint_and_freshness(memory):
    fail = memory.record_memory(failure_candidate())
    cp = memory.checkpoint_session(
        goal="Fix containment",
        remaining="write the real junction test",
        related=(fail.id,),
    )
    stale, reasons = checkpoint_is_stale(cp, memory.vault, memory.index)
    assert stale is False
    assert cp.remaining
    broken = memory.checkpoint_session(
        goal="Points at missing",
        related=("FAIL-9999",),
    )
    stale2, reasons2 = checkpoint_is_stale(broken, memory.vault, memory.index)
    assert stale2 is True
    assert any("FAIL-9999" in r for r in reasons2)


def test_status_mentions_checkpoint(memory):
    memory.checkpoint_session(goal="keep going")
    status = memory.status()
    assert status["checkpoint_id"]
    assert status["exists"] is True
