# Changelog

All notable changes to PromptGraph are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-11

### Status
**Released** — first functional version. Standalone, tested, documented.

### Added
- `promptgraph` package with full context-preparation pipeline.
- Requirement extraction from messy explanations (rule-based, deterministic).
- Prompt linting (ambiguity, vagueness, contradictions, length, overclaims).
- Question budgeting — ask only the necessary clarifying questions.
- Context graph (DAG) with dependency-aware traversal, cycle detection,
  topological ordering, and transitive closure.
- Token budgeting with priority-aware greedy selection.
- Ranking-based context selection with dependency promotion.
- Decision ledger (persistent JSON, atomic writes).
- Persistent technical memory with optional ledger integration.
- Context package generation and markdown rendering.
- Contradiction detection (bidirectional, lexical pattern pairs).
- Missing-requirement detection across 8 dimensions.
- `argparse` CLI: `prepare`, `lint`, `questions`, `decisions`, `status`.
- Optional sibling integration via `importlib.find_spec` (graceful degradation).
- `__main__.py` for `python -m promptgraph` invocation.

### Fixed
- **Classification precedence**: SECURITY, CONSTRAINT, NON_FUNCTIONAL, and
  BUSINESS patterns now evaluated before generic FUNCTIONAL. Previously
  "must encrypt" classified as FUNCTIONAL because "must" matched first.
- **Decision.rationale** changed from required to optional (default `""`).
- **Contradiction detection** now checks both directions (A↔B), not just one.
- **Pattern coverage**: added `auth\w*` (matches "authentication"),
  `performant`, `respond\w*`, `response time`, `limits?`, `caps?` plurals.
- Added missing `__main__.py` for `python -m promptgraph` support.

### Tests
- **49 tests passing** (0 failed, 0 skipped, 0 xfail).
- Coverage: 83.8% (threshold: 80%).
- 7 regression tests added for classification precedence bugs.

### Security
- No telemetry. No data collection. No network calls.
- Standalone by default; optional integrations never required.
- No third-party runtime dependencies (stdlib only).

### Known Limitations (accepted for v0.1.0)
1. **Requirement extraction is rule-based** (regex heuristics, not LLM).
   Phrases like "need a login" may classify as UNKNOWN because "need a"
   (vague) ≠ "need to" (imperative). Conservative by design.
2. **Token estimation is heuristic** (chars ÷ 4), not a real tokenizer.
3. **Contradiction detection is lexical** (pattern matching, not semantic).
   Cannot detect paraphrased or conceptual contradictions.

These limitations are accepted for v0.1.0 and may be addressed in future versions.
