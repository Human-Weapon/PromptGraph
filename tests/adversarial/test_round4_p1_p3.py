"""Adversarial Round 4 regressions: P1-01..P3-01."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from promptgraph.context_package import ContextPackageBuilder
from promptgraph.core import PromptGraph
from promptgraph.decision_ledger import DecisionLedger
from promptgraph.exceptions import (
    BudgetExceededError,
    CorruptStorageError,
    PathEscapeError,
    PersistenceError,
    QuestionBudgetError,
    StorageLockError,
    TokenBudgetError,
)
from promptgraph.models import Decision, Requirement
from promptgraph.question_budget import QuestionBudgeter
from promptgraph.safe_json_store import SafeJsonStore
from promptgraph.technical_memory import TechnicalMemory


def _make_junction_or_symlink(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if link.exists():
        if link.is_dir() and not link.is_symlink():
            # empty real dir before junction
            try:
                link.rmdir()
            except OSError:
                import shutil

                shutil.rmtree(link)
        else:
            link.unlink()
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace")
            pytest.skip(f"Cannot create junction: {err}")
    else:
        os.symlink(target, link, target_is_directory=True)


# ---------- P1-01 per-call budget ----------


class TestP101PerCallBudget:
    def test_prepare_budget_overrides_constructor(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pg = PromptGraph(
            token_budget=1000,
            memory_path=tmp_path / "m.json",
            decisions_path=tmp_path / "d.json",
            trusted_root=tmp_path,
        )
        # budget=1 should not silently use 1000
        with pytest.raises((BudgetExceededError, TokenBudgetError)):
            pg.prepare("Must support login with OAuth2 tokens.", budget=1)

    def test_prepare_budget_sets_package_token_budget(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pg = PromptGraph(
            token_budget=1000,
            memory_path=tmp_path / "m.json",
            decisions_path=tmp_path / "d.json",
            trusted_root=tmp_path,
        )
        result = pg.prepare("Must support login.", budget=500)
        pkg = result["package"]
        assert pkg.token_budget == 500
        assert pkg.total_tokens <= 500

    def test_prepare_negative_budget_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pg = PromptGraph(
            memory_path=tmp_path / "m.json",
            decisions_path=tmp_path / "d.json",
            trusted_root=tmp_path,
        )
        with pytest.raises(TokenBudgetError):
            pg.prepare("Must support login.", budget=-1)

    def test_build_explicit_token_budget_override(self):
        b = ContextPackageBuilder(token_budget=1000)
        pkg = b.build(
            "T",
            [Requirement(id="R1", description="Must support login.")],
            token_budget=400,
        )
        assert pkg.token_budget == 400
        assert pkg.total_tokens <= 400

    def test_cli_negative_budget_nonzero_no_traceback(self, tmp_path):
        env = {**os.environ, "PYTHONPATH": ""}
        # Use installed package if possible; fall back to module
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "promptgraph",
                "prepare",
                "-e",
                "Must support login.",
                "--budget",
                "-1",
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )
        assert proc.returncode != 0
        assert "Traceback" not in (proc.stderr or "")
        assert "Traceback" not in (proc.stdout or "")


# ---------- P1-02 path aliases + junction ----------


class TestP102PathAliases:
    def test_dot_slash_agentops_gets_trusted_root(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pg = PromptGraph(
            memory_path="./.agentops/context/memory.json",
            decisions_path="./.agentops/decisions/d.json",
        )
        assert pg.trusted_root is not None

    def test_junction_rejects_all_aliases(self, tmp_path):
        if os.name != "nt":
            pytest.skip("Windows junction test")
        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        agentops = project / ".agentops"
        _make_junction_or_symlink(agentops, outside)

        aliases = [
            ".agentops/decisions/d.json",
            "./.agentops/decisions/d.json",
            str(project / ".agentops" / "decisions" / "d.json"),
        ]
        old = os.getcwd()
        try:
            os.chdir(project)
            for rel in aliases:
                with pytest.raises(PathEscapeError):
                    ld = DecisionLedger(rel, trusted_root=project)
                    ld.record(Decision(id="x", title="t", context="c", decision="no"))
        finally:
            os.chdir(old)
        leaked = list(outside.rglob("*"))
        assert not leaked, f"Outside artifacts: {leaked}"


# ---------- P2-01 TOCTOU lock ----------


class TestP201LockTOCTOU:
    def test_post_construct_junction_creates_zero_outside_artifacts(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        agentops = project / ".agentops"
        agentops.mkdir()
        dest_dir = agentops / "decisions"
        dest_dir.mkdir()
        path = dest_dir / "decisions.json"

        store = SafeJsonStore(path, trusted_root=project)

        # Swap agentops for junction AFTER construction
        import shutil

        shutil.rmtree(agentops)
        _make_junction_or_symlink(agentops, outside)

        with pytest.raises((PathEscapeError, PersistenceError)):
            store.update(lambda d: {**d, "k": 1} if isinstance(d, dict) else {"k": 1})

        leaked = list(outside.rglob("*"))
        assert leaked == [], f"Outside artifacts created: {leaked}"


# ---------- P2-02 schema validation ----------


class TestP202SchemaValidation:
    def test_ledger_array_root_quarantined(self, tmp_path):
        p = tmp_path / "d.json"
        p.write_text("[]", encoding="utf-8")
        with pytest.raises(CorruptStorageError) as ei:
            DecisionLedger(p)
        assert ei.value.quarantined_path is not None
        assert Path(ei.value.quarantined_path).exists()

    def test_ledger_partial_record_quarantined(self, tmp_path):
        p = tmp_path / "d.json"
        p.write_text('{"d":{"id":"d"}}', encoding="utf-8")
        with pytest.raises(CorruptStorageError):
            DecisionLedger(p)

    def test_memory_missing_content_quarantined(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text('{"notes":{"n":{"key":"n"}}}', encoding="utf-8")
        with pytest.raises(CorruptStorageError) as ei:
            TechnicalMemory(p)
        assert ei.value.quarantined_path is not None
        assert Path(ei.value.quarantined_path).exists()


# ---------- P2-03 negative max_questions ----------


class TestP203NegativeQuestions:
    def test_question_budgeter_rejects_negative(self):
        with pytest.raises(QuestionBudgetError):
            QuestionBudgeter(max_questions=-1)

    def test_promptgraph_rejects_negative(self, tmp_path):
        with pytest.raises(QuestionBudgetError):
            PromptGraph(
                max_questions=-1,
                memory_path=tmp_path / "m.json",
                decisions_path=tmp_path / "d.json",
                trusted_root=tmp_path,
            )

    @pytest.mark.parametrize("val", [0, 1, 8])
    def test_valid_max_questions(self, val):
        qb = QuestionBudgeter(max_questions=val)
        assert qb.max_questions == val


# ---------- P3-01 neutral errors ----------


class TestP301NeutralErrors:
    def test_safe_json_store_lock_error_is_storage_lock(self, tmp_path, monkeypatch):
        import promptgraph.safe_json_store as sjs

        path = tmp_path / "x.json"
        store = SafeJsonStore(path)

        def boom(self):  # noqa: ANN001
            raise StorageLockError("lock failed")

        monkeypatch.setattr(sjs.FileLock, "acquire", boom)
        with pytest.raises(StorageLockError):
            store.update(lambda d: d)
        # Must NOT be DecisionError
        with pytest.raises(PersistenceError):
            store.update(lambda d: d)

    def test_safe_json_store_source_no_decision_error(self):
        import inspect

        import promptgraph.safe_json_store as sjs

        src = inspect.getsource(sjs)
        assert "DecisionError" not in src
