"""ContextSelection — select relevant context from available sources.

Works with a ContextGraph and a token budget to pick the most relevant context
nodes for a given task/query, avoiding redundant context.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .context_graph import ContextGraph
from .models import ContextNode
from .token_budget import BudgetResult, TokenBudgetManager


def tokenize_terms(text: str) -> set[str]:
    """Extract a set of lowercase keyword terms from text (stopwords removed)."""
    _STOP = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "for",
        "nor",
        "so",
        "to",
        "of",
        "on",
        "in",
        "at",
        "by",
        "with",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "from",
        "will",
        "would",
        "can",
        "could",
        "shall",
        "should",
        "must",
        "do",
        "does",
        "did",
        "not",
        "have",
        "has",
        "had",
        "any",
        "all",
        "each",
        "every",
        "please",
        "you",
    }
    tokens = [
        t for t in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if t not in _STOP and len(t) > 1
    ]
    return set(tokens)


class ContextSelector:
    """Select the subset of a context graph most relevant to a task query."""

    def __init__(self, graph: ContextGraph) -> None:
        self.graph = graph

    def rank(
        self,
        query: str,
        nodes: Sequence[ContextNode] | None = None,
        *,
        include_dependencies_of: Iterable[str] = (),
    ) -> list[ContextNode]:
        """Rank context nodes by relevance to the query, most relevant first.

        - Direct token overlap with the query boosts score.
        - Nodes reachable as dependencies of explicitly requested seed ids are
          promoted (they are needed to understand the seeds).
        """
        candidates = list(nodes) if nodes is not None else list(self.graph.nodes)
        query_terms = tokenize_terms(query)
        dependency_seeds: set[str] = set(include_dependencies_of)
        promote: set[str] = set()
        if dependency_seeds:
            promote = self.graph.closure_from(dependency_seeds, direction="dependencies") - set(
                dependency_seeds
            )

        scored: list[tuple[float, ContextNode]] = []
        for node in candidates:
            content = tokenize_terms(f"{node.title} {node.content}")
            overlap = len(query_terms & content)
            score = overlap
            if node.id in dependency_seeds:
                score += 10  # explicitly requested
            elif node.id in promote:
                score += 4  # needed by explicitly requested seeds
            # Small specificity bonus for nodes whose title matches a query term.
            title_tokens = tokenize_terms(node.title)
            if query_terms & title_tokens:
                score += 2
            if score > 0:
                scored.append((score, node))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [n for _, n in scored]

    def select(
        self,
        query: str,
        budget: int,
        nodes: Sequence[ContextNode] | None = None,
        *,
        include_dependencies_of: Iterable[str] = (),
    ) -> BudgetResult:
        """Rank then fit the best context within a token budget.

        PG-05 fix: The ranking from ``rank()`` is preserved within each
        priority tier.  ``TokenBudgetManager.plan()`` uses a stable sort
        by priority only, so relevance ordering is not discarded.
        """
        ranked = self.rank(query, nodes=nodes, include_dependencies_of=include_dependencies_of)
        manager = TokenBudgetManager(budget=budget)
        return manager.plan(ranked)
