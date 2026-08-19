"""PromptGraph core — orchestrates the full context-preparation pipeline.

PG-04: trusted_root wires path containment into default persistence.
PG-01/02/08: budget and contradiction propagation.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import _sibling_utils
from .context_graph import ContextGraph
from .context_package import ContextPackage, ContextPackageBuilder
from .context_selection import ContextSelector
from .contradiction_detection import Contradiction, ContradictionDetector
from .decision_ledger import DecisionLedger
from .exceptions import QuestionBudgetError, TokenBudgetError
from .memory.host import ProjectMemory
from .memory.models import (
    CompactionManifest,
    MemoryCandidate,
    MemoryRecord,
    RetrievalHit,
    ValidationReport,
)
from .missing_requirement_detection import MissingRequirement, MissingRequirementDetector
from .models import ContextNode, Decision, Requirement  # noqa: F401
from .path_security import is_project_local_agentops
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
        trusted_root: str | Path | None = None,
        project_root: str | Path | None = None,
        memory_root: str | Path | None = None,
    ) -> None:
        if token_budget < 0:
            raise TokenBudgetError("token_budget must be non-negative.")
        if max_questions is not None and max_questions < 0:
            raise QuestionBudgetError("max_questions must be non-negative.")

        self.project_root = Path(project_root) if project_root is not None else Path.cwd()
        resolved_memory = Path(memory_path)
        resolved_decisions = Path(decisions_path)
        if not resolved_memory.is_absolute():
            resolved_memory = self.project_root / resolved_memory
        if not resolved_decisions.is_absolute():
            resolved_decisions = self.project_root / resolved_decisions

        # Default trusted root for project-local .agentops paths (any spelling)
        if trusted_root is None and (
            is_project_local_agentops(resolved_memory, project_root=self.project_root)
            or is_project_local_agentops(resolved_decisions, project_root=self.project_root)
        ):
            trusted_root = self.project_root

        self.trusted_root = Path(trusted_root) if trusted_root is not None else None
        self.memory_root = Path(memory_root) if memory_root is not None else None
        self._project_memory: ProjectMemory | None = None
        self.extractor = RequirementExtractor()
        self.contradiction_detector = ContradictionDetector()
        self.missing_detector = MissingRequirementDetector()
        self.question_budgeter = QuestionBudgeter(max_questions=max_questions)
        self.token_budget = token_budget
        self.graph = ContextGraph()
        self.memory = TechnicalMemory(resolved_memory, trusted_root=self.trusted_root)
        self.ledger = DecisionLedger(resolved_decisions, trusted_root=self.trusted_root)
        self.memory.with_decision_ledger(self.ledger)
        self.selector = ContextSelector(self.graph)
        self.builder = ContextPackageBuilder(token_budget=token_budget)
        self._integrations: dict[str, object] = {}

    @property
    def project_memory(self) -> ProjectMemory:
        if self._project_memory is None:
            trusted = self.trusted_root or self.project_root
            self._project_memory = ProjectMemory(
                self.project_root,
                memory_root=self.memory_root,
                trusted_root=trusted,
            )
        return self._project_memory

    def record_memory(self, candidate: MemoryCandidate | dict[str, Any]) -> MemoryRecord:
        return self.project_memory.record_memory(candidate)

    def checkpoint_session(self, **kwargs: Any) -> MemoryRecord:
        return self.project_memory.checkpoint_session(**kwargs)

    def build_context_pack(self, task: str, **kwargs: Any):
        return self.project_memory.build_context_pack(task, **kwargs)

    def search_memory(self, query: str, **kwargs: Any) -> list[RetrievalHit]:
        return self.project_memory.search_memory(query, **kwargs)

    def validate_memory(self) -> ValidationReport:
        return self.project_memory.validate_memory()

    def plan_compaction(self, **kwargs: Any) -> CompactionManifest:
        return self.project_memory.plan_compaction(**kwargs)

    def detect_integrations(self) -> dict[str, bool]:
        return {
            name: _sibling_utils.is_installed(name)
            for name in ("agentgear", "agentbench", "projectkaizen", "skillguard")
        }

    def extract_requirements(self, explanation: str) -> list[Requirement]:
        return self.extractor.extract(explanation)

    def detect_contradictions(self, requirements: Iterable[Requirement]) -> list[Contradiction]:
        return self.contradiction_detector.detect(requirements)

    def detect_missing(self, requirements: Iterable[Requirement]) -> list[MissingRequirement]:
        return self.missing_detector.detect(requirements)

    def budget_questions(
        self, requirements: Iterable[Requirement], answered: set[str] | None = None
    ) -> QuestionSet:
        return self.question_budgeter.budget(requirements, answered_ids=answered)

    def record_decision(self, decision: Decision) -> str:
        return self.ledger.record(decision)

    def remember(self, key: str, content: str, tags: list[str] | None = None) -> str:
        return self.memory.record_note(key, content, tags)

    def recall(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        return self.memory.search(query, limit=limit)

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
        effective_budget = self.token_budget if budget is None else budget
        return self.selector.select(
            query,
            effective_budget,
            include_dependencies_of=include_dependencies_of,
        )

    def build_package(
        self,
        title: str,
        requirements: list[Requirement],
        context_nodes: list[ContextNode] | None = None,
        decisions: list[Decision] | None = None,
        contradictions: list[Contradiction] | None = None,
        excluded_nodes: list[ContextNode] | None = None,
        system_prompt: str = "You are a precise software engineering agent.",
    ) -> ContextPackage:
        return self.builder.build(
            title,
            requirements,
            context_nodes,
            decisions,
            contradictions=contradictions,
            excluded_nodes=excluded_nodes,
            system_prompt=system_prompt,
        )

    def prepare(
        self,
        explanation: str,
        title: str = "Task context",
        *,
        budget: int | None = None,
        include_prior_decisions: bool = True,
        system_prompt: str = "You are a precise software engineering agent.",
    ) -> dict[str, object]:
        # P1-01: validate per-call budget before any pipeline work
        if budget is not None and budget < 0:
            raise TokenBudgetError("budget must be non-negative.")
        effective_budget = self.token_budget if budget is None else budget

        requirements = self.extract_requirements(explanation)
        det_result = self.contradiction_detector.detect_with_meta(requirements)
        contradictions = det_result.findings
        missing = self.detect_missing(requirements)
        questions = self.budget_questions(requirements)

        query = " ".join(r.description for r in requirements)
        selection = self.selector.select(query, effective_budget)

        decisions: list[Decision] = []
        if include_prior_decisions:
            for d in self.ledger.all():
                if any(
                    t in d.decision.lower() or t in d.title.lower()
                    for t in query.lower().split()[:5]
                ):
                    decisions.append(d)
            decisions = decisions[:5]

        package = self.builder.build(
            title,
            requirements,
            selection.selected,
            decisions,
            contradictions=contradictions,
            excluded_nodes=selection.excluded,
            system_prompt=system_prompt,
            token_budget=effective_budget,
            analysis_truncated=det_result.analysis_truncated,
            pair_checks=det_result.pair_checks,
            max_pair_checks=self.contradiction_detector.max_pair_checks,
        )

        return {
            "requirements": requirements,
            "contradictions": contradictions,
            "missing_dimensions": missing,
            "questions": [q.text for q in questions],
            "context_nodes": selection.selected,
            "package": package,
            "total_tokens": package.total_tokens,
            "package_status": package.status.value,
            "budget_exceeded": package.budget_exceeded,
            "analysis_truncated": det_result.analysis_truncated,
            "pair_checks": det_result.pair_checks,
        }
