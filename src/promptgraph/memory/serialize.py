"""Strict frontmatter + Markdown serialization (stdlib, no YAML parser)."""

from __future__ import annotations

import json
import re
from typing import Any

from ..exceptions import MemoryValidationError
from .models import (
    FailedAttempt,
    MemoryRecord,
    normalize_record,
)

_WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_ID_IN_TEXT = re.compile(r"\b((?:REQ|CON|ASM|DEC|FAIL|ATT|LESSON|ARCH|CP|AUD|EVID|PROJ)-\d{4,})\b")
_BARE_VALUE = re.compile(r"[A-Za-z0-9_./+-]+")
_FRONTMATTER_KEYS = (
    "id",
    "type",
    "status",
    "area",
    "importance",
    "disposition",
    "scope",
    "evidence_status",
    "root_cause_status",
    "tags",
    "related",
    "paths",
    "approach_keys",
    "supersedes",
    "superseded_by",
    "summary",
    "unresolved",
    "relations",
)


def extract_wiki_ids(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _WIKI_RE.finditer(text or ""):
        token = match.group(1).strip()
        ident = _ID_IN_TEXT.search(token)
        if ident:
            value = ident.group(1)
            if value not in found:
                found.append(value)
    for ident in _ID_IN_TEXT.findall(text or ""):
        if ident not in found:
            found.append(ident)
    return tuple(found)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---"):
        raise MemoryValidationError("Record must start with a frontmatter delimiter.")
    rest = text[3:]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    else:
        raise MemoryValidationError("Frontmatter opening delimiter must be its own line.")
    lines = rest.splitlines()
    meta_lines: list[str] = []
    close_at: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            close_at = i
            break
        meta_lines.append(line)
    if close_at is None:
        raise MemoryValidationError("Frontmatter closing delimiter is missing.")
    body = "\n".join(lines[close_at + 1 :])
    if rest.endswith("\n") and not body.endswith("\n") and lines[close_at + 1 :]:
        body += "\n"
    meta: dict[str, Any] = {}
    for raw in meta_lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise MemoryValidationError(f"Invalid frontmatter line: {raw!r}")
        key, value = raw.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise MemoryValidationError(f"Invalid frontmatter key: {key!r}")
        meta[key] = _parse_scalar(value.strip())
    return meta, body


def _parse_scalar(raw: str) -> Any:
    if raw == "":
        return ""
    if raw[0] in '"[{tfn-0123456789' or raw in {"true", "false", "null"}:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    if _BARE_VALUE.fullmatch(raw):
        return raw
    raise MemoryValidationError(f"Invalid frontmatter value: {raw!r}")


def dump_frontmatter(meta: dict[str, Any]) -> str:
    lines = ["---"]
    for key in _FRONTMATTER_KEYS:
        if key not in meta:
            continue
        lines.append(f"{key}: {json.dumps(meta[key], ensure_ascii=False)}")
    extra_keys = sorted(k for k in meta if k not in _FRONTMATTER_KEYS)
    for key in extra_keys:
        lines.append(f"{key}: {json.dumps(meta[key], ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def record_to_markdown(record: MemoryRecord) -> str:
    meta: dict[str, Any] = {
        "id": record.id,
        "type": record.type.value,
        "status": record.status.value,
        "area": record.area,
        "importance": record.disposition.value,
        "disposition": record.disposition.value,
        "scope": record.scope.value,
        "evidence_status": record.evidence_status.value,
        "root_cause_status": record.root_cause_status.value,
        "tags": list(record.tags),
        "related": list(record.related),
        "paths": list(record.paths),
        "approach_keys": list(record.approach_key_set()),
        "supersedes": list(record.supersedes),
        "superseded_by": record.superseded_by,
        "summary": record.one_line_summary(),
        "unresolved": list(record.unresolved),
        "relations": [edge.to_dict() for edge in record.relations],
    }
    chunks = [dump_frontmatter(meta), f"# {record.title.strip()}\n"]
    _section(chunks, "Summary", record.summary)
    _section(chunks, "Problem", record.problem)
    _section(chunks, "Symptom", record.symptom)
    _section(chunks, "Evidence", record.evidence)
    if record.root_cause:
        _section(chunks, "Root cause", record.root_cause)
    if record.failed_attempts:
        chunks.append("## Failed attempts\n")
        for attempt in record.failed_attempts:
            chunks.append(f"### Attempt {attempt.index} - {attempt.title}\n")
            chunks.append(f"Result:\n{attempt.result}\n")
            chunks.append(f"Why:\n{attempt.why}\n")
            if attempt.approach_key:
                chunks.append(f"Approach key:\n{attempt.approach_key}\n")
            chunks.append("")
    _section(chunks, "Correct solution", record.solution)
    if any(record.regression.to_dict().values()):
        proof = record.regression
        chunks.append("## Regression proof\n")
        chunks.append(f"Baseline:\n{proof.baseline_commit}\n")
        chunks.append(f"Regression test:\n{proof.test_name}\n")
        chunks.append(f"Baseline result:\n{proof.baseline_result}\n")
        chunks.append(f"Fixed result:\n{proof.fixed_result}\n")
        if proof.fixed_commit:
            chunks.append(f"Fixed commit:\n{proof.fixed_commit}\n")
        chunks.append("")
    _section(chunks, "Result", record.result)
    _section(chunks, "Lesson", record.lesson)
    _section(chunks, "Goal", record.goal)
    _section(chunks, "Current state", record.current_state)
    _section(chunks, "Completed", record.completed)
    _section(chunks, "Remaining work", record.remaining)
    _section(chunks, "Start next session with", record.next_task)
    if record.body.strip():
        _section(chunks, "Notes", record.body)
    related = list(record.related)
    for ident in extract_wiki_ids(
        "\n".join(
            [
                record.body,
                record.problem,
                record.lesson,
                record.next_task,
                record.evidence,
            ]
        )
    ):
        if ident not in related:
            related.append(ident)
    if related:
        chunks.append("## Related\n")
        for ident in related:
            chunks.append(f"- [[{ident}]]")
        chunks.append("")
    text = "\n".join(chunks).rstrip() + "\n"
    return text


def _section(chunks: list[str], heading: str, value: str) -> None:
    if value and value.strip():
        chunks.append(f"## {heading}\n")
        chunks.append(value.strip() + "\n")


def markdown_to_record(text: str) -> MemoryRecord:
    meta, body = parse_frontmatter(text)
    sections = _parse_sections(body)
    title = sections.pop("_title", "") or str(meta.get("title") or "")
    attempts = _parse_attempts(sections.pop("Failed attempts", ""))
    regression = _parse_regression(sections.pop("Regression proof", ""))
    related = meta.get("related") or []
    if not isinstance(related, list):
        raise MemoryValidationError("related must be a list.")
    wiki_ids = extract_wiki_ids(body)
    merged_related = []
    for ident in [*related, *wiki_ids]:
        ident_s = str(ident)
        if ident_s not in merged_related:
            merged_related.append(ident_s)
    known = {
        "Notes",
        "Summary",
        "Problem",
        "Symptom",
        "Evidence",
        "Root cause",
        "Failed attempts",
        "Correct solution",
        "Regression proof",
        "Result",
        "Lesson",
        "Goal",
        "Current state",
        "Completed",
        "Remaining work",
        "Start next session with",
        "Related",
        "_preamble",
        "_title",
    }
    notes = sections.pop("Notes", "")
    leftover = "\n\n".join(
        f"## {name}\n{content}".strip()
        for name, content in sections.items()
        if content.strip() and name not in known
    )
    body_text = notes.strip()
    if leftover.strip():
        body_text = f"{body_text}\n\n{leftover}".strip() if body_text else leftover.strip()
    preamble = sections.get("_preamble", "").strip()
    if preamble and not body_text:
        body_text = preamble
    payload = {
        **meta,
        "title": title,
        "body": body_text,
        "summary": str(meta.get("summary") or sections.get("Summary") or ""),
        "problem": sections.get("Problem", ""),
        "symptom": sections.get("Symptom", ""),
        "evidence": sections.get("Evidence", ""),
        "root_cause": (
            sections.get("Root cause") if "Root cause" in sections else meta.get("root_cause")
        ),
        "failed_attempts": [a.to_dict() for a in attempts],
        "solution": sections.get("Correct solution", ""),
        "result": sections.get("Result", ""),
        "lesson": sections.get("Lesson", ""),
        "regression": regression,
        "related": merged_related,
        "goal": sections.get("Goal", ""),
        "current_state": sections.get("Current state", ""),
        "completed": sections.get("Completed", ""),
        "remaining": sections.get("Remaining work", ""),
        "next_task": sections.get("Start next session with", ""),
    }
    return normalize_record(MemoryRecord.from_dict(payload))


def _parse_sections(body: str) -> dict[str, str]:
    lines = body.splitlines()
    title = ""
    current = "_preamble"
    buckets: dict[str, list[str]] = {"_preamble": []}
    for line in lines:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            buckets.setdefault(current, [])
            continue
        buckets.setdefault(current, []).append(line)
    out = {key: "\n".join(vals).strip() for key, vals in buckets.items()}
    out["_title"] = title
    return out


def _parse_attempts(text: str) -> tuple[FailedAttempt, ...]:
    if not text.strip():
        return ()
    parts = re.split(r"(?m)^### Attempt\s+(\d+)\s+[—-]\s+", text)
    if len(parts) < 3:
        return ()
    attempts: list[FailedAttempt] = []
    preamble = parts[0]
    del preamble
    i = 1
    while i + 1 < len(parts):
        index = int(parts[i])
        block = parts[i + 1]
        title_line, _, rest = block.partition("\n")
        result = _field_after(rest, "Result")
        why = _field_after(rest, "Why")
        key = _field_after(rest, "Approach key")
        attempts.append(
            FailedAttempt(
                title=title_line.strip(),
                result=result,
                why=why,
                approach_key=key,
                index=index,
            )
        )
        i += 2
    return tuple(attempts)


def _field_after(text: str, label: str) -> str:
    match = re.search(
        rf"(?is)^{label}:\s*\n(.*?)(?=^[A-Za-z][A-Za-z ]*:\s*$|\Z)",
        text,
        re.MULTILINE,
    )
    if not match:
        return ""
    return match.group(1).strip()


def _parse_regression(text: str) -> dict[str, str]:
    if not text.strip():
        return {}
    return {
        "baseline_commit": _field_after(text, "Baseline"),
        "test_name": _field_after(text, "Regression test"),
        "baseline_result": _field_after(text, "Baseline result"),
        "fixed_result": _field_after(text, "Fixed result"),
        "fixed_commit": _field_after(text, "Fixed commit"),
    }
