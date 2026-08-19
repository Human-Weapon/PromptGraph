from __future__ import annotations

from pathlib import Path

from promptgraph.memory import ProjectMemory


def test_sample_vault_surfaces_failed_approach():
    root = Path(__file__).resolve().parents[2] / "examples" / "project-memory"
    mem = ProjectMemory(root, trusted_root=root)
    pack = mem.build_context_pack("Fix Windows filesystem containment", budget=2000)
    assert "FAIL-0001" in pack.selected_ids
    assert "LESSON-0001" in pack.selected_ids
    assert "string-only path normalization" in pack.markdown
    assert "User:" not in pack.markdown
