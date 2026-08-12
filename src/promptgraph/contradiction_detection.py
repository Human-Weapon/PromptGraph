"""Contradiction detection between structured requirements.

Detects conflicting/contradictory requirements so agents are not asked to
satisfy impossible constraints simultaneously.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Requirement

# Pairs of terms that typically signal contradiction when present in two
# different requirements.
_CONTRADICTION_PAIRS: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (
        re.compile(r"\b(read-only|read only)\b", re.I),
        re.compile(r"\b(writable|write to|write access|read-write)\b", re.I),
    ),
    (
        re.compile(r"\b(public|open to all|no auth)\b", re.I),
        re.compile(r"\b(private|auth required|must authenticate)\b", re.I),
    ),
    (
        re.compile(r"\b(synchronous|blocking)\b", re.I),
        re.compile(r"\b(asynchronous|non-blocking)\b", re.I),
    ),
    (
        re.compile(r"\b(allow|permit|enabled?)\b", re.I),
        re.compile(r"\b(deny|forbid|disabled|never allow)\b", re.I),
    ),
    (
        re.compile(r"\b(delete|remove|drop)\b", re.I),
        re.compile(r"\b(preserve|keep|retain)\b", re.I),
    ),
    (
        re.compile(r"\b(increase|add|expand)\b", re.I),
        re.compile(r"\b(decrease|reduce|shrink)\b", re.I),
    ),
]


@dataclass
class Contradiction:
    """A detected contradiction between two requirements."""

    requirement_a: str
    requirement_b: str
    snippet_a: str
    snippet_b: str
    reason: str = ""
    severity: str = "warning"

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement_a": self.requirement_a,
            "requirement_b": self.requirement_b,
            "snippet_a": self.snippet_a,
            "snippet_b": self.snippet_b,
            "reason": self.reason,
            "severity": self.severity,
        }


class ContradictionDetector:
    """Detects pairwise contradictions among a set of requirements."""

    def __init__(self) -> None:
        self.patterns = _CONTRADICTION_PAIRS

    def detect(self, requirements: Iterable[Requirement]) -> list[Contradiction]:
        reqs = list(requirements)
        findings: list[Contradiction] = []
        for i in range(len(reqs)):
            for j in range(i + 1, len(reqs)):
                a, b = reqs[i], reqs[j]
                for pat_a, pat_b in self.patterns:
                    # Check both directions: pat_a in A + pat_b in B, OR pat_b in A + pat_a in B.
                    match_a = pat_a.search(a.description)
                    match_b = pat_b.search(b.description)
                    if match_a and match_b:
                        findings.append(
                            Contradiction(
                                requirement_a=a.id,
                                requirement_b=b.id,
                                snippet_a=match_a.group(0),
                                snippet_b=match_b.group(0),
                                reason=(
                                    f"'{match_a.group(0)}' in R#{a.id} conflicts with "
                                    f"'{match_b.group(0)}' in R#{b.id}"
                                ),
                            )
                        )
                        continue  # avoid duplicate from reverse check
                    # Reverse direction
                    match_a2 = pat_b.search(a.description)
                    match_b2 = pat_a.search(b.description)
                    if match_a2 and match_b2:
                        findings.append(
                            Contradiction(
                                requirement_a=a.id,
                                requirement_b=b.id,
                                snippet_a=match_a2.group(0),
                                snippet_b=match_b2.group(0),
                                reason=(
                                    f"'{match_a2.group(0)}' in R#{a.id} conflicts with "
                                    f"'{match_b2.group(0)}' in R#{b.id}"
                                ),
                            )
                        )
        return findings
