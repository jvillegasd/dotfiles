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

`tracker`, `spec_home`, and `domain_layout` may use project-specific values.
Keep the four label keys stable while allowing mapped values to change. Update
an existing file in place instead of discarding user choices.

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

For other trackers, record their native parent/dependency behavior in
`docs/agents/README.md`. Do not install GitHub automation, and do not promise
automatic parent closure.

Report every created or updated path. Do not authenticate interactively.
