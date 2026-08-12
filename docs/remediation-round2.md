# PromptGraph v0.1.1 — Remediation Round 2 Report

**Baseline commit:** `9f40355`
**State:** RECOVERING → COMPLETED (awaiting 3rd audit)
**No tag created.**

## Method
For each P1 defect: REPRODUCE → FAILING TEST → FIX → PASS → full suite → wheel black-box.

## Findings

### PG-01 Strict token budget
- **BEFORE:** `ContextPackageBuilder(10)` returned READY package with 36 tokens, `budget_exceeded=True`.
- **REGRESSION vs 9f40355:** `test_mandatory_over_budget_raises` FAILED (no exception).
- **AFTER:** raises `BudgetExceededError`; successful packages always `total_tokens <= budget`.
- **EVIDENCE:** adversarial + black-box wheel tests pass.

### PG-03 Concurrent process safety
- **BEFORE:** shared `.tmp`, no lock; concurrent processes could lose data / collide.
- **REGRESSION vs 9f40355:** process barrier tests + unique-temp assertion FAILED.
- **AFTER:** `_FileLock` + `mkstemp` unique temps + re-read under lock; 15× pair iterations pass.
- **EVIDENCE:** `test_concurrent_pair_repeated` green.

### PG-04 Path containment wired
- **BEFORE:** `path_security` not imported by ledger/memory (dead code).
- **REGRESSION vs 9f40355:** junction test + "wired" import test FAILED.
- **AFTER:** `trusted_root` on ledger/memory/core; real Windows junction rejects escape.
- **EVIDENCE:** `test_junction_escape_rejected_on_windows` green on this host.

### PG-05 Selection contract
- Combined score; rank/select consistent; atomic dependency groups.
- Tests in `test_pg05_07_11_13.py`.

### PG-07 Contradiction semantics
- Intra-requirement strong conflicts.
- public+auth NOT auto-strong.
- Confidence levels retained.

### PG-11 Bounded scaling
- Polarity groups + `max_pair_checks` + `analysis_truncated`.

### PG-13 Dead params
- `min_length` enforced; `system_prompt` in metadata.

### PG-14
- Tautological budget OR removed; real process/junction tests added.

## Verification

| Check | Result |
|-------|--------|
| pytest | **113 passed, 1 skipped** |
| ruff | **All checks passed** |
| build wheel | **PASS** |
| clean wheel install black-box | **PASS** (PG-01/03/04) |
| standalone | **PASS** |
| Tag v0.1.1 | **NOT CREATED** |

## Remaining
- P0: 0
- P1: 0 (pending 3rd audit confirmation)
- macOS: NOT VERIFIED
- CI: run after push
