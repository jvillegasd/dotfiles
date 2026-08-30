---
name: ship
description: Deliver one eligible ticket as a green, reviewed, ready-for-human draft pull request.
metadata:
  opencode/autoinvoke: "false"
---

# Ship

Require `docs/agents/harness.json`, one ticket, clean credentials, and the
ticket's full approved contract. Escalate before changing code if any blocker
is not closed by a merged pull request.

## Worktree and claim

1. Fetch the remote default branch and derive `<type>/<id>-<short-slug>` from
   the ticket.
2. Inside Orca, use the runtime-provided Orca CLI guide and create an Orca
   worktree from the updated remote default branch. Never guess Orca commands.
3. Otherwise run Worktrunk non-interactively:
   `wt switch --create <branch> --base origin/<default> --no-cd --format=json --yes`,
   then work only in the returned path.
4. Change the ticket from mapped `ready_for_agent` to mapped `in_progress`.

## Delivery loop

1. Treat the ticket's test seams as pre-agreed. Use `tdd` one red/green
   vertical slice at a time and run the repository's narrowest relevant checks.
2. Make the fewest coherent Conventional Commits; every commit stays green.
3. Run `code-review` against the remote-default merge base and the ticket.
   Treat `docs/agents/harness.json` plus `docs/agents/issue-tracker.md` created
   by `setup-harness` as satisfying its tracker prerequisite; never redirect
   the user to `setup-matt-pocock-skills`.
   Keep Standards and Spec isolated, parallel where supported and sequential
   otherwise. Repair all findings and repeat until both axes pass.
4. Push, then create or update a draft PR with a Conventional Commit title and
   a closing reference to the ticket.
5. Watch required remote checks. Repair owned failures, rerun local checks,
   commit, push, and review again. Stop after three consecutive unchanged
   external or flaky failures; credential, permission, destructive-scope, and
   contract problems escalate immediately.
6. When required checks and both review axes are green, mark the PR ready and
   change the ticket from mapped `in_progress` to mapped `ready_for_human`.

Return the PR, checks, review result, and retained worktree path. Never merge
the PR or remove the worktree.

## Nested skills

- `tdd`
- `codebase-design` when an agreed seam needs implementation vocabulary
- `diagnosing-bugs` for failures that do not have an obvious local cause
- `code-review`
- `resolving-merge-conflicts` only when the ticket worktree is conflicted
