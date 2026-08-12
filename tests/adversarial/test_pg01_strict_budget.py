"""Adversarial regression: PG-01 strict token budget.

Contract:
  A successful package MUST NOT exceed its configured hard budget.
  If mandatory content cannot fit: raise BudgetExceededError.
  Never return READY above budget.
"""

from __future__ import annotations

import pytest

from promptgraph.context_package import ContextPackageBuilder
from promptgraph.exceptions import BudgetExceededError, TokenBudgetError
from promptgraph.models import ContextNode, PackageStatus, Requirement


class TestPG01StrictBudget:
    def test_mandatory_over_budget_raises(self):
        """ContextPackageBuilder(10) + content >10 must raise BudgetExceededError."""
        builder = ContextPackageBuilder(token_budget=10)
        reqs = [
            Requirement(
                id="R1",
                description=(
                    "Must encrypt user passwords at rest with AES-256 "
                    "and rotate keys every 90 days without exception."
                ),
            )
        ]
        with pytest.raises(BudgetExceededError):
            builder.build("Over budget task", reqs)

    def test_successful_package_never_exceeds_budget(self):
        """Any successfully returned package must satisfy total_tokens <= budget."""
        builder = ContextPackageBuilder(token_budget=500)
        reqs = [Requirement(id="R1", description="Must support CSV export.")]
        nodes = [ContextNode(id="n1", title="Note", content="short note")]
        pkg = builder.build("OK", reqs, nodes)
        assert pkg.total_tokens <= pkg.token_budget
        assert pkg.budget_exceeded is False
        assert pkg.status != PackageStatus.BLOCKED or pkg.total_tokens <= pkg.token_budget

    def test_headings_count_in_budget(self):
        """Rendered headings/structure must be part of the same token count."""
        builder = ContextPackageBuilder(token_budget=100000)
        reqs = [Requirement(id="R1", description="Must do X.")]
        pkg = builder.build("Title with structure", reqs)
        # Prompt includes markdown headings — tokens must equal estimate of final prompt.
        from promptgraph.models import estimate_token_count

        assert pkg.total_tokens == estimate_token_count(pkg.prompt)
        assert "# Title with structure" in pkg.prompt
        assert "## Requirements" in pkg.prompt

    def test_budget_zero_rejects_nonempty_mandatory(self):
        builder = ContextPackageBuilder(token_budget=0)
        reqs = [Requirement(id="R1", description="Must do anything at all.")]
        with pytest.raises(BudgetExceededError):
            builder.build("Zero", reqs)

    def test_budget_negative_rejected_at_construction(self):
        with pytest.raises(TokenBudgetError):
            ContextPackageBuilder(token_budget=-1)

    def test_optional_context_trimmed_not_mandatory(self):
        """Optional nodes are dropped to fit; mandatory requirements remain."""
        builder = ContextPackageBuilder(token_budget=80)
        reqs = [Requirement(id="R1", description="Must support login.")]
        huge = ContextNode(id="big", title="Big", content="x" * 2000)
        pkg = builder.build("Trim", reqs, [huge])
        assert pkg.total_tokens <= 80
        assert pkg.budget_exceeded is False
        # Huge optional node must not appear in selected context
        assert all(n.id != "big" for n in pkg.context_nodes)
        assert any(n.id == "big" for n in pkg.excluded_nodes)

    def test_never_ready_when_over_budget(self):
        """Even if exception is not raised in some path, READY over budget is forbidden.

        Primary contract is raise; this guards any alternate path.
        """
        builder = ContextPackageBuilder(token_budget=10)
        reqs = [
            Requirement(
                id="R1",
                description="Must encrypt everything with strong cryptography always.",
            )
        ]
        try:
            pkg = builder.build("X", reqs)
        except BudgetExceededError:
            return  # correct
        # If no exception, package must not be READY and must not be usable over budget
        assert pkg.total_tokens <= pkg.token_budget or pkg.status != PackageStatus.READY
        assert pkg.total_tokens <= pkg.token_budget  # strict: never over budget if returned
