"""Validate, persist, read back, and verify durable memory records."""

from __future__ import annotations

from dataclasses import replace

from ..exceptions import (
    DuplicateMemoryError,
    MemoryIntegrityError,
    MemoryValidationError,
)
from .graph import MemoryGraph
from .index import MemoryIndex, collect_existing_ids
from .models import (
    Disposition,
    MemoryCandidate,
    MemoryRecord,
    RecordStatus,
    normalize_record,
)
from .privacy import apply_privacy, assert_shareable_safe
from .serialize import markdown_to_record, record_to_markdown
from .vault import MemoryVault


class MemoryWriter:
    def __init__(self, vault: MemoryVault, index: MemoryIndex | None = None) -> None:
        self.vault = vault
        self.index = index or MemoryIndex(vault)
        self.graph = MemoryGraph(vault)

    def persist_candidate(self, candidate: MemoryCandidate) -> MemoryRecord:
        if candidate.disposition is Disposition.EPHEMERAL:
            raise MemoryValidationError("EPHEMERAL candidates are not persisted.")
        cleaned = apply_privacy(candidate)
        with self.vault.lock():
            existing = collect_existing_ids(self.vault)
            assigned = cleaned.id
            if assigned:
                if assigned in existing:
                    raise DuplicateMemoryError(f"Memory id {assigned!r} already exists.")
            else:
                assigned = self.vault.next_id(cleaned.type, existing)
                if assigned in existing:
                    raise DuplicateMemoryError(f"Memory id {assigned!r} already exists.")
            record = cleaned.to_record(assigned)
            return self._persist_unlocked(record)

    def persist_record(self, record: MemoryRecord) -> MemoryRecord:
        assert_shareable_safe(record)
        with self.vault.lock():
            return self._persist_unlocked(record)

    def persist_many(self, candidates: list[MemoryCandidate]) -> list[MemoryRecord]:
        written: list[MemoryRecord] = []
        with self.vault.lock():
            existing = collect_existing_ids(self.vault)
            for candidate in candidates:
                if candidate.disposition is Disposition.EPHEMERAL:
                    raise MemoryValidationError("EPHEMERAL candidates are not persisted.")
                cleaned = apply_privacy(candidate)
                assigned = cleaned.id
                if assigned:
                    if assigned in existing:
                        raise DuplicateMemoryError(f"Memory id {assigned!r} already exists.")
                else:
                    assigned = self.vault.next_id(cleaned.type, existing)
                if assigned in existing:
                    raise DuplicateMemoryError(f"Memory id {assigned!r} already exists.")
                record = cleaned.to_record(assigned)
                written.append(self._persist_unlocked(record, existing=existing, rebuild=False))
                existing.add(record.id)
            self.index.invalidate()
            self.index.rebuild()
            self.graph.rebuild()
        return written

    def _persist_unlocked(
        self,
        record: MemoryRecord,
        *,
        existing: set[str] | None = None,
        rebuild: bool = True,
    ) -> MemoryRecord:
        known = existing if existing is not None else collect_existing_ids(self.vault)
        if record.id in known:
            raise DuplicateMemoryError(f"Memory id {record.id!r} already exists.")
        record = normalize_record(record)
        assert_shareable_safe(record)
        path = self.vault.path_for(record)
        markdown = record_to_markdown(record)
        expected = record.fingerprint()
        self.vault.write_text(path, markdown)
        try:
            read_back = markdown_to_record(self.vault.read_text(path))
        except MemoryValidationError as exc:
            raise MemoryIntegrityError(f"Readback schema failed for {record.id}: {exc}") from exc
        if read_back.id != record.id:
            raise MemoryIntegrityError(f"Readback id mismatch for {record.id}.")
        if read_back.fingerprint() != expected:
            raise MemoryIntegrityError(f"Fingerprint mismatch after write for {record.id}.")
        if record.supersedes:
            self._mark_superseded(record)
        rel = self.vault.relpath(path)
        if rebuild:
            self.index.invalidate()
            self.index.upsert(read_back, rel)
            self.graph.rebuild()
        return read_back

    def _mark_superseded(self, newer: MemoryRecord) -> None:
        for old_id in newer.supersedes:
            entry = None
            try:
                entry = self.index.get(old_id)
            except Exception:
                entry = None
            if not entry:
                continue
            rel = str(entry.get("relpath") or "")
            if not rel:
                continue
            try:
                path = self.vault.resolve_rel(rel)
                old = markdown_to_record(self.vault.read_text(path))
            except (MemoryValidationError, OSError):
                continue
            updated = replace(
                old,
                status=RecordStatus.SUPERSEDED,
                superseded_by=newer.id,
            )
            self.vault.write_text(path, record_to_markdown(updated))

    def read(self, record_id: str) -> MemoryRecord:
        entry = self.index.get(record_id)
        if not entry:
            self.index.invalidate()
            self.index.load()
            entry = self.index.get(record_id)
        if not entry:
            raise MemoryValidationError(f"Unknown memory id: {record_id}")
        path = self.vault.resolve_rel(str(entry["relpath"]))
        record = markdown_to_record(self.vault.read_text(path))
        if record.fingerprint() != entry.get("fingerprint"):
            self.index.invalidate()
            self.index.rebuild()
        return record

    def try_read(self, record_id: str) -> MemoryRecord | None:
        try:
            return self.read(record_id)
        except (MemoryValidationError, OSError, MemoryIntegrityError):
            return None

    def verify_retrievable(self, record_id: str) -> bool:
        record = self.try_read(record_id)
        return record is not None and record.id == record_id
