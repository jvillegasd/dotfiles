---
name: tickets
description: Publish implementation-ready vertical slices from an approved spec.
metadata:
  opencode/autoinvoke: "false"
---

# Tickets

Require `docs/agents/harness.json` and an approved source spec. Load
`to-tickets` for tracer-bullet and expand-contract rules, but skip its quiz and
approval step: the approved spec is the contract.

Each ticket must fit one fresh context and contain:

```markdown
## Type
<feat|fix|refactor|perf|test|docs|build|ci|chore>

## Source spec
<canonical reference>

## What to build
<one complete, demoable vertical slice>

## Acceptance criteria
- [ ] <observable behavior>

## Test seams and checks
- <agreed public seam and required check>

## Blocked by
- <native reference, or None>
```

Publish in dependency order. On GitHub, create every ticket as a native
sub-issue of the parent and create native `blocked-by` edges. Apply mapped
`blocked` when blockers remain; otherwise apply mapped `ready_for_agent`.
Remove both frontier labels from the parent while its children are active.

For another tracker, use its native relationships where available and record
textual edges otherwise. Automatic parent closure is GitHub-only.

Return the ticket DAG and current ready frontier. Do not ask for another
substantive approval.

## Nested skills

- `to-tickets`
