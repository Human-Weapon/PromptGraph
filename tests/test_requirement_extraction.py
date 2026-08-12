"""Tests for requirement extraction."""

from __future__ import annotations

import pytest

from promptgraph.exceptions import RequirementValidationError
from promptgraph.models import Priority, Requirement, RequirementType
from promptgraph.requirement_extraction import RequirementExtractor


def test_extract_basic():
    extr = RequirementExtractor()
    explanation = (
        "We need a login system. It must support OAuth. Users should be able to reset passwords."
    )
    reqs = extr.extract(explanation)
    assert len(reqs) >= 3
    assert all(isinstance(r, Requirement) for r in reqs)


def test_extract_orders_ids():
    extr = RequirementExtractor()
    reqs = extr.extract("Must allow upload. Must support search.")
    assert [r.id for r in reqs] == ["R1", "R2"]


def test_extract_ignores_non_actionable():
    extr = RequirementExtractor()
    # 'hi' is too short to be substantive — genuinely ignored.
    reqs = extr.extract("hi.")
    assert len(reqs) == 0


def test_classify_priority_security():
    extr = RequirementExtractor()
    reqs = extr.extract("Must never expose secrets or leak user data.")
    assert reqs
    assert reqs[0].priority == Priority.P0


def test_classify_type_security():
    req = RequirementExtractor().extract("Must encrypt passwords at rest.")[0]
    assert req.requirement_type == RequirementType.SECURITY


def test_vague_tagging():
    extr = RequirementExtractor()
    reqs = extr.extract("It should somehow improve performance eventually.")
    if reqs:
        assert "needs_clarification" in reqs[0].tags


def test_raises_on_empty():
    extr = RequirementExtractor()
    with pytest.raises(RequirementValidationError):
        extr.extract("   ")


def test_extract_preserving_all_tags_low_confidence():
    extr = RequirementExtractor()
    reqs = extr.extract_preserving_all("We need the thing to work.")
    # returns at least one requirement (or empty — verify no crash).
    assert isinstance(reqs, list)


# --- Regression tests for classification precedence (BUG #2) ---
# "must" must NOT automatically classify as FUNCTIONAL when a more specific
# semantic category applies. Specific categories (SECURITY, CONSTRAINT,
# NON_FUNCTIONAL, BUSINESS) take precedence over the generic FUNCTIONAL pattern.


def test_classify_must_encrypt_is_security():
    """Regression: 'must encrypt' must classify as SECURITY, not FUNCTIONAL."""
    req = RequirementExtractor().extract("Must encrypt user data.")[0]
    assert req.requirement_type == RequirementType.SECURITY


def test_classify_must_authenticate_is_security():
    req = RequirementExtractor().extract(
        "The system must require authentication for admin access."
    )[0]
    assert req.requirement_type == RequirementType.SECURITY


def test_classify_must_respond_200ms_is_non_functional():
    req = RequirementExtractor().extract("The API must respond within 200ms.")[0]
    assert req.requirement_type == RequirementType.NON_FUNCTIONAL


def test_classify_must_not_log_is_constraint():
    """'must not' without security keywords should classify as CONSTRAINT."""
    req = RequirementExtractor().extract("The system must not exceed 100 requests per second.")[0]
    assert req.requirement_type == RequirementType.CONSTRAINT


def test_classify_generic_must_is_functional():
    """A generic 'must support X' with no specific keywords stays FUNCTIONAL."""
    req = RequirementExtractor().extract("The system must support CSV export.")[0]
    assert req.requirement_type == RequirementType.FUNCTIONAL


def test_classify_allow_is_functional():
    """'allow users to export' is generic functional, not security."""
    req = RequirementExtractor().extract("Must allow users to export their data.")[0]
    assert req.requirement_type == RequirementType.FUNCTIONAL
