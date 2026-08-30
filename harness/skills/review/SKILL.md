---
name: review
description: Review a diff on the isolated Standards and Spec axes, by explicit invocation or from ship and address-review only.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Review

This is the only entry point to the locked `code-review` body. That body
carries auto-trigger phrasing and, being hash-locked, cannot be guarded in
Claude Code or OpenCode without drift, so it is not installed under its own
name. This wrapper carries the guards for all three clients.

Enter only by explicit human invocation, or from `ship` and `address-review`.
Never route here from plain language, and never ask for review consent on
another workflow's behalf.

Load `harness/skills/code-review/SKILL.md` and follow it, with two
corrections:

1. Keep the Standards and Spec axes isolated, parallel where the client
   supports it and sequential otherwise. Neither axis sees the other's
   findings.
2. Where it names `/setup-matt-pocock-skills` for a missing tracker, use
   `setup-harness` instead. `docs/agents/harness.json` and
   `docs/agents/issue-tracker.md` are what satisfy that prerequisite.

Resolve findings in the working tree. Never post them to the forge.

Agent-initiated review runs `adversarial-review` first: blind reviewers holding
neither the contract nor the rationale. This is the second axis over that same
diff, not a re-run of it.

## Nested skills

- `code-review` as the locked body this wrapper loads
