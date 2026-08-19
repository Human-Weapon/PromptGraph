from __future__ import annotations

from pathlib import Path

import pytest

from promptgraph.memory import FailedAttempt, MemoryCandidate, ProjectMemory
from promptgraph.memory.models import (
    Disposition,
    EvidenceStatus,
    MemoryType,
    RootCauseStatus,
    StorageScope,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


@pytest.fixture
def memory(project: Path) -> ProjectMemory:
    mem = ProjectMemory(project, trusted_root=project)
    mem.init()
    return mem


def failure_candidate(**overrides) -> MemoryCandidate:
    data = dict(
        type=MemoryType.FAILURE,
        title="Windows junction escaped containment",
        scope=StorageScope.SHAREABLE,
        disposition=Disposition.PERSISTENT,
        area="filesystem",
        tags=("windows", "junction", "containment"),
        paths=("src/promptgraph/path_security.py",),
        problem="A directory junction could resolve outside the permitted project root.",
        evidence="The original test used mocked paths and did not exercise a real reparse point.",
        symptom="The suite passed even though the OS-level invariant had never been proved.",
        root_cause=(
            "The test reproduced implementation assumptions instead of real filesystem behavior."
        ),
        root_cause_status=RootCauseStatus.CONFIRMED,
        failed_attempts=(
            FailedAttempt(
                title="string-only path normalization",
                result="FAILED",
                why="Normalization does not resolve junction targets.",
                approach_key="filesystem:string-normalization-only",
                index=1,
            ),
            FailedAttempt(
                title="mocked junction test",
                result="INVALID EVIDENCE",
                why="The test could not falsify the defective implementation.",
                approach_key="filesystem:mocked-junction-only",
                index=2,
            ),
        ),
        solution="Resolve the actual target and enforce containment on the resolved destination.",
        lesson=(
            "Filesystem containment involving links/reparse points requires "
            "real filesystem objects."
        ),
        evidence_status=EvidenceStatus.VERIFIED,
    )
    data.update(overrides)
    return MemoryCandidate(**data)
