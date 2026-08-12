# Changelog

All notable changes to PromptGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] — 2026-08-12 (remediation candidate — not tagged)

### Status
Remediation round 2 against adversarial audit of commit `9f40355`.
No tag until third independent audit passes.

### P1 — Release blockers

#### PG-01 Strict token budget
- Successful packages **must** satisfy `total_tokens <= token_budget`.
- Mandatory content (title, requirements, decisions, contradictions, headings)
  that exceeds budget raises `BudgetExceededError`.
- Optional context nodes are dropped greedily until the final rendered prompt fits.
- Never returns `READY` above budget.
- Single authoritative count of the final rendered prompt text.

#### PG-03 Process-level concurrent ledger safety
- Cross-platform exclusive file lock (`msvcrt` / `fcntl`).
- Unique temp files via `tempfile.mkstemp` (no shared `decisions.json.tmp`).
- Re-read after lock, merge, atomic replace.
- Duplicate IDs rejected under lock.
- Regression: two real processes, barrier-synced, 15 iterations.

#### PG-04 Path containment WIRED
- `DecisionLedger` and `TechnicalMemory` accept `trusted_root`.
- Default PromptGraph sets `trusted_root=cwd` for `.agentops` paths.
- Real Windows junction + POSIX symlink tests reject escape writes.
- `path_security` is on the write path (not dead code).

### P2

#### PG-05 Selection contract
- Single combined score (relevance dominates; priority is mild tie-breaker).
- `rank()` and `select()` share the same order.
- Dependency closure is atomic (seed+deps or exclude seed).

#### PG-07 Contradiction semantics
- Intra-requirement detection (e.g. public and private in one sentence).
- Confidence: `strong` / `heuristic`.
- **Not** hardcoding public+authentication as contradiction.
- Heuristic pairs require minimal content overlap to reduce false positives.

#### PG-11 Bounded scaling
- Polarity-group candidate filtering (ALLOW vs DENY, etc.).
- `max_pair_checks` bound with `analysis_truncated` signal.
- Deterministic pair-check counts preferred over fragile timings.

### P3

#### PG-13 Dead parameters
- `min_length` enforced in `RequirementExtractor`.
- `system_prompt` stored in package metadata (observable).

#### PG-14 Test quality
- Removed tautological `tokens <= budget OR budget_exceeded`.
- Real process concurrency tests.
- Real junction/symlink containment tests.
- `tests/adversarial/` suite.

### Tests
- **113 passed, 1 skipped** (POSIX symlink skip on Windows).

### Known Limitations
1. Rule-based extraction (not LLM).
2. Heuristic token estimation (chars÷4).
3. Lexical contradiction detection (not full semantic).
4. macOS CI NOT VERIFIED.

## [0.1.0] — 2026-08-11

First functional release. Tag `v0.1.0` remains immutable baseline.
