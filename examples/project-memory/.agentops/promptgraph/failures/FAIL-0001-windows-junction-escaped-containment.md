---
id: "FAIL-0001"
type: "failure"
status: "active"
area: "filesystem"
importance: "persistent"
disposition: "persistent"
scope: "shareable"
evidence_status: "verified"
root_cause_status: "confirmed"
tags: ["windows", "junction", "containment"]
related: ["REQ-0001", "DEC-0001"]
paths: ["src/promptgraph/path_security.py"]
approach_keys: ["filesystem:string-normalization-only", "filesystem:mocked-junction-only"]
supersedes: []
superseded_by: ""
summary: "Filesystem containment involving links/reparse points requires real filesystem objects."
unresolved: []
relations: [{"source": "FAIL-0001", "target": "DEC-0001", "relation": "relates_to"}, {"source": "FAIL-0001", "target": "REQ-0001", "relation": "relates_to"}]
---

# Windows junction escaped containment

## Summary

Filesystem containment involving links/reparse points requires real filesystem objects.

## Problem

A directory junction could resolve outside the permitted project root.

## Symptom

The suite passed even though the OS-level invariant had never been proved.

## Evidence

The original test used mocked paths and did not exercise a real reparse point.

## Root cause

The test reproduced implementation assumptions instead of real filesystem behavior.

## Failed attempts

### Attempt 1 - string-only path normalization

Result:
FAILED

Why:
Normalization does not resolve junction targets.

Approach key:
filesystem:string-normalization-only


### Attempt 2 - mocked junction test

Result:
INVALID EVIDENCE

Why:
The test could not falsify the defective implementation.

Approach key:
filesystem:mocked-junction-only


## Correct solution

Resolve the actual target and enforce containment on the resolved destination.

## Lesson

Filesystem containment involving links/reparse points requires real filesystem objects.

## Related

- [[REQ-0001]]
- [[DEC-0001]]
