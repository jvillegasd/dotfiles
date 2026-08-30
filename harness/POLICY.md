# Portable AI Harness Policy

This policy is the shared global instruction surface for Codex, Claude Code,
and OpenCode. Project instructions override it when they are more specific.

## Invocation

- Skills never auto-invoke on description matching. Load a skill only when the
  user names it, or when the routing table below sends a plain-language request
  to it. Announce that routing in one line so a wrong guess is cheap to correct.
  Locally authored skills enforce this structurally, with a guard for each
  client. A locked body cannot be guarded without drift, so this rule is its
  only control, and a locked body that must never fire on its own is not
  installed as a skill at all.
- After an orchestrator is explicitly invoked, it may load only the skills
  named in its `Nested skills` section.
- Use ephemeral specialist roles. Do not create persistent client-specific
  personas when a skill or isolated review context is enough.
- Run independent roles in parallel when the client supports it; otherwise run
  them sequentially without merging their scopes.
- Treat locked SEO bodies as primitives behind the local `seo` portability
  layer: resolve `claude-seo` with its bundled launcher and any
  `skills/seo/...` path relative to the local `seo` skill directory. A locked
  body naming `seo-performance` or `seo-visual` means `roles/performance` or
  `roles/visual` inside that same directory; neither is an installed skill.

### Routing

| Plain language | Follow |
| --- | --- |
| "set this repo up for the workflow" | `setup-harness` |
| "triage this", a pasted ticket, a production error signal | `triage` |
| "poke holes in this", "challenge this design" | `grilling` |
| "spec this out", "write it up" | `spec` |
| "break this into tickets", "slice this" | `tickets` |
| "how should we do this", a design with no contract yet | native plan mode |
| "implement this", "go build it", an approved plan, a ticket id | `ship` |
| a bullet list of changes to work already in a pull request | `feedback` |
| "address the review comments", "CI is red on my PR" | `address-review` |
| "look into X", "is it true that" | `research` |
| "why does X happen", something broken or slow | `diagnosing-bugs` |
| "prototype this", "spike it" | `prototype` |

Routing carries the workflow's gates, not just its steps: `spec` still asks
once before publishing, and `ship` still never merges.

Do not route when the request is conversational or a one-line lookup where the
workflow costs more than the answer, or when two entries match and the choice
changes the outcome. Name both and ask.

Never route into producing a code review. `adversarial-review` and the locked
`code-review` body are entered only by explicit human invocation or from `ship`
and `address-review`. `code-review` is deliberately not installed as a skill:
its upstream description advertises review trigger phrases it cannot be stopped
from matching, so `ship` and `address-review` read it from
`harness/skills/code-review/SKILL.md` by path instead.

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

## Planning

Every change needs an agreed contract before implementation. There are two
routes to one, and exactly one of them is required.

- **`spec` plus `tickets`**, for work worth documenting: a large feature,
  anything touching several surfaces, or anything whose reasoning should
  outlive the pull request. The published spec is the contract.
- **Native plan mode**, for everything else. Cheaper, in-conversation, nothing
  to publish. Trace the relevant system end to end, name the source of truth
  and the lifecycle implications, clarify only load-bearing ambiguity, and
  recommend the smallest coherent change with its files and verification. The
  approved plan is the contract `ship` consumes in its lightweight mode.

Never do both. An approved spec is already the implementation contract, so
re-entering plan mode to restate it adds a second gate over the same
decisions. Go straight from the approved contract to `ship`.

Whichever route, pressure-test with `grilling` before committing to it.

A `triage` plan brief, a `research` finding ledger, or a `prototype`
requirements ledger is the contract's input, not a suggestion to re-derive. Do
not re-investigate what it already grounded with a `path:line` or a linked
number. Carry its verification concerns forward verbatim and its open
questions in as decisions with defaults. Re-run only evidence it marked
refuted or unchecked.

## Approval means autonomous execution

Approving a contract is the go-ahead to run to completion. This applies to
every surface that produces one: native plan mode, `ExitPlanMode`, a published
spec, or a ticket.

On approval, follow `ship` without being asked. Treat the contract as the
implementation contract, work autonomously, and do not stop until `ship`
reaches its terminal state: a pull request open with every resolved rung
green. Do not ask for confirmation to begin, between steps, before committing,
or before pushing. Do not re-present the contract or ask which part to start.

Stop early only when implementation reveals the contract is invalid against
repository evidence, a load-bearing decision is genuinely unresolvable, or
pre-existing unrelated changes cannot be safely separated. Otherwise pick the
minimal option, record it in the pull request body, and continue.

Never commit implementation to the default branch, in any mode. `ship`
branches before editing; interactive work does the same. Work found sitting on
the default branch moves to a branch before pushing, not after.

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

Record the resolved ladder in Worktrunk's per-branch vars
(`git config worktrunk.state.<branch>.vars.ladder`) so later passes and any
supervisor do not re-derive it, and so a wrong inference is visible rather
than silent.

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

These counters must survive a restart or a context compaction, or the detector
silently resets to zero on exactly the long runs it exists for. Keep the
attempt and escalation counts in Worktrunk's per-branch vars
(`git config worktrunk.state.<branch>.vars.attempts` and `.escalations`),
which live in `.git`. Use vars, never the activity marker: the marker is
rewritten on every prompt and would erase an escalation.

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
- A claim is load-bearing only if being wrong about it changes the decision.
  Check those against telemetry, or mark them explicitly unchecked. Never state
  a number without its source deep link and timeframe. Where a project has not
  configured a telemetry capability, say so and move on: absence of data never
  blocks the work and never justifies inventing a number.
- When `rtk` is available, prefix shell commands with `rtk`.

## Conventions

These instructions load in three clients, so anything client-specific written
here is wrong somewhere.

- Name an MCP tool as its server plus its bare tool name, for example "the
  Linear MCP's `save_issue`". Never write a client-specific prefix.
- File edits go through the client's own edit tool, never `sed`, a heredoc, or
  a script, even where a permissions mode says to prefer the shell. An edit
  tool fails loudly on a missing or ambiguous target; a replacement that
  matches nothing exits 0 and reports success, so the mistake surfaces later as
  a change that was never made. The shell is still right for a mechanical sweep
  across many files; read the result back afterwards, because nothing else
  confirms it landed.
- Render a link as its complete absolute URL, including scheme and host. Never
  hide one behind alias text, and never render a bare path as a link.
- Never use em-dashes in prose, commit messages, pull request text, or code
  comments. Use a comma, a colon, parentheses, or a period.
- Commit subjects are Conventional, imperative, and at most 50 characters, with
  a body only when the "why" is non-obvious. No AI attribution, no emoji, no
  filler.

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
