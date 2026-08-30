# Portable AI Harness Policy

This policy is the shared global instruction surface for Codex, Claude Code,
and OpenCode. Project instructions override it when they are more specific.

## Invocation

- Skills never auto-invoke on description matching. Load a skill only when the
  user names it, or when the routing table below sends a plain-language request
  to it. Announce that routing in one line so a wrong guess is cheap to correct.
- After an orchestrator is explicitly invoked, it may load only the skills
  named in its `Nested skills` section.
- Use ephemeral specialist roles. Do not create persistent client-specific
  personas when a skill or isolated review context is enough.
- Run independent roles in parallel when the client supports it; otherwise run
  them sequentially without merging their scopes.
- Treat locked SEO bodies as primitives behind the local `seo` portability
  layer: resolve `claude-seo` with its bundled launcher and any
  `skills/seo/...` path relative to the local `seo` skill directory.

### Routing

| Plain language | Follow |
| --- | --- |
| "set this repo up for the workflow" | `setup-harness` |
| "poke holes in this", "challenge this design" | `grilling` |
| "spec this out", "write it up" | `spec` |
| "break this into tickets", "slice this" | `tickets` |
| "implement this", "go build it", an approved plan, a ticket id | `ship` |
| "address the review comments", "CI is red on my PR" | `address-review` |
| "look into X", "is it true that" | `research` |
| "why does X happen", something broken or slow | `diagnosing-bugs` |
| "prototype this", "spike it" | `prototype` |

Routing carries the workflow's gates, not just its steps: `spec` still asks
once before publishing, and `ship` still never merges.

Do not route when the request is conversational or a one-line lookup where the
workflow costs more than the answer, or when two entries match and the choice
changes the outcome. Name both and ask.

Never route into producing a code review. `code-review` and
`adversarial-review` are entered only by explicit human invocation or from
`ship` and `address-review`.

When a request matches a workflow but omits something the workflow needs,
follow the workflow and let its own steps handle the gap. Do not fall back to
an ad-hoc answer.

## Public workflow

The lifecycle is `setup-harness` -> `grilling` -> `spec` -> `tickets` ->
`ship`, with `address-review` for an existing pull request.

- `grilling` is the only interview protocol. Do not substitute
  `grill-with-docs`, publish a spec from it, or act on its result. It finishes
  when the design-tree frontier is empty and the user confirms shared
  understanding.
- `spec` owns the only substantive approval gate before publication.
- `docs/agents/harness.json` plus `docs/agents/issue-tracker.md`, both written
  by `setup-harness`, satisfy the tracker and label prerequisite of every
  locked skill. Never redirect the user to the legacy
  `setup-matt-pocock-skills` workflow.
- GitHub lifecycle labels are `blocked`, `ready-for-agent`, `in-progress`, and
  `ready-for-human`, or the mappings recorded in `docs/agents/harness.json`.
- Delivery ends at a green, reviewed, ready-for-human pull request. A human
  merges it and later removes its worktree.

## Oracle ladder

Done is machine-checkable, not a judgement call. The shape is global; each
repository supplies the commands.

Cheapest first, each green before ascending:

1. type or compile check
2. lint
3. tests
4. build
5. push, open the pull request, remote required checks green

Resolve the concrete commands in this order: the project's own instruction
file when it declares them; else its declared task runner, meaning a
`justfile`, `Makefile`, or package-manifest target named `ci`, `check`, or
similar; else infer them from the toolchain. Prefer a variant that narrows the
run to what changed.

Re-derive the failure list on every pass; never work from a stale one. A
missing rung is skipped, never faked: no remote CI means the ladder ends at the
local rungs plus an open pull request, and no test suite means a shorter
ladder.

Resolving review threads is not a rung. Threads appear only after a human
reviews, so `address-review` owns them.

## Escalation contract

### Ask or decide

Ask only when both hold:

1. The answer is not derivable from repository evidence, telemetry, or an
   existing convention in this codebase. If three or fewer read-only actions
   would settle it, take them instead of asking.
2. Choosing wrong is expensive to reverse, or the choice is not yours.
   Expensive to reverse means a schema or data migration, any write visible
   outside this machine, a public-contract or auth-boundary change, money, or
   deleting something you cannot reconstruct. Not yours to make means product
   intent, priority, and scope-versus-ship tradeoffs.

Otherwise decide, then declare: the decision, the alternative you rejected, and
the one fact that would flip it.

Never ask permission to begin, for confirmation between steps, to proceed
after reporting progress, or to re-confirm something already answered.

### Question format

Every question states, in this order: the decision being made, in one line;
what was already checked, with a `path:line` for code or a linked number for
telemetry, and what each finding ruled out; the options, with the consequence
of each; your default if there is no answer; and what it costs if the default
is wrong.

Batch every open question into one stop. Never ask serially.

### Rabbit-hole detector

Stop and escalate the moment any of these trips, whatever step you are on:

- the same check has failed three times under three different fixes
- three consecutive unchanged external or flaky failures
- two consecutive attempts produced no new information
- the diff has grown past roughly three times the size the contract implied
- evidence contradicts the premise of the work
- a second review round raises a new blocking finding
- the fix requires touching a surface outside the stated intent

On a trip, do not try a fourth thing. Report what was attempted, what each
attempt disproved, the smallest next hypothesis, and what you need. A trip is
information, not failure.

### Surfaces that escalate on first touch

Touching one of these is an escalation however small the change looks, unless
the request or the approved contract explicitly names that surface:

- schema and data migrations
- CI/CD configuration
- dependency lockfiles
- shared or public contract surfaces
- infrastructure as code
- auth and secrets configuration

### Do not escalate for

Flaky or timed-out CI (rerun once; only a second failure counts as an
attempt). Lint or format failures (auto-fix them). A branch behind or
mechanically conflicting with its base (rebase, resolve, continue; only a
semantic conflict escalates). Type errors in code you just wrote. Dependency
install, cache, or port collisions (rerun the project's provisioning). "This
design may not be optimal" (pick the minimal option, record it, continue).

## Safety

- Escalate immediately for missing credentials or permissions, destructive
  work outside the approved contract, or a required contract change.
- Keep secrets, authentication, histories, trust decisions, approvals,
  databases, caches, backups, and mutable client configuration out of source
  control.
- Prefer primary sources for research, and follow `evidence` before asserting
  a load-bearing claim about runtime behavior, impact, or frequency. Re-verify
  time-sensitive technical and SEO guidance before presenting it as current.
- When `rtk` is available, prefix shell commands with `rtk`.

## Git discipline

- Use branches named `<type>/<tracker-id>-<short-slug>`.
- Make the fewest independently coherent Conventional Commits and keep each
  commit green.
- Never merge a pull request or remove its worktree as part of `ship` or
  `address-review`.

## Validating harness changes

This policy and these skills are themselves a surface with an oracle: the real
sessions they produce. Validate a change to `harness/` by comparing the session
population before and after its commit date with `harness/bench/measure.py`,
which reads every client's own session store.

Cost and friction are the measured part; quality stays a human judgment made by
reading transcripts. Compare populations, not pairs: a single session proves
nothing.

Re-reading a harness change and judging it plausible is not validation.
