from __future__ import annotations

from promptgraph.memory.models import MemoryRecord, MemoryType, StorageScope
from promptgraph.memory.serialize import (
    extract_wiki_ids,
    markdown_to_record,
    parse_frontmatter,
    record_to_markdown,
)
from tests.memory.helpers import failure_candidate


def test_roundtrip_failure(memory):
    rec = memory.record_memory(failure_candidate())
    text = record_to_markdown(rec)
    back = markdown_to_record(text)
    assert back.fingerprint() == rec.fingerprint()
    assert back.failed_attempts[0].approach_key == "filesystem:string-normalization-only"
    assert back.failed_attempts[1].why.startswith("The test could not")


def test_unicode_roundtrip(memory):
    rec = memory.record_memory(
        failure_candidate(title="Fallo de unión Windows 連結", problem="日本語とemoji 🧪")
    )
    back = markdown_to_record(record_to_markdown(rec))
    assert "連結" in back.title
    assert "🧪" in back.problem


def test_wiki_links_extracted():
    ids = extract_wiki_ids("See [[DEC-0018-filesystem-containment]] and [[LESSON-0007]].")
    assert "DEC-0018" in ids
    assert "LESSON-0007" in ids


def test_code_fences_and_fake_frontmatter_stay_in_body():
    rec = MemoryRecord(
        id="ARCH-0001",
        type=MemoryType.ARCHITECTURE,
        title="Safe notes",
        scope=StorageScope.SHAREABLE,
        body='```\n---\nid: "FAKE-9999"\ntype: "failure"\n---\n```\n## Hostile\nnot metadata',
    )
    text = record_to_markdown(rec)
    meta, body = parse_frontmatter(text)
    assert meta["id"] == "ARCH-0001"
    assert "FAKE-9999" in body
    back = markdown_to_record(text)
    assert back.id == "ARCH-0001"
    assert "FAKE-9999" in back.body


def test_deterministic_serialization(memory):
    rec = memory.record_memory(failure_candidate())
    assert record_to_markdown(rec) == record_to_markdown(rec)
