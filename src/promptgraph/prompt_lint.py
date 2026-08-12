"""PromptLint — validate prompts for common issues.

Checks for ambiguity, missing context, contradictions, redundant content,
missing constraints, and non-determinism markers (subjectivity, vagueness).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contradiction_detection import ContradictionDetector

_VAGUE_TERMS = re.compile(
    r"\b(somehow|some way|as needed|appropriately|eventually|later on|something like|"
    r"etc\.?|and so on|make it work|cleanup|properly|well)\b",
    re.I,
)
_AMBIGUITY_TERMS = re.compile(r"\b(it|they|the thing|whatever|etc)\b", re.I)
_MISSING_CONSTRAINT = re.compile(r"\b(don't specify|no constraint|any way|whatever works)\b", re.I)
_STRONG_WORDS = re.compile(r"\b(absolutely|definitely|always|never|best|fastest|perfect)\b", re.I)


@dataclass
class LintIssue:
    """A single lint finding on a prompt."""

    severity: str  # info | warning | error
    category: str
    message: str
    line: int = 0
    snippet: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "line": self.line,
            "snippet": self.snippet,
        }


class PromptLinter:
    """Lint a prompt string for quality and safety issues."""

    def __init__(self) -> None:
        self._contradiction = ContradictionDetector()

    def lint(self, prompt: str) -> list[LintIssue]:
        """Run all heuristic checks over a prompt and return findings."""
        issues: list[LintIssue] = []
        if not prompt or not prompt.strip():
            issues.append(LintIssue("error", "emptiness", "Prompt is empty."))
            return issues

        lines = prompt.splitlines()
        full = " ".join(lines)

        for i, line in enumerate(lines, start=1):
            if _VAGUE_TERMS.search(line):
                issues.append(
                    LintIssue(
                        "warning",
                        "vagueness",
                        "Vague phrasing detected.",
                        line=i,
                        snippet=line.strip()[:80],
                    )
                )
            if _AMBIGUITY_TERMS.search(line):
                issues.append(
                    LintIssue(
                        "warning",
                        "ambiguity",
                        "Ambiguous pronoun/noun ('it/they/etc') — be specific.",
                        line=i,
                        snippet=line.strip()[:80],
                    )
                )
            if _MISSING_CONSTRAINT.search(line):
                issues.append(
                    LintIssue(
                        "warning",
                        "missing_constraint",
                        "Possible missing constraint/scope statement.",
                        line=i,
                        snippet=line.strip()[:80],
                    )
                )

        if _STRONG_WORDS.search(full):
            issues.append(
                LintIssue(
                    "info", "overclaim", "Overconfident language; grounds claims in evidence."
                )
            )

        if len(full) < 20:
            issues.append(
                LintIssue("warning", "completeness", "Prompt is very short; it may lack context.")
            )

        if len(lines) > 40:
            issues.append(
                LintIssue(
                    "info", "length", "Prompt is long (>40 lines); consider a context package."
                )
            )

        return issues

    def lint_requirements(self, descriptions: list[str]) -> list[LintIssue]:
        """Lint a set of requirement descriptions for contradictions."""
        issues: list[LintIssue] = []
        from .requirement_extraction import Requirement  # local to avoid cycles

        reqs = [Requirement(id=f"R{i}", description=d) for i, d in enumerate(descriptions)]
        for c in self._contradiction.detect(reqs):
            issues.append(
                LintIssue(
                    "error",
                    "contradiction",
                    f"Contradiction: {c.snippet_a} conflicts with {c.snippet_b}"  # noqa: E501
                    f" ({c.requirement_a} vs {c.requirement_b})",
                )
            )
        return issues
