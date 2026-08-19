# PromptGraph project memory

5 records.

- [[CP-0001]] Checkpoint: Fix Windows filesystem containment — Fix Windows filesystem containment
- [[DEC-0001]] Resolve real destinations before containment checks — String normalization is not sufficient proof of containment.
- [[FAIL-0001]] Windows junction escaped containment — Filesystem containment involving links/reparse points requires real filesystem objects.
- [[LESSON-0001]] OS-level invariants require real OS-level regression tests — Do not treat mocked junction tests as proof.
- [[REQ-0001]] Contain all memory writes — Every durable write must remain inside the configured project root.
