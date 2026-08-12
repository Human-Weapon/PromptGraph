"""Exception types for PromptGraph.

Domain-specific exceptions so callers can handle expected failure modes
without catching broad ``Exception``.
"""

from __future__ import annotations


class PromptGraphError(Exception):
    """Base exception for all PromptGraph errors."""


class RequirementValidationError(PromptGraphError):
    """Raised when a requirement fails validation."""


class ContextGraphError(PromptGraphError):
    """Raised when the context graph cannot be built or traversed."""


class CycleError(ContextGraphError):
    """Raised when adding a dependency that would create a cycle (PG-12).

    The graph is documented as a DAG.  Cycles are rejected at mutation
    time so the graph never enters an invalid internal state.
    """


class TokenBudgetError(PromptGraphError):
    """Raised when token budget constraints cannot be satisfied."""


class BudgetExceededError(TokenBudgetError):
    """Raised when mandatory content cannot fit within the configured budget."""


class DecisionError(PromptGraphError):
    """Raised when a decision cannot be recorded or retrieved."""


class DuplicateDecisionError(DecisionError):
    """Raised when recording a decision whose id already exists (PG-03)."""


class CorruptStorageError(PromptGraphError):
    """Raised when persistent storage is corrupt and cannot be loaded (PG-09).

    The corrupt source file is quarantined (renamed) before this error
    is raised so the user can recover data.
    """

    def __init__(self, message: str, quarantined_path: str | None = None) -> None:
        super().__init__(message)
        self.quarantined_path = quarantined_path


class PathEscapeError(PromptGraphError):
    """Raised when a resolved path escapes the allowed base directory (PG-04)."""
