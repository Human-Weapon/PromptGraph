# Changelog

All notable changes to PromptGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-08-12

### Summary
Adversarial audit remediation across 4 rounds (rounds 1–4).
Baseline: v0.1.0 (`b81b326`). Release: `37a5fd0`.

### P1 — Release blockers (all fixed)

- **PG-01: Strict token budget.** One authoritative token count of the final
  rendered prompt. Successful packages never exceed `token_budget`. Mandatory
  content over budget raises `BudgetExceededError`. Optional context nodes
  dropped to fit. Per-call `prepare(budget=N)` / `build(token_budget=N)`
  honored end-to-end. Negative budgets rejected early. CLI `--budget -1`
  exits non-zero without traceback.

- **PG-03: Process-safe DecisionLedger.** Cross-platform file lock
  (`msvcrt` / `fcntl`), unique `mkstemp` temps, re-read under lock, merge,
  atomic replace. Duplicate IDs rejected. Two-process barrier tests
  (15 iterations). Zero silent data loss.

- **PG-04: Path containment wired.** `trusted_root` on all default
  persistent writers. `is_project_local_agentops()` detects all equivalent
  path spellings (`.agentops`, `./.agentops`, `.\.agentops`, absolute).
  Real Windows junction and POSIX symlink escape rejected. Zero outside
  artifacts after rejected write (TOCTOU re-validation on lock/temp/dest).

### P2 — Significant (all fixed)

- **PG-05: Selection contract.** Unified scoring (relevance dominates;
  priority is tie-breaker). `rank()` and `select()` share the same order.
  Dependency closure is atomic (seed+deps or exclude seed).

- **PG-07: Contradiction semantics.** Intra-requirement strong conflicts.
  Confidence levels: `strong` / `heuristic`. Public + authentication
  NOT hardcoded as contradiction. Heuristic pairs require content overlap.

- **PG-08: Zero/None handling.** `budget=0` and `max_questions=0` valid;
  `None` means unlimited. No falsy-or patterns.

- **PG-09: Persistence corruption.** Corrupt JSON quarantined with
  `CorruptStorageError`. No silent empty start.

- **PG-10: CLI error handling.** Domain errors produce concise stderr,
  stable non-zero exit codes. No tracebacks for expected errors.

- **PG-11: Bounded contradiction scaling.** Polarity-group candidate
  filtering. Hard `max_pair_checks` bound (`pair_checks <= max` always).
  `analysis_truncated` signal when limit reached.

- **PG-12: DAG cycle rejection.** Cycles rejected at `add_dependency`
  insertion time with `CycleError`.

- **NEW-01: TechnicalMemory concurrency.** Extracted `SafeJsonStore`
  shared primitive (lock + unique temp + atomic write). Both ledger and
  memory use it. Concurrent writes preserve all acknowledged keys.

- **NEW-02: Truncation propagation.** `analysis_truncated` propagates
  through `PromptGraph.prepare()` → `ContextPackage` status
  (`ANALYSIS_INCOMPLETE`) → metadata → visible agent-facing prompt warning.

- **NEW-03: Hard max_pair_checks.** `pair_checks` never exceeds configured
  maximum. `max=0` means zero comparisons with truncated signal.

- **P3-01: Neutral persistence errors.** `SafeJsonStore` raises
  `PersistenceError` / `StorageLockError` only. No domain-specific
  `DecisionError` leakage.

### P3 — Minor (all fixed)

- **PG-13: Dead parameters.** `min_length` enforced in `RequirementExtractor`.
  `system_prompt` rendered under `## System Instructions` and counted in
  the hard token budget.

- **PG-14: Test quality.** Tautological tests removed. Real process
  concurrency tests, real junction/symlink tests, adversarial test suite
  under `tests/adversarial/`.

### P4

- **PG-16: SPDX license.** `license = "MIT"` (SPDX form).

### Architecture
- `SafeJsonStore` — shared persistence primitive (process lock, unique
  temps, atomic replace, path containment, corruption quarantine).
- `PathSecurity` — canonical resolution, containment validation,
  project-local path detection.
- `PersistenceError` hierarchy — neutral storage errors.
- `PackageStatus.ANALYSIS_INCOMPLETE` — explicit non-READY status.

### Tests
- **143 passed, 1 skipped** (POSIX symlink test on Windows).
- Coverage: ≥80% threshold.
- Adversarial suite: `tests/adversarial/` (budget, concurrency,
  containment, schema, selection, contradictions, system_prompt).

### CI
- Windows: 3.10 / 3.11 / 3.12 — GREEN
- Ubuntu: 3.10 / 3.11 / 3.12 — GREEN
- macOS: NOT VERIFIED

### Known Limitations
1. Rule-based requirement extraction (not LLM-powered).
2. Heuristic token estimation (chars ÷ 4).
3. Lexical (not full semantic) contradiction detection.
4. English keyword matching for actionability; non-English preserved as
   UNKNOWN but not semantically classified.
5. macOS CI not configured.

## [0.1.0] — 2026-08-11

First functional release. Tag `v0.1.0` (commit `b81b326`) remains immutable
baseline. 49 passed, 0 failed. Coverage 83.8%.
