"""Domain data models for PromptGraph."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class Priority(enum.IntEnum):
    """Priority levels for requirements, matched to ecosystem P0-P7."""

    P0 = 0  # Security / data loss / critical bugs
    P1 = 1  # Broken functionality
    P2 = 2  # Core functionality
    P3 = 3  # Tests / reliability
    P4 = 4  # Performance
    P5 = 5  # Developer experience
    P6 = 6  # Documentation
    P7 = 7  # Cosmetic improvements


class RequirementType(enum.Enum):
    """Classification of a structured requirement."""

    FUNCTIONAL = "functional"
    CONSTRAINT = "constraint"
    NON_FUNCTIONAL = "non_functional"
    SECURITY = "security"
    BUSINESS = "business"
    UNKNOWN = "unknown"


@dataclass
class Requirement:
    """A single structured requirement extracted from a messy explanation."""

    id: str
    description: str
    requirement_type: RequirementType = RequirementType.UNKNOWN
    priority: Priority = Priority.P2
    source: str = ""  # original sentence/segment it came from
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # requirement ids
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "requirement_type": self.requirement_type.value,
            "priority": self.priority.name,
            "source": self.source,
            "tags": list(self.tags),
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Requirement:
        return cls(
            id=data["id"],
            description=data["description"],
            requirement_type=RequirementType(data.get("requirement_type", "unknown")),
            priority=Priority[data.get("priority", "P2")],
            source=data.get("source", ""),
            tags=list(data.get("tags", [])),
            dependencies=list(data.get("dependencies", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ContextNode:
    """A node in the context graph — a unit of project knowledge."""

    id: str
    title: str
    content: str
    kind: str = "note"  # e.g. note, decision, architecture, code, doc
    token_estimate: int = 0
    tags: list[str] = field(default_factory=list)
    priority: Priority = Priority.P2
    metadata: dict[str, Any] = field(default_factory=dict)

    def estimate_tokens(self, chars_per_token: int = 4) -> int:
        """Estimate token count from content length."""
        self.token_estimate = max(1, len(self.content) // chars_per_token)
        return self.token_estimate

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "kind": self.kind,
            "token_estimate": self.token_estimate,
            "tags": list(self.tags),
            "priority": self.priority.name,
            "metadata": dict(self.metadata),
        }


@dataclass
class Decision:
    """A recorded technical or product decision."""

    id: str
    title: str
    context: str
    decision: str
    rationale: str = ""
    alternatives: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    requirements: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "context": self.context,
            "decision": self.decision,
            "rationale": self.rationale,
            "alternatives": list(self.alternatives),
            "created_at": self.created_at.isoformat(),
            "requirements": list(self.requirements),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decision:
        return cls(
            id=data["id"],
            title=data["title"],
            context=data["context"],
            decision=data["decision"],
            rationale=data["rationale"],
            alternatives=list(data.get("alternatives", [])),
            created_at=datetime.fromisoformat(data["created_at"]),
            requirements=list(data.get("requirements", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Question:
    """A question PromptGraph asks to fill a knowledge gap."""

    text: str
    requirement_ids: list[str] = field(default_factory=list)
    reason: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "requirement_ids": list(self.requirement_ids),
            "reason": self.reason,
            "required": self.required,
        }


@dataclass
class ContextPackage:
    """The final assembled context package delivered to an agent."""

    title: str
    prompt: str
    context_nodes: list[ContextNode] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    total_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_tokens(self) -> int:
        """Compute total tokens from content and node estimates."""

        def _est(text: str) -> int:
            return max(1, len(text) // 4)

        total = _est(self.prompt)
        for node in self.context_nodes:
            total += node.estimate_tokens()
        for req in self.requirements:
            total += _est(req.description)
        for dec in self.decisions:
            total += _est(dec.decision)
        self.total_tokens = total
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "prompt": self.prompt,
            "context_nodes": [n.to_dict() for n in self.context_nodes],
            "requirements": [r.to_dict() for r in self.requirements],
            "decisions": [d.to_dict() for d in self.decisions],
            "total_tokens": self.total_tokens,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }
