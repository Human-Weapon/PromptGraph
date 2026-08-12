"""Adversarial regression: PG-04 path containment must be WIRED into writers.

Creates a REAL Windows junction (or POSIX symlink) and verifies that
default PromptGraph persistence refuses to write outside the trusted root.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from promptgraph.exceptions import PathEscapeError


def _make_junction_or_symlink(link: Path, target: Path) -> None:
    """Create a real directory junction (Windows) or symlink (POSIX)."""
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # mklink /J does not require admin
        cmd = ["cmd", "/c", "mklink", "/J", str(link), str(target)]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace")
            pytest.skip(f"Cannot create junction: {err}")
    else:
        os.symlink(target, link, target_is_directory=True)


class TestPG04PathContainmentWired:
    def test_normal_path_inside_root_ok(self, tmp_path):
        root = tmp_path / "project"
        root.mkdir()
        dest = root / ".agentops" / "decisions" / "decisions.json"
        dest.parent.mkdir(parents=True)
        # Creating ledger inside root must succeed
        from promptgraph.decision_ledger import DecisionLedger
        from promptgraph.models import Decision

        ld = DecisionLedger(dest, trusted_root=root)
        ld.record(Decision(id="ok1", title="T", context="c", decision="d"))
        assert dest.exists()

    def test_junction_escape_rejected_on_windows(self, tmp_path):
        """REAL junction: project/.agentops -> outside must reject writes."""
        if os.name != "nt":
            pytest.skip("Windows junction test")

        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        agentops = project / ".agentops"
        _make_junction_or_symlink(agentops, outside)

        # Path that resolves outside via junction
        dest = agentops / "decisions" / "decisions.json"

        from promptgraph.decision_ledger import DecisionLedger
        from promptgraph.models import Decision

        with pytest.raises(PathEscapeError):
            ld = DecisionLedger(dest, trusted_root=project)
            ld.record(Decision(id="evil", title="T", context="c", decision="should not write"))

        # Outside must NOT receive the file
        leaked = list(outside.rglob("*.json"))
        assert not any("decisions" in str(p) for p in leaked), f"Leak detected: {leaked}"

    def test_symlink_escape_rejected_on_posix(self, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX symlink test")

        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        agentops = project / ".agentops"
        _make_junction_or_symlink(agentops, outside)

        dest = agentops / "decisions" / "decisions.json"
        from promptgraph.decision_ledger import DecisionLedger
        from promptgraph.models import Decision

        with pytest.raises(PathEscapeError):
            ld = DecisionLedger(dest, trusted_root=project)
            ld.record(Decision(id="evil", title="T", context="c", decision="nope"))

        leaked = list(outside.rglob("*.json"))
        assert not leaked

    def test_path_security_used_by_ledger(self):
        """path_security must be imported/used by DecisionLedger (not dead code)."""
        import inspect

        from promptgraph import decision_ledger as mod

        src = inspect.getsource(mod)
        assert (
            "path_security" in src
            or "validate_contained" in src
            or "PathEscapeError" in src
            or "SafeJsonStore" in src
        )

    def test_cli_decisions_rejects_junction_escape(self, tmp_path, monkeypatch):
        """Black-box-ish: DecisionLedger used as CLI does must reject junction escape."""
        if os.name != "nt":
            pytest.skip("Windows junction CLI path test")

        project = tmp_path / "proj"
        project.mkdir()
        outside = tmp_path / "out"
        outside.mkdir()
        agentops = project / ".agentops"
        _make_junction_or_symlink(agentops, outside)

        monkeypatch.chdir(project)
        from promptgraph.core import PromptGraph
        from promptgraph.models import Decision

        # Default paths under .agentops must not escape
        with pytest.raises(PathEscapeError):
            pg = PromptGraph(
                memory_path=project / ".agentops" / "context" / "memory.json",
                decisions_path=project / ".agentops" / "decisions" / "decisions.json",
                trusted_root=project,
            )
            pg.record_decision(Decision(id="cli-evil", title="T", context="c", decision="leak"))
