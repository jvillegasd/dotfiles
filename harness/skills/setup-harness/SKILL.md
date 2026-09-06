---
name: setup-harness
description: Configure a repository for the portable spec-to-PR workflow.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Setup Harness

Explore the repository before writing. Reuse existing domain and documentation conventions when they are unambiguous; ask only for choices that cannot be inferred safely. The tracker mode is the exception: present it and ask, because a remote reveals where the code is hosted and not where the user wants contracts kept.

Write `docs/agents/harness.json` with this stable shape:

```json
{
  "version": 1,
  "tracker": "github",
  "spec_home": "github-issues",
  "domain_layout": "single-context",
  "labels": {
    "blocked": "blocked",
    "ready_for_agent": "ready-for-agent",
    "in_progress": "in-progress",
    "ready_for_human": "ready-for-human"
  }
}
```

`tracker` and `spec_home` name the configured mode. The harness writes two. Present both by name and ask, always, including in a repository with no remote. A remote reveals where the code is hosted, never where the user wants contracts kept, so nothing about it settles this choice. Any other tracker follows the last section. `domain_layout` may use project-specific values. Wherever a command writes `<spec_home>`, it means this file's `spec_home` value.

Local markdown keeps the same shape, changing only the two mode values. `docs/specs` is the default to propose for `spec_home`; confirm it alongside the mode rather than writing it unasked, since a project with its own docs convention will want that path instead:

```json
{
  "version": 1,
  "tracker": "local-markdown",
  "spec_home": "docs/specs",
  "domain_layout": "single-context",
  "labels": {
    "blocked": "blocked",
    "ready_for_agent": "ready-for-agent",
    "in_progress": "in-progress",
    "ready_for_human": "ready-for-human"
  }
}
```

Keep the four label keys stable while allowing mapped values to change. Update an existing file in place instead of discarding user choices.

For GitHub:

1. Verify the remote and `gh auth status`; escalate if credentials or issue
   permissions are missing.
2. Create or update the four mapped labels with `gh label create --force`.
3. Write `docs/agents/issue-tracker.md` as the compatibility contract for
   locked Matt skills: identify GitHub, require the `gh` CLI, document how to
   read the source issue/spec, and name native sub-issues and dependencies as
   the relationship source of truth. Do not tell the user to run a second
   setup skill.
4. Copy `assets/agent-lifecycle.yml` to
   `.github/workflows/agent-lifecycle.yml` and
   `scripts/reconcile-agent-lifecycle.py` to
   `.github/scripts/reconcile-agent-lifecycle.py`.
5. Preserve unrelated workflows and configuration. State that lifecycle
   automation becomes active only after both copied files reach the default
   branch; include them in the normal human-reviewed change rather than
   pushing or merging them directly.

For local markdown:

Nothing creates labels in this mode, so the vocabulary the `Status:` line uses is the four mapped values plus the literal `done`.

1. Write `docs/agents/issue-tracker.md` as the compatibility contract for locked Matt skills. It has to stand alone, because those skills read it and have no reason to load a harness skill: identify local markdown, state that it needs no CLI and no network, give the root path, and reproduce the `local-tracker` skill's Layout, State, Identity, and Frontier sections so the file carries the directory layout, the `Status:` line, the `Blocked by:` edges, the ticket id form, and the frontier rule in full rather than by reference. That skill is the source of truth and this file is a restatement of it, so a rule changes there first and is regenerated here; otherwise every already-written copy goes silently stale. Point at it for the rest, starting with the mapping from a lifecycle transition to the commit that records it. Do not tell the user to run a second setup skill.
2. Copy no `.github/` workflow and no reconcile script, and state that this is deliberate rather than missing. The lifecycle state is committed lines in the working tree, so no issue event exists for a workflow to react to.
3. Preserve unrelated documentation and configuration.

For other trackers, record their native parent/dependency behavior in
`docs/agents/README.md`. Do not install GitHub automation, and do not promise
automatic parent closure.

Report every created or updated path. Do not authenticate interactively.
