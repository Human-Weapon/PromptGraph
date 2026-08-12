"""QuestionBudget — determine what questions are truly necessary to ask.

The goal is to ask ONLY what is necessary to fill gaps, not to interrogate the
user about everything.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .missing_requirement_detection import MissingRequirementDetector
from .models import Question, Requirement

_TERM_HINTS: dict[str, tuple[str, ...]] = {
    "error": ("error", "failure", "fallback", "exception", "retry", "timeout"),
    "auth": ("auth", "login", "password", "token", "permission", "role", "user", "admin"),
    "retention": ("store", "save", "persist", "database", "retention", "backup"),
    "limits": ("limit", "cap", "max", "quota", "size", "concurrency", "concurrent"),
    "platform": ("platform", "windows", "linux", "macos", "browser", "mobile", "api"),
    "perf": ("performance", "latency", "speed", "scalab", "response"),
}


@dataclass
class QuestionSet:
    """The set of questions PromptGraph asks, with a reason for each."""

    questions: list[Question] = field(default_factory=list)

    def add(self, question: Question) -> None:
        self.questions.append(question)

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self):
        return iter(self.questions)


class QuestionBudgeter:
    """Compute the minimal necessary set of questions for a requirement set.

    Combines:
      - flagged 'needs_clarification' requirements (from extraction)
      - missing-dimension gaps (from MissingRequirementDetector)
      - prior-decision gaps (optional, from a DecisionLedger)
    """

    def __init__(self, max_questions: int = 8) -> None:
        self.max_questions = max_questions
        self._missing_detector = MissingRequirementDetector()

    def budget(
        self,
        requirements: Iterable[Requirement],
        answered_ids: set[str] | None = None,
    ) -> QuestionSet:
        reqs = list(requirements)
        answered = answered_ids or set()
        qs = QuestionSet()
        seen: set[str] = set()

        # 1. Clarification for low-confidence / vague requirements.
        for req in reqs:
            if req.id in answered:
                continue
            if "needs_clarification" in req.tags or "low_confidence" in req.tags:
                question = Question(
                    text=f"Please clarify '{req.description}'.",
                    requirement_ids=[req.id],
                    reason=f"Tagged as {[t for t in req.tags if t.startswith(('needs', 'low'))]}",
                )
                if question.text not in seen:
                    seen.add(question.text)
                    qs.add(question)

        # 2. Missing dimensions.
        for gap in self._missing_detector.detect(reqs):
            text = gap.suggested_question
            if text not in seen:
                seen.add(text)
                qs.add(
                    Question(
                        text=text,
                        reason=f"Missing dimension: {gap.label}",
                        required=True,
                    )
                )

        # 3. Truncate to budget.
        if self.max_questions and len(qs) > self.max_questions:
            # Keep clarification questions first, then missing-dimension ones.
            qs.questions = qs.questions[: self.max_questions]
        return qs

    def format(self, qset: QuestionSet) -> str:
        """Render questions as a human-readable list."""
        if not qset:
            return "No questions needed — requirements are sufficiently clear."
        lines = [
            f"{i + 1}. {q.text}" + ("" if q.required else " (optional)") for i, q in enumerate(qset)
        ]
        return "\n".join(lines)
