"""Missing-requirement detection — find gaps in a set of requirements.

Aims to surface implicit, missing requirements by matching on common missing
dimensions (error handling, security, resource bounds, inputs/outputs, context).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import Requirement

# Each dimension: a name, a "does any requirement mention this?" detector, and
# a default question to surface if missing.
_DIMENSIONS: list[dict[str, object]] = [
    {
        "name": "error_handling",
        "label": "Error handling",
        "pattern": re.compile(r"\b(error|failure|fail|exception|fallback|retry|timeout)\b", re.I),
        "question": "What should happen when an error or failure occurs?",
    },
    {
        "name": "security",
        "label": "Security",
        "pattern": re.compile(
            r"\b(auth|authoriz|authentic|password|token|key|secret|permission|role|encrypt|secure)\b",
            re.I,
        ),
        "question": "What are the security and authentication requirements?",
    },
    {
        "name": "performance",
        "label": "Performance",
        "pattern": re.compile(
            r"\b(performance|performant|latency|speed|throughput|scalab"  # noqa: E501
            r"|response time|fast|respond\w*)\b",
            re.I,
        ),
        "question": "What performance or latency requirements exist?",
    },
    {
        "name": "data_retention",
        "label": "Data retention / persistence",
        "pattern": re.compile(
            r"\b(save|persist|store|retention|database|storage|durable|backup)\b", re.I
        ),
        "question": "What data needs to be persisted and for how long?",
    },
    {
        "name": "resource_limits",
        "label": "Resource limits",
        "pattern": re.compile(
            r"\b(bound|limits?|caps?|max|quota|budget|constraint|concurrency|concurrent)\b", re.I
        ),
        "question": "Are there limits on resources, size, concurrency or scale?",
    },
    {
        "name": "compatibility",
        "label": "Compatibility / platform",
        "pattern": re.compile(
            r"\b(platform|os|windows|linux|macos|browser|compatible|version|api)\b", re.I
        ),
        "question": "Which platforms or versions must be supported?",
    },
    {
        "name": "access_control",
        "label": "Access control / users",
        "pattern": re.compile(
            r"\b(user|role|permission|access|admin|read.?only|write.?access|owner)\b", re.I
        ),
        "question": "Who is allowed to access or modify this?",
    },
    {
        "name": "observability",
        "label": "Observability / logging",
        "pattern": re.compile(
            r"\b(log|logging|metric|monitor|trace|observab|telemetry|audit)\b", re.I
        ),
        "question": "What logging, metrics, or observability is required?",
    },
]


@dataclass
class MissingRequirement:
    """A detected gap / missing dimension."""

    dimension: str
    label: str
    suggested_question: str
    severity: str = "suggestion"

    def to_dict(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "label": self.label,
            "suggested_question": self.suggested_question,
            "severity": self.severity,
        }


class MissingRequirementDetector:
    """Detect commonly-overlooked dimensions absent from a requirement set."""

    def __init__(self) -> None:
        self.dimensions = _DIMENSIONS

    def detect(self, requirements: Iterable[Requirement]) -> list[MissingRequirement]:
        reqs = list(requirements)
        if not reqs:
            # With no requirements everything is missing; only flag a couple to
            # avoid noise.
            return [
                MissingRequirement(
                    "baseline",
                    "Base functionality",
                    "Please describe the core functionality in detail.",
                )
            ]
        combined = " ".join(r.description for r in reqs)
        findings: list[MissingRequirement] = []
        for dim in self.dimensions:
            pat = dim["pattern"]
            if not pat.search(combined):  # type: ignore[operator]
                findings.append(
                    MissingRequirement(
                        dimension=dim["name"],
                        label=dim["label"],
                        suggested_question=dim["question"],
                    )
                )
        return findings
