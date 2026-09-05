---
name: setup-harness
description: Configure a repository for the portable spec-to-PR workflow.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Setup Harness

Explore the repository before writing. Reuse existing tracker, domain, and
documentation conventions when they are unambiguous; ask only for choices that
cannot be inferred safely.

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

`tracker` and `spec_home` name the configured mode. The harness writes two. Present both by name and ask, because a GitHub remote never settles the choice on its own: a repository hosted there may still want its contracts in the tree. Only the absence of any remote infers local markdown. Any other tracker follows the last section. `domain_layout` may use project-specific values. Wherever a command writes `<spec_home>`, it means this file's `spec_home` value.

Local markdown keeps the same shape, changing only the two mode values:

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

Nothing creates labels in this mode, so the four mapped values are only the vocabulary the `Status:` line uses.

1. Write `docs/agents/issue-tracker.md` as the compatibility contract for locked Matt skills. Identify local markdown, state that it needs no CLI and no network, and document the layout and how state is read:
   - One directory per feature under `spec_home`, committed with the code: the spec at `<spec_home>/<feature-slug>/spec.md` and its slices at `<spec_home>/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` in dependency order, one ticket per file.
   - A `Status:` line near the top of every ticket and of `spec.md`, carrying one mapped label value or `done`. `done` is terminal and means the work merged; it is what GitHub mode gets from closing an issue. `spec.md` is the parent, and it goes `done` only once every ticket in its `issues/` directory is `done`.
   - A `Blocked by: NN, NN` line on every ticket, naming ticket numbers in the same feature directory, or `Blocked by: none`. Edges never cross feature directories. A ticket is unblocked once every ticket it names is `done`.
   - A ticket id of `<feature-slug>-<NN>`, which is what a branch name and a pull request reference use, because `NN` alone repeats across features. A ticket's closing reference is its path; nothing closes it automatically.
   - Conversation appended under a `## Comments` heading. A ticket is its body plus those comments.
   - A ready frontier computed by scanning `<spec_home>` for tickets that are mapped `ready_for_agent` and unblocked, ordered by feature directory then number.

   Do not tell the user to run a second setup skill.
2. Copy no `.github/` workflow and no reconcile script, and state that this is deliberate rather than missing. The `Status:` and `Blocked by:` lines are the lifecycle state, and they live in the working tree, so there is no issue event for a workflow to react to. Reconciling them is a file edit a human reviews like any other change, which is what `/land` and `/squash-land` already do wherever the tracker is not GitHub.
3. Preserve unrelated documentation and configuration.

For other trackers, record their native parent/dependency behavior in
`docs/agents/README.md`. Do not install GitHub automation, and do not promise
automatic parent closure.

Report every created or updated path. Do not authenticate interactively.
