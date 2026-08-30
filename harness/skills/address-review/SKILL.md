---
name: address-review
description: Resolve review or CI feedback on an existing harness pull request in its retained worktree.
metadata:
  opencode/autoinvoke: "false"
---

# Address Review

Require `docs/agents/harness.json` and an existing PR created by `ship`.

1. Locate and reuse the PR's existing Orca worktree when running inside Orca;
   otherwise read the PR's `headRefName` with `gh pr view`, find that exact
   branch in `wt list --format=json`, and switch to the existing branch with
   `wt switch <branch> --no-cd --format=json --yes`. Escalate if the retained
   worktree is missing. Do not use the `pr:<number>` shortcut here because
   Worktrunk creates a worktree when none exists.
2. Fetch every unresolved review thread and failing required check. Group by
   root cause and distinguish owned failures from unchanged external failures.
3. Add or adjust a behavior-level test first when feedback exposes a defect.
   Make the smallest fix, run the relevant suite, and resolve each thread with
   evidence.
4. Run the same isolated Standards and Spec review used by `ship`, repair all
   findings, make coherent Conventional Commits, and push. The portable
   `docs/agents/harness.json` and `docs/agents/issue-tracker.md` satisfy locked
   `code-review`'s tracker prerequisite; never run or request the legacy setup
   skill.
5. Repeat until feedback, required CI, and both review axes are green. Apply the
   same three-unchanged-external-failure stop rule.
6. Keep the PR ready and the ticket mapped `ready_for_human`.

Never merge the PR or remove its worktree.

## Nested skills

- `tdd`
- `diagnosing-bugs`
- `code-review`
- `resolving-merge-conflicts` only when already conflicted
