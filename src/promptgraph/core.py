"""PromptGraph core — orchestrates the full context-preparation pipeline.

Pipeline:
    User's messy explanation
      → RequirementExtractor → structured requirements
      → ContradictionDetector + MissingRequirementDetector → gaps
      → QuestionBudgeter → only the necessary questions
      → DecisionLedger / TechnicalMemory → prior decisions consulted
      → ContextSelector → relevant context nodes
      → ContextPackageBuilder → final prompt/context package
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from . import _sibling_utils
from .context_graph import ContextGraph
from .context_package import ContextPackage, ContextPackageBuilder
from .context_selection import ContextSelector
from .contradiction_detection import Contradiction, ContradictionDetector
from .decision_ledger import DecisionLedger
from .missing_requirement_detection import MissingRequirement, MissingRequirementDetector
from .models import ContextNode, Decision, Question, Requirement  # noqa: F401 (re-export)
from .question_budget import QuestionBudgeter, QuestionSet
from .requirement_extraction import RequirementExtractor
from .technical_memory import TechnicalMemory
from .token_budget import BudgetResult


class PromptGraph:
    """High-level orchestrator for context preparation."""

    def __init__(
        self,
        memory_path: str | Path = ".agentops/context/memory.json",
        decisions_path: str | Path = ".agentops/decisions/decisions.json",
        token_budget: int = 8000,
        max_questions: int = 8,
    ) -> None:
        self.extractor = RequirementExtractor()
        self.contradiction_detector = ContradictionDetector()
        self.missing_detector = MissingRequirementDetector()
        self.question_budgeter = QuestionBudgeter(max_questions=max_questions)
        self.token_budget = token_budget
        self.graph = ContextGraph()
        self.memory = TechnicalMemory(memory_path)
        self.ledger = DecisionLedger(decisions_path)
        self.memory.with_decision_ledger(self.ledger)
        self.selector = ContextSelector(self.graph)
        self.builder = ContextPackageBuilder(token_budget=token_budget)
        self._integrations: dict[str, object] = {}

    # --- Detection of optional integrations ---------------------------------
    def detect_integrations(self) -> dict[str, bool]:
        """Return which ecosystem siblings are installed."""
        return {
            name: _sibling_utils.is_installed(name)
            for name in ("agentgear", "agentbench", "projectkaizen", "skillguard")
        }

    # --- Phase 1: turn messy explanation into requirements -------------------
    def extract_requirements(self, explanation: str) -> list[Requirement]:
        """Extract structured requirements from a messy explanation."""
        return self.extractor.extract(explanation)

    # --- Phase 2: detect gaps -------------------------------------------------
    def detect_contradictions(self, requirements: Iterable[Requirement]) -> list[Contradiction]:
        return self.contradiction_detector.detect(requirements)

    def detect_missing(self, requirements: Iterable[Requirement]) -> list[MissingRequirement]:
        return self.missing_detector.detect(requirements)

    # --- Phase 3: decide what questions to ask -------------------------------
    def budget_questions(
        self, requirements: Iterable[Requirement], answered: set[str] | None = None
    ) -> QuestionSet:
        return self.question_budgeter.budget(requirements, answered_ids=answered)

    # --- Phase 4: prior decisions / technical memory -------------------------
    def record_decision(self, decision: Decision) -> str:
        return self.ledger.record(decision)

    def remember(self, key: str, content: str, tags: list[str] | None = None) -> str:
        return self.memory.record_note(key, content, tags)

    def recall(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        return self.memory.search(query, limit=limit)

    # --- Phase 5: build context graph & select context ------------------------
    def add_context_node(self, node: ContextNode) -> None:
        self.graph.add_node(node)

    def add_dependency(self, node_id: str, depends_on: str) -> None:
        self.graph.add_dependency(node_id, depends_on)

    def select_context(
        self,
        query: str,
        budget: int | None = None,
        *,
        include_dependencies_of: Iterable[str] = (),
    ) -> BudgetResult:
        return self.selector.select(
            query,
            budget or self.token_budget,
            include_dependencies_of=include_dependencies_of,
        )

    # --- Phase 6: assemble final context package -----------------------------
    def build_package(
        self,
        title: str,
        requirements: list[Requirement],
        context_nodes: list[ContextNode] | None = None,
        decisions: list[Decision] | None = None,
    ) -> ContextPackage:
        return self.builder.build(title, requirements, context_nodes, decisions)

    # --- Full pipeline convenience -------------------------------------------
    def prepare(
        self,
        explanation: str,
        title: str = "Task context",
        *,
        budget: int | None = None,
        include_prior_decisions: bool = True,
    ) -> dict[str, object]:
        """Run the full pipeline and return a structured result dict."""
        requirements = self.extract_requirements(explanation)
        contradictions = self.detect_contradictions(requirements)
        missing = self.detect_missing(requirements)
        questions = self.budget_questions(requirements)

        # Build a context query from the requirement descriptions.
        query = " ".join(r.description for r in requirements)

        selection = self.selector.select(query, budget or self.token_budget)

        decisions: list[Decision] = []
        if include_prior_decisions:
            # Pull the top related prior decisions.
            for d in self.ledger.all():
                if any(
                    t in d.decision.lower() or t in d.title.lower()
                    for t in query.lower().split()[:5]
                ):
                    decisions.append(d)
            decisions = decisions[:5]

        package = self.builder.build(title, requirements, selection.selected, decisions)

        return {
            "requirements": requirements,
            "contradictions": contradictions,
            "missing_dimensions": missing,
            "questions": [q.text for q in questions],
            "context_nodes": selection.selected,
            "package": package,
            "total_tokens": package.total_tokens,
        }
