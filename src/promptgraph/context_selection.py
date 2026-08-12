"""ContextSelection — select relevant context from available sources.

PG-05 contract:
  - Single scoring function combining relevance, priority, and size.
  - rank() and select() use the SAME order.
  - Dependencies of selected nodes are atomic (seed+deps fit together or
    the seed is excluded). Never return seed without required deps.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .context_graph import ContextGraph
from .models import ContextNode
from .token_budget import BudgetResult


def tokenize_terms(text: str) -> set[str]:
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
    return {t for t in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if t not in _STOP and len(t) > 1}


class ContextSelector:
    """Select the subset of a context graph most relevant to a task query."""

    def __init__(self, graph: ContextGraph) -> None:
        self.graph = graph

    def score_node(
        self,
        node: ContextNode,
        query_terms: set[str],
        *,
        seed_ids: set[str] | None = None,
        promote_ids: set[str] | None = None,
    ) -> float:
        """Deterministic combined score (higher is better).

        relevance dominates; priority is a mild tie-breaker; size is a tiny penalty.
        """
        content = tokenize_terms(f"{node.title} {node.content}")
        overlap = len(query_terms & content)
        title_bonus = 2.0 if query_terms & tokenize_terms(node.title) else 0.0
        relevance = float(overlap) + title_bonus
        prio_boost = (7 - int(node.priority)) * 0.5
        seed_boost = 100.0 if seed_ids and node.id in seed_ids else 0.0
        promote_boost = 20.0 if promote_ids and node.id in promote_ids else 0.0
        node.estimate_tokens()
        size_penalty = node.token_estimate * 0.001
        return relevance * 10.0 + prio_boost + seed_boost + promote_boost - size_penalty

    def rank(
        self,
        query: str,
        nodes: Sequence[ContextNode] | None = None,
        *,
        include_dependencies_of: Iterable[str] = (),
    ) -> list[ContextNode]:
        candidates = list(nodes) if nodes is not None else list(self.graph.nodes)
        query_terms = tokenize_terms(query)
        dependency_seeds = set(include_dependencies_of)
        promote: set[str] = set()
        if dependency_seeds:
            try:
                promote = (
                    self.graph.closure_from(dependency_seeds, direction="dependencies")
                    - dependency_seeds
                )
            except KeyError:
                promote = set()

        scored: list[tuple[float, str, ContextNode]] = []
        for node in candidates:
            s = self.score_node(node, query_terms, seed_ids=dependency_seeds, promote_ids=promote)
            if s > 0 or not query_terms:
                scored.append((s, node.id, node))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [n for _, _, n in scored]

    def select(
        self,
        query: str,
        budget: int,
        nodes: Sequence[ContextNode] | None = None,
        *,
        include_dependencies_of: Iterable[str] = (),
    ) -> BudgetResult:
        """Rank then fit using the same order as rank().

        Dependency closure is atomic per candidate node.
        """
        ranked = self.rank(query, nodes=nodes, include_dependencies_of=include_dependencies_of)
        by_id = {n.id: n for n in self.graph.nodes}
        if nodes is not None:
            for n in nodes:
                by_id.setdefault(n.id, n)

        selected: list[ContextNode] = []
        excluded: list[ContextNode] = []
        selected_ids: set[str] = set()
        total = 0

        for node in ranked:
            if node.id in selected_ids:
                continue

            # Atomic dependency group
            try:
                deps = self.graph.dependencies_of(node.id)
            except Exception:
                deps = set()
            if deps and node.id in by_id:
                try:
                    group_ids = self.graph.closure_from([node.id], direction="dependencies")
                except KeyError:
                    group_ids = {node.id}
            else:
                group_ids = {node.id}

            group_nodes: list[ContextNode] = []
            group_cost = 0
            incomplete = False
            for gid in sorted(group_ids):  # deterministic
                if gid in selected_ids:
                    continue
                gn = by_id.get(gid)
                if gn is None:
                    incomplete = True
                    break
                gn.estimate_tokens()
                group_nodes.append(gn)
                group_cost += gn.token_estimate

            if incomplete or total + group_cost > budget:
                excluded.append(node)
                continue

            for gn in group_nodes:
                if gn.id not in selected_ids:
                    selected.append(gn)
                    selected_ids.add(gn.id)
                    total += gn.token_estimate

        for node in ranked:
            if node.id not in selected_ids and all(e.id != node.id for e in excluded):
                excluded.append(node)

        over = any(n.estimate_tokens() > budget for n in ranked)
        return BudgetResult(
            selected=selected,
            total_tokens=total,
            budget=budget,
            excluded=excluded,
            over_budget=over,
        )
