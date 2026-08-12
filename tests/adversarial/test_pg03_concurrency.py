"""Adversarial regression: PG-03 process-level concurrent ledger integrity.

INVARIANT: Two successful concurrent records must both survive.
Never silent loss. Never shared-temp collision.
"""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path


def _worker_record(path_str: str, decision_id: str, barrier: object, result_q: object) -> None:
    """Child process: wait on barrier, then record one decision."""
    try:
        from promptgraph.decision_ledger import DecisionLedger
        from promptgraph.models import Decision

        barrier.wait(timeout=30)
        ld = DecisionLedger(path_str)
        ld.record(
            Decision(
                id=decision_id,
                title=f"Title {decision_id}",
                context="concurrent",
                decision=f"decision body {decision_id}",
            )
        )
        result_q.put(("ok", decision_id, None))
    except Exception as exc:  # noqa: BLE001 — report any failure to parent
        result_q.put(("err", decision_id, f"{type(exc).__name__}: {exc}"))


def _run_pair(path: Path, id_a: str, id_b: str) -> tuple[str, str, set[str]]:
    """Launch two processes that write distinct IDs concurrently."""
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    q: mp.Queue = ctx.Queue()
    p1 = ctx.Process(target=_worker_record, args=(str(path), id_a, barrier, q))
    p2 = ctx.Process(target=_worker_record, args=(str(path), id_b, barrier, q))
    p1.start()
    p2.start()
    p1.join(timeout=60)
    p2.join(timeout=60)
    if p1.is_alive():
        p1.terminate()
    if p2.is_alive():
        p2.terminate()

    results = []
    while not q.empty():
        results.append(q.get_nowait())

    statuses = {r[0] for r in results}
    # Reload ledger from disk
    from promptgraph.decision_ledger import DecisionLedger
    from promptgraph.exceptions import CorruptStorageError

    try:
        ld = DecisionLedger(path)
        present = {d.id for d in ld.all()}
    except CorruptStorageError:
        present = set()
        statuses.add("corrupt")

    return statuses, {r[1] for r in results if r[0] == "ok"}, present


class TestPG03ProcessConcurrency:
    def test_two_processes_both_survive(self, tmp_path):
        """Two processes writing distinct IDs: both decisions must exist on disk."""
        path = tmp_path / "decisions.json"
        statuses, ok_ids, present = _run_pair(path, "proc-a", "proc-b")

        # Never corruption
        assert "corrupt" not in statuses

        # Both successful writes must be present; if a process failed with explicit
        # conflict that is OK only if it reported err — silent loss is not OK.
        if "ok" in statuses and len(ok_ids) == 2:
            assert "proc-a" in present and "proc-b" in present
        elif len(ok_ids) == 1:
            # One succeeded, one failed with explicit error — survivor must be on disk
            assert ok_ids.issubset(present)
            assert len(present) >= 1
        else:
            # Both failed with explicit errors is allowed only if nothing was claimed ok
            assert "ok" not in statuses or ok_ids.issubset(present)

        # Hard invariant: no silent partial success
        for oid in ok_ids:
            assert oid in present, f"Silent loss: {oid} reported ok but missing from disk"

    def test_concurrent_pair_repeated(self, tmp_path):
        """Run concurrent pair many times — never silent loss."""
        failures = []
        for i in range(15):
            path = tmp_path / f"decisions_{i}.json"
            statuses, ok_ids, present = _run_pair(path, f"a{i}", f"b{i}")
            if "corrupt" in statuses:
                failures.append((i, "corrupt", ok_ids, present))
            for oid in ok_ids:
                if oid not in present:
                    failures.append((i, f"silent_loss:{oid}", ok_ids, present))
        assert not failures, f"Concurrency failures: {failures[:5]}"

    def test_no_shared_temp_name(self):
        """Implementation must not use a single fixed .tmp sibling name alone."""
        import inspect

        from promptgraph import decision_ledger as mod

        src = inspect.getsource(mod.DecisionLedger)
        unique = any(
            token in src
            for token in (
                "mkstemp",
                "NamedTemporaryFile",
                "uuid",
                "getpid",
                "tempfile",
            )
        )
        assert unique, "DecisionLedger must use unique temp files, not only fixed .tmp"
        assert "_FileLock" in src or "msvcrt" in src or "fcntl" in src
