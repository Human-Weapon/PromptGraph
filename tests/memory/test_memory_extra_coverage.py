from __future__ import annotations

import json

from promptgraph.cli import main
from promptgraph.memory.context_pack import MemoryContextPackBuilder
from promptgraph.memory.models import Disposition, MemoryType, StorageScope
from tests.memory.helpers import failure_candidate


def test_suggest_consolidation(memory):
    for i in range(3):
        memory.record_memory(
            failure_candidate(
                title=f"Containment miss {i}",
                tags=("windows", "junction"),
                area="filesystem",
            )
        )
    suggestions = memory.suggest_consolidation()
    assert suggestions
    assert len(suggestions[0]["source_ids"]) >= 3


def test_validate_missing_vault(tmp_path):
    from promptgraph.memory import ProjectMemory

    report = ProjectMemory(tmp_path / "empty", trusted_root=tmp_path / "empty").validate_memory()
    assert report.ok is False
    assert report.status == "analysis_incomplete"


def test_stale_context_pack(memory):
    memory.record_memory(failure_candidate())
    pack = memory.build_context_pack("windows containment", budget=1200)
    memory.record_memory(failure_candidate(title="Another windows containment miss"))
    marked = MemoryContextPackBuilder(memory.vault).mark_stale_if_needed(pack)
    assert marked.stale is True


def test_cli_show_rebuild_and_help(project, capsys):
    assert main(["memory", "init", str(project), "--json"]) == 0
    json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                "memory",
                "record",
                str(project),
                "--type",
                "lesson",
                "--title",
                "Keep failures",
                "--scope",
                "shareable",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["memory", "show", str(project), "LESSON-0001", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "LESSON-0001"
    assert main(["memory", "rebuild", str(project), "--json"]) == 0
    json.loads(capsys.readouterr().out)
    assert main(["memory"]) == 2
    assert main(["context"]) == 2


def test_search_empty_vault(tmp_path):
    from promptgraph.memory import ProjectMemory

    mem = ProjectMemory(tmp_path / "none", trusted_root=tmp_path / "none")
    assert mem.search_memory("anything") == []


def test_canonical_constraint_type(memory):
    memory.record_memory(
        {
            "type": MemoryType.CONSTRAINT.value,
            "title": "No network",
            "body": "PromptGraph never phones home.",
            "scope": StorageScope.SHAREABLE.value,
            "disposition": Disposition.CANONICAL.value,
        }
    )
    hits = memory.search_memory("network phones home")
    assert any(h.record_id.startswith("CON-") for h in hits)
