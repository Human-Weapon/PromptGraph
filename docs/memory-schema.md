# Memory schema

Durable records are Markdown files with a strict, JSON-compatible
frontmatter block. Core PromptGraph does not require PyYAML.

```
---
id: "FAIL-0001"
type: "failure"
status: "resolved"
area: "filesystem"
importance: "persistent"
tags: ["windows", "junction"]
related: ["DEC-0001", "LESSON-0001"]
---
```

## Types and ID prefixes

| Type | Prefix | Typical folder |
|---|---|---|
| project | `PROJ` | `PROJECT.md` |
| requirement | `REQ` | `requirements/` |
| constraint | `CON` | `constraints/` |
| assumption | `ASM` | `assumptions/` |
| decision | `DEC` | `decisions/` |
| failure | `FAIL` | `failures/` |
| attempt | `ATT` | `attempts/` |
| lesson | `LESSON` | `lessons/` |
| architecture | `ARCH` | `architecture/` |
| checkpoint | `CP` | `checkpoints/` |
| audit | `AUD` | `audits/` |
| evidence | `EVID` | `evidence/` |

IDs are assigned under a vault lock and are never reused for unrelated
content.

## Dispositions

- `ephemeral` — not persisted
- `temporary` — session-useful, local by default
- `persistent` — survives sessions
- `canonical` — strongest retrieval priority

## Evidence status

`reported` | `observed` | `verified` | `disproved` | `superseded`

A README claim is not automatically `verified`.

## Failure chain

A failure may include problem, evidence, symptom, root cause (or
`unknown`), failed attempts, why each attempt failed, solution,
regression proof, result, and lesson. Missing fields stay unknown.
Root causes are never invented.

## Derived state

`index.json` and `graph.json` are rebuildable from Markdown. If they are
missing or corrupt, PromptGraph rebuilds them. It does not pretend the
vault is empty.

## Storage layout

```
.agentops/promptgraph/
  INDEX.md
  index.json
  graph.json
  .gitignore          # local/ and context-packs/
  requirements/
  decisions/
  failures/
  lessons/
  checkpoints/
  local/
  context-packs/
```

Directories are created lazily.
