---
name: adversarial-review
description: Review a diff with blind reviewers before pushing, then triage their findings.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Adversarial Review

Self-review that grades its own homework is worthless. This protocol removes
the implementer's context from the reviewer so the diff has to defend itself.

## Invocation

Launch reviewers as read-only subagents, in parallel, each with a fresh
context. Never pass the conversation, the plan, your rationale, or a prior
round. Anchoring a reviewer on why you thought the code was right is what makes
the review useless.

Scale to blast radius:

- One reviewer when the diff is under roughly 50 changed lines, in a single
  file, and touches no data, auth, concurrency, migration, or public-contract
  surface. Use Reviewer B and hand it the requirements too: on a small diff a
  missed requirement is usually visible in the diff itself, while a bug is not.
- Two reviewers otherwise.
- Never three. A third mostly re-finds what the first two found.

## Reviewer A: does it do the job

Give it the diff and the requirements. Nothing else.

> Assume this diff fails to do what the requirements say. Find where.

Lenses: an unmet requirement; scope creep past what was asked; an edge case
handled wrongly; a missing failure path; an error swallowed silently; a
migration without a rollback; an auth or data-boundary change; a broken public
contract; a check that would still pass if the logic it covers were deleted.

## Reviewer B: is it wrong

Give it only the diff. No requirements, no context, no ticket.

> Assume this diff is wrong. Find the bug.

Lenses: callers of every touched symbol left unupdated, so grep them; sibling
code paths left broken because a fix landed at one call site only; dead code
and leftovers; `ponytail` violations, meaning a new abstraction with one user,
a dependency for a few lines, or config for a constant; anything whose
correctness depends on information not visible in the diff.

On a UI diff, add one more lens: a palette, token system, or state set the
contract never asked for is unrequested surface area.

On added or modified lines, add one more lens: a comment restating the line it sits on, or a docstring longer than what it documents.

## Reviewer output

One line per finding:

```
path:Lline: <severity>: <problem>. <fix>.
```

Severity is one of:

- `bug:` broken behavior that will cause an incident
- `risk:` works but fragile, meaning a race, a missing guard, or a swallowed
  error
- `nit:` naming, style, or micro-optimization; the implementer may ignore it
- `q:` a genuine question rather than a suggestion, and where an unsure
  reviewer belongs

Name the symbol in backticks and give the fix, not "consider refactoring". Drop
the throat-clearing: no hedging, no restating what the line does. A security
finding or an architectural disagreement is the exception and needs its
reasoning spelled out.

A reviewer that finds nothing must state what it checked and why the diff
survives. "Looks good" is not a review.

Reviewers never edit files, and findings never reach the forge.

## Triage, by the implementer

For each finding, exactly one of:

- Fix it, with the smallest change that resolves it, per `ponytail`.
- Reject it, with a specific reason recorded in the pull request body under
  `Rejected review findings`. A rejection you cannot justify in one line is a
  fix you are avoiding.
- Escalate it, per the escalation contract, when it is a product decision.

Fix a `nit:` only when the fix is smaller than the argument.

## Loop cap

At most two rounds; round two re-reviews only the delta from your fixes. A new
blocking finding in round two, in code that round one's fixes touched, is a
rabbit-hole trip: stop and escalate rather than starting round three.
