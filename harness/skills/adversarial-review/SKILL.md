---
name: adversarial-review
description: Review a diff with a requirements-aware reviewer and a diff-only reviewer before pushing, then triage their findings.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Adversarial Review

Self-review that grades its own homework is worthless. This protocol withholds the implementer's rationale from the reviewer, so the diff has to defend itself.

## Invocation

Launch each reviewer as its named agent, in parallel, each with a fresh context: `reviewer-a` and `reviewer-b` in Claude Code and OpenCode, `reviewer_a` and `reviewer_b` in Codex. The installer generates them from `roles/reviewer-a.md` and `roles/reviewer-b.md` beside this skill, which own each reviewer's standing instructions, lenses, and output format.

Never pass the conversation, the implementation rationale, the plan behind the change, or a prior round. Anchoring a reviewer on why you thought the code was right is what makes the review useless.

When a named agent is unavailable, say so, launch a general agent with the matching role file's full text as its instructions, and report that this fallback enforces only the general agent's own permissions rather than the named agent's read-search restrictions. Never skip or silently omit a review because a named agent is missing.

In Codex, give that fallback the role text with its Access line replaced by `CODEX_ACCESS` from `clients/agents.py`, because shell is how Codex reads files.

The named agents' restrictions are best effort: each client enforces what its own controls support, and `clients/agents.py` reports the gaps.

Reviewer A holds the requirements but never that rationale; Reviewer B holds only the diff. Requirements are what let a reviewer check conformance; rationale only biases it.

Give Reviewer A the requirements and the diff, never the implementation rationale. Nothing else.

Give Reviewer B only the diff. No requirements, no rationale, no ticket.

Scale to blast radius:

- One reviewer when the diff is under roughly 50 changed lines, in a single file, and touches no data, auth, concurrency, migration, or public-contract surface. Use Reviewer A, so the single reviewer gets the requirements and not the rationale, the same explicit context rule the two-reviewer case uses.
- Two reviewers otherwise.
- Never three. A third mostly re-finds what the first two found.

## Diff delivery

Snapshot the complete diff once per round into a readable temporary file outside the worktree, and give each reviewer that path. A reviewer that answers `unreadable: <path>` gets the same snapshot inline instead. Never truncate the diff: when neither the file nor inline text can carry the complete snapshot, stop and escalate per the escalation contract.

Reviewers never edit files, and findings never reach the forge.

## Triage, by the implementer

For each finding, exactly one of:

- Fix it, with the smallest change that resolves it, per `ponytail`.
- Reject it, with a specific reason recorded in the pull request body under
  `## Rejected review findings`. A rejection you cannot justify in one line is a
  fix you are avoiding.
- Escalate it, per the escalation contract, when it is a product decision.

Fix a `nit:` only when the fix is smaller than the argument.

## Loop cap

At most two rounds; round two re-reviews only the delta from your fixes. A new
blocking finding in round two, in code that round one's fixes touched, is a
rabbit-hole trip: stop and escalate rather than starting round three.
