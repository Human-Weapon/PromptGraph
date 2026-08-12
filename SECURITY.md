# Security Policy for PromptGraph

## Reporting a vulnerability

If you discover a security issue, **please do not open a public issue**. Email the maintainers instead (address TBD once the repo is published) with:

- A description of the issue
- Steps to reproduce
- Affected versions
- Any suggested fix

We will acknowledge receipt within 48 hours and work toward a coordinated disclosure.

## Scope

PromptGraph is a **context preparation** library and CLI. Its security-sensitive surface is:

- **Local file I/O**: decision ledgers, technical memory, context packages are written under your configured paths (default `.agentops/`).
- **No network calls**: PromptGraph never sends data anywhere.
- **No arbitrary code execution** from untrusted content.

## What PromptGraph deliberately does NOT do

PromptGraph does **not** validate the security of skills, plugins, gears, or automations. That responsibility belongs to **SkillGuard**. Do not treat PromptGraph as a sandbox.

## Standalone guarantee

PromptGraph must **never** require a sibling package to function. If a mandatory dependency or hidden integration is ever added, that is a security regression. Optional sibling imports must fail silently via `importlib.find_spec`.

## Reporting process (priority)

We follow the ecosystem priority rubric:

- **P0** — security / data loss / critical bugs: fix immediately.
- **P1** — broken functionality: next release.
- **P2+** — scheduled normally.