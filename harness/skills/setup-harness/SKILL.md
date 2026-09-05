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

`tracker` and `spec_home` name the configured mode. Offer the two the harness writes by name and let the user pick: GitHub issues, `"github"` with `"github-issues"`, or local markdown files committed to the repository, `"local-markdown"` with the committed spec root, `"docs/specs"` unless the user names another. Infer the choice only where the repository settles it, such as having no remote at all. Any other tracker follows the last section. `domain_layout` may use project-specific values.

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

1. Write `docs/agents/harness.json` with the local mode values. Nothing creates labels here, so the four mapped values are only the vocabulary the `Status:` line uses.
2. Write `docs/agents/issue-tracker.md` as the compatibility contract for locked Matt skills: identify local markdown, require no CLI, and document the layout and how state is read. One directory per feature under the configured spec root, committed with the code, holding the spec at `<spec_home>/<feature-slug>/spec.md` and its slices at `<spec_home>/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` in dependency order, one ticket per file. A `Status:` line near the top of each ticket carries one mapped label value. A `Blocked by: NN, NN` line carries the dependency edges, and a ticket is unblocked once every file it names is resolved. Conversation appends under a `## Comments` heading, and a ticket is its body plus those comments. The ready frontier is a scan of the feature directory for tickets that are mapped `ready_for_agent` and unblocked, lowest number first. Do not tell the user to run a second setup skill.
3. Copy no `.github/` workflow and no reconcile script. State that this is deliberate rather than missing: parent closure and the frontier are the `Status:` and `Blocked by:` lines themselves, read by a directory scan, so there is no separate state to reconcile.
4. Preserve unrelated documentation and configuration.

For other trackers, record their native parent/dependency behavior in
`docs/agents/README.md`. Do not install GitHub automation, and do not promise
automatic parent closure.

Report every created or updated path. Do not authenticate interactively.
