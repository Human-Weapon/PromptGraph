# PromptGraph v0.1.0 — Final Release Report

**Date:** 2026-08-11
**Status:** RELEASED
**Tag:** v0.1.0

---

## Summary

PromptGraph is the **context preparation** tool of the HERMES OSS ecosystem.
It transforms messy human explanations into structured, token-budgeted context
packages for AI agents. It decides WHAT CONTEXT to deliver — not how to execute.

## Verification Results

| Check | Result |
|-------|--------|
| pytest | **49 passed, 0 failed** |
| ruff | **All checks passed** |
| build (wheel) | **PASS** — `promptgraph-0.1.0-py3-none-any.whl` |
| import | **PASS** — `import promptgraph` works in clean venv |
| standalone | **PASS** — no siblings required, all integrations `False` |
| CLI | **PASS** — `status`, `prepare`, `lint`, `questions`, `decisions` |
| coverage | **83.8%** (threshold: 80%) |
| secrets scan | **CLEAN** — no secrets, keys, or credentials |
| debug scan | **CLEAN** — no breakpoints, pdb, FIXME, temp files |

## Bugs Found and Fixed During Stabilization

| # | Root Cause | Impact | Fix |
|---|-----------|--------|-----|
| 1 | `Decision.rationale` required positional arg | 2 tests crashed with `TypeError` | Made optional with default `""` |
| 2 | FUNCTIONAL pattern matched "must" before SECURITY | "must encrypt" → FUNCTIONAL (wrong) | Reordered: specific patterns first |
| 3 | `auth` pattern didn't match "authentication" | Security requirements misclassified | Changed to `auth\w*` |
| 4 | Missing "performant"/"respond"/"response time" | Non-functional requirements missed | Added to pattern |
| 5 | Singular-only "limit"/"cap" | Resource limits dimension not detected | Added plurals `limits?`/`caps?` |
| 6 | Contradiction detection unidirectional | "deny X" + "enable Y" not detected | Added bidirectional check |
| 7 | Missing `__main__.py` | `python -m promptgraph` failed | Created |

## Regression Tests Added

1. `test_classify_must_encrypt_is_security` — SECURITY precedence over FUNCTIONAL
2. `test_classify_must_authenticate_is_security` — `auth\w*` matching
3. `test_classify_must_respond_200ms_is_non_functional` — performance patterns
4. `test_classify_must_not_log_is_constraint` — CONSTRAINT vs FUNCTIONAL
5. `test_classify_generic_must_is_functional` — generic "must" still works
6. `test_ledger_rationale_optional` — Decision without rationale
7. `test_missing_detection_with_full_coverage` — all 8 dimensions covered

## Architecture

```
src/promptgraph/
├── __init__.py          # Public API + re-exports
├── __main__.py          # python -m promptgraph
├── cli.py               # argparse CLI
├── core.py              # PromptGraph orchestrator (full pipeline)
├── models.py            # Requirement, ContextNode, Decision, Question, ContextPackage
├── exceptions.py        # Exception hierarchy
├── requirement_extraction.py
├── prompt_lint.py
├── question_budget.py
├── context_graph.py     # DAG with cycle detection + topological sort
├── token_budget.py      # Priority-aware greedy selection
├── decision_ledger.py   # Persistent JSON (atomic writes)
├── technical_memory.py
├── contradiction_detection.py  # Bidirectional lexical patterns
├── missing_requirement_detection.py  # 8 dimensions
├── context_selection.py # Ranking + dependency promotion
├── context_package.py   # Assembly + markdown rendering
└── _sibling_utils.py    # Optional integration (importlib.find_spec)
```

## Known Limitations (Accepted for v0.1.0)

1. **Rule-based extraction** — regex heuristics, not LLM-backed.
2. **Heuristic token estimation** — chars ÷ 4, not a real tokenizer.
3. **Lexical contradiction detection** — pattern matching, not semantic.

## Dependencies

- **Runtime:** Python ≥ 3.10, stdlib only (zero third-party dependencies).
- **Dev:** pytest, pytest-cov, ruff, build.

## Ecosystem Compliance

- [x] **USEFUL ALONE** — works without any sibling
- [x] **BETTER TOGETHER** — detects siblings via `importlib.find_spec`
- [x] **No duplicate responsibilities** — context preparation only
- [x] **Elegant degradation** — missing siblings never break functionality
- [x] **Security by default** — no telemetry, no network, no code execution
- [x] **Auditability** — persistent decisions and memory
- [x] **Efficiency** — stdlib only, minimal footprint
