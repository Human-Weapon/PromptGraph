"""PromptGraph — Transform human intent + project knowledge into precise context for AI agents.

PromptGraph decides WHAT CONTEXT to deliver. It does not decide which model
executes a task (that belongs to AgentGear).
"""

from __future__ import annotations

__version__ = "0.1.1"

from .core import PromptGraph  # noqa: A004
from .exceptions import (
    BudgetExceededError,
    ContextGraphError,
    CorruptStorageError,
    CycleError,
    DecisionError,
    DuplicateDecisionError,
    DuplicateMemoryError,
    MemoryError,
    MemoryIntegrityError,
    MemoryValidationError,
    PathEscapeError,
    PersistenceError,
    PromptGraphError,
    QuestionBudgetError,
    RequirementValidationError,
    StorageLockError,
    TokenBudgetError,
)
from .models import (
    ContextNode,
    ContextPackage,
    Decision,
    PackageStatus,
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
    "PackageStatus",
    "PromptGraphError",
    "RequirementValidationError",
    "ContextGraphError",
    "CycleError",
    "TokenBudgetError",
    "BudgetExceededError",
    "QuestionBudgetError",
    "PersistenceError",
    "StorageLockError",
    "DecisionError",
    "DuplicateDecisionError",
    "DuplicateMemoryError",
    "MemoryError",
    "MemoryIntegrityError",
    "MemoryValidationError",
    "CorruptStorageError",
    "PathEscapeError",
    "__version__",
]
