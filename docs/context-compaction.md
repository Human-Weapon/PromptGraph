# Context compaction contract

PromptGraph does **not** delete provider chat history.

It can tell a host:

> The declared memory candidates and checkpoint were persisted and verified.
> It is `SAFE_TO_COMPACT_DECLARED_CONTEXT`.

The host may then replace old conversation messages with the generated
context package **if that host supports it**.

PromptGraph will never report `CHAT_HISTORY_DELETED`.

## Required sequence

```
EXTRACT → CLASSIFY → VALIDATE → PERSIST → ATOMIC WRITE → READ BACK
→ VERIFY SCHEMA → VERIFY CONTENT HASH → UPDATE INDEX → UPDATE GRAPH
→ VERIFY RETRIEVABILITY → BUILD CHECKPOINT → BUILD CONTEXT PACK
→ COMPACTION READINESS → host MAY discard old context
```

If any persistence, readback, index, retrieval, checkpoint, or pack step
fails: `safe_to_compact = false`.

Never discard first and save later.

## `safe_to_compact` means

All **declared** memory candidates and checkpoint data were persisted and
verified.

It does **not** mean:

- nothing important in the original conversation was omitted
- the chat history was deleted
- semantic extraction completeness was independently proven

The caller must attest `extraction_complete=true` before PromptGraph will
return `safe_to_compact=true`.

## Host integration

```python
from promptgraph.core import PromptGraph
from promptgraph.memory.session import checkpoint_candidate_from_kwargs

pg = PromptGraph(project_root=".")
pg.record_memory({"type": "failure", "title": "...", "scope": "shareable"})
pg.checkpoint_session(goal="Hand off the task")
manifest = pg.plan_compaction(
    session_id="session-a",
    candidates=[],
    checkpoint=checkpoint_candidate_from_kwargs(goal="compact after persist"),
    task="Continue the Windows containment fix",
    extraction_complete=True,
)
if manifest.safe_to_compact:
    pack = pg.build_context_pack("Continue the Windows containment fix")
    # Host may now replace old messages with pack.markdown
```

`host_chat_deletion` is always `NOT_PERFORMED` unless an external host
records that it did the deletion itself. PromptGraph never does.
