# Harness AI

One committed source for Claude Code and OpenCode. Codex CLI is a retired client; see Codex retirement below.

| Path | Holds |
| --- | --- |
| `POLICY.md` | The routing table, oracle ladder, and escalation contract. Linked to each client's global instruction path. |
| `commands/` | The workflows, invoked as `/name` in Claude Code and OpenCode. |
| `skills/` | Protocol, vocabulary, and locked third-party bodies. |
| `install.sh` | Installs clients and integrations, reconciles links, preserves mutable client state. |
| `locked-skills.sh` | Adds, updates, removes, and validates third-party skill locks. |
| `bench/measure.py` | Compares the session population before and after a change. Manual in `bench/README.md`. |
| `statusline/` | One file per provider that has a status line. |
| `clients/` | The client settings this harness owns: `claude.json` declares them and `agents.py` renders the reviewer agents. |

`clients/` declares rather than symlinks, because the live file is mostly machine state: hook manifests and generated absolute paths. A tracked key replaces the live value on every install, so deleting one here deletes it from the machine; untracked keys are left alone. `permissions` merges a level down, so `deny` stays owned while the Engram allowlist survives. This runs after `engram setup`, which rewrites the file from its own template, so being last is what makes a tracked key win over every other writer, the client included: `model`, `effortLevel`, `theme`, and `remoteControlAtStartup` are what `/model`, `/config`, and Remote Control write back at runtime, so an in-session change survives only until the next install.

## Development lifecycle

Every change reaches `/ship` through one of three contract routes, and exactly one is required. `grilling` pressure-tests the chosen route first, interactively when a human drives and in self-grill mode when a workflow needs its own approach broken without blocking. Delivery ends at a green, reviewed, ready-for-human pull request; a human decides to merge it, and `/land` closes the lifecycle, merging it first when that human explicitly invokes `/land`.

```mermaid
flowchart TD
    subgraph CONTRACT["contract"]
        ask_in["a bounded question"] --> ask["/ask<br>read-only, changes nothing"]
        ask -.->|needs deep tracing| research
        ask -.->|unclear requirements or a tradeoff| grill
        ask -.->|unclear requirements or a tradeoff| plan

        research_in["a question or a claim"] --> research["/research"]
        research --> ledger["finding ledger<br>planning input, not a contract"]

        triage_in["a ticket or a production error"] --> triage["/triage"]
        triage --> brief["plan brief<br>evidence-backed, path:line"]

        doc_in["work worth documenting"] --> spec["/spec<br>the only approval gate<br>before publication"]
        spec --> createticket["/create-ticket"]
        ledger --> createticket
        createticket --> ticket["implementation-ready tickets"]
        createticket -->|research ticket,<br>contract fields missing| planning["planning-only ticket<br>no lifecycle label"]
        planning -->|fields supplied,<br>/create-ticket promotes| ticket

        proto_in["requirements that<br>will not settle on paper"] --> proto["/proto<br>build a slice, local rungs green,<br>a human tries it, fold feedback in"]
        proto --> protoledger["requirements ledger"]

        else_in["everything else"] --> plan["native plan mode"]
        brief --> plan
        brief --> spec

        grill["grilling<br>interactive, or self-grill:<br>settle what evidence can settle,<br>surface only the survivors"]
        grill -.-> spec
        grill -.-> plan
        grill -.-> proto

        ticket --> approval(["approved contract"])
        plan --> approval
        protoledger --> approval
    end

    subgraph BUILD["build"]
        approval --> ship["/ship<br>worktree and branch first,<br>never the default branch"]
        ship --> ladder["resolve the oracle ladder<br>project instructions, else task runner,<br>else the toolchain"]
        ladder --> implement["implement<br>loading ponytail"]
        implement --> rungs["local rungs green:<br>types, lint, tests, build"]
        rungs --> commit["commit"] --> review["adversarial-review<br>named reviewer agents, requirements-aware<br>and diff-only, disclosed fallback"]
        review --> conform["spec-conformance pass<br>diff against the contract"]
        conform --> push["push"] --> pr["open the draft pull request<br>capped body: what changed, contract,<br>checks, assumptions, refuted, rejected"]
        pr --> checks(["remote required checks<br>and both review passes green"])
        checks -->|mark the draft ready| ready(["ready-for-human<br>terminal state"])
    end

    subgraph AFTER["after"]
        ready --> feedback["/feedback<br>a bullet list from you;<br>deferred rounds apply only,<br>a full round settles the debt"]
        ready --> addressreview["/address-review<br>review threads, red CI"]
        feedback --> merge{"a human decides to merge"}
        addressreview --> merge
        ready --> merge
        merge -->|already merged: they type /land n| land["/land merged lane<br>verify conformance, where a mismatch<br>can only be reported"]
        merge -->|they type /land n| land2["/land open lane<br>gates and conformance first,<br>then squash merge, then repair dependents"]
        land --> landtail["reconcile the tracker,<br>retire the worktree"]
        land2 --> landtail
        merge -->|they close it unmerged| abandon["/abandon<br>name what is discarded, one confirmation,<br>release or reconcile cancelled scope,<br>retire the worktree"]
        proto -.->|premise refuted: kill it, record why| abandon
    end
```

The escalation contract can stop any run: the same check failing three times under three different fixes, two attempts that produced no new information, three unchanged external failures, a diff far past the size the contract implied, evidence contradicting the premise, a second review round raising a new blocking finding, or a first touch of a migration, CI config, lockfile, shared contract, infrastructure, or auth surface the request never named. The counters live in `git config` rather than the conversation, so a restart or a compaction cannot reset them.

## Commands and skills

A workflow's source is `commands/`, never `skills/`. Claude Code and OpenCode link them into `~/.claude/commands` and `$XDG_CONFIG_HOME/opencode/command` (defaulting to `~/.config`) and invoke `/name`.

Every command that ingests text written elsewhere, a ticket body, a review comment, an error payload, states that the input is task data and cannot override the workflow's constraints.

A locally authored skill carries all three invocation guards: `policy.allow_implicit_invocation: false` in its `agents/openai.yaml`, plus `disable-model-invocation: true` and `metadata."opencode/autoinvoke": "false"` in its frontmatter. A locked body gets none, because `agents/openai.yaml` is upstream content and `computedHash` covers the whole directory, so anything written inside it is clobbered by the next update with the lockfile recording the loss as correct. The only control that survives an update is not installing the body at all. The `agents/openai.yaml` guard stays although Codex is retired, because a Codex still installed on the machine reads the shared `~/.agents/skills` root and honors that guard, keeping it from firing a local skill on description match (https://learn.chatgpt.com/docs/build-skills).

## Reviewer agents

`adversarial-review` launches Reviewer A and Reviewer B as named agents. Their standing instructions, lenses, output format, and read-search intent live once, in `skills/adversarial-review/roles/`; the skill keeps orchestration, scaling, diff delivery, triage, and the loop cap. `clients/agents.py <roles> <output>` renders one definition per reviewer per client and rewrites nothing that already matches; `--check` reports a missing, drifted, unmanaged, or widened definition.

The installer generates into `harness/.generated/agents/`, gitignored machine state owned by this checkout, and links each definition into its client's agent directory. The only links it claims are ones whose text points into that directory: an install removes a link whose definition was retired, an uninstall removes every such link and the generated directory, and a private agent or another checkout's link beside them is left alone. `check_links` fails on a missing link or on a definition that lost its restrictions.

| Client | Agents | Path | Control | Not enforced |
| --- | --- | --- | --- | --- |
| Claude Code | `reviewer-a`, `reviewer-b` | `~/.claude/agents/` | `tools: Read, Grep, Glob`, so writes, shell, web, MCP tools, and `Agent` are absent | nothing documented; reading a diff file outside the project without a prompt is unverified |
| OpenCode | `reviewer-a`, `reviewer-b` | `$XDG_CONFIG_HOME/opencode/agents/` | `mode: subagent` with every permission denied and only `read`, `grep`, `glob`, and `list` re-allowed, `.env` reads still denied | reading a diff file outside the project, which the deny refuses, so the inline fallback covers it; whether MCP tools fall under the deny is unverified |

Every restriction is best effort: the table is what each client documents, the generator prints the same gaps on every install, and no row is runtime-verified until a probe runs against an installed client. Probe during an intentional installation, never as a validation shortcut: in each client, launch each named agent, ask it to write a file, run a command, fetch a URL, and delegate, and record each result as enforced, not enforced, or unverified. The unverified rows are whether Claude Code loads a symlinked definition, whether a Claude Code reviewer reads a diff outside the project without a prompt, whether OpenCode's deny covers MCP tools, whether the `ccyolo` and `ocyolo` launchers leave agent restrictions in force, and diff delivery's inline fallback and escalation.

Reviewer A receives the requirements and the diff, never the implementation rationale; Reviewer B receives only the diff. The parent writes one complete diff snapshot per round to a temporary file outside the worktree. A reviewer that cannot read it answers `unreadable: <path>` and gets the same snapshot inline, and when neither transport can carry the whole diff the review escalates instead of truncating. When a named agent is unavailable, the parent says so and launches a general agent with the role file as its instructions, disclosing that the fallback enforces only that agent's own permissions. Review is never skipped. Nothing here claims model diversity: both reviewers run whatever model their client assigns.

## Install

The root `../macos.sh` and `../linux.sh` install the harness by default. To reconcile only policy, commands, and skills:

```sh
./harness/install.sh --links-only
```

| Flag | Effect |
| --- | --- |
| `--links-only` | Reconcile links without installing packages. Engram and agent-browser are still reconciled, so both must already be installed. |
| `--no-backup` | Delete what is in the way instead of archiving it. Destructive and unrecoverable. |
| `--uninstall` | Remove every managed link, the generated reviewer agents, the alias block, the tracked client keys, Engram, and agent-browser. Keeps `~/.engram` and `~/.agent-browser`. |
| `--clear-backups` | Delete every archive under `~/.dotfiles-backups/harness/`. Runs on its own. |

Reconciliation removes as well as adds. A symlink in a managed root is backed up and removed when its target is gone, points into `harness/` at something no longer installed, or carries a name differing from its target's, so a retired entry cannot outlive the change that retired it. A real directory shadowing a managed name is backed up too, since the sweep cannot see it. One defect is left in place and tracked separately: the dangling branch removes a dangling symlink whoever wrote it, because a target resolving to nothing cannot be tested for ownership.

Managed roots are real directories, so harness links and your private entries sit side by side; a symlink standing in for one is moved aside under `.previous-link`. The OpenCode skills root is normalized but never created, since OpenCode reads `~/.agents/skills`. OpenCode's own three paths follow `XDG_CONFIG_HOME` when set, the same default `../lib/common.sh` resolves. Anything in the way is moved to a timestamped directory under `~/.dotfiles-backups/harness/`, or deleted with `--no-backup`, which the root installer forwards. Each removal is logged.

Both run modes verify what they wrote. `check_links` asserts every skill, command, policy, status line, and reviewer agent link on every run; `check_tools` adds the client, plugin, and interpreter assertions only a full run can satisfy. Its OpenCode assertion reads `opencode debug config` through a temporary file rather than a pipe: that command stops at the 64 KiB pipe capacity whenever stdout is not a regular file, and this config passed 64 KiB once the harness's own command templates went into it, so the piped form failed on a JSON parse error instead of on the assertion. Both run after Engram, which rewrites `settings.json` and `opencode.json`.

### MCP servers

Engram is core, not optional: the policy assumes memory survives a session. `install_engram` runs one `engram setup <agent>` per client, as engram's own `docs/AGENT-SETUP.md` (https://github.com/Gentleman-Programming/engram) documents, and is idempotent. Both run modes reconcile it unconditionally rather than probing, because probing sees presence but never whether the pinned absolute binary path still resolves; setup rewrites the pin every time. The claude-code command is answered yes to allowlist Engram's tools; the opencode command takes a closed stdin. The allowlist stays untracked, since a tracked copy of a tool set Engram owns goes stale silently.

agent-browser (https://github.com/vercel-labs/agent-browser) ships no per-client registrar, so `install_agent_browser` writes both registrations itself: `claude mcp add --scope user`, plus a JSON edit to `opencode.json` for the client whose `opencode mcp add` is interactive. It runs from `reconcile_clients`, after `engram setup`, which would otherwise drop it. `check_tools` asserts both servers per client, so a run that clobbered Engram's entry fails.

Registration is global, because a browser driver is a general tool like `gh` rather than a dependency of one repository. Each registration is removed and re-added, so a re-run is idempotent and the pinned path is never stale. The profile is the default, meaning no `--tools` flag, so only `core` loads. Widening to `network`, `state`, `debug`, `tabs`, `react`, `mobile`, or `all` is a one-word edit there, and each would cost context in every session of both clients.

The formula is homebrew-core. It publishes no x86_64 macOS bottle, so an Intel Mac builds from source, and on Linux the install takes `--with-deps`, which is mandatory there and rejected elsewhere. Its caveat is run rather than printed: `agent-browser install` downloads Chrome for Testing, without which every browser call fails mid-session. The uninstall removes both registrations and the formula, and leaves `~/.agent-browser` alone: it holds the browser download and whatever profiles the CLI saved beside it, and this installer does not delete another tool's data directory. The summary measures the directory and reports it.

### Packages

Homebrew carries every tool on both platforms, because three of them (OpenCode, Engram, Worktrunk) ship only as taps. Claude Code comes from Anthropic's native latest channel. The installer never starts an interactive client or authenticates for you.

Python belongs to uv rather than Homebrew:

```sh
uv python install 3.14
```

`PYTHON_VERSIONS` in `../lib/python.sh` is the one declaration, and sourcing it is the only thing this installer reads from outside `harness/`. The root scripts call `install_pythons`; `check_tools` calls `assert_pythons`, because the harness consumes the interpreters. That check asks `uv python find --managed-python` rather than testing `PATH`, since a shadowing Homebrew `python3.14` would pass while uv had nothing to resolve, and `uv` therefore arrives first, from `Brewfile` on macOS and `linux.sh` on Linux. Nothing here claims the name `python3`: each version also lands as `~/.local/bin/python3.14`, usually behind the pyenv shims. Run `uv python update-shell` to change that.

### OpenAI models through OpenCode

OpenAI models reach the harness through OpenCode, and Claude models through Claude Code, each in its own client. The installer never authenticates, copies a credential, or bridges one client into another. Sign OpenCode in natively: run `/connect` inside OpenCode, select OpenAI, then `ChatGPT Plus/Pro`, which opens a browser sign-in for that subscription (https://opencode.ai/docs/providers/). `opencode auth login` configures a provider from a shell, and `opencode auth list` shows what `~/.local/share/opencode/auth.json` holds (https://opencode.ai/docs/cli/).

`Manually enter API Key` is API billing, a separate payment path. Choose it only on purpose, never as a fallback for a failed subscription sign-in. OpenCode also loads provider keys from environment variables and a project's `.env`, and which credential wins when both exist is undocumented, so an exported `OPENAI_API_KEY` is a second way onto API billing: unset it before relying on the subscription. A failed sign-in or model request is reported as it is, never worked around through another account, provider, or key. Account access stays unverified until a sign-in and a model request succeed on this machine.

### Codex retirement

Codex CLI is not a harness client. The installer no longer installs it, generates its command adapters or reviewer agents, links the policy into `~/.codex`, reconciles `~/.codex/config.toml` or its status line, registers MCP servers for it, or defines `cyolo`. Provisioning and every check run without a `codex` executable.

Every run, install and uninstall alike, retires what an earlier install wrote there, and only what link text proves this checkout wrote: the `~/.codex/harness-commands` tree whose `.source` points at this checkout's `commands/`, the `~/.codex/skills` links into it, legacy `~/.codex/prompts` command links, the `~/.codex/AGENTS.md` policy link, and `~/.codex/agents` links into `harness/.generated/agents/`. A private file at any of those names, a foreign link, and a symlinked root are left alone. `check_links` and `check_removed` fail if the owned adapter tree, a prompt link, the policy link, or an agent link survives. A `~/.codex/skills` link left dangling after its adapter tree is already gone proves no checkout's ownership, so it stays, the same reason the orphan sweep's dangling-link defect is not extended. An install archives what it retires; an uninstall deletes it.

Nothing else under `~/.codex` is touched: not `config.toml`, whose model, status line, Engram, and agent-browser entries cannot be told apart from ones Codex or you wrote; not credentials or session history; and not the Codex binary, which stays installed until you remove it, since `brew bundle` runs without cleanup. An Engram or agent-browser entry an earlier install wrote there survives a later uninstall and names a binary that uninstall removed. `bench/measure.py` still reads `~/.codex/sessions`, and CodexBar stays in `Brewfile`.

## Shell aliases

`aliases.sh` holds the yolo-mode launchers and is sourced from `~/.zshrc` through one managed line. The installer removes any hand-written `ccyolo` or `ocyolo`, and the retired `cyolo` and `oyolo`, so the committed file is the only source, and leaves every other alias alone.

| Alias | Runs |
| --- | --- |
| `ccyolo` | `claude --dangerously-skip-permissions` |
| `ocyolo` | `opencode` with `OPENCODE_PERMISSION` set to allow edit, bash, and webfetch |

OpenCode has no bypass flag: its permissions are configuration, and `OPENCODE_PERMISSION` overrides them for one run.

Zsh is the only shell either shell-facing step writes: the aliases go into `~/.zshrc`, and Worktrunk is asked for its zsh integration by name. A run whose `$SHELL` is something else warns and names both, rather than leaving the aliases quietly absent. Source `aliases.sh` from your own rc and run `wt config shell install` for that shell.

## Status line

The two clients expose different amounts of surface, so one committed script cannot serve both.

| Client | File | Mechanism |
| --- | --- | --- |
| Claude Code | `statusline/claude.sh` | A renderer run on every draw, linked to `~/.claude/statusline.sh` with `statusLine` pointed at it |
| OpenCode | none | No status line field in its schema and no plugin hook, so there is nothing to render into |

`claude.sh` renders model, context-window percentage, directory and branch with a dirty marker, session duration, and reasoning effort, then the five-hour and weekly rate-limit bars, fetched from the OAuth usage endpoint and cached for sixty seconds in `/tmp/claude`.

## Third-party skill updates

`.agents/skills` points to `harness/skills`. `locked-skills.sh` keeps the skills.sh call, `skills-lock.json`, and the Claude bookkeeping link in one reviewed workflow:

```sh
./harness/locked-skills.sh add <owner/repo> <name>
./harness/locked-skills.sh update
./harness/locked-skills.sh remove <name>
./harness/locked-skills.sh check
```

`add` refuses invalid sources and existing paths before delegating. `update` updates every locked body. `remove` accepts only a current lock entry. Every mutation prints the affected paths; `check` runs syntax and diff hygiene. The helper's `--help` is side-effect free, but do not probe the upstream update subcommand with `--help`: skills.sh treats that as a full update.

Review every upstream body, security report, and diff, then commit only the approved change. Locked bodies stay pristine; behavior changes belong in a command or in `POLICY.md`. Provisioning never runs the helper or a lockfile restore. A copied skill with unknown provenance stays an attributed local fork until its upstream is identified. Engram and Orca-provided skills are runtime managed and never belong in `skills-lock.json`.

Binaries are the deliberate exception. Every prose body has its hash in `skills-lock.json`, while the clients arrive unpinned: `curl -fsSL https://claude.ai/install.sh | bash` and two Homebrew taps. A locked body is a reviewed instruction this harness executes forever, so a change to one has to be read; a client is a moving target whose next version is the point of re-running the installer. The trade is a supply chain that trusts Anthropic and two tap owners at install time.

## Roster

Commands are `/ask`, `/research`, `/triage`, `/harness-audit`, `/spec`, `/create-ticket`, `/proto`, `/ship`, `/feedback`, `/address-review`, `/land`, and `/abandon`.

`/land` has two lanes, selected by the pull request's state. Explicit `/land <n>` authorizes squash-merging an open non-draft pull request after its gates pass; an already-merged one runs only the remaining cleanup. No extra argument or second confirmation. Automatic routing and other workflows never invoke it. Both the mergeability gate and the conformance check precede the merge, so a blocking mismatch prevents it, where the merged lane can only report one. With no argument it resolves the current worktree's head branch, falling back to a search over merged pull requests only.

`/abandon` is the other exit, for work that will not land. No tracker automation recovers a ticket stranded at `in-progress`, since the reconciler skips an active label and fires only on close or reopen, so the worktree and the claim would have no owner. It is a command rather than a lane inside `/land` because `/proto` calls it to kill a prototype. Being the only workflow that discards unmerged work, it lists every commit and uncommitted change and takes one confirmation on that list. An abandoned attempt preserves scope and dependencies for retry; explicit cancellation reconciles parent scope and obsolete edges in the same confirmation, and never counts as merge evidence.

Local skills are `adversarial-review`, `evidence`, `grilling`, `grill-with-docs`, `local-tracker`, `setup-harness`, and `workflow-checkpoint`, each carrying the three guards. `local-tracker` holds what a tracker operation means when the tracker is committed markdown, so the delivery commands gain one pointer each instead of a files-mode branch apiece. `workflow-checkpoint` is the one definition of the branch-scoped Engram checkpoint: its topic key, record schema, recovery validation, and terminal states, so the delivery commands can load it by name instead of each restating the schema. `setup-harness` stays a skill because it installs bundled assets only a skill directory can carry. `grilling` is local rather than locked so it can carry a self-grill mode and ask one question at a time. `grill-with-docs` composes it with `domain-modeling`, and is the only surface that writes `CONTEXT.md` or an ADR. A `/research` ledger stays planning input until a route produces a complete contract; a finalized `/proto` ledger is itself a contract.

Locked Matt Pocock skills provide domain and module vocabulary, `improve-codebase-architecture`, TDD, diagnosis, handoff, and conflict resolution. Locked `DietrichGebert/ponytail` provides lazy mode. Locked `JuliusBrussee/caveman` provides `caveman-commit`; only `skills/` is taken, which that repository licenses MIT. Where a locked body and the policy disagree the policy wins: caveman allows a 72-character subject, `POLICY.md` allows 50.

`improve-codebase-architecture` produces planning input, never a change contract: keep its report read-only and route a candidate through native plan mode, `/spec`, or `/proto` before changing files.

### Impeccable

Locked `pbakaus/impeccable` is the one frontend design body. It is description-matchable, so the control is scope rather than a guard: no command or local skill loads it, and `POLICY.md` keeps the project's existing styling layer winning inside `/proto` and `/ship`.

It arrives only through `locked-skills.sh`. Four of its own routes are forbidden, because each writes outside the lock: `npx impeccable install` and `$impeccable hooks on` wire `PostToolUse` and `Stop` hooks into a project unasked, `npx impeccable update` rewrites the locked directory out from under `skills-lock.json`, and `scripts/pin.mjs` mints a `$<command>` shortcut as a real skill directory that `install.sh` would link everywhere and neither sweep would reclaim. The lock covers the body's bytes, not its runtime egress: several scripts call the author's site. At 4.8 MB across 168 files it is the largest thing in `skills/`, against about 99 KB for everything else combined.

### Ponytail

Ponytail is a locked skill body, not a plugin. None of the plugin is installed, and `check_links` asserts the body is present. What replaces its `SessionStart` hook is one line in each command that writes code, `/ship`, `/proto`, `/feedback`, and `/address-review`, plus `adversarial-review` using ponytail violations as a review lens. Lazy mode then applies where code is written rather than to every conversation, and delivers the full `SKILL.md` instead of the hook's level-filtered condensation. The trade is that `/ponytail lite|ultra` switching and the auxiliary skills are gone, and in exchange the body changes only through a reviewed update, where the plugin once moved 4.7.0 to 4.9.0 mid-install with six agent-steering bodies changing unread.

## Invocation guards

`POLICY.md` opens with the commands-and-skills split. Command storage carries it for the workflows. For the local skills the roster lists, the three guards carry it. For a locked body prose is the only control, which is why a body that must never fire on its own is not installed at all.

## GitHub lifecycle

In GitHub mode, `setup-harness` writes `docs/agents/harness.json`, creates the four labels, writes the tracker compatibility file, and copies the bundled workflow and reconciler. The workflow becomes active when that reviewed change reaches the default branch. GitHub native sub-issue and dependency relationships remain the source of truth. A blocker satisfies the frontier only when a merged pull request closed it, which is why `blocker_satisfied` walks `closedByPullRequestsReferences` rather than trusting the closed state; closing an issue by hand does not open the frontier behind it. The parent closes only after every child has that same evidence.

The other mode is local markdown, where `setup-harness` writes the config and compatibility file and nothing else: no labels, no workflow, no reconciler. Lifecycle state is a `Status:` line and a `Blocked by:` line committed beside the code, and the `local-tracker` skill holds what each operation means there.

```mermaid
flowchart TD
    setup["setup-harness<br>invoked by hand, per repository"] --> config["docs/agents/harness.json<br>tracker, spec home, label mapping"]
    setup --> labels["gh label create --force<br>blocked · ready-for-agent<br>in-progress · ready-for-human"]
    setup --> trackerdoc["docs/agents/issue-tracker.md<br>compatibility contract for locked skills"]
    setup --> files[".github/workflows/agent-lifecycle.yml<br>.github/scripts/reconcile-agent-lifecycle.py"]
    files --> active(["active once that reviewed change<br>reaches the default branch"])

    subgraph GRAPH["issue graph, GitHub native"]
        parent["parent issue"] --- children["sub-issues"]
        children --- deps["blocked-by / blocking"]
    end

    subgraph RUN["reconciler, on issues closed or reopened"]
        active --> trigger["workflow run"]
        trigger --> frontier["reconcile_frontier<br>on the event issue and everything it blocks"]
        frontier -->|any blocker unsatisfied| blocked["label: blocked<br>in-progress and ready-for-human cleared"]
        frontier -->|every blocker satisfied,<br>nothing active| ready["label: ready-for-agent"]
        trigger --> parentstate["reconcile_parent"]
        parentstate -->|every child closed by a merged PR| closeparent["parent closed"]
        parentstate -->|a child reopened| reopenparent["parent reopened,<br>label: in-progress"]
        parentstate -->|state changed| parentqueue["parent queued for<br>a full reconcile pass"]
        parentqueue --> trigger
    end

    GRAPH --> trigger

    subgraph AGENT["what the agent does with it"]
        ready --> ship["/ship picks up a ready ticket<br>branch: type/tracker-id-slug"]
        ship --> inprogress["label: in-progress"]
        inprogress --> prready["pull request green and reviewed<br>label: ready-for-human"]
        prready --> humanmerge["a human decides to merge"]
        humanmerge -->|they merge it on GitHub| merged["merged, the closing reference<br>closes the ticket"]
        humanmerge -->|they type /land n| landopen["/land open lane:<br>gates and conformance first,<br>then squash merge"]
        landopen --> mergedself["merged by this run, the closing<br>reference closes the ticket"]
        mergedself --> trigger
        merged --> trigger
        merged -->|already merged: they type /land n| landmerged["/land merged lane<br>verify conformance, report a mismatch"]
        landmerged -->|conformance clean| landtail["reconcile the tracker,<br>retire the worktree"]
        mergedself -->|the same run continues| landtail
        humanmerge -->|closed unmerged: requirement retained| abandonlabel["/abandon releases the claim by hand:<br>the reconciler skips an active label<br>and fires only on close or reopen"]
        humanmerge -->|requirement explicitly cancelled| cancelscope["/abandon: confirm scope changes,<br>preserve history, remove obsolete edges,<br>reconcile remaining required scope"]
        inprogress -->|the run died| abandonlabel
        abandonlabel -->|every blocker still satisfied| ready
        abandonlabel -->|a blocker reopened meanwhile| blocked
    end
```

Contract source and tracker binding are independent: the source controls conformance, the binding controls branch names, closing references, and label transitions. An in-conversation, `/proto`, or trackerless ticket contract is preserved in an inline `## Contract`; only a tracker-bound ticket-sourced contract can remain solely in its ticket.

`/land` resolves the pull request first and lets that state pick the lane, prefers the inline contract for conformance, and falls back to the ticket when none exists. Trackerless work skips tracker transitions. A legacy trackerless pull request with neither source reports that conformance cannot be reconstructed, verifies merge and default-branch health, and removes only a clean retained worktree.

## Validation

Validate a change to this directory against the sessions it produced, as `harness/bench/README.md` explains:

```sh
python3 harness/bench/measure.py --split <commit-date> --since <window-start>
```

It reads Claude Code JSONL transcripts, Codex rollout JSONL, and the OpenCode SQLite database, and reports each client separately; `--client` narrows it. Codex rollouts stay readable so sessions from before its retirement remain measurable. A metric a client does not record, such as a declined tool call in Codex or OpenCode, prints as `-` rather than zero.

Eight medians per cohort: `turns`, `tool_calls`, and `minutes` for cost, `interrupts`, `denials`, and `errors` for friction, and `commands` and `delegation` for routing adoption and subagent use. A subagent gets its own transcript in both clients that delegate, and counts as the parent's delegation rather than as a session.

A hard week at work moves every one of those numbers without the harness changing. Copy `harness/bench/cohorts.example.json` to `cohorts.json` and list the project patterns that mean work, and the report splits work from personal. That file is gitignored.

Populations, not pairs. Cost and friction are the measured part; quality stays a human read of the sessions.

Do not enable the Worktrunk Claude Code plugin. Its `UserPromptSubmit` hook rewrites the same per-branch slot `POLICY.md` uses for attempt and escalation counts, which would erase an escalation on the next prompt.
