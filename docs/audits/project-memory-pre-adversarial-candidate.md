# PromptGraph persistent project memory — pre-adversarial candidate

Status: **READY FOR FIRST INDEPENDENT ADVERSARIAL AUDIT**

This document does not self-certify a release.

## SHAs and version

| Field | Value |
|---|---|
| Base SHA | `20ac5ffc30dc13f5a689ab015eb2af9210f89ab5` |
| Implementation SHA | `edb973c49b93457b269be088b286faaafae128f9` |
| Final candidate SHA | `edb973c49b93457b269be088b286faaafae128f9` plus this documentation note |
| Declared version | `0.1.1` |
| Release promotion | **not performed** |

Tags `v0.1.0` and `v0.1.1` were not moved. No GitHub Release. No PyPI publish.

## New architecture

PromptGraph still prepares context. This expansion adds a Markdown-canonical
project-memory vault so agents can persist knowledge independently of a chat.

Reuse, not replacement:

- `SafeJsonStore` / `FileLock` for derived JSON and vault locking
- `path_security` containment, including real junctions
- `TokenBudget` / `estimate_token_count` for pack budgets
- `ContextGraph` for dependency-like memory edges
- `ContradictionDetector` for active canonical conflicts
- existing DecisionLedger and TechnicalMemory left in place

New package: `promptgraph.memory`.

Host API (provider-neutral):

- `record_memory`
- `checkpoint_session`
- `build_context_pack`
- `search_memory`
- `validate_memory`
- `plan_compaction`

No OpenAI / Claude / Codex / Gemini / Hermes hardcoding.

## Storage layout

Default root: `.agentops/promptgraph/`

```
INDEX.md
index.json          # derived, rebuildable
graph.json          # derived, rebuildable
.gitignore          # local/, context-packs/, locks, temps
requirements/
decisions/
failures/
lessons/
checkpoints/
local/              # LOCAL_ONLY
context-packs/      # generated packs, local by default
```

Directories are created lazily. Markdown is the durable record.

## Memory schema

Strict JSON-compatible frontmatter. No general YAML parser. PyYAML remains
optional and unused by core memory.

Types: PROJECT, REQUIREMENT, CONSTRAINT, ASSUMPTION, DECISION, FAILURE,
ATTEMPT, LESSON, ARCHITECTURE, CHECKPOINT, AUDIT, EVIDENCE.

Dispositions: EPHEMERAL (not persisted), TEMPORARY, PERSISTENT, CANONICAL.

Evidence status is preserved (`reported` is not auto-promoted to `verified`).

## Tests

Local: full suite green except the pre-existing
`test_standalone_no_sibling_required` when AgentBench is installed in the
developer environment. CI images do not have siblings.

New tests under `tests/memory/` cover records, Markdown safety, writer/index
rebuild, retrieval/packs, privacy/CLI, e2e failure-repetition, safe
compaction, containment/junctions, corruption, concurrency, large vault,
checkpoints, and the sample vault.

## Platform-specific skips

- POSIX symlink-only tests skipped on Windows
- Windows junction tests skip if `mklink /J` cannot create the link

## Coverage

- Line coverage (full suite, local): **84.35%**
- Branch coverage (full suite, local): **82.08%**
- New memory modules: generally 82–95% line; `writer.py` ~78% branch
- Threshold still `fail_under = 80`
- New modules are included in coverage

## Quality gates (local)

| Gate | Result |
|---|---|
| ruff check | pass |
| ruff format --check | pass |
| git diff --check | pass (CRLF warnings only) |
| pytest | pass (see sibling note) |
| python -m build | wheel + sdist |

## Black-box

Fresh venvs under `%TEMP%\opencode\`:

- wheel: `promptgraph --version` → 0.1.1; memory init/record/validate/context build
- sdist: same CLI surface
- siblings absent in those venvs
- no Obsidian, no LLM, no network required after install

## Privacy / compaction

- Raw transcripts rejected unless explicitly allowed, then forced local-only
- Secret-like strings redacted and forced local-only (not claimed complete)
- Context packs default `include_local=False`
- Vault gitignores `local/` and `context-packs/`
- No automatic git add/commit/push
- `safe_to_compact` requires `extraction_complete=true`, verified persist,
  checkpoint, readback, index, retrieval, and a generated pack
- `host_chat_deletion` is always `NOT_PERFORMED`

## Large-vault evidence

503-record synthetic vault (500 unrelated + related failure/lesson/constraint):
bounded 1800-token pack kept the related records, omitted most billing
history, and opened far fewer bodies than the vault size.

## Self-adversarial findings

| ID | Sev | Finding | State |
|---|---|---|---|
| PM-01 | P2 | Trailing whitespace broke Markdown fingerprint roundtrip | FIXED |
| PM-02 | P2 | `DuplicateMemoryError` was not caught by compaction planner | FIXED |
| PM-03 | P2 | `PromptGraph(project_root=tmp)` still resolved default ledger paths against CWD | FIXED |
| PM-04 | P3 | `memory init` left derived index/graph missing | FIXED |
| PM-05 | P3 | Writer branch coverage is weaker than other new modules | OPEN |
| PM-06 | P3 | Secret detection is heuristic only | OPEN / documented |
| PM-07 | P3 | macOS CI still absent | OPEN / pre-existing |
| PM-08 | P4 | `prepare()` does not auto-merge the Markdown vault | OPEN / intentional |
| PM-09 | P4 | Em-dash in pack headings can render poorly on some consoles | OPEN |

No P0/P1 left open. No known P2 hidden as a “limitation.”

## Limitations

- No embeddings / LLM classification
- No claim of complete extraction or complete secret detection
- Cannot delete provider chat history
- DecisionLedger JSON and vault `DEC-*` notes are separate stores
- Cross-process safety is bounded FileLock (10s); failure is explicit
- Heuristic token estimates (chars ÷ 4)

## Release state

- Tag: none created
- GitHub Release: none
- PyPI: not published
- Version left at 0.1.1 pending independent audit
