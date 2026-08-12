"""PromptGraph — Transform human intent + project knowledge into precise context for AI agents.

PromptGraph decides WHAT CONTEXT to deliver. It does not decide which model
executes a task (that belongs to AgentGear).
"""

from __future__ import annotations

__version__ = "0.1.0"

from .core import PromptGraph  # noqa: A004
from .exceptions import (
    ContextGraphError,
    DecisionError,
    PromptGraphError,
    RequirementValidationError,
    TokenBudgetError,
)
from .models import (
    ContextNode,
    ContextPackage,
    Decision,
    Priority,
    Question,
    Requirement,
    RequirementType,
)

__all__ = [
    "PromptGraph",
    "Requirement",
    "Priority",
    "RequirementType",
    "ContextNode",
    "Decision",
    "Question",
    "ContextPackage",
    "PromptGraphError",
    "RequirementValidationError",
    "ContextGraphError",
    "TokenBudgetError",
    "DecisionError",
    "__version__",
]
