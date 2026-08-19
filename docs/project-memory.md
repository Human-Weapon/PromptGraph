# Persistent project memory

PromptGraph can keep **project knowledge** across agent sessions.

The conversation is working memory. Important facts belong in the project,
under `.agentops/promptgraph/`, as ordinary Markdown.

This is not a chat archive. PromptGraph persists distilled knowledge:
requirements, constraints, decisions, failures, attempts, lessons,
architecture, checkpoints, audits, and evidence.

## Why this exists

Long projects outlive any one chat window. A later agent should be able to
ask:

> What do I need to know to continue this task?

and receive a **bounded context package**, not yesterday's entire transcript.

## What is remembered

| Remember | Do not remember by default |
|---|---|
| Approved requirements and constraints | Casual conversation |
| Final decisions | Temporary narration |
| Significant failures and why attempts failed | Raw chat transcripts |
| Persistent lessons | Secret-like material as shareable notes |
| Session checkpoints | The entire vault on every query |

Uncertain or sensitive records default to **local-only** storage under
`local/`. That folder is gitignored by the vault.

## Zero-config workflow

```bash
promptgraph memory init .
promptgraph memory record . --type failure --title "Windows junction escaped containment" --scope shareable
promptgraph context build . --task "Fix the failing Windows test" --budget 8000
promptgraph memory checkpoint . --goal "Hand off containment work"
```

A normal user does not need to know about graphs, token allocation, or
Obsidian. Those are implementation details.

## How agents resume

### Session A

Works for several hours, discovers failures, makes decisions, and creates a
checkpoint. PromptGraph persists the verified knowledge. The chat transcript
is not stored.

### Session B

Starts with no chat history and asks PromptGraph for context for the next
task. PromptGraph returns the current checkpoint, active constraints,
relevant decisions, the relevant failure, the persistent lesson, and
relevant files. Session B continues without Session A's transcript.

## Obsidian compatibility

You may open `.agentops/promptgraph/` as an Obsidian vault. Wiki links such
as `[[FAIL-0001]]` are ordinary Markdown. PromptGraph understands them
itself. Obsidian is optional.

## Decision ledger

The existing DecisionLedger (`.agentops/decisions/decisions.json`) is
unchanged. Vault `DEC-*` records are the project-memory form of decisions.
They are not a silent copy of the JSON ledger.

## Honest claims

PromptGraph **can**:

- preserve project knowledge across agent sessions
- build a bounded context package from persistent memory
- surface relevant known failures so later agents do not need the original
  conversation
- verify that **declared** context was persisted before reporting
  compaction readiness

PromptGraph **cannot**:

- prove that an extractor omitted nothing important from a conversation
- delete ChatGPT/Claude/Codex chat history
- guarantee that no secret can ever be persisted
- prove two failed approaches are semantically identical
- eliminate context costs
