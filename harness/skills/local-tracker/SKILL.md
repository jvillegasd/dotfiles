---
name: local-tracker
description: What a tracker operation means when the tracker is committed markdown files rather than a service.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Local Tracker

The workflow commands speak in tracker operations: publish a spec, create a ticket, read a ticket, apply a mapped label, resolve a closing reference, compute the ready frontier. Against GitHub each is an API call. Against `"tracker": "local-markdown"` each is an edit to a committed file, which means each also needs a commit, a branch, and a push, and nothing else in the harness says where those go.

Load this whenever `docs/agents/harness.json` sets `"tracker": "local-markdown"`. It replaces nothing in a command's steps; it says only what that command's tracker vocabulary resolves to.

Local markdown is a tracker, not the absence of one. Work under it is tracker-bound: `/ship`, `/land`, and `/squash-land` run their ticket transitions rather than skipping them as trackerless.

## Layout

One directory per feature under `spec_home`, committed with the code:

```
<spec_home>/<feature-slug>/spec.md
<spec_home>/<feature-slug>/issues/<NN>-<slug>.md
```

`<feature-slug>` is the spec title reduced to a branch-style slug: lowercase, non-alphanumeric runs collapsed to a single hyphen, trimmed. `/spec` fixes it at publication and every later command reuses that directory name rather than re-deriving it. `<NN>` numbers tickets from `01` in dependency order.

## State

Two lines precede the `## Type` heading in every implementation-ready ticket, and a `Status:` line precedes the first heading of `spec.md`:

```
Status: ready-for-agent
Blocked by: 01, 03
```

`Status:` carries one mapped label value from `harness.json` or the literal `done`. `done` is terminal and means the ticket's pull request merged; it is what GitHub mode gets from closing an issue, and without it nothing ever leaves the frontier. `Blocked by:` names ticket numbers in the same feature directory, or `none`. Edges never cross feature directories; a dependency on another feature is recorded in prose, not as an edge this scan reads.

`spec.md` is the parent. It carries mapped `in_progress` from publication and goes `done` only once every file in its `issues/` directory is `done`. A ticket still carrying no `Status:` line blocks parent closure and is reported as blocking it, the same way GitHub mode refuses to close a parent whose child lacks merge evidence.

A planning-only ticket, one lacking `Acceptance criteria` or `Test seams and checks`, carries no `Status:` line at all. That absence keeps it out of the frontier, but not out of the parent's closure test, which reports it as blocking closure until it is promoted. This matches the GitHub branch, which leaves such a ticket unlabelled and still refuses to close a parent whose child lacks merge evidence. `/create-ticket` promotes it in place once its contract fields are filled, and that promotion is what writes its first `Status:` line.

## Identity

The ticket id is `<feature-slug>-<NN>`, because `<NN>` alone repeats across features. That id is what a branch name's `<tracker-id>` uses. Nothing parses the id back out of a branch name, so the hyphens inside it cost nothing.

An id resolves to exactly one file, `<spec_home>/<feature-slug>/issues/<NN>-*.md`. That is how `/triage` reads a ticket it was given by id and how `/proto` names a branch from one.

A ticket's closing reference is its repository-relative path, named under a `Closes` line in the pull request body as prose. Never write `Closes #<NN>`, which resolves against GitHub issue numbers unrelated to this ticket. Because no API links the two, `/land` resolves a ticket to its pull request by searching pull request bodies for the ticket path, and resolves a pull request to its ticket by reading that same line.

## Reading

Comments append under a `## Comments` heading, oldest first. The policy's rule for reading a ticket applies unchanged: read the whole thread, and the newest word wins.

Duplicate detection has no issue listing to run. Grep `<spec_home>` for the spec's key terms instead, and surface every hit.

## Writing state

A tracker is useful because everyone sees the same state. A file only has that property once it is on the default branch, and `/ship` builds its worktree from `origin/<default>`, so a ticket that lives only on a feature branch is invisible to the next run and absent from the tree that has to edit it.

So every operation below is a commit on the default branch, fetched and fast-forwarded first, then pushed. These are bookkeeping commits, never implementation, which is the committed-files tracker exception the policy's default-branch rule names. The list below is what that exception covers, and it is the authority on its own extent; a tracker write that is not one of these bullets is not authorized.

Never reach the default branch by checking it out. A command that has created a worktree is standing on the feature branch, where `git checkout <default>` exits 128. Resolve the default branch's own worktree with `git worktree list`, take the entry whose branch is `<default>`, and run every tracker edit, commit, and push with `git -C <that path>`.

Where the default branch is protected, stop and escalate, as the policy's default-branch rule requires.

- **`/spec` publishes.** Write `spec.md` with `Status:` set to mapped `in_progress`. Commit as `docs(tracker): publish <feature-slug>`.
- **`/create-ticket` publishes.** Write every ticket file with its `Status:` and `Blocked by:` lines already correct: mapped `blocked` while blockers remain, otherwise mapped `ready_for_agent`. Commit as `docs(tracker): slice <feature-slug>`. This has to land before any `/ship` run, which is the whole reason publication is not deferred to a branch.
- **`/create-ticket` promotes.** When a planning-only ticket returns with its contract fields filled, write its first `Status:` line in place, mapped `blocked` or `ready_for_agent` by its edges. Commit as `chore(tracker): promote <feature-slug>-<NN>`. The file keeps its number, so every edge already pointing at it stays valid.
- **`/ship` claims, at its worktree step.** Re-read the ticket on freshly fetched `origin/<default>` first and abort the run if its `Status:` is no longer mapped `ready_for_agent`, because another run claimed it between the frontier scan and here. Otherwise set it to mapped `in_progress` and commit as `chore(tracker): claim <feature-slug>-<NN>`. On the default branch this is what makes the claim visible to that other run at all.
- **`/ship` finishes, when it marks the pull request ready, and `/address-review` when it keeps it there.** Set the ticket to mapped `ready_for_human` and commit as `chore(tracker): hand off <feature-slug>-<NN>`. Where it already carries that value there is nothing to write and nothing to commit. This lands on the default branch, so it adds no commit to the pull request and re-triggers none of its checks; rung 5 stays green.
- **Anyone releases an abandoned claim.** A ticket left at mapped `in_progress` by a run that died is off the frontier with no other way back. Where its branch has no open pull request, set it to mapped `ready_for_agent` and commit as `chore(tracker): release <feature-slug>-<NN>`. Never release one whose pull request is open; that run is still live.
- **`/land` and `/squash-land` retire.** After the merge, set the ticket to `done`, set every dependent whose blockers are now all `done` to mapped `ready_for_agent`, and set `spec.md` to `done` only if every file in `issues/` now carries `Status: done`, reporting any ticket still without a `Status:` line as what blocks that closure. Commit as `chore(tracker): close <feature-slug>-<NN>`. Do this only after the local default branch has been fast-forwarded past the merge, and before the worktree is retired; committing on a default branch still behind the merge gets the push rejected as non-fast-forward.

Because every one of these is a separate commit on the default branch, none of them appears in a pull request's diff. The review passes and the conformance pass therefore see no bookkeeping and need no path exclusion; a pull request that genuinely contracts to edit a spec or ticket file is reviewed like any other.

## Frontier

Scan every `<spec_home>/*/issues/*.md` on the default branch, not one feature directory, since `/land` and `/squash-land` report the frontier for the repository. A ticket is ready when it carries mapped `ready_for_agent` and every number in its `Blocked by:` line is `done`. Order by feature directory, then by `<NN>`.

There is no automation behind any of this. The `Status:` and `Blocked by:` lines are the whole lifecycle state, they live in the repository, and no issue event exists for a workflow to react to, which is why local mode installs no `.github/` workflow and no reconcile script.
