"""Local-only scope, transcript refusal, and best-effort secret redaction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..exceptions import MemoryValidationError
from .models import Disposition, MemoryCandidate, MemoryRecord, StorageScope

_TURN_RE = re.compile(
    r"(?m)^(User|Assistant|Human|ChatGPT|Claude|Codex|Gemini|System)\s*:",
)
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
)


@dataclass(frozen=True)
class PrivacyDecision:
    scope: StorageScope
    redacted: bool
    reasons: tuple[str, ...]
    text_map: dict[str, str]


def looks_like_transcript(text: str) -> bool:
    return len(_TURN_RE.findall(text or "")) >= 4


def find_secret_like(text: str) -> bool:
    return any(pat.search(text or "") for pat in _SECRET_PATTERNS)


def redact_secret_like(text: str) -> tuple[str, bool]:
    changed = False
    out = text or ""
    for pat in _SECRET_PATTERNS:
        new = pat.sub("[REDACTED]", out)
        if new != out:
            changed = True
            out = new
    return out, changed


def _rewrite(value: str) -> tuple[str, bool]:
    return redact_secret_like(value)


def inspect_candidate(candidate: MemoryCandidate) -> PrivacyDecision:
    reasons: list[str] = []
    blob = "\n".join(
        [
            candidate.title,
            candidate.body,
            candidate.summary,
            candidate.problem,
            candidate.evidence,
            candidate.lesson,
            candidate.solution,
        ]
    )
    if looks_like_transcript(blob) and not candidate.allow_raw_chat:
        raise MemoryValidationError(
            "Raw chat transcripts are not persisted by default. "
            "Store distilled project knowledge instead."
        )
    if looks_like_transcript(blob) and candidate.allow_raw_chat:
        reasons.append("raw chat explicitly allowed; forced local_only")
    redacted_any = False
    text_map = {
        "title": candidate.title,
        "body": candidate.body,
        "summary": candidate.summary,
        "problem": candidate.problem,
        "symptom": candidate.symptom,
        "evidence": candidate.evidence,
        "lesson": candidate.lesson,
        "solution": candidate.solution,
        "result": candidate.result,
        "root_cause": candidate.root_cause or "",
    }
    for key, value in list(text_map.items()):
        new, changed = _rewrite(value)
        if changed:
            redacted_any = True
            text_map[key] = new
    scope = candidate.scope if candidate.scope is not None else StorageScope.LOCAL_ONLY
    if redacted_any or find_secret_like(blob):
        reasons.append("secret-like material forced local_only")
        scope = StorageScope.LOCAL_ONLY
    if looks_like_transcript(blob):
        scope = StorageScope.LOCAL_ONLY
    if candidate.disposition is Disposition.TEMPORARY and scope is StorageScope.SHAREABLE:
        scope = StorageScope.LOCAL_ONLY
        reasons.append("temporary memory defaults to local_only")
    return PrivacyDecision(
        scope=scope,
        redacted=redacted_any,
        reasons=tuple(reasons),
        text_map=text_map,
    )


def apply_privacy(candidate: MemoryCandidate) -> MemoryCandidate:
    decision = inspect_candidate(candidate)
    tm = decision.text_map
    return MemoryCandidate(
        type=candidate.type,
        title=tm["title"],
        body=tm["body"],
        id=candidate.id,
        status=candidate.status,
        disposition=candidate.disposition,
        scope=decision.scope,
        evidence_status=candidate.evidence_status,
        area=candidate.area,
        tags=candidate.tags,
        related=candidate.related,
        paths=candidate.paths,
        summary=tm["summary"],
        problem=tm["problem"],
        symptom=tm["symptom"],
        evidence=tm["evidence"],
        root_cause=tm["root_cause"] if candidate.root_cause is not None else None,
        root_cause_status=candidate.root_cause_status,
        failed_attempts=candidate.failed_attempts,
        solution=tm["solution"],
        result=tm["result"],
        lesson=tm["lesson"],
        regression=candidate.regression,
        provenance=candidate.provenance,
        approach_keys=candidate.approach_keys,
        supersedes=candidate.supersedes,
        goal=candidate.goal,
        current_state=candidate.current_state,
        completed=candidate.completed,
        remaining=candidate.remaining,
        next_task=candidate.next_task,
        unresolved=candidate.unresolved,
        relations=candidate.relations,
        allow_raw_chat=candidate.allow_raw_chat,
    )


def assert_shareable_safe(record: MemoryRecord) -> None:
    if record.scope is StorageScope.SHAREABLE and (
        find_secret_like(record.body)
        or find_secret_like(record.title)
        or find_secret_like(record.evidence)
    ):
        raise MemoryValidationError("Shareable records must not contain secret-like material.")
