"""Adversarial Round 3 regressions: NEW-01..NEW-04."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from promptgraph.context_package import ContextPackageBuilder
from promptgraph.contradiction_detection import ContradictionDetector
from promptgraph.core import PromptGraph
from promptgraph.exceptions import BudgetExceededError
from promptgraph.models import PackageStatus, Requirement

# ---------- NEW-01 TechnicalMemory concurrency ----------


def _tm_worker(path_str: str, key: str, barrier, q) -> None:
    try:
        from promptgraph.technical_memory import TechnicalMemory

        barrier.wait(timeout=30)
        tm = TechnicalMemory(path_str)
        tm.record_note(key, f"content for {key}", tags=["conc"])
        q.put(("ok", key, None))
    except Exception as exc:  # noqa: BLE001
        q.put(("err", key, f"{type(exc).__name__}: {exc}"))


def _tm_run_n(path: Path, keys: list[str]) -> tuple[set[str], set[str]]:
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(len(keys))
    q: mp.Queue = ctx.Queue()
    procs = [ctx.Process(target=_tm_worker, args=(str(path), k, barrier, q)) for k in keys]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
        if p.is_alive():
            p.terminate()
    ok_keys: set[str] = set()
    while not q.empty():
        status, key, _err = q.get_nowait()
        if status == "ok":
            ok_keys.add(key)
    from promptgraph.technical_memory import TechnicalMemory

    tm = TechnicalMemory(path)
    present = {k for k in ok_keys if tm.get_note(k) is not None}
    return ok_keys, present


class TestNEW01TechnicalMemoryConcurrency:
    def test_two_writers_both_survive(self, tmp_path):
        path = tmp_path / "mem.json"
        ok, present = _tm_run_n(path, ["k-a", "k-b"])
        for k in ok:
            assert k in present, f"Silent loss of acknowledged note {k}"

    def test_five_writers_repeated(self, tmp_path):
        failures = []
        for i in range(15):
            path = tmp_path / f"mem_{i}.json"
            keys = [f"w{j}-{i}" for j in range(5)]
            ok, present = _tm_run_n(path, keys)
            for k in ok:
                if k not in present:
                    failures.append((i, k, ok, present))
        assert not failures, f"Lost notes: {failures[:5]}"

    def test_uses_shared_lock_primitive(self):
        import inspect

        from promptgraph import technical_memory as tm

        src = inspect.getsource(tm)
        assert "SafeJsonStore" in src or "FileLock" in src or "msvcrt" in src or "fcntl" in src


# ---------- NEW-02 truncation propagation ----------


class TestNEW02TruncationPropagates:
    def test_prepare_exposes_truncated_analysis(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pg = PromptGraph(
            token_budget=8000,
            memory_path=tmp_path / "m.json",
            decisions_path=tmp_path / "d.json",
            trusted_root=tmp_path,
        )
        pg.contradiction_detector = ContradictionDetector(max_pair_checks=1)
        # Many allow/deny pairs
        parts = []
        for i in range(8):
            parts.append(f"Allow feature{i} access.")
            parts.append(f"Deny feature{i} access.")
        result = pg.prepare(" ".join(parts))
        pkg = result["package"]

        assert result.get("analysis_truncated") is True or (
            pkg.metadata.get("contradiction_analysis", {}).get("complete") is False
        )
        assert pkg.status != PackageStatus.READY
        # Visible in agent-facing prompt
        assert (
            "incomplete" in pkg.prompt.lower()
            or "truncated" in pkg.prompt.lower()
            or "analysis limit" in pkg.prompt.lower()
        )


# ---------- NEW-03 hard max_pair_checks ----------


class TestNEW03HardPairLimit:
    @pytest.mark.parametrize("limit", [0, 1, 2, 10])
    def test_pair_checks_never_exceeds_max(self, limit):
        det = ContradictionDetector(max_pair_checks=limit)
        reqs = []
        for i in range(20):
            reqs.append(Requirement(id=f"A{i}", description=f"Allow feature {i} access now."))
            reqs.append(Requirement(id=f"D{i}", description=f"Deny feature {i} access now."))
        r = det.detect_with_meta(reqs)
        assert r.pair_checks <= limit, f"pair_checks={r.pair_checks} > max={limit}"

    def test_zero_means_zero_and_truncated(self):
        det = ContradictionDetector(max_pair_checks=0)
        reqs = [
            Requirement(id="A0", description="Allow feature access now."),
            Requirement(id="D0", description="Deny feature access now."),
        ]
        r = det.detect_with_meta(reqs)
        assert r.pair_checks == 0
        assert r.analysis_truncated is True


# ---------- NEW-04 system_prompt rendered ----------


class TestNEW04SystemPromptRendered:
    def test_system_prompt_in_package_prompt(self):
        b = ContextPackageBuilder(token_budget=5000)
        pkg = b.build(
            "T",
            [Requirement(id="R1", description="Must support login.")],
            system_prompt="CUSTOM SYSTEM PROMPT XYZ",
        )
        assert "CUSTOM SYSTEM PROMPT XYZ" in pkg.prompt
        from promptgraph.models import estimate_token_count

        assert pkg.total_tokens == estimate_token_count(pkg.prompt)

    def test_large_system_prompt_exceeds_budget(self):
        b = ContextPackageBuilder(token_budget=20)
        with pytest.raises(BudgetExceededError):
            b.build(
                "T",
                [Requirement(id="R1", description="Must do X.")],
                system_prompt="WORD " * 200,
            )

    def test_unicode_system_prompt(self):
        b = ContextPackageBuilder(token_budget=5000)
        pkg = b.build(
            "T",
            [Requirement(id="R1", description="Must support export.")],
            system_prompt="Instrucciones: 日本語 café",
        )
        assert "日本語" in pkg.prompt
        assert "café" in pkg.prompt
