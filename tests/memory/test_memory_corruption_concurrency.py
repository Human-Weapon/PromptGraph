from __future__ import annotations

import multiprocessing as mp

import pytest

from promptgraph.exceptions import MemoryValidationError
from promptgraph.memory import ProjectMemory
from promptgraph.memory.host import ProjectMemory as PM
from promptgraph.memory.serialize import parse_frontmatter
from tests.memory.helpers import failure_candidate


def test_invalid_utf8(memory):
    rec = memory.record_memory(failure_candidate())
    path = memory.vault.resolve_rel(memory.index.get(rec.id)["relpath"])
    path.write_bytes(b"\xff\xfe not utf8")
    with pytest.raises(MemoryValidationError, match="UTF-8"):
        memory.vault.read_text(path)
    report = memory.validate_memory()
    assert report.corrupt_records
    assert report.status == "analysis_incomplete"


def test_truncated_frontmatter(memory):
    rec = memory.record_memory(failure_candidate())
    path = memory.vault.resolve_rel(memory.index.get(rec.id)["relpath"])
    path.write_text('---\nid: "FAIL-0001"\n', encoding="utf-8")
    with pytest.raises(MemoryValidationError):
        parse_frontmatter(path.read_text(encoding="utf-8"))


def test_missing_link_is_unresolved_not_invented(memory):
    memory.record_memory(
        {
            "type": "decision",
            "title": "Depends on missing",
            "body": "See [[DEC-9999]]",
            "scope": "shareable",
            "related": ["DEC-9999"],
        }
    )
    report = memory.validate_memory()
    assert report.unresolved_links
    assert all("DEC-9999" in item for item in report.unresolved_links)


def _worker(project: str, title: str, queue) -> None:
    try:
        mem = PM(project, trusted_root=project)
        rec = mem.record_memory(failure_candidate(title=title))
        queue.put(("ok", rec.id))
    except Exception as exc:  # noqa: BLE001
        queue.put(("err", f"{type(exc).__name__}: {exc}"))


def test_concurrent_writers_unique_ids(project):
    mem = ProjectMemory(project, trusted_root=project)
    mem.init()
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    procs = [
        ctx.Process(target=_worker, args=(str(project), f"Failure {i}", queue)) for i in range(2)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=60)
        if proc.is_alive():
            proc.terminate()
    results = []
    while not queue.empty():
        results.append(queue.get_nowait())
    oks = [item[1] for item in results if item[0] == "ok"]
    mem.index.invalidate()
    mem.index.load()
    ids = mem.index.ids()
    if len(oks) == 2:
        assert len(set(oks)) == 2
        assert set(oks) <= ids
    else:
        assert results
        assert all(item[0] == "err" or item[1] in ids for item in results)
        assert "lost" not in "".join(str(r) for r in results)
