"""TokenBudget — estimate, allocate, and enforce token budgets for context.

PG-01 fix: There is ONE authoritative token-accounting path
(``estimate_tokens`` / ``estimate_token_count`` in models).  The budget
manager does not double-count: it estimates each node's content cost once.

PG-08 fix: ``budget=0`` means zero tokens.  Callers must pass ``None``
explicitly when they want no limit (handled by callers, not here).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .exceptions import TokenBudgetError
from .models import ContextNode, estimate_token_count

DEFAULT_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Estimate token count of a text string using a simple heuristic."""
    return estimate_token_count(text, chars_per_token)


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
            return 1.0 if self.total_tokens > 0 else 0.0
        return self.total_tokens / self.budget


class TokenBudgetManager:
    """Allocates a token budget across context nodes.

    Selection strategy (deterministic):
      - Nodes are ranked by priority (lower value = more critical first),
        preserving caller ordering within the same priority.
      - Greedily include nodes until the budget is reached.

    Zero budget is valid: it means no nodes can be selected (unless they
    have zero token cost).
    """

    def __init__(self, budget: int, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> None:
        if budget < 0:
            raise TokenBudgetError("Budget must be non-negative.")
        if budget == 0:
            # Zero is valid — it means allow nothing.
            pass
        self.budget = budget
        self.chars_per_token = chars_per_token

    def plan(self, nodes: Sequence[ContextNode]) -> BudgetResult:
        """Select the highest-value set of nodes that fits within the budget.

        Nodes are sorted by priority only; their relative ordering from
        the caller is preserved (stable sort).  This allows callers like
        ``ContextSelector`` to pre-rank by relevance and have that order
        respected within each priority tier.

        Returns a ``BudgetResult`` with ``selected``, ``excluded``,
        ``total_tokens``, and ``over_budget`` flag.  Nodes that
        individually exceed the budget are excluded and flagged.
        """
        # Ensure token estimates are populated.
        prepared = [self._prepared(node) for node in nodes]

        # Stable sort by priority only (preserves caller ordering within tier).
        prepared.sort(key=lambda n: n.priority)

        selected: list[ContextNode] = []
        excluded: list[ContextNode] = []
        total = 0
        for node in prepared:
            if total + node.token_estimate <= self.budget:
                selected.append(node)
                total += node.token_estimate
            else:
                excluded.append(node)
        # Flag over_budget if any individual node exceeds the budget.
        over = any(n.token_estimate > self.budget for n in prepared)
        return BudgetResult(
            selected=selected,
            total_tokens=total,
            budget=self.budget,
            excluded=excluded,
            over_budget=over,
        )

    @staticmethod
    def _prepared(node: ContextNode) -> ContextNode:
        node.estimate_tokens()
        return node
