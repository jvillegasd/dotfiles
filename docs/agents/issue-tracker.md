# Issue tracker

This repository's tracker is GitHub Issues on https://github.com/jvillegasd/dotfiles. There is no second tracker and no external spec home: a published spec is an issue in this repository, and every ticket is an issue in this repository. The machine-readable form of what follows is `docs/agents/harness.json`; this file is the prose contract that locked third-party skills read.

## Access

All tracker reads and writes go through the `gh` CLI, authenticated as the repository owner. There is no REST or GraphQL client configured here beyond `gh`, and no tracker API token lives in this repository. Verify access with `gh auth status` before any tracker operation and escalate rather than authenticating interactively.

Read a source issue or spec with `gh issue view <number> --json number,title,body,state,labels,url`. Read its comment thread with `--comments` when the contract may have been amended after publication. Read a ticket's relationships with the sub-issue and dependency fields described below, never by parsing prose.

## Relationships

GitHub's native sub-issues and issue dependencies are the source of truth for parent and blocking relationships. A task list in an issue body, a checkbox, or a "blocks #12" line in prose is documentation, not data: never derive the frontier from it, and never write a relationship only into prose.

A spec issue is the parent. Each implementation-ready slice published by `/create-ticket` is a native sub-issue of that parent. A slice that cannot start until another slice merges records that as a native dependency, not as a label.

Parent closure follows child merge evidence. A parent closes only once every one of its sub-issues has merged, and `.github/workflows/agent-lifecycle.yml` is what applies that transition here. Never close a parent by hand while a child lacks merge evidence.

## Labels

The four lifecycle labels are `blocked`, `ready-for-agent`, `in-progress`, and `ready-for-human`. They are mapped in `docs/agents/harness.json` under the stable keys `blocked`, `ready_for_agent`, `in_progress`, and `ready_for_human`; read the mapping from that file rather than assuming the literal names.

Exactly one lifecycle label sits on a ticket at a time. GitHub's own default labels (`bug`, `enhancement`, `documentation`, and the rest) are orthogonal and are not part of the lifecycle.

## Automation

`.github/workflows/agent-lifecycle.yml` runs `.github/scripts/reconcile-agent-lifecycle.py` when an issue closes or reopens. It reconciles the frontier: it closes a parent once every child carries merge evidence, and it moves each newly unblocked sibling to the mapped `ready_for_agent`. It is active only once both files are on the default branch.

Where the automation has run, confirm its result rather than repeating its transitions. Where it has not, apply the transitions by hand and say which ones you applied.
