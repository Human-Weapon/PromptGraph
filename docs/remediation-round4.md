# PromptGraph v0.1.1 — Remediation Round 4 Report

**Baseline:** `afddb48`
**No tag created.**

## Method
TDD: reproduce → failing test → fix root cause → pass → full suite → wheel BB → CI.

## P1-01 Per-call budget
- BEFORE: `prepare(budget=1)` with ctor 1000 returned `package.token_budget=1000`
- FIX: `ContextPackageBuilder.build(..., token_budget=effective)`; validate negative early
- AFTER/WHEEL: PASS

## P1-02 Path aliases + junction
- BEFORE: `./.agentops` did not auto-set `trusted_root` (startswith bug)
- FIX: `is_project_local_agentops()` part-based detection
- REAL JUNCTION: all aliases rejected; outside empty
- WHEEL: PASS

## P2-01 Lock TOCTOU
- BEFORE: post-construct junction left `.lock` outside before write reject
- FIX: pre-create containment checks on lock/parent/temp/dest; zero outside artifacts
- OUTSIDE ARTIFACTS: 0
- WHEEL: PASS

## P2-02 Schema validation
- BEFORE: partial memory notes loaded; ledger `[]` raised ValueError not quarantined consistently
- FIX: schema validators on load; quarantine via SafeJsonStore
- QUARANTINE: `.corrupt` file created
- WHEEL: PASS

## P2-03 Negative max_questions
- BEFORE: `max_questions=-1` accepted → slice bug risk
- FIX: `QuestionBudgetError` at QuestionBudgeter/PromptGraph boundary
- AFTER: PASS

## P3-01 Neutral persistence errors
- BEFORE: SafeJsonStore raised `DecisionError`
- FIX: `PersistenceError` / `StorageLockError` hierarchy
- PUBLIC ERROR TYPE: `StorageLockError` (PersistenceError)
- AFTER: PASS
