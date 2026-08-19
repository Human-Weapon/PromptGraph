from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from promptgraph.exceptions import DuplicateMemoryError, MemoryValidationError
from promptgraph.memory.models import (
    Disposition,
    EvidenceStatus,
    MemoryRecord,
    MemoryType,
    RecordStatus,
    RootCauseStatus,
)
from tests.memory.helpers import failure_candidate


def test_unknown_type_rejected():
    with pytest.raises(MemoryValidationError, match="Unknown memory type"):
        MemoryRecord.from_dict({"id": "X-0001", "type": "vibes", "title": "nope"})


def test_duplicate_id_rejected(memory):
    memory.record_memory(failure_candidate())
    with pytest.raises(DuplicateMemoryError):
        memory.record_memory(failure_candidate(id="FAIL-0001"))


def test_stable_ids_increment(memory):
    a = memory.record_memory(failure_candidate())
    b = memory.record_memory(failure_candidate(title="Another failure"))
    assert a.id == "FAIL-0001"
    assert b.id == "FAIL-0002"


def test_ephemeral_not_persisted(memory):
    with pytest.raises(MemoryValidationError, match="EPHEMERAL"):
        memory.record_memory(failure_candidate(disposition=Disposition.EPHEMERAL))


def test_null_vs_omitted_root_cause():
    omitted = MemoryRecord.from_dict(
        {"id": "FAIL-0001", "type": "failure", "title": "x", "scope": "shareable"}
    )
    explicit_null = MemoryRecord.from_dict(
        {
            "id": "FAIL-0001",
            "type": "failure",
            "title": "x",
            "scope": "shareable",
            "root_cause": None,
        }
    )
    present = MemoryRecord.from_dict(
        {
            "id": "FAIL-0001",
            "type": "failure",
            "title": "x",
            "scope": "shareable",
            "root_cause": "known",
            "root_cause_status": "confirmed",
        }
    )
    assert omitted.root_cause is None
    assert explicit_null.root_cause is None
    assert present.root_cause == "known"


def test_frozen_failed_attempts():
    rec = MemoryRecord.from_dict(
        {
            "id": "FAIL-0001",
            "type": "failure",
            "title": "x",
            "scope": "shareable",
            "failed_attempts": [{"title": "a", "result": "FAILED", "why": "nope"}],
        }
    )
    with pytest.raises((AttributeError, FrozenInstanceError)):
        rec.failed_attempts[0].title = "changed"  # type: ignore[misc]


def test_confirmed_root_cause_requires_value():
    with pytest.raises(MemoryValidationError):
        MemoryRecord(
            id="FAIL-0001",
            type=MemoryType.FAILURE,
            title="x",
            root_cause_status=RootCauseStatus.CONFIRMED,
            root_cause=None,
        )


def test_prefix_must_match_type():
    with pytest.raises(MemoryValidationError, match="prefix"):
        MemoryRecord(id="DEC-0001", type=MemoryType.FAILURE, title="x")


def test_evidence_status_survives():
    rec = MemoryRecord.from_dict(
        {
            "id": "FAIL-0001",
            "type": "failure",
            "title": "x",
            "scope": "shareable",
            "evidence_status": "reported",
        }
    )
    assert rec.evidence_status is EvidenceStatus.REPORTED
    assert rec.status is RecordStatus.ACTIVE
