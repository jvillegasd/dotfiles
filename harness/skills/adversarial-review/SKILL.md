---
name: adversarial-review
description: Review a diff with a requirements-aware reviewer and a reviewer that sees only the diff and standards before pushing, then triage their findings.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Adversarial Review

Self-review that grades its own homework is worthless. This protocol withholds the implementer's rationale from the reviewer, so the diff has to defend itself.

## Invocation

Launch each reviewer as its named agent, in parallel, each with a fresh context: `reviewer-a` and `reviewer-b` in Claude Code and OpenCode. The installer generates them from `roles/reviewer-a.md` and `roles/reviewer-b.md` beside this skill, which own each reviewer's standing instructions, lenses, and output format.

Never pass the conversation, the implementation rationale, the plan behind the change, or a prior round. Anchoring a reviewer on why you thought the code was right is what makes the review useless.

When a named agent is unavailable, say so, launch a general agent with the matching role file's full text as its instructions, and report that this fallback enforces only the general agent's own permissions rather than the named agent's read-search restrictions. Never skip or silently omit a review because a named agent is missing.

The named agents' restrictions are best effort: each client enforces what its own controls support, and `clients/agents.py` reports the gaps.

Reviewer A holds the requirements and its standards but never that rationale; Reviewer B holds only the diff and its standards. Requirements are what let a reviewer check conformance; rationale only biases it.

Give Reviewer A the requirements, the diff snapshot path, and the exact absolute path of the project's own instruction file as its standards, never the implementation rationale. Nothing else.

Give Reviewer B only the diff snapshot path and the exact absolute paths of its review standards: the loaded `ponytail` body and the project's own instruction file. No requirements, no rationale, no ticket.

Standards are paths, never requirements or rationale, so supplying them leaves each reviewer's information boundary where it was. Count a standards file as read only when the reviewer's `loaded:` line names it: supplying a path, or a reviewer recalling what a standard says, is not evidence that it was read.

The project's own instruction file is `AGENTS.md` at the repository root, or `CLAUDE.md` there when no `AGENTS.md` exists, and is left out when neither does. Where the client is known to refuse a standards path, such as OpenCode for a file outside the project, paste that file's text into the first launch instead of its path. When a supplied standards file is missing from a reviewer's `loaded:` line, relaunch that reviewer once with that file's text pasted in; the relaunch replaces that reviewer's output for the same round and never counts toward the cap. A reviewer names a pasted standard as `inline:<absolute path>`. If a standard is still unread, disclose it under the pull request's `## Checks`, or in the requirements ledger under `/proto`.

This block is the one definition of what each reviewer is given. Anything it does not list is withheld, and every standards path is absolute.

```json
{
  "inputs": {
    "reviewer-a": ["requirements", "diff_snapshot_path"],
    "reviewer-b": ["diff_snapshot_path"]
  },
  "standards": {
    "reviewer-a": ["project_instruction_file"],
    "reviewer-b": ["ponytail", "project_instruction_file"]
  },
  "optional_standards": ["project_instruction_file"],
  "loaded_prefix": "loaded: ",
  "inline_prefix": "inline:"
}
```

Scale to blast radius:

- One reviewer when the diff is under roughly 50 changed lines, in a single file, and touches no data, auth, concurrency, migration, or public-contract surface. Use Reviewer A, so the single reviewer gets the requirements and not the rationale, the same explicit context rule the two-reviewer case uses.
- Two reviewers otherwise.
- Never three. A third mostly re-finds what the first two found.

## Diff delivery

Snapshot the complete diff once per round into a readable temporary file outside the worktree, and give each reviewer that path. A reviewer that answers `unreadable: <path>` gets the same snapshot inline instead. Never truncate the diff: when neither the file nor inline text can carry the complete snapshot, stop and escalate per the escalation contract.

Reviewers never edit files, and findings never reach the forge.

## Triage, by the implementer

This block is the one definition of triage. Every workflow that runs this review follows it, and the prose below explains it without adding rules.

```json
{
  "severities": {
    "bug": {"blocking": true, "actions": ["fix", "reject", "escalate"]},
    "risk": {"blocking": true, "actions": ["fix", "reject", "escalate"]},
    "nit": {"blocking": false, "actions": ["fix_when_smaller_than_argument", "drop"]},
    "q": {"blocking": false, "actions": ["answer", "reclassify_on_evidence"]}
  },
  "reclassify_to": ["bug", "risk"],
  "second_round": {"trigger": "fixed_blocking_finding", "scope": "repair_delta"},
  "conformance_repair": "counts_as_fixed_blocking_finding",
  "conformance_repair_after_cap": "recheck_and_disclose",
  "max_rounds": 2,
  "new_blocking_in_repaired_code": "escalate"
}
```

Only `bug:` and `risk:` block. For each, exactly one of:

- Fix it, with the smallest change that resolves it, per `ponytail`.
- Reject it, with a specific reason recorded in the pull request body under `## Rejected review findings`. A rejection you cannot justify in one line is a fix you are avoiding.
- Escalate it, per the escalation contract, when it is a product decision.

A `nit:` is fixed only when the fix is smaller than the argument, and otherwise dropped. A nit fix never starts another review round.

A `q:` is answered. It becomes a `bug:` or `risk:` only when evidence exposes a defect, and is then triaged as one. A question alone never blocks delivery.

## Loop cap

At most two rounds. A second round runs only after a fixed blocking finding, and it reviews the repair delta alone. A new blocking finding in round two, in code that round one's fixes touched, is a rabbit-hole trip: stop and escalate rather than starting round three.

A conformance repair counts as a fixed blocking finding for the second-round trigger. After round two, a conformance repair is rechecked by the conformance pass alone and disclosed under `## Checks`, never given a third round.
