# Sample project memory

This folder is a tiny PromptGraph memory vault.

It records:

- one requirement (`REQ-0001`)
- one decision (`DEC-0001`)
- one failure with two failed attempts (`FAIL-0001`)
- one persistent lesson (`LESSON-0001`)
- one checkpoint (`CP-0001`)

## Resume without the original chat

```bash
promptgraph context build examples/project-memory \
    --task "Fix Windows filesystem containment" \
    --budget 2000
```

The package must mention the known failed approach
`string-only path normalization` so the next agent does not repeat it.

Open `.agentops/promptgraph/` in Obsidian if you want a graph view.
Obsidian is not required.
