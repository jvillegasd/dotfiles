---
name: ship
description: Deliver one eligible ticket as a green, reviewed, ready-for-human draft pull request.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Ship

Require clean credentials and a contract. The contract is either a published
ticket with its full approved detail, or, for a change too small to justify
`spec` and `tickets`, a plain sentence or an existing issue.

In the lightweight mode the branch slug derives from the sentence, and label
transitions are skipped when `docs/agents/harness.json` or the mapped labels
are absent. Everything else below is unchanged. Escalate to `spec` only if the
change turns out to touch a surface the sentence did not name.

With a ticket, escalate before changing code if any blocker is not closed by a
merged pull request.

## Worktree and claim

1. Fetch the remote default branch and derive `<type>/<id>-<short-slug>` from
   the contract.
2. Inside Orca, use the runtime-provided Orca CLI guide and create an Orca
   worktree from the updated remote default branch. Never guess Orca commands.
3. Otherwise run Worktrunk non-interactively:
   `wt switch --create <branch> --base origin/<default> --no-cd --format=json --yes`,
   then work only in the returned path.
4. Change the ticket from mapped `ready_for_agent` to mapped `in_progress`.

## Delivery loop

1. Treat the contract's test seams as pre-agreed. Use `tdd` one red/green
   vertical slice at a time and drive the oracle ladder in the policy to green,
   preferring the narrowest variant of each rung.
2. Make the fewest coherent Conventional Commits; every commit stays green.
3. Review the diff before pushing. Run `adversarial-review` first, and triage
   every finding. Then run `review` against the remote-default merge base
   and the contract, keeping Standards and Spec isolated, parallel where
   supported and sequential otherwise. Repair all findings and repeat until
   every axis passes. `review` is the second axis here, not a re-run:
   the blind round already saw the diff without the plan.
4. Push, then create or update a draft pull request with a Conventional Commit
   title and a closing reference to the ticket. The body states what changed,
   why, and the checks run, plus three sections:
   - `Assumptions`: each decision made without asking, its rejected
     alternative, and the one fact that would flip it.
   - `Refuted evidence`: any claim the evidence contradicted and what changed
     as a result. Omit when no evidence was gathered.
   - `Rejected review findings`: each review finding not fixed, with its
     reason. Omit when there are none.
5. Watch required remote checks. Repair owned failures, rerun local rungs,
   commit, push, and review again. Apply the escalation contract's do-not-
   escalate list before counting an attempt, and stop on any rabbit-hole trip.
6. When required checks and every review axis are green, mark the pull request
   ready and change the ticket from mapped `in_progress` to mapped
   `ready_for_human`.

Return the pull request, checks, review result, and retained worktree path.
Never merge the pull request or remove the worktree.

## Nested skills

- `tdd`
- `evidence` when a load-bearing runtime claim decides the approach
- `codebase-design` when an agreed seam needs implementation vocabulary
- `diagnosing-bugs` for failures that do not have an obvious local cause
- `adversarial-review`
- `review`
- `resolving-merge-conflicts` only when the ticket worktree is conflicted
