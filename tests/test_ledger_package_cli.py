"""Tests for decision ledger, technical memory, context packaging, CLI, and standalone behavior."""

from __future__ import annotations

import pytest

from promptgraph._sibling_utils import is_installed
from promptgraph.context_package import ContextPackageBuilder
from promptgraph.decision_ledger import DecisionLedger
from promptgraph.models import ContextNode, ContextPackage, Decision, Requirement
from promptgraph.technical_memory import TechnicalMemory


# --- decision ledger ---
def test_ledger_roundtrip(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = DecisionLedger(path)
    ledger.record(
        Decision(
            id="d1",
            title="Use Postgres",
            context="db choice",
            decision="postgres",
            rationale="proven",
        )
    )
    assert ledger.get("d1") is not None

    # Re-open persisted file.
    ledger2 = DecisionLedger(path)
    assert ledger2.get("d1").decision == "postgres"


def test_ledger_search(tmp_path):
    ledger = DecisionLedger(tmp_path / "ld.json")
    # rationale now has a default — no need to pass it.
    ledger.record(Decision(id="d1", title="Auth", decision="use oauth2", context="x"))
    ledger.record(Decision(id="d2", title="Storage", decision="use s3", context="y"))
    hits = ledger.search("oauth")
    assert [d.id for d in hits] == ["d1"]


def test_ledger_rationale_optional(tmp_path):
    """Regression: Decision must be constructible without rationale."""
    d = Decision(id="x", title="T", context="c", decision="d")
    assert d.rationale == ""


# --- technical memory ---
def test_memory_note_roundtrip(tmp_path):
    mem = TechnicalMemory(tmp_path / "mem.json")
    mem.record_note("stack", "python 3.11", tags=["runtime"])
    assert mem.get_note("stack")["content"] == "python 3.11"

    mem2 = TechnicalMemory(tmp_path / "mem.json")
    assert mem2.get_note("stack") is not None


def test_memory_search_with_ledger(tmp_path):
    mem = TechnicalMemory(tmp_path / "mem.json")
    ledger = DecisionLedger(tmp_path / "ld.json")
    ledger.record(Decision(id="d1", title="Use Redis", decision="redis for cache", context="x"))
    mem.with_decision_ledger(ledger)
    mem.record_note("cache", "use redis client", tags=[])
    results = mem.search("redis")
    assert len(results) >= 2


# --- context packaging ---
def test_package_render():
    pkg = ContextPackageBuilder().build(
        title="Upload task",
        requirements=[Requirement(id="R1", description="Must support uploads.")],
        context_nodes=[ContextNode(id="n1", title="Upload", content="s3 flow")],
    )
    assert "Upload task" in pkg.prompt
    assert "Must support uploads" in pkg.prompt
    assert pkg.total_tokens > 0


def test_package_to_markdown():
    pkg = ContextPackage(title="T", prompt="p")
    md = ContextPackageBuilder().to_markdown(pkg)
    assert isinstance(md, str)


# --- CLI ---
def test_cli_version_exits_zero():
    """--version is expected to call sys.exit(0) per argparse convention."""
    from promptgraph.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0


def test_cli_lint_no_file():
    from promptgraph.cli import main

    rc = main(["lint"])
    assert rc == 2


def test_cli_status_does_not_crash():
    from promptgraph.cli import main

    rc = main(["status"])
    assert rc == 0


# --- standalone ---
def test_standalone_no_sibling_required():
    """The package must import and operate without any sibling installed."""
    import promptgraph  # noqa: F401

    pg = __import__("promptgraph.core", fromlist=["PromptGraph"]).PromptGraph()
    result = pg.prepare("We need a login system. It must support OAuth.")
    assert result["requirements"]
    integrations = pg.detect_integrations()
    # detect_integrations returns a dict; ALL values must be False (no siblings).
    assert all(v is False for v in integrations.values()), (
        f"Expected no siblings installed, got: {integrations}"
    )


def test_sibling_is_installed_helper():
    # stdlib modules should be detected; imaginary sibling should not.
    assert is_installed("json")
    assert not is_installed("definitely_not_a_real_sibling_xyz")
