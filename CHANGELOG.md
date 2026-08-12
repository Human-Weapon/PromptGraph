# Changelog

All notable changes to PromptGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-08-12

### Status
**Remediation release** — addresses 14 confirmed defects from adversarial audit
of v0.1.0. All P1 (release blockers) resolved. All reproduced P2/P3/P4 resolved.

### Security
- **PG-04**: Path containment validation added (`path_security.py`). Persistent
  writers validate paths against base directory to prevent symlink/junction escapes.
- **PG-03**: Duplicate decision IDs are now rejected (`DuplicateDecisionError`).
  Stale-write protection: `record()` re-reads from disk before saving.
- **PG-09**: Corrupt storage is quarantined (renamed to `.corrupt`) and raised
  as `CorruptStorageError` with quarantine path. No silent data loss.

### Changed (breaking)
- **PG-01**: Token budget is now enforced. `ContextPackage.compute_tokens()`
  counts the rendered prompt ONCE (no double-counting). `budget_exceeded` flag
  on package. `excluded_nodes` exposed.
- **PG-02**: `ContextPackage` now carries `contradictions` and `status` fields.
  Status: `READY` / `NEEDS_CLARIFICATION` / `BLOCKED`. Detected contradictions
  propagate from analysis to output.
- **PG-12**: `ContextGraph.add_dependency()` rejects cycle-creating edges at
  insertion time (`CycleError`), not later.
- **PG-13**: Removed dead parameters `order_key` and `reverse` from
  `TokenBudgetManager.plan()`.
- **PG-16**: License metadata updated to SPDX form (`license = "MIT"`).

### Added
- **PG-07**: Contradiction findings carry `confidence` field (`strong` / `heuristic`).
  Same-subject detection via token overlap reduces false positives.
- **PG-11**: Candidate filtering in contradiction detection (only compares
  requirements containing pattern keywords, reducing O(n²) constant factor).
- **PG-06**: Substantive non-English input is preserved as UNKNOWN requirement
  (tagged `possibly_non_english`) instead of silently dropped.
- **PG-08**: `budget=0` now correctly means zero (previously treated as falsy →
  used default via `or`). Explicit `None` check replaces `or` pattern.
- **PG-10**: CLI catches `PromptGraphError` and prints concise stderr with
  stable exit code 1. No Python tracebacks for expected errors.
- **PG-15**: GitHub Actions CI (Ubuntu + Windows, Python 3.10/3.11/3.12).
- New exceptions: `CycleError`, `DuplicateDecisionError`, `CorruptStorageError`,
  `PathEscapeError`, `BudgetExceededError`.
- New module: `path_security.py`.
- New model: `PackageStatus` enum.
- 40 new regression tests across 6 test files.

### Fixed
- Sentence splitter no longer breaks on intra-word hyphens (e.g. "read-only"
  was incorrectly split into "read" + "only").
- `QuestionBudgeter` with `max_questions=0` now correctly returns 0 questions.
- `ContextSelector.select()` preserves relevance ranking within priority tiers
  (stable sort instead of re-sorting by token size).

### Tests
- **89 tests passing** (0 failed, 0 skipped).
- Coverage: 84.1%.

### Known Limitations (unchanged from v0.1.0)
1. Requirement extraction is rule-based (regex heuristics, not LLM).
2. Token estimation is heuristic (chars ÷ 4), not a real tokenizer.
3. Contradiction detection is lexical (pattern matching, not semantic).

## [0.1.0] — 2026-08-11

### Status
**Released** — first functional version. Superseded by v0.1.1 remediation.

(See git history for details.)
