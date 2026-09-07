# Issue tracker: GitHub

This repository keeps its contracts as GitHub issues on `jvillegasd/dotfiles`. A spec is an issue, its slices are that issue's native sub-issues, and the ordering between them is native issue dependencies. Nothing here lives in a file; the tracker is the service.

## Prerequisites

The `gh` CLI, authenticated with issue write permission (`gh auth status`). Every operation below is a `gh` call, so an unauthenticated session cannot read or write the tracker at all. There is no offline fallback in this mode.

## Reading the source issue or spec

Fetch the full body and the whole comment thread, in order, before acting on any ticket: `gh issue view <n> --comments`. A ticket is its description plus its comments, and the newest word wins. Comments here routinely add requirements, narrow scope, or overturn the description outright, so a body read on its own is an incomplete contract. When a comment contradicts the description, say which one you followed.

A spec issue is the parent. Its slices are its sub-issues, and each slice names the spec as its source.

## Relationships

Native GitHub relationships are the source of truth for this repository. Do not restate them as prose in issue bodies, and do not infer them from task lists: both are already available as API state, and a second copy is a second thing to keep in sync.

- **Parent and child**: native sub-issues. `gh api repos/jvillegasd/dotfiles/issues/<n> --jq .sub_issues_summary` reports a parent's children; the sub-issues endpoint adds and removes them. Both are enabled on this repository.
- **Ordering**: native issue dependencies. A slice declares what must finish first as a `blocked_by` edge, added with `gh api --method POST repos/jvillegasd/dotfiles/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-database-id>`. The `issue_id` is the blocker's numeric **database id** from `gh api repos/jvillegasd/dotfiles/issues/<n> --jq .id`, not its `#number` and not its `node_id`. Passing the number silently addresses the wrong issue or fails, so resolve the id first.
- **Reading the gate**: `issue_dependencies_summary.blocked_by` counts open blockers only, which is the live gate. `total_blocked_by` counts every edge including satisfied ones, so it never answers "can this start".

## Lifecycle labels

Four labels carry ticket state, and they exist on the remote already:

| Label | Meaning |
| --- | --- |
| `blocked` | Waiting on a dependency |
| `ready-for-agent` | Contract complete, ready to implement |
| `in-progress` | An agent is implementing it |
| `ready-for-human` | Green pull request awaiting human review |

`docs/agents/harness.json` maps these four keys to those values. Read the mapping from that file rather than hardcoding the strings, so a renamed label stays a one-line change.

An implementation-ready ticket carries `blocked` while any blocker is open and `ready-for-agent` once none is. A ticket that lacks acceptance criteria and test seams is planning-only and carries no lifecycle label at all, which is what keeps it out of the ready frontier until its contract is completed.

## The ready frontier

The tickets an agent may start: open, carrying `ready-for-agent`, with no open blocker. `gh issue list --label ready-for-agent --state open` lists the candidates, and `issue_dependencies_summary.blocked_by` on each confirms the gate.

## Automatic reconciliation

`.github/workflows/agent-lifecycle.yml` runs `.github/scripts/reconcile-agent-lifecycle.py` whenever an issue is closed or reopened. It walks the closed issue's dependents, moves each newly unblocked one from `blocked` to `ready-for-agent`, and closes a parent once every child is closed. Closing an issue is therefore how the frontier advances; nothing needs to relabel dependents by hand.

The workflow reacts to any issue in this repository, not only to harness tickets, so an issue that sits on a dependency edge will be labelled by it whether or not it was filed as a harness ticket.

## Publishing

Publishing a spec creates or updates the parent issue and applies mapped `in-progress`. Publishing slices creates each as a native sub-issue of that parent, in dependency order so that every edge references an issue that already exists, then wires the `blocked_by` edges in a second pass. A ticket's closing reference is the ordinary `Closes #<n>`, which resolves against this repository's issue numbers.
