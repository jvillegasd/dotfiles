---
name: workflow-checkpoint
description: The one branch-scoped Engram checkpoint protocol: topic key format, record schema, recovery validation, and terminal states, wired into the delivery commands at their return boundaries.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Workflow Checkpoint

A workflow that spans sessions needs continuity that survives a context reset. Engram already stores persistent project memory; this skill fixes what a checkpoint is, where it lives, and when it may be trusted, so the delivery commands share one schema instead of each carrying its own.

This skill owns the protocol. It does not own the boundaries: the delivery commands save and read back at their existing return points, and wiring them to this skill is issue #77, where they refer here by name rather than restating the schema.

## Protocol

This block is the canonical definition. The prose below explains it; a change to a rule belongs in this block, and anything implementing the protocol reads it from here.

```json
{
  "topic_key": "checkpoint/<branch>",
  "states": ["active", "completed", "abandoned", "cancelled"],
  "active_state": "active",
  "terminal_states": ["completed", "abandoned", "cancelled"],
  "fields": {
    "state": "string",
    "branch_tip": "string",
    "contract": "array",
    "checks": "array",
    "rationale": "string",
    "next_action": "string"
  },
  "require_non_empty": ["contract", "next_action"],
  "stale_invalidates": ["checks", "next_action"]
}
```

## Topic key

Every active implementation branch has exactly one checkpoint, stored under the `topic_key` above with `scope: project`, so a later session upserts the same record rather than appending a second one. The branch, not the ticket, scopes it: the branch is what a worktree carries across sessions, and two tickets on one branch share one checkpoint. A branch that does not exist yet, a published spec, or an unclaimed ticket has no checkpoint.

## Record

The checkpoint carries exactly the canonical `fields`, each with the shape the canonical block gives it:

| Field | Holds |
| --- | --- |
| `state` | One of the canonical `states`. |
| `branch_tip` | The git commit sha of the branch head at save time. |
| `contract` | Durable references, never copied text: a ticket URL or path, a pull request URL, or a finalized prototype ledger path. `require_non_empty`. |
| `checks` | Resolved ladder results for this tip. Valid only while the tip matches. |
| `rationale` | The narrow exception for a decision that exists nowhere durable yet. Keep the key; set it empty when the contract already records the rationale. |
| `next_action` | One step, not a plan. `require_non_empty`. |

Save the record for the branch tip it describes, and read it back before trusting it.

## Recovery

Continuation retrieves the branch checkpoint explicitly. Recent memory context is not a substitute, because it is not scoped and may belong to another branch.

1. Derive the topic key from the current branch and retrieve it.
2. Reject the record, reusing nothing, when any of these holds:
   - `state` is in `terminal_states`, which is auditable but excluded from ordinary continuation.
   - `state` is not a canonical state at all. The canonical set is exactly `active_state` plus `terminal_states`.
   - A field is missing or its value does not match its canonical shape.
   - A `require_non_empty` field is empty.
   - No `contract` reference resolves against current Git, tracker, or pull request state. A reference that does not resolve is dropped; when none survives, the record cannot drive continuation.
3. When the record survives validation, drop the `stale_invalidates` fields if `branch_tip` differs from the current head, and re-derive them from the surviving contract. The contract references and the rationale survive a moved tip.
4. Reuse only what validated. When a requirement the work needs is missing from the validated record and the contract, ask about it rather than inferring it.
5. After saving, retrieve the topic key again and confirm the record matches what was written. A save with no read-back is unverified.

## Terminal states

`/land` finalizes a checkpoint as `completed` after the pull request merges. `/abandon` finalizes it as `abandoned` (a discarded attempt) or `cancelled` (scope explicitly cancelled). All three are terminal: they remain auditable, and ordinary continuation ignores them. New work after a terminal checkpoint gets a new ticket, a new branch, and a new topic key rather than reopening the finished record.

## Constraints

- No `.agent` directory, event log, or second continuity store. Engram is the only store.
- Do not duplicate a ticket, pull request, or prototype contract into the checkpoint; reference it.
- Do not create a checkpoint for a published spec or an unclaimed ticket.
