"""Regression tests for PG-03: DecisionLedger data loss."""

from __future__ import annotations

import pytest

from promptgraph.decision_ledger import DecisionLedger
from promptgraph.exceptions import CorruptStorageError, DuplicateDecisionError
from promptgraph.models import Decision


class TestPG03LedgerDataLoss:
    def test_duplicate_id_rejected(self, tmp_path):
        """Recording a duplicate id must raise, not silently overwrite."""
        ld = DecisionLedger(tmp_path / "ld.json")
        ld.record(Decision(id="d1", title="First", context="c", decision="A"))
        with pytest.raises(DuplicateDecisionError):
            ld.record(Decision(id="d1", title="Second", context="c", decision="B"))

    def test_original_preserved_after_duplicate_attempt(self, tmp_path):
        ld = DecisionLedger(tmp_path / "ld.json")
        ld.record(Decision(id="d1", title="First", context="c", decision="original"))
        try:
            ld.record(Decision(id="d1", title="Second", context="c", decision="overwrite"))
        except DuplicateDecisionError:
            pass
        d = ld.get("d1")
        assert d.decision == "original"

    def test_stale_writer_merges(self, tmp_path):
        """Two instances writing different IDs should not clobber each other."""
        path = tmp_path / "ld.json"
        ld1 = DecisionLedger(path)
        ld2 = DecisionLedger(path)
        ld1.record(Decision(id="d2", title="L1", context="c", decision="from instance 1"))
        ld2.record(Decision(id="d3", title="L2", context="c", decision="from instance 2"))
        # Reload to check both survived
        ld_reload = DecisionLedger(path)
        assert ld_reload.get("d2") is not None
        assert ld_reload.get("d3") is not None

    def test_corrupt_json_quarantined(self, tmp_path):
        """Corrupt JSON should be quarantined and raise CorruptStorageError."""
        path = tmp_path / "corrupt.json"
        path.write_text("NOT VALID JSON {{{", encoding="utf-8")
        with pytest.raises(CorruptStorageError) as exc_info:
            DecisionLedger(path)
        assert exc_info.value.quarantined_path is not None

    def test_reopen_persistence(self, tmp_path):
        path = tmp_path / "ld.json"
        ld = DecisionLedger(path)
        ld.record(Decision(id="d1", title="Test", context="c", decision="persist me"))
        ld2 = DecisionLedger(path)
        assert ld2.get("d1").decision == "persist me"

    def test_unicode_decision(self, tmp_path):
        ld = DecisionLedger(tmp_path / "ld.json")
        ld.record(Decision(id="u1", title="Tëst", context="café", decision="日本語"))
        ld2 = DecisionLedger(tmp_path / "ld.json")
        d = ld2.get("u1")
        assert d.decision == "日本語"
        assert d.title == "Tëst"
