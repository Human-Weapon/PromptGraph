"""Regression tests for PG-01: Token budget enforcement (strict)."""

from __future__ import annotations

import pytest

from promptgraph.context_package import ContextPackageBuilder
from promptgraph.exceptions import BudgetExceededError, TokenBudgetError
from promptgraph.models import ContextNode, Requirement
from promptgraph.token_budget import TokenBudgetManager, estimate_tokens


class TestPG01TokenBudgetEnforcement:
    def test_budget_not_exceeded_normal(self):
        """Under normal successful generation, tokens must not exceed budget."""
        builder = ContextPackageBuilder(token_budget=5000)
        reqs = [Requirement(id="R1", description="Must do X.")]
        pkg = builder.build("Test", reqs)
        assert pkg.total_tokens <= builder.token_budget
        assert pkg.budget_exceeded is False

    def test_no_double_counting(self):
        builder = ContextPackageBuilder(token_budget=100000)
        big = ContextNode(id="n1", title="Big", content="x" * 800)
        reqs = [Requirement(id="R1", description="Must do something.")]
        pkg = builder.build("Test", reqs, [big])
        rendered_tokens = estimate_tokens(pkg.prompt)
        assert pkg.total_tokens == rendered_tokens

    def test_zero_budget_valid_for_manager(self):
        mgr = TokenBudgetManager(budget=0)
        assert mgr.budget == 0

    def test_negative_budget_rejected(self):
        with pytest.raises(TokenBudgetError):
            TokenBudgetManager(budget=-1)
        with pytest.raises(TokenBudgetError):
            ContextPackageBuilder(token_budget=-1)

    def test_mandatory_over_budget_raises(self):
        """Mandatory content over budget raises — not a READY package."""
        builder = ContextPackageBuilder(token_budget=10)
        reqs = [
            Requirement(
                id="R1",
                description="Must encrypt user passwords at rest with AES-256 forever.",
            )
        ]
        with pytest.raises(BudgetExceededError):
            builder.build("Test", reqs)

    def test_optional_nodes_dropped_to_fit(self):
        """Huge optional nodes are dropped rather than exceeding budget."""
        builder = ContextPackageBuilder(token_budget=200)
        reqs = [Requirement(id="R1", description="Must support login.")]
        huge = ContextNode(id="n1", title="Big", content="x" * 5000)
        pkg = builder.build("Test", reqs, [huge])
        assert pkg.total_tokens <= 200
        assert any(n.id == "n1" for n in pkg.excluded_nodes) or not pkg.context_nodes

    def test_excluded_nodes_visible(self):
        builder = ContextPackageBuilder(token_budget=100000)
        excluded = [ContextNode(id="ex1", title="Excluded", content="excluded content")]
        reqs = [Requirement(id="R1", description="Must do X.")]
        pkg = builder.build("Test", reqs, excluded_nodes=excluded)
        assert len(pkg.excluded_nodes) == 1
