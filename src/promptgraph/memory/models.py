"""Typed persistent-memory records and related value objects."""

from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from ..exceptions import MemoryValidationError

ID_PREFIXES: dict[str, str] = {
    "project": "PROJ",
    "requirement": "REQ",
    "constraint": "CON",
    "assumption": "ASM",
    "decision": "DEC",
    "failure": "FAIL",
    "attempt": "ATT",
    "lesson": "LESSON",
    "architecture": "ARCH",
    "checkpoint": "CP",
    "audit": "AUD",
    "evidence": "EVID",
}

PREFIX_TO_TYPE = {v: k for k, v in ID_PREFIXES.items()}


class MemoryType(enum.Enum):
    PROJECT = "project"
    REQUIREMENT = "requirement"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"
    DECISION = "decision"
    FAILURE = "failure"
    ATTEMPT = "attempt"
    LESSON = "lesson"
    ARCHITECTURE = "architecture"
    CHECKPOINT = "checkpoint"
    AUDIT = "audit"
    EVIDENCE = "evidence"


class Disposition(enum.Enum):
    EPHEMERAL = "ephemeral"
    TEMPORARY = "temporary"
    PERSISTENT = "persistent"
    CANONICAL = "canonical"


class MemoryLevel(enum.IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


class EvidenceStatus(enum.Enum):
    REPORTED = "reported"
    OBSERVED = "observed"
    VERIFIED = "verified"
    DISPROVED = "disproved"
    SUPERSEDED = "superseded"


class RecordStatus(enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    OPEN = "open"


class RootCauseStatus(enum.Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    UNKNOWN = "unknown"


class StorageScope(enum.Enum):
    LOCAL_ONLY = "local_only"
    SHAREABLE = "shareable"


class RelationType(enum.Enum):
    RELATES_TO = "relates_to"
    AFFECTS = "affects"
    CAUSED_BY = "caused_by"
    ATTEMPTED = "attempted"
    FAILED_BECAUSE = "failed_because"
    RESOLVED_BY = "resolved_by"
    VERIFIED_BY = "verified_by"
    LEARNED_FROM = "learned_from"
    CONSTRAINS = "constrains"
    DEPENDS_ON = "depends_on"
    SUPERSEDES = "supersedes"


class DisclosureLevel(enum.IntEnum):
    TITLE = 1
    SECTIONS = 2
    FULL = 3
    EVIDENCE = 4


TYPE_LEVEL: dict[MemoryType, MemoryLevel] = {
    MemoryType.PROJECT: MemoryLevel.L2,
    MemoryType.REQUIREMENT: MemoryLevel.L2,
    MemoryType.CONSTRAINT: MemoryLevel.L2,
    MemoryType.ASSUMPTION: MemoryLevel.L2,
    MemoryType.DECISION: MemoryLevel.L2,
    MemoryType.FAILURE: MemoryLevel.L2,
    MemoryType.ATTEMPT: MemoryLevel.L2,
    MemoryType.LESSON: MemoryLevel.L3,
    MemoryType.ARCHITECTURE: MemoryLevel.L2,
    MemoryType.CHECKPOINT: MemoryLevel.L1,
    MemoryType.AUDIT: MemoryLevel.L4,
    MemoryType.EVIDENCE: MemoryLevel.L4,
}

TYPE_DIRS: dict[MemoryType, str] = {
    MemoryType.PROJECT: "",
    MemoryType.REQUIREMENT: "requirements",
    MemoryType.CONSTRAINT: "constraints",
    MemoryType.ASSUMPTION: "assumptions",
    MemoryType.DECISION: "decisions",
    MemoryType.FAILURE: "failures",
    MemoryType.ATTEMPT: "attempts",
    MemoryType.LESSON: "lessons",
    MemoryType.ARCHITECTURE: "architecture",
    MemoryType.CHECKPOINT: "checkpoints",
    MemoryType.AUDIT: "audits",
    MemoryType.EVIDENCE: "evidence",
}


def _tuple_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _enum(cls: type[enum.Enum], value: Any, default: enum.Enum) -> enum.Enum:
    if value is None:
        return default
    if isinstance(value, cls):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized or item.name.lower() == normalized:
                return item
    raise MemoryValidationError(f"Invalid {cls.__name__}: {value!r}")


@dataclass(frozen=True)
class FailedAttempt:
    title: str
    result: str
    why: str
    approach_key: str = ""
    index: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "result": self.result,
            "why": self.why,
            "approach_key": self.approach_key,
            "index": self.index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FailedAttempt:
        if not isinstance(data, dict):
            raise MemoryValidationError("Failed attempt must be an object.")
        return cls(
            title=str(data.get("title") or ""),
            result=str(data.get("result") or ""),
            why=str(data.get("why") or ""),
            approach_key=str(data.get("approach_key") or ""),
            index=int(data.get("index") or 1),
        )


@dataclass(frozen=True)
class Provenance:
    session: str = ""
    path: str = ""
    commit: str = ""
    ci_run: str = ""
    audit: str = ""
    command: str = ""
    test: str = ""
    report: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session,
            "path": self.path,
            "commit": self.commit,
            "ci_run": self.ci_run,
            "audit": self.audit,
            "command": self.command,
            "test": self.test,
            "report": self.report,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Provenance:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise MemoryValidationError("Provenance must be an object or omitted.")
        return cls(
            session=str(data.get("session") or ""),
            path=str(data.get("path") or ""),
            commit=str(data.get("commit") or ""),
            ci_run=str(data.get("ci_run") or ""),
            audit=str(data.get("audit") or ""),
            command=str(data.get("command") or ""),
            test=str(data.get("test") or ""),
            report=str(data.get("report") or ""),
            source=str(data.get("source") or ""),
        )


@dataclass(frozen=True)
class RegressionProof:
    baseline_commit: str = ""
    fixed_commit: str = ""
    test_name: str = ""
    baseline_result: str = ""
    fixed_result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_commit": self.baseline_commit,
            "fixed_commit": self.fixed_commit,
            "test_name": self.test_name,
            "baseline_result": self.baseline_result,
            "fixed_result": self.fixed_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RegressionProof:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise MemoryValidationError("Regression proof must be an object or omitted.")
        return cls(
            baseline_commit=str(data.get("baseline_commit") or ""),
            fixed_commit=str(data.get("fixed_commit") or ""),
            test_name=str(data.get("test_name") or ""),
            baseline_result=str(data.get("baseline_result") or ""),
            fixed_result=str(data.get("fixed_result") or ""),
        )


@dataclass(frozen=True)
class MemoryEdge:
    source: str
    target: str
    relation: RelationType

    def to_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
        }


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    type: MemoryType
    title: str
    body: str = ""
    status: RecordStatus = RecordStatus.ACTIVE
    disposition: Disposition = Disposition.PERSISTENT
    scope: StorageScope = StorageScope.LOCAL_ONLY
    evidence_status: EvidenceStatus = EvidenceStatus.REPORTED
    area: str = ""
    tags: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    summary: str = ""
    problem: str = ""
    symptom: str = ""
    evidence: str = ""
    root_cause: str | None = None
    root_cause_status: RootCauseStatus = RootCauseStatus.UNKNOWN
    failed_attempts: tuple[FailedAttempt, ...] = ()
    solution: str = ""
    result: str = ""
    lesson: str = ""
    regression: RegressionProof = field(default_factory=RegressionProof)
    provenance: Provenance = field(default_factory=Provenance)
    approach_keys: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    superseded_by: str = ""
    goal: str = ""
    current_state: str = ""
    completed: str = ""
    remaining: str = ""
    next_task: str = ""
    unresolved: tuple[str, ...] = ()
    relations: tuple[MemoryEdge, ...] = ()
    allow_raw_chat: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def level(self) -> MemoryLevel:
        return TYPE_LEVEL[self.type]

    @property
    def importance(self) -> Disposition:
        return self.disposition

    def __post_init__(self) -> None:
        validate_record(self)

    def one_line_summary(self) -> str:
        if self.summary.strip():
            return self.summary.strip().splitlines()[0][:240].rstrip()
        for candidate in (self.lesson, self.problem, self.body, self.title):
            text = candidate.strip()
            if text:
                return text.splitlines()[0][:240].rstrip()
        return self.title.strip()

    def approach_key_set(self) -> tuple[str, ...]:
        keys = list(self.approach_keys)
        for attempt in self.failed_attempts:
            if attempt.approach_key:
                keys.append(attempt.approach_key)
        seen: list[str] = []
        for key in keys:
            if key not in seen:
                seen.append(key)
        return tuple(seen)

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "body": self.body,
            "status": self.status.value,
            "disposition": self.disposition.value,
            "scope": self.scope.value,
            "evidence_status": self.evidence_status.value,
            "area": self.area,
            "tags": list(self.tags),
            "related": list(self.related),
            "paths": list(self.paths),
            "summary": self.summary,
            "problem": self.problem,
            "symptom": self.symptom,
            "evidence": self.evidence,
            "root_cause": self.root_cause,
            "root_cause_status": self.root_cause_status.value,
            "failed_attempts": [a.to_dict() for a in self.failed_attempts],
            "solution": self.solution,
            "result": self.result,
            "lesson": self.lesson,
            "regression": self.regression.to_dict(),
            "provenance": self.provenance.to_dict(),
            "approach_keys": list(self.approach_key_set()),
            "supersedes": list(self.supersedes),
            "superseded_by": self.superseded_by,
            "goal": self.goal,
            "current_state": self.current_state,
            "completed": self.completed,
            "remaining": self.remaining,
            "next_task": self.next_task,
            "unresolved": list(self.unresolved),
            "relations": [e.to_dict() for e in self.relations],
        }

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        data = self.canonical_payload()
        data["level"] = int(self.level)
        data["fingerprint"] = self.fingerprint()
        data["allow_raw_chat"] = self.allow_raw_chat
        if self.extra:
            data["extra"] = dict(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        if not isinstance(data, dict):
            raise MemoryValidationError("Memory record must be an object.")
        raw_type = data.get("type")
        if raw_type is None:
            raise MemoryValidationError("Memory record missing type.")
        try:
            mem_type = _enum(MemoryType, raw_type, MemoryType.EVIDENCE)
        except MemoryValidationError as exc:
            raise MemoryValidationError(f"Unknown memory type: {raw_type!r}") from exc
        root_cause: str | None
        if "root_cause" not in data:
            root_cause = None
        elif data["root_cause"] is None:
            root_cause = None
        else:
            root_cause = str(data["root_cause"])
        attempts_raw = data.get("failed_attempts") or ()
        attempts = tuple(FailedAttempt.from_dict(item) for item in attempts_raw)
        relations_raw = data.get("relations") or ()
        relations = []
        for item in relations_raw:
            if not isinstance(item, dict):
                raise MemoryValidationError("Relation must be an object.")
            relations.append(
                MemoryEdge(
                    source=str(item.get("source") or data.get("id") or ""),
                    target=str(item.get("target") or ""),
                    relation=_enum(RelationType, item.get("relation"), RelationType.RELATES_TO),
                )
            )
        extra = data.get("extra")
        return cls(
            id=str(data.get("id") or ""),
            type=mem_type,
            title=str(data.get("title") or ""),
            body=str(data.get("body") or ""),
            status=_enum(RecordStatus, data.get("status"), RecordStatus.ACTIVE),
            disposition=_enum(
                Disposition,
                data.get("disposition") or data.get("importance"),
                Disposition.PERSISTENT,
            ),
            scope=_enum(StorageScope, data.get("scope"), StorageScope.LOCAL_ONLY),
            evidence_status=_enum(
                EvidenceStatus, data.get("evidence_status"), EvidenceStatus.REPORTED
            ),
            area=str(data.get("area") or ""),
            tags=_tuple_str(data.get("tags")),
            related=_tuple_str(data.get("related")),
            paths=_tuple_str(data.get("paths")),
            summary=str(data.get("summary") or ""),
            problem=str(data.get("problem") or ""),
            symptom=str(data.get("symptom") or ""),
            evidence=str(data.get("evidence") or ""),
            root_cause=root_cause,
            root_cause_status=_enum(
                RootCauseStatus, data.get("root_cause_status"), RootCauseStatus.UNKNOWN
            ),
            failed_attempts=attempts,
            solution=str(data.get("solution") or data.get("correct_solution") or ""),
            result=str(data.get("result") or ""),
            lesson=str(data.get("lesson") or ""),
            regression=RegressionProof.from_dict(
                data.get("regression") or data.get("regression_proof")
            ),
            provenance=Provenance.from_dict(data.get("provenance")),
            approach_keys=_tuple_str(data.get("approach_keys")),
            supersedes=_tuple_str(data.get("supersedes")),
            superseded_by=str(data.get("superseded_by") or ""),
            goal=str(data.get("goal") or ""),
            current_state=str(data.get("current_state") or ""),
            completed=str(data.get("completed") or ""),
            remaining=str(data.get("remaining") or ""),
            next_task=str(data.get("next_task") or ""),
            unresolved=_tuple_str(data.get("unresolved")),
            relations=tuple(relations),
            allow_raw_chat=bool(data.get("allow_raw_chat", False)),
            extra=dict(extra) if isinstance(extra, dict) else {},
        )


@dataclass(frozen=True)
class MemoryCandidate:
    type: MemoryType
    title: str
    body: str = ""
    id: str | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    disposition: Disposition = Disposition.PERSISTENT
    scope: StorageScope | None = None
    evidence_status: EvidenceStatus = EvidenceStatus.REPORTED
    area: str = ""
    tags: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    summary: str = ""
    problem: str = ""
    symptom: str = ""
    evidence: str = ""
    root_cause: str | None = None
    root_cause_status: RootCauseStatus = RootCauseStatus.UNKNOWN
    failed_attempts: tuple[FailedAttempt, ...] = ()
    solution: str = ""
    result: str = ""
    lesson: str = ""
    regression: RegressionProof = field(default_factory=RegressionProof)
    provenance: Provenance = field(default_factory=Provenance)
    approach_keys: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    goal: str = ""
    current_state: str = ""
    completed: str = ""
    remaining: str = ""
    next_task: str = ""
    unresolved: tuple[str, ...] = ()
    relations: tuple[MemoryEdge, ...] = ()
    allow_raw_chat: bool = False

    def to_record(self, assigned_id: str) -> MemoryRecord:
        scope = self.scope if self.scope is not None else StorageScope.LOCAL_ONLY
        relations = tuple(
            MemoryEdge(
                source=assigned_id if e.source in {"", "PENDING-0000"} else e.source,
                target=e.target,
                relation=e.relation,
            )
            for e in self.relations
        )
        return MemoryRecord(
            id=assigned_id,
            type=self.type,
            title=self.title,
            body=self.body,
            status=self.status,
            disposition=self.disposition,
            scope=scope,
            evidence_status=self.evidence_status,
            area=self.area,
            tags=self.tags,
            related=self.related,
            paths=self.paths,
            summary=self.summary,
            problem=self.problem,
            symptom=self.symptom,
            evidence=self.evidence,
            root_cause=self.root_cause,
            root_cause_status=self.root_cause_status,
            failed_attempts=self.failed_attempts,
            solution=self.solution,
            result=self.result,
            lesson=self.lesson,
            regression=self.regression,
            provenance=self.provenance,
            approach_keys=self.approach_keys,
            supersedes=self.supersedes,
            goal=self.goal,
            current_state=self.current_state,
            completed=self.completed,
            remaining=self.remaining,
            next_task=self.next_task,
            unresolved=self.unresolved,
            relations=relations,
            allow_raw_chat=self.allow_raw_chat,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryCandidate:
        record_like = dict(data)
        if not record_like.get("id"):
            record_like["id"] = "PENDING-0000"
        preview = MemoryRecord.from_dict(record_like)
        raw_id = data.get("id")
        assigned = str(raw_id) if raw_id else None
        raw_scope = data.get("scope")
        scope = None if raw_scope is None else preview.scope
        return cls(
            type=preview.type,
            title=preview.title,
            body=preview.body,
            id=assigned,
            status=preview.status,
            disposition=preview.disposition,
            scope=scope,
            evidence_status=preview.evidence_status,
            area=preview.area,
            tags=preview.tags,
            related=preview.related,
            paths=preview.paths,
            summary=preview.summary,
            problem=preview.problem,
            symptom=preview.symptom,
            evidence=preview.evidence,
            root_cause=preview.root_cause,
            root_cause_status=preview.root_cause_status,
            failed_attempts=preview.failed_attempts,
            solution=preview.solution,
            result=preview.result,
            lesson=preview.lesson,
            regression=preview.regression,
            provenance=preview.provenance,
            approach_keys=preview.approach_keys,
            supersedes=preview.supersedes,
            goal=preview.goal,
            current_state=preview.current_state,
            completed=preview.completed,
            remaining=preview.remaining,
            next_task=preview.next_task,
            unresolved=preview.unresolved,
            relations=preview.relations,
            allow_raw_chat=preview.allow_raw_chat,
        )


@dataclass(frozen=True)
class RetrievalHit:
    record_id: str
    score: int
    reasons: tuple[str, ...]
    disclosure: DisclosureLevel = DisclosureLevel.TITLE
    summary: str = ""
    title: str = ""
    type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.record_id,
            "score": self.score,
            "reasons": list(self.reasons),
            "disclosure": int(self.disclosure),
            "summary": self.summary,
            "title": self.title,
            "type": self.type,
        }


@dataclass
class CompactionManifest:
    session_id: str
    source_range: str = ""
    checkpoint_id: str | None = None
    persisted_memory_ids: tuple[str, ...] = ()
    context_pack_id: str | None = None
    context_pack_fingerprint: str = ""
    memory_index_fingerprint: str = ""
    unresolved_items: tuple[str, ...] = ()
    extraction_complete: bool = False
    persistence_verified: bool = False
    retrieval_verified: bool = False
    safe_to_compact: bool = False
    reasons: tuple[str, ...] = ()
    declared_status: str = "NOT_SAFE_TO_COMPACT"
    host_chat_deletion: str = "NOT_PERFORMED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_range": self.source_range,
            "checkpoint_id": self.checkpoint_id,
            "persisted_memory_ids": list(self.persisted_memory_ids),
            "context_pack_id": self.context_pack_id,
            "context_pack_fingerprint": self.context_pack_fingerprint,
            "memory_index_fingerprint": self.memory_index_fingerprint,
            "unresolved_items": list(self.unresolved_items),
            "extraction_complete": self.extraction_complete,
            "persistence_verified": self.persistence_verified,
            "retrieval_verified": self.retrieval_verified,
            "safe_to_compact": self.safe_to_compact,
            "reasons": list(self.reasons),
            "declared_status": self.declared_status,
            "host_chat_deletion": self.host_chat_deletion,
            "safe_to_compact_means": (
                "all DECLARED memory candidates and checkpoint data were persisted and verified"
            ),
            "does_not_mean": ("nothing important in the original conversation was omitted"),
        }


@dataclass
class ValidationReport:
    ok: bool
    record_count: int = 0
    unresolved_links: tuple[str, ...] = ()
    corrupt_records: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    index_current: bool = True
    graph_current: bool = True
    status: str = "ready"
    messages: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "record_count": self.record_count,
            "unresolved_links": list(self.unresolved_links),
            "corrupt_records": list(self.corrupt_records),
            "contradictions": list(self.contradictions),
            "index_current": self.index_current,
            "graph_current": self.graph_current,
            "status": self.status,
            "messages": list(self.messages),
        }


def normalize_record(record: MemoryRecord) -> MemoryRecord:
    from dataclasses import replace

    edges = list(record.relations)
    have = {(e.source, e.target, e.relation) for e in edges}
    for ident in record.related:
        key = (record.id, ident, RelationType.RELATES_TO)
        if ident and key not in have:
            edges.append(
                MemoryEdge(source=record.id, target=ident, relation=RelationType.RELATES_TO)
            )
            have.add(key)
    for ident in record.supersedes:
        key = (record.id, ident, RelationType.SUPERSEDES)
        if ident and key not in have:
            edges.append(
                MemoryEdge(source=record.id, target=ident, relation=RelationType.SUPERSEDES)
            )
            have.add(key)
    edges.sort(key=lambda e: (e.source, e.relation.value, e.target))
    summary = (record.summary.strip() or record.one_line_summary()).strip()
    return replace(
        record,
        relations=tuple(edges),
        summary=summary,
        body=record.body.strip(),
        problem=record.problem.strip(),
        symptom=record.symptom.strip(),
        evidence=record.evidence.strip(),
        lesson=record.lesson.strip(),
        solution=record.solution.strip(),
        result=record.result.strip(),
    )


def validate_record(record: MemoryRecord) -> None:
    if not record.id or not str(record.id).strip():
        raise MemoryValidationError("Memory record id is required.")
    if "\n" in record.id or "/" in record.id or "\\" in record.id:
        raise MemoryValidationError("Memory record id must be a single path-safe token.")
    if not record.title or not record.title.strip():
        raise MemoryValidationError("Memory record title is required.")
    if "\x00" in record.title or "\x00" in record.body:
        raise MemoryValidationError("Memory record may not contain NUL bytes.")
    if record.disposition is Disposition.EPHEMERAL:
        raise MemoryValidationError("EPHEMERAL records must not be persisted.")
    confirmed = record.root_cause_status is RootCauseStatus.CONFIRMED
    if confirmed and not (record.root_cause or "").strip():
        raise MemoryValidationError("Confirmed root cause requires a root_cause value.")
    prefix = ID_PREFIXES[record.type.value]
    if record.id != "PENDING-0000" and not record.id.startswith(f"{prefix}-"):
        raise MemoryValidationError(
            f"Memory id {record.id!r} does not match type prefix {prefix}-."
        )
