"""Contained Markdown vault under .agentops/promptgraph/."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from ..exceptions import MemoryValidationError, PathEscapeError, PersistenceError
from ..path_security import assert_path_family_contained, safe_join, validate_contained
from ..safe_json_store import FileLock, SafeJsonStore
from .models import ID_PREFIXES, TYPE_DIRS, MemoryRecord, MemoryType, StorageScope

DEFAULT_RELATIVE_ROOT = Path(".agentops") / "promptgraph"
SKIP_NAMES = {
    "INDEX.md",
    "index.json",
    "graph.json",
    ".gitignore",
    ".vault.lock",
}
SKIP_DIRS = {"context-packs"}
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ID_RE = re.compile(r"^(REQ|CON|ASM|DEC|FAIL|ATT|LESSON|ARCH|CP|AUD|EVID|PROJ)-(\d{4,})$")


def default_memory_root(project_root: str | Path) -> Path:
    return Path(project_root) / DEFAULT_RELATIVE_ROOT


def slugify(title: str, limit: int = 40) -> str:
    slug = _SLUG_RE.sub("-", (title or "").lower()).strip("-")
    return slug[:limit].strip("-")


def parse_memory_id(value: str) -> tuple[str, int] | None:
    match = _ID_RE.fullmatch(value.strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


class MemoryVault:
    def __init__(
        self,
        project_root: str | Path,
        *,
        memory_root: str | Path | None = None,
        trusted_root: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        if memory_root is not None:
            self.root = Path(memory_root)
        else:
            self.root = default_memory_root(self.project_root)
        if not self.root.is_absolute():
            self.root = self.project_root / self.root
        self.trusted_root = Path(trusted_root) if trusted_root is not None else self.project_root
        self._assert_contained(self.root)

    def _assert_contained(self, target: str | Path) -> Path:
        return validate_contained(target, self.trusted_root)

    def lock_path(self) -> Path:
        return self.root / ".vault.lock"

    def lock(self) -> FileLock:
        self._assert_contained(self.lock_path())

        def _pre(path: Path) -> None:
            assert_path_family_contained(path, trusted_root=self.trusted_root)

        return FileLock(self.lock_path(), pre_create_check=_pre)

    def init(self) -> Path:
        self._assert_contained(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._assert_contained(self.root)
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            self.write_text(
                gitignore,
                "local/\ncontext-packs/\n*.lock\n*.tmp\n*.corrupt\n*.corrupt.*\n",
            )
        index_md = self.root / "INDEX.md"
        if not index_md.exists():
            self.write_text(index_md, "# PromptGraph project memory\n\nNo records yet.\n")
        from .graph import MemoryGraph
        from .index import MemoryIndex

        if not (self.root / "index.json").exists():
            MemoryIndex(self).rebuild()
        if not (self.root / "graph.json").exists():
            MemoryGraph(self).rebuild()
        return self.root

    def exists(self) -> bool:
        return self.root.is_dir()

    def relpath(self, path: Path) -> str:
        contained = self._assert_contained(path)
        return contained.relative_to(self._assert_contained(self.root)).as_posix()

    def resolve_rel(self, relpath: str) -> Path:
        if not relpath or relpath.startswith("/") or relpath.startswith("\\"):
            raise PathEscapeError(f"Invalid memory path: {relpath!r}")
        parts = Path(relpath).parts
        if any(p in {"..", ""} for p in parts):
            raise PathEscapeError(f"Invalid memory path: {relpath!r}")
        joined = safe_join(self.root, *parts)
        return self._assert_contained(joined)

    def type_dir(self, mem_type: MemoryType, scope: StorageScope) -> Path:
        rel = TYPE_DIRS[mem_type]
        if scope is StorageScope.LOCAL_ONLY:
            parts = ["local"]
            if rel:
                parts.append(rel)
            return self.resolve_rel("/".join(parts))
        if not rel:
            return self.root
        return self.resolve_rel(rel)

    def filename_for(self, record: MemoryRecord) -> str:
        parsed = parse_memory_id(record.id)
        if parsed is None:
            raise MemoryValidationError(f"Invalid memory id: {record.id!r}")
        if record.type is MemoryType.PROJECT and record.scope is StorageScope.SHAREABLE:
            return "PROJECT.md"
        slug = slugify(record.title)
        name = f"{record.id}-{slug}.md" if slug else f"{record.id}.md"
        if any(ch in name for ch in '<>:"/\\|?*') or "\x00" in name:
            raise MemoryValidationError("Invalid generated filename.")
        return name

    def path_for(self, record: MemoryRecord) -> Path:
        directory = self.type_dir(record.type, record.scope)
        directory.mkdir(parents=True, exist_ok=True)
        self._assert_contained(directory)
        return self._assert_contained(directory / self.filename_for(record))

    def write_text(self, path: Path, text: str) -> None:
        target = Path(path)
        self._assert_contained(target)
        assert_path_family_contained(target, trusted_root=self.trusted_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        assert_path_family_contained(target, trusted_root=self.trusted_root)
        payload = text if text.endswith("\n") else text + "\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=f".{os.getpid()}.tmp",
            dir=str(target.parent),
        )
        tmp = Path(tmp_name)
        try:
            assert_path_family_contained(tmp, trusted_root=self.trusted_root)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            assert_path_family_contained(tmp, trusted_root=self.trusted_root)
            tmp.replace(target)
        except PathEscapeError:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        except OSError as exc:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise PersistenceError(f"Cannot write {target}: {exc}") from exc

    def read_text(self, path: Path) -> str:
        target = self._assert_contained(path)
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise MemoryValidationError(f"Unreadable UTF-8 in {target}: {exc}") from exc

    def iter_markdown(self) -> Iterator[Path]:
        if not self.root.exists():
            return
        root = self._assert_contained(self.root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if name not in SKIP_DIRS and not name.startswith(".")
            ]
            current = Path(dirpath)
            try:
                self._assert_contained(current)
            except PathEscapeError:
                dirnames[:] = []
                continue
            for name in sorted(filenames):
                if not name.endswith(".md") or name in SKIP_NAMES:
                    continue
                yield current / name

    def json_store(self, name: str) -> SafeJsonStore:
        path = self._assert_contained(self.root / name)
        return SafeJsonStore(path, trusted_root=self.trusted_root, default=dict)

    def next_id(self, mem_type: MemoryType, existing: set[str]) -> str:
        prefix = ID_PREFIXES[mem_type.value]
        highest = 0
        for ident in existing:
            parsed = parse_memory_id(ident)
            if parsed and parsed[0] == prefix:
                highest = max(highest, parsed[1])
        return f"{prefix}-{highest + 1:04d}"

    def fingerprint_bytes(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def dump_json(self, path: Path, data: object) -> None:
        text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        self.write_text(path, text)
