"""Regression tests for PG-02: Contradiction propagation and package status."""

from __future__ import annotations

from promptgraph.context_package import ContextPackageBuilder
from promptgraph.contradiction_detection import Contradiction
from promptgraph.core import PromptGraph
from promptgraph.models import ContextPackage, PackageStatus, Requirement


class TestPG02ContradictionPropagation:
    def test_package_has_contradictions_field(self):
        """ContextPackage must have a 'contradictions' field."""
        fields = ContextPackage.__dataclass_fields__
        assert "contradictions" in fields

    def test_package_has_status_field(self):
        fields = ContextPackage.__dataclass_fields__
        assert "status" in fields

    def test_contradictions_propagated_to_package(self):
        """prepare() must propagate contradictions to the package."""
        pg = PromptGraph()
        result = pg.prepare(
            "The file must be read-only after upload. Users must be able to write to the file."
        )
        pkg = result["package"]
        assert len(pkg.contradictions) > 0

    def test_strong_contradiction_blocks(self):
        """Strong contradiction should set status to BLOCKED."""
        builder = ContextPackageBuilder()
        contra = Contradiction(
            requirement_a="R1",
            requirement_b="R2",
            snippet_a="read-only",
            snippet_b="write to",
            confidence="strong",
        )
        reqs = [
            Requirement(id="R1", description="read-only"),
            Requirement(id="R2", description="write"),
        ]
        pkg = builder.build("T", reqs, contradictions=[contra])
        assert pkg.status == PackageStatus.BLOCKED

    def test_heuristic_contradiction_needs_clarification(self):
        builder = ContextPackageBuilder()
        contra = Contradiction(
            requirement_a="R1",
            requirement_b="R2",
            snippet_a="allow",
            snippet_b="deny",
            confidence="heuristic",
        )
        reqs = [
            Requirement(id="R1", description="allow X"),
            Requirement(id="R2", description="deny Y"),
        ]
        pkg = builder.build("T", reqs, contradictions=[contra])
        assert pkg.status == PackageStatus.NEEDS_CLARIFICATION

    def test_no_contradiction_is_ready(self):
        builder = ContextPackageBuilder()
        reqs = [Requirement(id="R1", description="Must do X.")]
        pkg = builder.build("T", reqs)
        assert pkg.status == PackageStatus.READY
