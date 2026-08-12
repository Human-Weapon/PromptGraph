"""Tests for contradiction and missing-requirement detection."""

from __future__ import annotations

from promptgraph.contradiction_detection import ContradictionDetector
from promptgraph.missing_requirement_detection import MissingRequirementDetector
from promptgraph.models import Requirement


def _req(desc: str, rid: str = "R1") -> Requirement:
    return Requirement(id=rid, description=desc)


def test_contradiction_detect():
    detector = ContradictionDetector()
    findings = detector.detect(
        [
            _req("The file must be read-only after upload.", "R1"),
            _req("Users must be able to write to the file.", "R2"),
        ]
    )
    assert findings
    assert findings[0].requirement_a in ("R1", "R2")
    assert findings[0].requirement_b in ("R1", "R2")


def test_no_false_contradiction():
    detector = ContradictionDetector()
    findings = detector.detect(
        [
            _req("Support both upload and download.", "R1"),
            _req("Allow access after login.", "R2"),
        ]
    )
    # 'allow'/'support' alone don't trigger a contradiction pair.
    assert not findings


def test_contradiction_to_dict():
    detector = ContradictionDetector()
    f = detector.detect([_req("deny all access.", "R1"), _req("enable anonymous login.", "R2")])
    assert f, "Expected a contradiction between 'enable' and 'deny'"
    d = f[0].to_dict()
    assert "requirement_a" in d
    assert d["requirement_a"] == "R1"
    assert d["requirement_b"] == "R2"


def test_missing_detection_no_requirements():
    detector = MissingRequirementDetector()
    findings = detector.detect([])
    assert any(not f.dimension or f.dimension == "baseline" for f in findings)


def test_missing_detection_finds_gaps():
    """A narrow requirement should surface several missing dimensions."""
    detector = MissingRequirementDetector()
    findings = detector.detect([_req("just a basic module.", "R1")])
    dims = {f.dimension for f in findings}
    # At least security and error_handling should be flagged.
    assert "security" in dims
    assert "error_handling" in dims


def test_missing_detection_with_full_coverage():
    """When all major dimensions are mentioned, few or none should be missing."""
    detector = MissingRequirementDetector()
    covered = (
        "Must handle errors with retry. Must support auth. Must be performant. "
        "Must persist to a database with retention. Must run on linux. "
        "Must enforce user permissions. Must log and monitor. "
        "Must enforce resource limits and caps."
    )
    findings = detector.detect([_req(covered, "R1")])
    dims = {f.dimension for f in findings}
    # All our detector's known dimensions should be covered.
    for critical in (
        "security",
        "error_handling",
        "performance",
        "data_retention",
        "compatibility",
        "access_control",
        "observability",
        "resource_limits",
    ):
        assert critical not in dims, f"Dimension '{critical}' should be covered"


def test_missing_to_dict():
    detector = MissingRequirementDetector()
    f = detector.detect([_req("just a basic module.", "R1")])
    found = [x for x in f if x.dimension in {"security", "error_handling"}]
    assert found
    assert "suggested_question" in found[0].to_dict()
