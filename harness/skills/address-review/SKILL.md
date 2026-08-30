---
name: address-review
description: Resolve review or CI feedback on an existing harness pull request in its retained worktree.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Address Review

Require an existing pull request created by `ship`.

1. Locate and reuse the pull request's existing Orca worktree when running
   inside Orca; otherwise read its `headRefName` with `gh pr view`, find that
   exact branch in `wt list --format=json`, and switch to it with
   `wt switch <branch> --no-cd --format=json --yes`. Escalate if the retained
   worktree is missing. Do not use the `pr:<number>` shortcut here, because
   Worktrunk creates a worktree when none exists.
2. Fetch every unresolved review thread and failing required check. Group by
   root cause and distinguish owned failures from unchanged external failures.
3. Add or adjust a behavior-level test first when feedback exposes a defect.
   Make the smallest fix, drive the oracle ladder in the policy to green, and
   resolve each thread with evidence.
4. Review the new diff the same way `ship` does: `adversarial-review` first,
   then the isolated Standards and Spec `review`. Repair all findings,
   make coherent Conventional Commits, and push.
5. Keep the pull request body's `Assumptions`, `Refuted evidence`, and
   `Rejected review findings` sections current with anything this pass decided
   or rejected.
6. Repeat until feedback, required CI, and every review axis are green. Apply
   the escalation contract's rabbit-hole detector unchanged.
7. Keep the pull request ready and the ticket mapped `ready_for_human`.

Never merge the pull request or remove its worktree.

## Nested skills

- `tdd`
- `diagnosing-bugs`
- `adversarial-review`
- `review`
- `resolving-merge-conflicts` only when already conflicted
