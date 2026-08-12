"""TokenBudget — estimate, allocate, and enforce token budgets for context.

Helps keep context packages within model-specific token limits so agents get
precise, efficient context rather than redundant sprawl.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .exceptions import TokenBudgetError
from .models import ContextNode

# Rough heuristic for tokens per character. English ≈ 3.5-4 chars/token;
# code is denser. Configurable.
DEFAULT_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Estimate token count of a text string using a simple heuristic."""
    if not text:
        return 0
    return max(1, len(text) // chars_per_token)


def count_words(text: str) -> int:
    """Count whitespace-delimited words — used as a cheap secondary metric."""
    return len(text.split())


@dataclass
class BudgetResult:
    """Result of enforcing a token budget over candidate context nodes."""

    selected: list[ContextNode]
    total_tokens: int
    budget: int
    excluded: list[ContextNode] = field(default_factory=list)
    over_budget: bool = False

    @property
    def used_ratio(self) -> float:
        if self.budget <= 0:
            return 1.0
        return self.total_tokens / self.budget


class TokenBudgetManager:
    """Allocates a token budget across context nodes.

    Selection strategy (deterministic, configurable):
      - rank nodes by priority (higher first), then by size (smaller first)
      - greedily include nodes until the budget is reached
    This is a heuristic; callers can override with an explicit selection function.
    """

    def __init__(self, budget: int, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> None:
        if budget < 0:
            raise TokenBudgetError("Budget must be non-negative.")
        self.budget = budget
        self.chars_per_token = chars_per_token

    def plan(
        self,
        nodes: Sequence[ContextNode],
        order_key: str | None = None,
        reverse: bool = True,
    ) -> BudgetResult:
        """Select the highest-value set of nodes that fits within the budget.

        If a single node alone exceeds the budget it is still excluded, and the
        caller is warned via `over_budget`.
        """
        # Ensure token estimates are populated.
        ranked = [self._prepared(node) for node in nodes]

        # Default ranking: lower priority value (= more critical) first,
        # then smaller token size first.
        ranked.sort(key=lambda n: (n.priority, n.token_estimate, n.id))

        selected: list[ContextNode] = []
        excluded: list[ContextNode] = []
        total = 0
        for node in ranked:
            if total + node.token_estimate <= self.budget:
                selected.append(node)
                total += node.token_estimate
            else:
                excluded.append(node)
        over = any(n.token_estimate > self.budget for n in ranked)
        return BudgetResult(
            selected=selected,
            total_tokens=total,
            budget=self.budget,
            excluded=excluded,
            over_budget=over,
        )

    @staticmethod
    def _prepared(node: ContextNode) -> ContextNode:
        node.estimate_tokens()  # ensure accuracy
        return node
