"""Session checkpoints and declared-context compaction planning."""

from __future__ import annotations

from ..exceptions import MemoryError, MemoryIntegrityError, MemoryValidationError
from .context_pack import MemoryContextPack, MemoryContextPackBuilder
from .gitinfo import project_git_state
from .index import MemoryIndex
from .models import (
    CompactionManifest,
    MemoryCandidate,
    MemoryRecord,
    MemoryType,
    Provenance,
    RecordStatus,
)
from .retriever import ContextRetriever
from .serialize import markdown_to_record
from .vault import MemoryVault
from .writer import MemoryWriter


def checkpoint_is_stale(
    record: MemoryRecord,
    vault: MemoryVault,
    index: MemoryIndex,
    *,
    expected_commit: str | None = None,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    git_state = project_git_state(vault.project_root)
    commit = expected_commit if expected_commit is not None else record.provenance.commit
    if commit and git_state.get("commit") and git_state["commit"] != commit:
        reasons.append("Git HEAD has changed since this checkpoint")
    recs = {}
    try:
        recs = index.records()
    except Exception:
        reasons.append("memory index is unavailable")
        return True, tuple(reasons)
    for ident in (*record.related, *record.unresolved):
        parsed = ident.split()[0]
        prefixes = (
            "REQ-",
            "CON-",
            "DEC-",
            "FAIL-",
            "LESSON-",
            "ARCH-",
            "ATT-",
            "AUD-",
            "EVID-",
            "CP-",
        )
        if parsed.startswith(prefixes):
            if parsed not in recs:
                reasons.append(f"checkpoint references missing record {parsed}")
            else:
                entry = recs[parsed]
                if entry.get("status") == RecordStatus.SUPERSEDED.value:
                    reasons.append(f"referenced {parsed} has been superseded")
    return bool(reasons), tuple(reasons)


def plan_compaction(
    vault: MemoryVault,
    *,
    session_id: str,
    candidates: list[MemoryCandidate] | None = None,
    checkpoint: MemoryCandidate | None = None,
    task: str = "",
    budget: int = 8000,
    extraction_complete: bool = False,
    source_range: str = "",
    persist_candidates: bool = True,
) -> CompactionManifest:
    reasons: list[str] = []
    persisted: list[str] = []
    checkpoint_id: str | None = None
    pack: MemoryContextPack | None = None
    persistence_ok = False
    retrieval_ok = False
    index_fp = ""

    if not extraction_complete:
        reasons.append("extraction_complete is false — host has not attested declared extraction")

    writer = MemoryWriter(vault)
    index = writer.index
    try:
        if persist_candidates and candidates:
            written = writer.persist_many(candidates)
            persisted.extend(r.id for r in written)
        if persist_candidates and checkpoint is not None:
            cp_record = writer.persist_candidate(checkpoint)
            checkpoint_id = cp_record.id
            persisted.append(cp_record.id)
        for ident in persisted:
            again = writer.read(ident)
            entry = writer.index.get(ident)
            if entry is None or again.fingerprint() != entry.get("fingerprint"):
                raise MemoryIntegrityError(f"Index fingerprint mismatch for {ident}")
            if not writer.verify_retrievable(ident):
                raise MemoryIntegrityError(f"Record {ident} is not retrievable")
        persistence_ok = True
        index.invalidate()
        index.load()
        index_fp = index.fingerprint()
        retriever = ContextRetriever(vault, index)
        if persisted:
            for ident in persisted:
                if retriever.load_record(ident).id != ident:
                    raise MemoryIntegrityError(f"Retrieval failed for {ident}")
        retrieval_ok = True
        if task:
            pack = MemoryContextPackBuilder(vault, retriever).build(
                task,
                budget=budget,
                include_local=True,
            )
    except (MemoryError, OSError) as exc:
        reasons.append(str(exc))
        retrieval_ok = False

    if checkpoint_id is None:
        reasons.append("checkpoint was not saved")
    if pack is None:
        reasons.append("context pack was not generated")
    safe = (
        extraction_complete
        and persistence_ok
        and retrieval_ok
        and pack is not None
        and checkpoint_id is not None
        and not reasons
    )
    status = "SAFE_TO_COMPACT_DECLARED_CONTEXT" if safe else "NOT_SAFE_TO_COMPACT"
    return CompactionManifest(
        session_id=session_id,
        source_range=source_range,
        checkpoint_id=checkpoint_id,
        persisted_memory_ids=tuple(dict.fromkeys(persisted)),
        context_pack_id=pack.pack_id if pack else None,
        context_pack_fingerprint=pack.fingerprint if pack else "",
        memory_index_fingerprint=index_fp,
        unresolved_items=tuple(checkpoint.unresolved) if checkpoint else (),
        extraction_complete=extraction_complete,
        persistence_verified=persistence_ok,
        retrieval_verified=retrieval_ok,
        safe_to_compact=safe,
        reasons=tuple(reasons),
        declared_status=status,
        host_chat_deletion="NOT_PERFORMED",
    )


def checkpoint_candidate_from_kwargs(
    *,
    goal: str,
    current_state: str = "",
    completed: str = "",
    remaining: str = "",
    next_task: str = "",
    related: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
    session: str = "",
    commit: str = "",
    title: str | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        type=MemoryType.CHECKPOINT,
        title=title or f"Checkpoint: {goal[:80]}",
        body="",
        status=RecordStatus.ACTIVE,
        area="session",
        related=related,
        summary=goal,
        goal=goal,
        current_state=current_state,
        completed=completed,
        remaining=remaining,
        next_task=next_task,
        unresolved=unresolved,
        provenance=Provenance(session=session, commit=commit),
    )


def load_checkpoint(vault: MemoryVault, checkpoint_id: str) -> MemoryRecord:
    path_entry = MemoryIndex(vault).get(checkpoint_id)
    if not path_entry:
        raise MemoryValidationError(f"Unknown checkpoint: {checkpoint_id}")
    return markdown_to_record(vault.read_text(vault.resolve_rel(str(path_entry["relpath"]))))
