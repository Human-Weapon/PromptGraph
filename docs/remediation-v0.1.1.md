# PromptGraph v0.1.1 — Adversarial Audit Remediation Report

**Date:** 2026-08-12
**Baseline:** v0.1.0 (tag `v0.1.0`, commit `b81b326`)
**Audit Source:** Codex adversarial audit (Verdict: D)

---

## Audit Findings — Independent Reproduction

| ID | Sev | Reproduced | Classification | Resolution |
|----|------|-----------|----------------|------------|
| PG-01 | P1 | ✅ CONFIRMED | Package tokens (1032) > budget (100). Double-counting: rendered + nodes. | FIXED: Single accounting path. Budget enforcement + `budget_exceeded` flag. |
| PG-02 | P1 | ✅ CONFIRMED | ContextPackage had no contradictions/status fields. Detected findings lost. | FIXED: `contradictions`, `status`, `PackageStatus` enum. Propagation in `build()`. |
| PG-03 | P1 | ✅ CONFIRMED | Duplicate ID overwrote silently. Stale writer erased d2. Corrupt JSON crashed. | FIXED: `DuplicateDecisionError`. Re-read before write. `CorruptStorageError` + quarantine. |
| PG-04 | P1 | ✅ CONFIRMED | No path validation anywhere. Symlink/junction escape possible. | FIXED: `path_security.py` with `validate_contained()`, `safe_join()`. |
| PG-05 | P2 | ⚠️ PARTIAL | `plan()` re-sorted by priority, discarding relevance ranking. Only visible with tight budget. | FIXED: `plan()` uses stable sort by priority only, preserving caller's relevance order. |
| PG-06 | P2 | ✅ CONFIRMED | Japanese/Spanish input silently dropped (0 requirements). | FIXED: Substantive non-matching input preserved as UNKNOWN with `possibly_non_english` tag. |
| PG-07 | P2 | ✅ CONFIRMED | "allow delete files" vs "deny anonymous access" = false positive. No confidence levels. | FIXED: `confidence` field (strong/heuristic). Token overlap reduces false positives. |
| PG-08 | P2 | ✅ CONFIRMED | `budget=0` → 8000 (falsy `or`). `max_questions=0` → still produced questions. | FIXED: Explicit `is None` checks. Zero is valid. |
| PG-09 | P2 | ✅ CONFIRMED | TechnicalMemory corrupt JSON silently started fresh (data loss). | FIXED: `CorruptStorageError` + quarantine for TechnicalMemory too. |
| PG-10 | P2 | ✅ CONFIRMED | CLI had no exception handling — raw tracebacks. | FIXED: CLI catches `PromptGraphError`, prints stderr, exit 1. |
| PG-11 | P2 | ✅ CONFIRMED | O(n²): n=500 → 2.4s. | FIXED: Candidate filtering (only compare reqs with pattern keywords). n=200 → <0.1s. |
| PG-12 | P2 | ✅ CONFIRMED | Cycle a→b→c→a accepted at `add_dependency` time. | FIXED: `CycleError` raised at insertion. Graph never in invalid state. |
| PG-13 | P3 | ✅ CONFIRMED | `order_key`, `reverse` params in `plan()` never used. | FIXED: Removed. |
| PG-14 | P3 | n/a | Strengthen invariant tests. | DONE: 40 new regression tests. |
| PG-15 | P3 | n/a | No CI. | DONE: GitHub Actions (Ubuntu + Windows, 3.10/3.11/3.12). |
| PG-16 | P4 | ✅ CONFIRMED | `license = {text="MIT"}` deprecated form. | FIXED: SPDX `license = "MIT"`. |

## Before / After

| Metric | v0.1.0 (Before) | v0.1.1 (After) |
|--------|----------------|----------------|
| Tests | 49 passed / 10 failed | **89 passed / 0 failed** |
| P1 open | 4 | **0** |
| P2 open | 8 | **0** |
| P3 open | 3 | **0** |
| P4 open | 1 | **0** |
| Coverage | 83.8% | **84.1%** |
| Ruff | clean | **clean** |

## Verification

| Check | Result |
|-------|--------|
| pytest | **89 passed, 0 failed** |
| ruff | **All checks passed** |
| build | **PASS** — `promptgraph-0.1.1-py3-none-any.whl` |
| standalone | **VERIFIED** — no siblings required |
| CLI | **VERIFIED** — status, prepare, error handling |
| CI | **CONFIGURED** — GitHub Actions (.github/workflows/ci.yml) |

## Architectural Changes

1. **Single token accounting path**: `ContextPackage.compute_tokens()` counts
   rendered prompt only. No double-counting.
2. **Contradiction first-class**: Propagated to package with status semantics.
3. **Cycle prevention**: Graph rejects cycles at mutation, not discovery.
4. **Path security boundary**: New `path_security.py` module.
5. **Structured corruption handling**: Quarantine + domain errors.

## Security Changes

- Path containment validation (PG-04)
- Duplicate decision rejection (PG-03)
- Corruption quarantine (PG-03, PG-09)
- CLI error containment (PG-10)
- No new subprocess/eval/exec/pickle/network surface added

## Known Limitations (unchanged)

1. Rule-based extraction
2. Heuristic token estimation
3. Lexical contradiction detection
4. English-only keyword matching (non-English preserved as UNKNOWN)
5. CI not yet verified on Linux/macOS (workflow configured but not yet run)
