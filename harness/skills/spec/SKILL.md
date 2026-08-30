---
name: spec
description: Synthesize the agreed design into the final contract and publish it after one approval.
metadata:
  opencode/autoinvoke: "false"
---

# Spec

Require `docs/agents/harness.json`; if missing, tell the user to invoke
`setup-harness`.
Together with `docs/agents/issue-tracker.md`, that configuration satisfies
`to-spec`'s tracker and label prerequisite. Never redirect to the legacy
`setup-matt-pocock-skills` workflow.

Load `to-spec` as the synthesis template, then repair its approval behavior:

1. Re-read the conversation, repository, domain docs, and relevant ADRs.
2. Produce one complete draft containing problem, solution, exhaustive user
   stories, implementation decisions, agreed behavior-level test seams and
   checks, out-of-scope items, and unresolved risks.
3. Include all seams in that draft. Do not request an earlier seam approval.
4. Ask once whether the entire final contract is approved for publication.
5. On approval, publish to the configured canonical spec home. For GitHub,
   create or update the parent issue and apply the mapped `in_progress` label.
   For a docs home, write the project-conventional spec path.

If the user changes the contract at the approval gate, revise and ask again.
That is the same gate, not a second approval. Do not create tickets.

## Nested skills

- `to-spec`
- `domain-modeling` only when existing domain vocabulary needs reconciliation
- `codebase-design` only when a test seam or module boundary is unresolved
