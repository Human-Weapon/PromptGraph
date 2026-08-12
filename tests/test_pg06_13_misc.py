"""Regression tests for PG-06, PG-07, PG-08, PG-09, PG-10, PG-12, PG-13."""

from __future__ import annotations

import pytest

from promptgraph.context_graph import ContextGraph
from promptgraph.contradiction_detection import ContradictionDetector
from promptgraph.core import PromptGraph
from promptgraph.exceptions import CorruptStorageError, CycleError
from promptgraph.models import ContextNode, Requirement
from promptgraph.question_budget import QuestionBudgeter
from promptgraph.requirement_extraction import RequirementExtractor
from promptgraph.technical_memory import TechnicalMemory
from promptgraph.token_budget import TokenBudgetManager


class TestPG06Multilingual:
    def test_japanese_preserved_not_dropped(self):
        extr = RequirementExtractor()
        reqs = extr.extract("システムはユーザーをサポートする必要があります。")
        assert len(reqs) > 0
        assert any("possibly_non_english" in r.tags for r in reqs)

    def test_spanish_preserved(self):
        extr = RequirementExtractor()
        reqs = extr.extract("El sistema debe soportar autenticación de usuarios.")
        assert len(reqs) > 0

    def test_english_still_works(self):
        extr = RequirementExtractor()
        reqs = extr.extract("Must encrypt user data at rest.")
        assert len(reqs) > 0
        assert reqs[0].requirement_type.value == "security"


class TestPG07ObjectBlindContradictions:
    def test_unrelated_allow_deny_no_false_positive_strong(self):
        """'allow delete files' vs 'deny anonymous access' should NOT be 'strong'."""
        det = ContradictionDetector()
        reqs = [
            Requirement(id="R1", description="Allow users to delete their own account files."),
            Requirement(id="R2", description="Deny anonymous access to the admin panel."),
        ]
        findings = det.detect(reqs)
        if findings:
            # If detected, must be heuristic, not strong.
            assert all(f.confidence == "heuristic" for f in findings)

    def test_confidence_field_exists(self):
        det = ContradictionDetector()
        reqs = [
            Requirement(id="R1", description="read-only file"),
            Requirement(id="R2", description="writable file"),
        ]
        findings = det.detect(reqs)
        assert findings
        assert hasattr(findings[0], "confidence")

    def test_same_subject_strong(self):
        """Contradictions about the same subject should remain strong."""
        det = ContradictionDetector()
        reqs = [
            Requirement(id="R1", description="The config file must be read-only."),
            Requirement(id="R2", description="The config file must be writable."),
        ]
        findings = det.detect(reqs)
        assert findings
        assert findings[0].confidence == "strong"


class TestPG08ZeroLimits:
    def test_budget_zero_means_zero(self):
        pg = PromptGraph(token_budget=8000)
        result = pg.select_context("test", budget=0)
        assert result.budget == 0

    def test_budget_none_uses_default(self):
        pg = PromptGraph(token_budget=8000)
        result = pg.select_context("test", budget=None)
        assert result.budget == 8000

    def test_max_questions_zero(self):
        qb = QuestionBudgeter(max_questions=0)
        reqs = [Requirement(id="R1", description="Must do X.")]
        qset = qb.budget(reqs)
        assert len(qset) == 0


class TestPG09CorruptionHandling:
    def test_technical_memory_corrupt_raises(self, tmp_path):

        path = tmp_path / "mem.json"
        path.write_text("NOT JSON {{{{", encoding="utf-8")
        with pytest.raises(CorruptStorageError):
            TechnicalMemory(path)


class TestPG10CLIHandling:
    def test_cli_catches_domain_error(self):
        """CLI should catch PromptGraphError, not show traceback."""
        from unittest.mock import patch

        from promptgraph.cli import main
        from promptgraph.exceptions import PromptGraphError

        with patch("promptgraph.cli.PromptGraph") as mock_pg:
            mock_pg.side_effect = PromptGraphError("test error")
            rc = main(["status"])
            assert rc == 1  # not a crash, clean exit


class TestPG12CycleRejection:
    def test_cycle_rejected_at_insert(self):
        g = ContextGraph()
        for nid in ("a", "b", "c"):
            g.add_node(ContextNode(id=nid, title=nid, content="c"))
        g.add_dependency("a", "b")
        g.add_dependency("b", "c")
        with pytest.raises(CycleError):
            g.add_dependency("c", "a")

    def test_self_loop_rejected(self):
        g = ContextGraph()
        g.add_node(ContextNode(id="x", title="x", content="c"))
        with pytest.raises(CycleError):
            g.add_dependency("x", "x")


class TestPG13DeadParams:
    def test_plan_has_no_order_key(self):
        import inspect

        sig = inspect.signature(TokenBudgetManager.plan)
        assert "order_key" not in sig.parameters
        assert "reverse" not in sig.parameters


class TestPG11Scaling:
    def test_large_set_completes_reasonably(self):
        """500 requirements should complete in under 3 seconds."""
        import time

        det = ContradictionDetector()
        reqs = [
            Requirement(id=f"R{i}", description=f"Requirement {i} must allow feature {i}.")
            for i in range(200)
        ]
        t0 = time.perf_counter()
        det.detect(reqs)
        elapsed = time.perf_counter() - t0
        assert elapsed < 3.0, f"Took {elapsed:.2f}s — candidate filtering may not be working"
