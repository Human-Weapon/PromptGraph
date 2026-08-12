"""Shared pytest fixtures for promptgraph tests."""

from __future__ import annotations

import pytest

from promptgraph.models import ContextNode, Priority


@pytest.fixture
def tmp_memory_dir(tmp_path):
    """Provide a temp dir that contains only .agentops to avoid test pollution."""
    return tmp_path


@pytest.fixture
def sample_requirements():
    """A small set of requirements for graph/selection tests."""
    from promptgraph.models import Requirement, RequirementType

    return [
        Requirement(
            id="R1",
            description="The system must allow users to upload CSV files.",
            requirement_type=RequirementType.FUNCTIONAL,
            priority=Priority.P2,
            tags=["upload"],
        ),
        Requirement(
            id="R2",
            description="Uploads must be validated for size and format.",
            requirement_type=RequirementType.CONSTRAINT,
            priority=Priority.P1,
            tags=["validation"],
        ),
        Requirement(
            id="R3",
            description="User data must be encrypted at rest.",
            requirement_type=RequirementType.SECURITY,
            priority=Priority.P0,
            tags=["security"],
        ),
    ]


@pytest.fixture
def context_nodes():
    """A set of context nodes with known sizes for token-budget tests."""
    return [
        ContextNode(
            id="auth",
            title="Auth design",
            content="token-based auth flow with refresh tokens. " * 10,
        ),
        ContextNode(
            id="db",
            title="Database schema",
            content="postgres schema with users and uploads tables. " * 10,
        ),
        ContextNode(
            id="upload", title="Upload pipeline", content="s3 presigned upload flow. " * 10
        ),
        ContextNode(id="ui", title="Frontend", content="react dashboard, upload form. " * 10),
    ]
