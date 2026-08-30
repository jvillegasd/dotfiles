# Portable AI Harness Policy

This policy is the shared global instruction surface for Codex, Claude Code,
and OpenCode. Project instructions override it when they are more specific.

## Invocation

- Treat every top-level skill as explicit-only: load it only when the user
  names or invokes it.
- After an orchestrator is explicitly invoked, it may load only the skills
  named in its `Nested skills` section.
- Use ephemeral specialist roles. Do not create persistent client-specific
  personas when a skill or isolated review context is enough.
- Run independent roles in parallel when the client supports it; otherwise run
  them sequentially without merging their scopes.
- Treat locked SEO bodies as primitives behind the local `seo` portability
  layer: resolve `claude-seo` with its bundled launcher and any
  `skills/seo/...` path relative to the local `seo` skill directory.

## Public workflow

The lifecycle is `setup-harness` -> `grill-me` -> `spec` -> `tickets` ->
`ship`, with `address-review` for an existing pull request.

- `spec` owns the only substantive approval gate before publication.
- GitHub lifecycle labels are `blocked`, `ready-for-agent`, `in-progress`, and
  `ready-for-human`, or the mappings recorded in `docs/agents/harness.json`.
- Delivery ends at a green, reviewed, ready-for-human pull request. A human
  merges it and later removes its worktree.

## Safety

- Escalate immediately for missing credentials or permissions, destructive
  work outside the approved contract, or a required contract change.
- Continue repairing local defects while progress is measurable. Stop after
  three consecutive unchanged external or flaky failures.
- Keep secrets, authentication, histories, trust decisions, approvals,
  databases, caches, backups, and mutable client configuration out of source
  control.
- Prefer primary sources for research. Re-verify time-sensitive technical and
  SEO guidance before presenting it as current.
- When `rtk` is available, prefix shell commands with `rtk`.

## Git discipline

- Use branches named `<type>/<tracker-id>-<short-slug>`.
- Make the fewest independently coherent Conventional Commits and keep each
  commit green.
- Never merge a pull request or remove its worktree as part of `ship` or
  `address-review`.
