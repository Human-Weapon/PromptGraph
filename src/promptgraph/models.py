"""Domain data models for PromptGraph."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contradiction_detection import Contradiction


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


class PackageStatus(enum.Enum):
    """Readiness status of a generated ContextPackage."""

    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"
    ANALYSIS_INCOMPLETE = "analysis_incomplete"


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
            rationale=data.get("rationale", ""),
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


def estimate_token_count(text: str, chars_per_token: int = 4) -> int:
    """Single authoritative token estimation function.

    Used by all components to avoid double-counting.
    """
    if not text:
        return 0
    return max(1, len(text) // chars_per_token)


@dataclass
class ContextPackage:
    """The final assembled context package delivered to an agent.

    Token accounting is authoritative: ``total_tokens`` reflects the cost
    of the *rendered* prompt only (no double-counting of node content).
    Contradictions detected during analysis are propagated here so they
    cannot be silently lost between analysis and output.
    """

    title: str
    prompt: str
    context_nodes: list[ContextNode] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    status: PackageStatus = PackageStatus.READY
    token_budget: int = 0
    total_tokens: int = 0
    budget_exceeded: bool = False
    excluded_nodes: list[ContextNode] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_tokens(self) -> int:
        """Compute total tokens from the *rendered prompt text only*.

        This is the single authoritative accounting path.  The rendered
        prompt already contains all requirement descriptions, node
        content, and decisions — so we count it once.
        """
        self.total_tokens = estimate_token_count(self.prompt)
        return self.total_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "prompt": self.prompt,
            "context_nodes": [n.to_dict() for n in self.context_nodes],
            "requirements": [r.to_dict() for r in self.requirements],
            "decisions": [d.to_dict() for d in self.decisions],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "status": self.status.value,
            "token_budget": self.token_budget,
            "total_tokens": self.total_tokens,
            "budget_exceeded": self.budget_exceeded,
            "excluded_nodes": [n.to_dict() for n in self.excluded_nodes],
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }
