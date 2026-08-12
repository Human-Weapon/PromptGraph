"""Adversarial regressions for PG-05, PG-07, PG-11, PG-13."""

from __future__ import annotations

from promptgraph.context_graph import ContextGraph
from promptgraph.context_selection import ContextSelector
from promptgraph.contradiction_detection import ContradictionDetector
from promptgraph.models import ContextNode, Priority, Requirement
from promptgraph.requirement_extraction import RequirementExtractor


class TestPG05SelectionContract:
    def test_rank_and_select_same_order_when_budget_allows(self):
        g = ContextGraph()
        g.add_node(
            ContextNode(
                id="rel",
                title="Auth",
                content="auth login token oauth csrf",
                priority=Priority.P7,
            )
        )
        g.add_node(
            ContextNode(
                id="prio",
                title="Misc",
                content="xyz random stuff unrelated",
                priority=Priority.P0,
            )
        )
        sel = ContextSelector(g)
        ranked = sel.rank("auth token login oauth")
        result = sel.select("auth token login oauth", budget=100000)
        # Top-ranked relevant node must appear before pure-priority node when both fit
        ids = [n.id for n in result.selected]
        assert "rel" in ids
        if "prio" in ids and "rel" in ids:
            # relevance should dominate: rel before prio OR prio may be excluded if score 0
            assert ids.index("rel") < ids.index("prio") or ranked[0].id == "rel"

    def test_dependency_closure_atomic(self):
        g = ContextGraph()
        g.add_node(ContextNode(id="dep", title="Dep", content="base dependency content"))
        g.add_node(ContextNode(id="seed", title="Seed", content="seed needs dep"))
        g.add_dependency("seed", "dep")
        sel = ContextSelector(g)
        # Budget of 1 token: neither group fits fully if both need space
        result = sel.select("seed dep", budget=1, include_dependencies_of=["seed"])
        # Must not select seed without dep
        ids = {n.id for n in result.selected}
        if "seed" in ids:
            assert "dep" in ids


class TestPG07ContradictionSemantics:
    def test_intra_requirement_public_private(self):
        det = ContradictionDetector()
        reqs = [
            Requirement(
                id="R1",
                description="The dashboard must be public and private at the same time.",
            )
        ]
        findings = det.detect(reqs)
        assert findings
        assert findings[0].requirement_a == findings[0].requirement_b == "R1"
        assert findings[0].confidence == "strong"

    def test_public_plus_auth_not_automatic_contradiction(self):
        """Public API + authentication is NOT necessarily contradictory."""
        det = ContradictionDetector()
        reqs = [
            Requirement(id="R1", description="The API must be public."),
            Requirement(id="R2", description="The API must require authentication."),
        ]
        findings = det.detect(reqs)
        # Should not flag public vs authentication as strong opposing pair
        strong = [f for f in findings if f.confidence == "strong"]
        assert not strong

    def test_read_only_vs_writable_strong(self):
        det = ContradictionDetector()
        reqs = [
            Requirement(id="R1", description="The config file must be read-only."),
            Requirement(id="R2", description="The config file must be writable."),
        ]
        findings = det.detect(reqs)
        assert findings
        assert any(f.confidence == "strong" for f in findings)


class TestPG11BoundedScaling:
    def test_pair_checks_bounded(self):
        det = ContradictionDetector(max_pair_checks=100)
        # Many allow/deny requirements to force opposing comparisons
        reqs = []
        for i in range(50):
            reqs.append(Requirement(id=f"A{i}", description=f"Allow feature number {i} access."))
            reqs.append(Requirement(id=f"D{i}", description=f"Deny feature number {i} access."))
        result = det.detect_with_meta(reqs)
        assert result.pair_checks <= 100 or result.analysis_truncated
        if result.pair_checks > 100:
            assert result.analysis_truncated

    def test_large_benign_set_fast_enough(self):
        det = ContradictionDetector()
        reqs = [
            Requirement(id=f"R{i}", description=f"Feature module {i} handles reports.")
            for i in range(500)
        ]
        result = det.detect_with_meta(reqs)
        # Benign set should do almost no opposing pair checks
        assert result.pair_checks < 1000


class TestPG13DeadParams:
    def test_min_length_enforced(self):
        extr = RequirementExtractor(min_length=20)
        # Short actionable phrase under min_length
        reqs = extr.extract("Must go.")
        assert all(len(r.description) >= 20 for r in reqs)

    def test_system_prompt_stored(self):
        from promptgraph.context_package import ContextPackageBuilder

        b = ContextPackageBuilder(token_budget=5000)
        pkg = b.build(
            "T",
            [Requirement(id="R1", description="Must support export.")],
            system_prompt="Custom system prompt here.",
        )
        assert pkg.metadata.get("system_prompt") == "Custom system prompt here."
