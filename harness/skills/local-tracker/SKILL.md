---
name: local-tracker
description: What a tracker operation means when the tracker is committed markdown files rather than a service.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Local Tracker

The workflow commands speak in tracker operations: publish a spec, create a ticket, read a ticket, apply a mapped label, resolve a closing reference, compute the ready frontier. Against GitHub each of those is an API call. Against `"tracker": "local-markdown"` each is an edit to a committed file, which means each also needs a commit and a push, and nothing else in the harness says where those go.

Load this whenever `docs/agents/harness.json` sets `"tracker": "local-markdown"`. It replaces nothing in a command's steps; it only says what that command's tracker vocabulary resolves to. Where a command's own instruction and this file disagree, the command wins on what happens and this file wins on how it is written down.

Local markdown is a tracker, not the absence of one. Work under it is tracker-bound: `/ship`, `/land`, and `/squash-land` run their ticket transitions rather than skipping them as trackerless.

## Layout

One directory per feature under `spec_home`, committed with the code:

```
<spec_home>/<feature-slug>/spec.md
<spec_home>/<feature-slug>/issues/<NN>-<slug>.md
```

`<feature-slug>` is the spec title reduced to a branch-style slug: lowercase, non-alphanumeric runs collapsed to a single hyphen, trimmed. `/spec` fixes it when it publishes, and every later command reuses that directory name rather than re-deriving it. `<NN>` numbers tickets from `01` in dependency order.

## State

Two lines precede the `## Type` heading in every ticket, and a `Status:` line precedes the first heading of `spec.md`:

```
Status: ready-for-agent
Blocked by: 01, 03
```

`Status:` carries one mapped label value from `harness.json` or the literal `done`. `done` is terminal and means the ticket's pull request merged; it is what GitHub mode gets from closing an issue, and without it nothing ever leaves the frontier. `Blocked by:` names ticket numbers in the same feature directory, or `none`. Edges never cross feature directories; a dependency on another feature is a blocker recorded in prose, not an edge this scan can read.

`spec.md` is the parent. It carries `Status: in-progress` from publication and goes `done` only once every ticket in its `issues/` directory is `done`.

A planning-only ticket, one lacking `Acceptance criteria` or `Test seams and checks`, carries no `Status:` line at all. That absence is what keeps it out of the frontier, and it matches the GitHub branch leaving such a ticket unlabelled.

## Identity

The ticket id is `<feature-slug>-<NN>`, because `<NN>` alone repeats across features. That id is what a branch name's `<tracker-id>` uses, so a branch reads `feat/checkout-retry-03-add-backoff`.

A ticket's closing reference is its repository-relative path. No keyword closes it: a pull request body names the path under a `Closes` line as prose, and `/land` is what actually writes `done`. Never write `Closes #<NN>`, which would resolve against GitHub issue numbers that have nothing to do with this ticket.

## Reading

A ticket is its body plus everything under its `## Comments` heading, appended oldest first. Read the whole file every time; the newest comment wins over the description, exactly as it does on a tracker.

Duplicate detection has no issue listing to run. Grep `<spec_home>` for the spec's key terms instead, and surface every hit.

## Writing state

Every transition below is a file edit, and an edit nobody commits is working-tree noise that leaves the frontier stale. Each has one place it belongs:

- **`/spec` publishes.** Write `spec.md` with `Status: in-progress` on the branch that carries the spec.
- **`/create-ticket` publishes.** Write each ticket file with its `Status:` and `Blocked by:` lines already correct: mapped `blocked` while blockers remain, otherwise mapped `ready_for_agent`.
- **`/ship` claims, at its worktree step.** Set the ticket to mapped `in_progress` and commit it alone as `chore(tracker): claim <feature-slug>-<NN>`, before the first implementation commit. Keeping it in its own commit is what lets the review passes and the conformance pass read the implementation diff without bookkeeping in it.
- **`/ship` finishes, when it marks the pull request ready.** Set the ticket to mapped `ready_for_human`, commit it the same way, and push. This is a push after the last implementation push, not a replacement for it.
- **`/land` and `/squash-land` retire.** After the merge, on the default branch, set the ticket to `done` and set its `spec.md` to `done` if every sibling ticket is now `done`. Commit as `chore(tracker): close <feature-slug>-<NN>` and push before retiring the worktree, because the worktree removal takes the tree those edits would otherwise sit in. This is the one bookkeeping commit the policy allows on an unprotected default branch.

Both review passes and the conformance pass ignore paths under `<spec_home>`. A bookkeeping commit is not implementation and has no acceptance criterion to conform to.

## Frontier

Scan every `<spec_home>/*/issues/*.md`, not one feature directory, since `/land` and `/squash-land` report the frontier for the repository. A ticket is ready when it carries mapped `ready_for_agent` and every number in its `Blocked by:` line is `done`. Order by feature directory, then by `<NN>`.

There is no automation behind any of this. The `Status:` and `Blocked by:` lines are the whole lifecycle state, they live in the working tree, and no issue event exists for a workflow to react to, which is why local mode installs no `.github/` workflow and no reconcile script.
