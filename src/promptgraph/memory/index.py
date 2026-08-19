"""Deterministic rebuildable memory index."""

from __future__ import annotations

import json
from typing import Any

from ..exceptions import CorruptStorageError, MemoryValidationError
from .models import MemoryRecord
from .serialize import markdown_to_record
from .vault import MemoryVault

INDEX_VERSION = 1


def entry_from_record(record: MemoryRecord, relpath: str) -> dict[str, Any]:
    return {
        "id": record.id,
        "type": record.type.value,
        "status": record.status.value,
        "title": record.title,
        "tags": list(record.tags),
        "paths": list(record.paths),
        "area": record.area,
        "related": list(record.related),
        "importance": record.disposition.value,
        "disposition": record.disposition.value,
        "scope": record.scope.value,
        "evidence_status": record.evidence_status.value,
        "summary": record.one_line_summary(),
        "fingerprint": record.fingerprint(),
        "relpath": relpath,
        "approach_keys": list(record.approach_key_set()),
        "supersedes": list(record.supersedes),
        "superseded_by": record.superseded_by,
        "level": int(record.level),
    }


class MemoryIndex:
    def __init__(self, vault: MemoryVault) -> None:
        self.vault = vault
        self.path = vault.root / "index.json"
        self._data: dict[str, Any] | None = None

    def load(self, *, rebuild_if_missing: bool = True) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        if not self.path.exists():
            if rebuild_if_missing:
                return self.rebuild()
            raise MemoryValidationError("Memory index is missing.")
        try:
            raw = json.loads(self.vault.read_text(self.path))
        except (json.JSONDecodeError, MemoryValidationError, UnicodeDecodeError) as exc:
            if rebuild_if_missing:
                return self.rebuild()
            raise CorruptStorageError(
                f"Memory index is corrupt: {exc}",
                quarantined_path=None,
            ) from exc
        if not isinstance(raw, dict) or "records" not in raw:
            if rebuild_if_missing:
                return self.rebuild()
            raise CorruptStorageError("Memory index schema is invalid.", quarantined_path=None)
        self._data = raw
        return raw

    def records(self) -> dict[str, dict[str, Any]]:
        data = self.load()
        recs = data.get("records") or {}
        if not isinstance(recs, dict):
            raise CorruptStorageError("Memory index records must be an object.")
        return recs

    def get(self, record_id: str) -> dict[str, Any] | None:
        return self.records().get(record_id)

    def ids(self) -> set[str]:
        return set(self.records())

    def fingerprint(self) -> str:
        data = self.load()
        return str(data.get("fingerprint") or "")

    def invalidate(self) -> None:
        self._data = None

    def rebuild(self) -> dict[str, Any]:
        records: dict[str, dict[str, Any]] = {}
        corrupt: list[str] = []
        for path in self.vault.iter_markdown():
            rel = self.vault.relpath(path)
            try:
                text = self.vault.read_text(path)
                record = markdown_to_record(text)
            except (MemoryValidationError, OSError, UnicodeDecodeError):
                corrupt.append(rel)
                continue
            if record.id in records:
                corrupt.append(rel)
                continue
            records[record.id] = entry_from_record(record, rel)
        payload = {
            "version": INDEX_VERSION,
            "records": dict(sorted(records.items())),
            "corrupt": sorted(corrupt),
        }
        digest = self.vault.fingerprint_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        )
        payload["fingerprint"] = digest
        self.vault.root.mkdir(parents=True, exist_ok=True)
        self.vault.dump_json(self.path, payload)
        self._write_index_markdown(payload)
        self._data = payload
        return payload

    def upsert(self, record: MemoryRecord, relpath: str) -> dict[str, Any]:
        data = self.load()
        recs = dict(data.get("records") or {})
        recs[record.id] = entry_from_record(record, relpath)
        payload = {
            "version": INDEX_VERSION,
            "records": dict(sorted(recs.items())),
            "corrupt": list(data.get("corrupt") or []),
        }
        digest = self.vault.fingerprint_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        )
        payload["fingerprint"] = digest
        self.vault.dump_json(self.path, payload)
        self._write_index_markdown(payload)
        self._data = payload
        return payload

    def _write_index_markdown(self, payload: dict[str, Any]) -> None:
        lines = ["# PromptGraph project memory", ""]
        recs = payload.get("records") or {}
        if not recs:
            lines.append("No records yet.")
        else:
            lines.append(f"{len(recs)} records.")
            lines.append("")
            for ident, entry in recs.items():
                title = entry.get("title") or ident
                summary = entry.get("summary") or ""
                lines.append(f"- [[{ident}]] {title} — {summary}")
        corrupt = payload.get("corrupt") or []
        if corrupt:
            lines.append("")
            lines.append("Unreadable files:")
            for rel in corrupt:
                lines.append(f"- {rel}")
        lines.append("")
        self.vault.write_text(self.vault.root / "INDEX.md", "\n".join(lines))


def collect_existing_ids(vault: MemoryVault) -> set[str]:
    ids: set[str] = set()
    index_path = vault.root / "index.json"
    if index_path.exists():
        try:
            data = json.loads(vault.read_text(index_path))
            recs = data.get("records") or {}
            if isinstance(recs, dict):
                ids.update(str(k) for k in recs)
        except (json.JSONDecodeError, MemoryValidationError, OSError):
            pass
    from .serialize import parse_frontmatter

    for path in vault.iter_markdown():
        try:
            meta, _ = parse_frontmatter(vault.read_text(path))
        except (MemoryValidationError, OSError):
            continue
        ident = meta.get("id")
        if isinstance(ident, str) and ident:
            ids.add(ident)
    return ids
