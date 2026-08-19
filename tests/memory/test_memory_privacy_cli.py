from __future__ import annotations

import json

import pytest

from promptgraph.cli import main
from promptgraph.exceptions import MemoryValidationError
from promptgraph.memory.models import MemoryCandidate, MemoryType, StorageScope


def test_raw_transcript_rejected(memory):
    text = "\n".join(
        [
            "User: hello",
            "Assistant: hi",
            "User: more",
            "Assistant: still chatting",
        ]
    )
    with pytest.raises(MemoryValidationError, match="transcript"):
        memory.record_memory(
            MemoryCandidate(
                type=MemoryType.FAILURE,
                title="chat",
                body=text,
                scope=StorageScope.SHAREABLE,
            )
        )


def test_secret_like_forced_local(memory):
    rec = memory.record_memory(
        {
            "type": "decision",
            "title": "Token note",
            "body": "api_key: 'sk-abcdefghijklmnopqrstuvwxyz0123456789'",
            "scope": "shareable",
        }
    )
    assert rec.scope is StorageScope.LOCAL_ONLY
    assert "[REDACTED]" in rec.body


def test_cli_json_purity(memory, project, capsys):
    rc = main(["memory", "status", str(project), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    json.loads(out)
    assert out.strip().startswith("{")


def test_cli_init_validate_search_context(project, capsys):
    assert main(["memory", "init", str(project)]) == 0
    assert (
        main(
            [
                "memory",
                "record",
                str(project),
                "--type",
                "failure",
                "--title",
                "Windows junction escaped containment",
                "--body",
                "string-only path normalization failed because junctions are not resolved",
                "--area",
                "filesystem",
                "--tag",
                "windows",
                "--tag",
                "containment",
                "--scope",
                "shareable",
            ]
        )
        == 0
    )
    assert main(["memory", "validate", str(project)]) == 0
    assert main(["memory", "search", str(project), "--query", "windows containment"]) == 0
    search = capsys.readouterr().out
    assert "FAIL-0001" in search
    assert (
        main(
            [
                "context",
                "build",
                str(project),
                "--task",
                "Fix Windows filesystem containment",
                "--budget",
                "1200",
            ]
        )
        == 0
    )
    built = capsys.readouterr().out
    assert "Context Package" in built
    assert "FAIL-0001" in built
    assert main(["memory", "checkpoint", str(project), "--goal", "handoff"]) == 0
    capsys.readouterr()
    assert main(["memory", "compact-plan", str(project), "--task", "next", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["safe_to_compact"] is False
    assert payload["host_chat_deletion"] == "NOT_PERFORMED"


def test_cli_unknown_type(project, capsys):
    main(["memory", "init", str(project)])
    rc = main(["memory", "record", str(project), "--type", "vibes", "--title", "x"])
    assert rc == 2
    assert "unknown memory type" in capsys.readouterr().err
