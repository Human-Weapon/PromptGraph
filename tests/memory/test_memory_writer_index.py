from __future__ import annotations

import json

from promptgraph.memory.models import RecordStatus
from tests.memory.helpers import failure_candidate


def test_readback_and_index(memory):
    rec = memory.record_memory(failure_candidate())
    again = memory.show(rec.id)
    assert again.fingerprint() == rec.fingerprint()
    assert rec.id in memory.index.ids()


def test_rebuild_from_markdown_only(memory):
    rec = memory.record_memory(failure_candidate())
    (memory.vault.root / "index.json").unlink()
    (memory.vault.root / "graph.json").unlink()
    rebuilt = memory.rebuild()
    assert rebuilt["index"]
    memory.index.invalidate()
    assert memory.index.get(rec.id)["title"] == rec.title
    a = json.loads((memory.vault.root / "index.json").read_text(encoding="utf-8"))
    memory.rebuild()
    b = json.loads((memory.vault.root / "index.json").read_text(encoding="utf-8"))
    assert a["fingerprint"] == b["fingerprint"]
    assert a["records"] == b["records"]


def test_corrupt_index_rebuilds(memory):
    memory.record_memory(failure_candidate())
    (memory.vault.root / "index.json").write_text("{not json", encoding="utf-8")
    memory.index.invalidate()
    data = memory.index.load()
    assert "FAIL-0001" in data["records"]


def test_no_silent_repair_of_corrupt_record(memory):
    rec = memory.record_memory(failure_candidate())
    path = memory.vault.resolve_rel(memory.index.get(rec.id)["relpath"])
    path.write_text("not a memory record", encoding="utf-8")
    memory.index.invalidate()
    rebuilt = memory.index.rebuild()
    assert rebuilt["corrupt"]
    report = memory.validate_memory()
    assert report.corrupt_records
    assert report.status == "analysis_incomplete"


def test_supersession_keeps_history(memory):
    first = memory.record_memory(
        {
            "type": "decision",
            "title": "Use string paths",
            "body": "Normalize strings only.",
            "scope": "shareable",
            "disposition": "canonical",
        }
    )
    second = memory.record_memory(
        {
            "type": "decision",
            "title": "Resolve real destinations",
            "body": "Follow junctions.",
            "scope": "shareable",
            "disposition": "canonical",
            "supersedes": [first.id],
        }
    )
    old = memory.show(first.id)
    assert old.status is RecordStatus.SUPERSEDED
    assert old.superseded_by == second.id
    assert memory.show(second.id).status is RecordStatus.ACTIVE


def test_lessons_do_not_delete_failures(memory):
    fail = memory.record_memory(failure_candidate())
    lesson = memory.record_memory(
        {
            "type": "lesson",
            "title": "Real OS tests",
            "body": "Do not mock junctions.",
            "scope": "shareable",
            "related": [fail.id],
            "area": "filesystem",
        }
    )
    assert memory.show(fail.id).id == fail.id
    assert fail.id in lesson.related
