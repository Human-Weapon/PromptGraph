"""ContextGraph — build a dependency graph over context elements.

PG-12 fix: The graph is documented as a DAG.  ``add_dependency`` now
rejects edges that would create a cycle at mutation time, raising
``CycleError`` immediately.  The graph never enters an invalid internal
state.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from .exceptions import CycleError
from .models import ContextNode


@dataclass
class Edge:
    """A directed dependency edge."""

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
        """Add a dependency edge. Raises ``CycleError`` if it would create a cycle.

        PG-12: Cycles are rejected at insertion time so the graph never
        enters an invalid state.
        """
        if node_id not in self._nodes:
            raise KeyError(f"Unknown node: {node_id}")
        if depends_on not in self._nodes:
            raise KeyError(f"Unknown dependency node: {depends_on}")
        if node_id == depends_on:
            raise CycleError("A node cannot depend on itself.")

        # Check if adding this edge would create a cycle.
        # A cycle exists if `depends_on` can already reach `node_id`
        # via its dependency chain.  We do a DFS from depends_on.
        if self._would_cycle(depends_on, node_id):
            raise CycleError(
                f"Adding dependency '{node_id}' -> '{depends_on}' would create "
                f"a cycle ('{depends_on}' already depends on '{node_id}')."
            )

        self._deps[node_id].add(depends_on)
        self._dependents[depends_on].add(node_id)

    def _would_cycle(self, start: str, target: str) -> bool:
        """Check if ``target`` is reachable from ``start`` via dependencies."""
        if start == target:
            return True
        visited: set[str] = set()
        stack = [start]
        while stack:
            n = stack.pop()
            if n == target:
                return True
            if n in visited:
                continue
            visited.add(n)
            stack.extend(self._deps.get(n, set()))
        return False

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
        """Detect a cycle (should never be True after PG-12 fix, but kept for safety)."""

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
        """Return node ids in dependency order (dependencies first)."""
        if self.has_cycle():
            raise CycleError("Cannot produce topological order for a cyclic graph.")
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
        """Return the full transitive closure reachable from seed nodes."""
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
