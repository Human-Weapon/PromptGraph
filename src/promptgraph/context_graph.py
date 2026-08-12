"""ContextGraph — build a dependency graph over context elements.

Enables dependency-aware traversal and detection of redundant context.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from .models import ContextNode


@dataclass
class Edge:
    """A directed dependency edge: how depends_on -> why depends_on."""

    to: str
    context: str = ""


class ContextGraph:
    """A directed acyclic graph (DAG) of context nodes.

    Nodes are referenced by id. Edges represent 'node_a depends on node_b'.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, ContextNode] = {}
        self._deps: dict[str, set[str]] = {}
        self._dependents: dict[str, set[str]] = {}

    def add_node(self, node: ContextNode) -> None:
        self._nodes[node.id] = node
        self._deps.setdefault(node.id, set())
        self._dependents.setdefault(node.id, set())

    def add_dependency(self, node_id: str, depends_on: str) -> None:
        if node_id not in self._nodes:
            raise KeyError(f"Unknown node: {node_id}")
        if depends_on not in self._nodes:
            raise KeyError(f"Unknown dependency node: {depends_on}")
        if node_id == depends_on:
            raise ValueError("A node cannot depend on itself.")
        self._deps[node_id].add(depends_on)
        self._dependents[depends_on].add(node_id)

    @property
    def nodes(self) -> list[ContextNode]:
        return list(self._nodes.values())

    def get(self, node_id: str) -> ContextNode | None:
        return self._nodes.get(node_id)

    def dependencies_of(self, node_id: str) -> set[str]:
        return set(self._deps.get(node_id, set()))

    def dependents_of(self, node_id: str) -> set[str]:
        return set(self._dependents.get(node_id, set()))

    def has_cycle(self) -> bool:
        """Detect a cycle in the graph (Kahn's algorithm over remaining nodes)."""

        def _visit(n: str, visiting: set[str], visited: set[str]) -> bool:
            if n in visiting:
                return True
            if n in visited:
                return False
            visiting.add(n)
            for dep in self._deps.get(n, set()):
                if _visit(dep, visiting, visited):
                    return True
            visiting.discard(n)
            visited.add(n)
            return False

        visited: set[str] = set()
        for n in self._nodes:
            if _visit(n, set(), visited):
                return True
        return False

    def topological_order(self) -> list[str]:
        """Return node ids in dependency order (dependencies first).

        Raises ValueError if the graph contains a cycle.
        """
        if self.has_cycle():
            raise ValueError("Cannot produce topological order for a cyclic graph.")
        indegree = {n: len(self._deps.get(n, set())) for n in self._nodes}
        queue = deque(sorted(n for n, d in indegree.items() if d == 0))
        order: list[str] = []
        ordered: set[str] = set()
        while queue:
            n = queue.popleft()
            order.append(n)
            ordered.add(n)
            for dependent in sorted(self._dependents.get(n, set())):
                if dependent not in ordered:
                    indegree[dependent] -= 1
                    if indegree[dependent] == 0:
                        queue.append(dependent)
        return order

    def closure_from(self, seed_ids: Iterable[str], direction: str = "dependencies") -> set[str]:
        """Return the full transitive closure reachable from seed nodes.

        direction='dependencies' follows 'X depends on Y' edges (upstream).
        direction='dependents' follows 'X is a dependency of Y' edges (downstream).
        Raises KeyError on unknown seed id.
        """
        seeds = list(seed_ids)
        for s in seeds:
            if s not in self._nodes:
                raise KeyError(f"Unknown node: {s}")
        edges = self._deps if direction == "dependencies" else self._dependents
        if direction not in ("dependencies", "dependents"):
            raise ValueError("direction must be 'dependencies' or 'dependents'")
        closure: set[str] = set(seeds)
        queue = deque(seeds)
        while queue:
            n = queue.popleft()
            for nxt in edges.get(n, set()):
                if nxt not in closure:
                    closure.add(nxt)
                    queue.append(nxt)
        return closure
