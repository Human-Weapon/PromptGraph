"""Regression tests for PG-01: Token budget enforcement."""

from __future__ import annotations

import pytest

from promptgraph.context_package import ContextPackageBuilder
from promptgraph.models import ContextNode, Requirement
from promptgraph.token_budget import TokenBudgetManager, estimate_tokens


class TestPG01TokenBudgetEnforcement:
    """Black-box: final_rendered_estimate <= configured_budget."""

    def test_budget_not_exceeded_normal(self):
        """Under normal successful generation, tokens must not exceed budget."""
        builder = ContextPackageBuilder(token_budget=5000)
        reqs = [Requirement(id="R1", description="Must do X.")]
        pkg = builder.build("Test", reqs)
        assert pkg.total_tokens <= builder.token_budget or pkg.budget_exceeded

    def test_no_double_counting(self):
        """Tokens should be counted once from rendered prompt, not node+rendered."""
        builder = ContextPackageBuilder(token_budget=100000)
        big = ContextNode(id="n1", title="Big", content="x" * 800)
        reqs = [Requirement(id="R1", description="Must do something.")]
        pkg = builder.build("Test", reqs, [big])
        # Before fix: total was ~2x the rendered tokens (node counted twice).
        # After fix: total equals rendered prompt token count.
        rendered_tokens = estimate_tokens(pkg.prompt)
        assert pkg.total_tokens == rendered_tokens

    def test_zero_budget_valid(self):
        """budget=0 is valid; it means no token allocation."""
        mgr = TokenBudgetManager(budget=0)
        assert mgr.budget == 0

    def test_negative_budget_rejected(self):
        from promptgraph.exceptions import TokenBudgetError

        with pytest.raises(TokenBudgetError):
            TokenBudgetManager(budget=-1)

    def test_budget_exceeded_flag(self):
        """When content exceeds budget, budget_exceeded must be True."""
        builder = ContextPackageBuilder(token_budget=10)
        big = ContextNode(id="n1", title="Big", content="x" * 1000)
        reqs = [Requirement(id="R1", description="Must do something important.")]
        pkg = builder.build("Test", reqs, [big])
        assert pkg.budget_exceeded is True

    def test_excluded_nodes_visible(self):
        """Excluded nodes should be visible on the package."""
        builder = ContextPackageBuilder(token_budget=100000)
        excluded = [ContextNode(id="ex1", title="Excluded", content="excluded content")]
        reqs = [Requirement(id="R1", description="Must do X.")]
        pkg = builder.build("Test", reqs, excluded_nodes=excluded)
        assert len(pkg.excluded_nodes) == 1
