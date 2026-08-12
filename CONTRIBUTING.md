# Contributing to PromptGraph

Thanks for considering contributing! This is part of the HERMES OSS ecosystem. By participating you agree to the ecosystem principles: **USEFUL ALONE + BETTER TOGETHER**, security by default, auditability, and evidence over confidence.

## Before you start

- **SEARCH before you create** — check if the feature already exists or belongs in a sibling project (AgentGear, SkillGuard, AgentBench, ProjectKaizen). PromptGraph's responsibility is **context preparation only**; we do not duplicate routing, security validation, measurement, or improvement.
- **EXTEND before you duplicate** — improve existing modules instead of adding overlapping ones.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running quality checks

```bash
pytest                      # run tests
ruff check src/ tests/      # lint
```

## Commit conventions

Use small, focused commits with conventional prefixes:

- `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `perf:`, `security:`, `chore:`

Never commit secrets. Run `git diff` + `ruff` + `pytest` before committing.

## Standards

- **No telemetry.** The package must never phone home or collect data.
- **Standalone by default.** Optional sibling integration must degrade gracefully.
- **Evidence > confidence.** Do not claim performance or correctness without tests.
- Aim for green: `pytest` + `ruff check` must pass before merge.