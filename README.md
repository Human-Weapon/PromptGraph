# PromptGraph

**Transform human intent + project knowledge into precise, efficient context for AI agents.**

PromptGraph is the **context preparation** tool of the HERMES OSS ecosystem. It takes a messy, unstructured explanation of a task, breaks it into structured requirements, detects gaps and contradictions, asks *only* the necessary clarifying questions, consults prior decisions, and assembles a token-budgeted context package that an agent can consume directly.

> **It decides WHAT CONTEXT to deliver. It does not decide how a task should be executed** — that belongs to AgentGear.

---

## What problem it solves

Agents waste tokens and produce worse results when they're given redundant, vague, or incomplete context. PromptGraph applies *context engineering*: it turns scattered intent into a precise, minimal, self-consistent context package.

## What it does NOT try to solve

- ❌ **Model routing / execution strategy** → AgentGear
- ❌ **Security validation of skills/plugins** → SkillGuard
- ❌ **Objective measurement / benchmarks** → AgentBench
- ❌ **Continuous improvement** → ProjectKaizen
- ❌ **Guaranteed "best" prompt** — linting is heuristic, not exhaustive

---

## Installation

```bash
# From this repo
pip install -e .
# Or from PyPI (once published)
pip install promptgraph
```

Requires **Python ≥ 3.10**. No required runtime dependencies beyond the standard library.

## Usage (CLI)

```bash
# Turn a messy explanation into a context package
promptgraph prepare --explanation "We need a login system. It must support OAuth and users should reset passwords."

# Lint a prompt file for ambiguity/vagueness/contradictions
promptgraph lint --file prompt.txt

# See what clarifying questions are necessary
promptgraph questions --explanation "It should somehow be fast eventually."

# Record / list prior decisions (persistent technical memory)
promptgraph decisions --title "DB choice" --decision "Use Postgres" --context "..." --rationale "..."
promptgraph decisions --list

# Show optional ecosystem integration status
promptgraph status
```

## Usage (Python API)

```python
from promptgraph.core import PromptGraph
from promptgraph.models import ContextNode

pg = PromptGraph()

# Build context corpus
pg.add_context_node(ContextNode(id="auth", title="Auth", content="OAuth2 flow with refresh tokens."))
pg.add_context_node(ContextNode(id="upload", title="Upload", content="S3 presigned upload flow."))
pg.add_dependency("upload", "auth")  # upload flow depends on auth context

# Full pipeline
result = pg.prepare(
    "We need a login system. It must support OAuth and users should reset passwords.",
    title="Auth task",
)
package = result["package"]
print(package.prompt)
print("Contradictions:", len(result["contradictions"]))
```

## Architecture

```
src/promptgraph/
├── cli.py                         # argparse CLI
├── core.py                        # PromptGraph orchestrator (pipeline)
├── models.py                      # Requirement, ContextNode, Decision, Question, ContextPackage
├── requirement_extraction.py      # messy text → structured requirements
├── prompt_lint.py                 # ambiguity / vagueness / contradiction linting
├── question_budget.py             # minimal necessary clarifying questions
├── context_graph.py               # DAG dependency graph over context
├── token_budget.py                # estimate + allocate token budget
├── decision_ledger.py             # persistent append-only decision log
├── technical_memory.py            # durable technical facts + notes
├── contradiction_detection.py     # pairwise requirement contradictions
├── missing_requirement_detection.py
├── context_selection.py           # rank + select relevant context
├── context_package.py             # assemble final prompt package
├── _sibling_utils.py              # optional ecosystem integration
└── exceptions.py
```

### Pipeline

```
User's messy explanation
  → extract requirements
  → detect contradictions + missing dimensions
  → budget the truly necessary questions
  → consult prior decisions / technical memory
  → select relevant context (ranked, token-budgeted)
  → build context package
```

## Security

- **No telemetry.** PromptGraph never phones home.
- **No data collection.** Everything stays local to your machine.
- **No code execution** of arbitrary content.
- Only reads/writes paths you configure (default under `.agentops/`).
- **Standalone by default.** All sibling integrations are optional and discovered at runtime.

PromptGraph **does not validate security of tools** — that is SkillGuard's job. PromptGraph only processes text and your own declared knowledge.

## Optional integrations (BETTER TOGETHER)

None are required. When present, PromptGraph can use them:

| Sibling | Optional benefit |
|---|---|
| `agentbench` | Use benchmark evidence to tune context selection |
| `agentgear` | Receive execution feedback to refine context |
| `projectkaizen` | Read improvement recommendations |

Because integration is via `importlib.find_spec`, a missing sibling **never** breaks the package. See `promptgraph/_sibling_utils.py`.

## Roadmap

- [x] Requirement extraction, linting, question budgeting, graph + selection, token budgeting
- [x] Decision ledger and persistent technical memory
- [x] Context package generation, CLI, tests
- [ ] LLM-backed extraction (optional, behind a flag)
- [ ] Integration adapters for AgentGear/AgentBench/ProjectKaizen

## License

MIT. See [LICENSE](LICENSE).