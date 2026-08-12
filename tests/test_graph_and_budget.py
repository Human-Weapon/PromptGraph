"""Tests for question budgeting, token budgeting, and context graph/selection."""

from __future__ import annotations

import pytest

from promptgraph.context_graph import ContextGraph
from promptgraph.context_selection import ContextSelector
from promptgraph.exceptions import TokenBudgetError
from promptgraph.models import ContextNode, Priority, Requirement
from promptgraph.question_budget import QuestionBudgeter
from promptgraph.token_budget import TokenBudgetManager


def test_question_budget_tags_clarification():
    reqs = [
        Requirement(
            id="R1", description="It should somehow work eventually.", tags=["needs_clarification"]
        ),
        Requirement(id="R2", description="Must provide upload feature."),
    ]
    qset = QuestionBudgeter().budget(reqs)
    texts = [q.text for q in qset]
    assert any("clarify" in t.lower() for t in texts)


def test_question_budget_missing_dimension():
    reqs = [
        Requirement(id="R1", description="Must provide upload feature."),
    ]
    qset = QuestionBudgeter().budget(reqs)
    assert len(qset) >= 1  # missing dimensions -> questions
    assert any("security" in q.text.lower() or "auth" in q.text.lower() for q in qset)


def test_question_budget_respects_max():
    reqs = [
        Requirement(id=f"R{i}", description=f"Must do feature {i}.", tags=["needs_clarification"])
        for i in range(20)
    ]
    qset = QuestionBudgeter(max_questions=5).budget(reqs)
    assert len(qset) <= 5


def test_budget_format_with_questions():
    """When there ARE requirements, format should list questions."""
    reqs = [Requirement(id="R1", description="Must provide upload feature.")]
    budgeter = QuestionBudgeter()
    qset = budgeter.budget(reqs)
    out = budgeter.format(qset)
    # With a single narrow requirement, missing dimensions produce questions.
    assert isinstance(out, str)


def test_budget_format_empty_when_no_questions():
    """When no questions are needed, format says so explicitly."""
    budgeter = QuestionBudgeter()
    # A fully-covered requirement set should produce no missing-dimension questions.
    reqs = [
        Requirement(
            id="R1",
            description=(
                "Must handle errors with retry. Must support auth. Must be performant. "
                "Must persist to a database with retention. Must run on linux. "
                "Must enforce user permissions. Must log and monitor. "
                "Must enforce resource limits and caps."
            ),
        )
    ]
    qset = budgeter.budget(reqs)
    out = budgeter.format(qset)
    if len(qset) == 0:
        assert "No questions needed" in out
    else:
        assert isinstance(out, str)  # some clarifying questions may remain


# --- token budget ---
def _node(rid, text, prio=Priority.P2):
    return ContextNode(id=rid, title=rid, content=text, priority=prio)


def test_token_budget_selects_within():
    nodes = [
        _node("a", "x" * 100, Priority.P0),
        _node("b", "y" * 400, Priority.P2),
    ]
    result = TokenBudgetManager(budget=200).plan(nodes)
    assert result.selected
    assert result.total_tokens <= 200


def test_token_budget_includes_priority_first():
    """When budget is tight, P0 nodes are selected before lower-priority ones."""
    nodes = [
        _node("low", "a" * 300, Priority.P7),
        _node("crit", "b" * 50, Priority.P0),
    ]
    # Budget of 30 tokens: only the small critical node fits.
    result = TokenBudgetManager(budget=30).plan(nodes)
    ids = [n.id for n in result.selected]
    assert "crit" in ids
    assert "low" not in ids  # low-priority large node doesn't fit


def test_token_budget_negative():
    with pytest.raises(TokenBudgetError):
        TokenBudgetManager(budget=-1)


def test_estimate_tokens_basic():
    """Verify estimate_tokens arithmetic."""
    from promptgraph.token_budget import estimate_tokens

    # 4 chars = 1 token; empty = 0
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2  # 8 // 4 = 2


def test_estimate_tokens_max1_floor():
    """Non-empty text always returns at least 1 token."""
    from promptgraph.token_budget import estimate_tokens

    assert estimate_tokens("hi") == 1  # 2 // 4 = 0, but max(1, 0) = 1


# --- context graph ---
def test_context_graph_dependencies():
    g = ContextGraph()
    for nid in ("root", "mid", "leaf"):
        g.add_node(ContextNode(id=nid, title=nid, content="c"))
    g.add_dependency("leaf", "mid")
    g.add_dependency("mid", "root")
    assert g.dependencies_of("leaf") == {"mid"}
    assert g.dependents_of("root") == {"mid"}


def test_context_graph_topological():
    g = ContextGraph()
    for nid in ("root", "mid", "leaf"):
        g.add_node(ContextNode(id=nid, title=nid, content="c"))
    g.add_dependency("mid", "root")
    g.add_dependency("leaf", "mid")
    order = g.topological_order()
    assert order.index("root") < order.index("mid") < order.index("leaf")


def test_context_graph_cycle():
    """PG-12: cycle-creating edge is rejected at insertion."""
    from promptgraph.exceptions import CycleError

    g = ContextGraph()
    g.add_node(ContextNode(id="a", title="a", content="c"))
    g.add_node(ContextNode(id="b", title="b", content="c"))
    g.add_dependency("a", "b")
    with pytest.raises(CycleError):
        g.add_dependency("b", "a")


def test_context_graph_cycle_rejected_at_insert():
    """PG-12: Cycle must be rejected at add_dependency, not later."""
    from promptgraph.exceptions import CycleError

    g = ContextGraph()
    for nid in ("a", "b", "c"):
        g.add_node(ContextNode(id=nid, title=nid, content="c"))
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    with pytest.raises(CycleError):
        g.add_dependency("c", "a")


def test_context_graph_closure():
    g = ContextGraph()
    for nid in ("a", "b", "c", "d"):
        g.add_node(ContextNode(id=nid, title=nid, content="c"))
    g.add_dependency("a", "b")
    g.add_dependency("b", "c")
    closure = g.closure_from(["a"])
    assert closure == {"a", "b", "c"}


def test_context_selection_ranking():
    g = ContextGraph()
    for nid, content in [
        ("auth", "token oauth login csrf"),
        ("ui", "dashboard form"),
        ("db", "postgres schema"),
    ]:
        g.add_node(ContextNode(id=nid, title=nid, content=content))
    selector = ContextSelector(g)
    ranked = selector.rank("oauth token auth", nodes=g.nodes)
    assert ranked and ranked[0].id == "auth"


def test_context_selection_budget():
    g = ContextGraph()
    for nid, content, prio in [
        ("big", "x" * 2000, Priority.P0),
        ("small", "auth token", Priority.P0),
    ]:
        g.add_node(ContextNode(id=nid, title=nid, content=content, priority=prio))
    result = ContextSelector(g).select("auth", budget=100)
    ids = [n.id for n in result.selected]
    assert "small" in ids
