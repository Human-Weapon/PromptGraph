"""Exception types for PromptGraph."""

from __future__ import annotations


class PromptGraphError(Exception):
    """Base exception for all PromptGraph errors."""


class RequirementValidationError(PromptGraphError):
    """Raised when a requirement fails validation."""


class ContextGraphError(PromptGraphError):
    """Raised when the context graph cannot be built or traversed."""


class TokenBudgetError(PromptGraphError):
    """Raised when token budget constraints cannot be satisfied."""


class DecisionError(PromptGraphError):
    """Raised when a decision cannot be recorded or retrieved."""
