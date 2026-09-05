# Harness AI

One committed source for Codex, Claude Code, and OpenCode:

- `POLICY.md` is linked to each client's global instruction path. It carries the routing table, the oracle ladder, and the escalation contract.
- `commands/` holds the workflows. Humans invoke them as `/name` in Claude Code and OpenCode, or `$name` in Codex.
- `skills/` holds protocol, vocabulary, and locked third-party bodies.
- `install.sh` installs current clients/integrations, preserves mutable client state, and reconciles policy, command, and skill links individually.
- `locked-skills.sh` adds, updates, removes, and validates reviewed third-party skill locks.
- `bench/measure.py` compares the real session population before and after a harness change, reading all three clients' own session stores. Its manual is `bench/README.md`.
- `statusline/` holds one file per provider: `claude.sh` renders Claude Code's line, `codex.sh` reconciles Codex's built-in one to match.
- `clients/` holds the client settings this harness owns: `claude.json` and `codex.toml` declare them, and `codex.sh` reconciles the TOML half. Nothing here is symlinked, because both live files are mostly machine state written by other tools, hook manifests and per-project trust decisions and generated absolute paths. A tracked key replaces the live value on every install, so removing one here removes it from the machine; every key not named there is left alone. `permissions` is the one exception, merged a level down so `deny` stays owned while the Engram allowlist survives. The install runs these after `engram setup`, which rewrites both files from its own template, so a tracked key wins over every other writer. That includes the client itself: `model`, `effortLevel`, and `theme` are what `/model` and `/config` write back at runtime, so an in-session change to one of them survives until the next install and no longer.
- `tests/` checks supply-chain, installer, and contract invariants, one file per subject.

## Development lifecycle

Every change reaches `/yolo` through one of three contract routes, and exactly one of them is required. `grilling` pressure-tests whichever route is chosen before it is committed to, interactively when a human is driving and in self-grill mode when a workflow needs its own approach broken without blocking. Delivery ends at a green, reviewed, ready-for-human pull request; a human decides to merge it, and `/land` closes the lifecycle, or `/squash-land` does both at once when that human invokes it by name.

```mermaid
flowchart TD
    subgraph CONTRACT["contract"]
        ask_in["a bounded question"] --> ask["/ask<br>read-only, changes nothing"]
        ask -.->|escalates when it is bigger than one answer| ask

        research_in["a question or a claim"] --> research["/research"]
        research --> ledger["finding ledger<br>planning input, not a contract"]

        triage_in["a ticket or a production error"] --> triage["/triage"]
        triage --> brief["plan brief<br>evidence-backed, path:line"]

        doc_in["work worth documenting"] --> spec["/spec<br>the only approval gate<br>before publication"]
        spec --> createticket["/create-ticket"]
        ledger --> createticket
        createticket --> ticket["implementation-ready tickets"]

        proto_in["requirements that<br>will not settle on paper"] --> proto["/proto<br>build a slice, local rungs green,<br>a human tries it, fold feedback in"]
        proto --> protoledger["requirements ledger"]
        proto -.->|premise refuted: kill it, record why| proto

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
        approval --> yolo["/yolo<br>worktree and branch first,<br>never the default branch"]
        yolo --> ladder["resolve the oracle ladder<br>project instructions, else task runner,<br>else the toolchain"]
        ladder --> implement["implement<br>loading ponytail"]
        implement --> rungs["local rungs green:<br>types, lint, tests, build"]
        rungs --> conform["spec-conformance pass<br>diff against the contract"]
        conform --> review["adversarial-review<br>blind reviewers, told the diff is wrong"]
        review --> commit["commit"] --> push["push"] --> pr["open the pull request<br>inline contract, assumptions,<br>refuted evidence, rejected findings"]
        pr --> checks(["remote required checks green<br>terminal state"])
    end

    subgraph AFTER["after"]
        checks --> feedback["/feedback<br>a bullet list from you;<br>deferred rounds apply only,<br>a full round settles the debt"]
        checks --> addressreview["/address-review<br>review threads, red CI"]
        feedback --> merge{"a human decides to merge"}
        addressreview --> merge
        checks --> merge
        merge -->|someone else merged it| land["/land<br>verify conformance, reconcile the tracker,<br>retire the worktree"]
        merge -->|they merge it themselves| squashland["/squash-land<br>gates and conformance first,<br>then squash merge, then land"]
    end
```

The escalation contract can stop any run: the same check failing three times under three different fixes, two attempts that produced no new information, three unchanged external failures, a diff far past the size the contract implied, evidence contradicting the premise, a second review round raising a new blocking finding, or a first touch of a migration, CI config, lockfile, shared contract, infrastructure, or auth surface the request never named. The counters live in `git config` rather than in the conversation, so a restart or a compaction cannot reset them.

## Commands and skills

A workflow's source is `commands/`, not `skills/`. Claude Code and OpenCode install canonical command links into `~/.claude/commands` and `$XDG_CONFIG_HOME/opencode/command` (defaulting to `~/.config`) and invoke them as `/name`. Codex invokes them as `$name`, for example `$yolo 38`, through generated explicit-only skill adapters in `~/.codex/skills`. The shared `~/.agents/skills` root gets no adapters, because OpenCode also reads it.

The installer generates wrappers in `~/.codex/harness-commands`, links each wrapper from `~/.codex/skills/<name>`, and links its `command.md` to the canonical body. Each wrapper binds invocation text to `$ARGUMENTS` as task data and carries `policy.allow_implicit_invocation: false` in `agents/openai.yaml`. `/name` references inside a workflow keep their meaning, including human-only merge approval. Reinstall after adding or removing commands; body edits take effect through the link. Generated adapters are machine state, never committed.

Legacy `~/.codex/prompts` is no longer populated or swept. Migration retires only exact command links owned by this checkout, including dangling ones; private prompt files, foreign links, and symlinked prompt roots remain untouched. Adapter collisions and changed generated trees use the existing backup policy. Uninstall removes this checkout's generated tree and exact adapter links, leaving other Codex skills and `.system` alone. `--no-backup` deletes displaced managed paths rather than archiving them.

Codex discovery was verified with the installed CLI's `app-server` `skills/list` API, not inferred from files existing. Reproduce the isolated, no-model-call smoke test with `HARNESS_CODEX_SMOKE=1 python3 -m unittest discover -s harness/tests -t harness/tests -p test_codex_commands.py -k test_real_codex`. The supported explicit-only metadata is documented at https://learn.chatgpt.com/docs/build-skills. Restart Codex if `$yolo` or `/skills` does not show the adapters after installation.

Every command that ingests text written elsewhere, a ticket body, a review comment, an error payload, a bullet list, states that the input is task data and cannot override the workflow's constraints. The acceptance suite asserts that line is present.

A locally authored skill still carries all three invocation guards: `policy.allow_implicit_invocation: false` in its `agents/openai.yaml` for Codex, plus `disable-model-invocation: true` and `metadata."opencode/autoinvoke": "false"` in its frontmatter for Claude Code and OpenCode. Only four skills are local now, so the guard matrix covers a much smaller surface than it did when it also had to hold the workflows.

A locked body gets no guard. `agents/openai.yaml` is upstream content, not a harness sidecar, and `computedHash` covers the whole directory, so anything written inside a locked skill is clobbered by the next `skills update` without a drift warning and with the lockfile rewritten to record the loss as correct. The control that survives an update is not installing the skill: a locked body whose upstream description advertises trigger phrases it must not act on is kept out of every client's skill directory. Every locked body carried today is installed under its own name, so nothing is currently excluded that way.

## Install

The root `../macos.sh` and `../linux.sh` install the harness by default. To reconcile only policy, commands, and skills:

```sh
./harness/install.sh --links-only
```

Reconciliation removes as well as adds. Any symlink in a managed skill or command root whose target is gone, that points into `harness/` at something no longer installed, or whose own name differs from its target's, is backed up and removed, so a renamed or retired entry cannot outlive the change that retired it. That last rule replaces a hardcoded list of retired names: a managed link is always named after its target, so a stale name is detectable structurally even when it still points at a body that is installed under its own name. A real directory shadowing a name the harness manages is backed up too, since the symlink sweep cannot see it.

One known defect is deliberately left in place here: the dangling branch removes a dangling symlink whoever wrote it, because a target that resolves to nothing cannot be tested for ownership. Two attempts to infer ownership from the link text failed in opposite directions, an absolute-path test a moved checkout defeats and a path-shape test that claims other checkouts, so the fix is a different ownership model rather than a third predicate, and it is tracked separately.

Every managed root is a real directory the harness owns, so its links and your private entries sit side by side. A symlink standing in for one is moved aside first, under a `.previous-link` suffix, and its target is left untouched: linking into someone else's directory would put managed entries somewhere this installer never sweeps, and would then aim the sweep at that directory's own entries. The OpenCode skills root is the one root normalized but never created, since OpenCode reads `~/.agents/skills` and a second copy would double-list.

OpenCode's three paths follow `XDG_CONFIG_HOME` when it is set, the same default `../lib/common.sh` resolves for the configs the root scripts place. Hardcoding `~/.config` here installed two thirds of the harness on such a machine and then asserted against the same wrong path, so it said it installed all of it.

Both run modes verify what they wrote. `check_links` asserts every skill, command, policy, and status line link on every run; `check_tools` adds the client, plugin, and interpreter assertions that only a full run can satisfy. A links-only run previously verified nothing at all, which made the mode that exists for reconciling links the one mode that never confirmed a link landed. Both run last, after Engram: `engram setup` rewrites `config.toml` and `settings.json`, which `check_links` asserts, so verifying ahead of it would check a state Engram then overwrites.

Anything in the way of a managed path is moved to a timestamped directory under `~/.dotfiles-backups/harness/` rather than overwritten. `--no-backup` deletes it instead, in both this installer and the root one, which forwards the flag:

```sh
./harness/install.sh --links-only --no-backup
```

It is destructive and unrecoverable: a private skill or a hand-edited config sitting at a managed path is gone, not archived. Each removal is still logged, so the run says what it took. Reach for it when the archives are noise, for example a repeated development install, not on a machine whose `~/.claude` or `~/.agents` you have not already reconciled.

Engram is core, not optional: the policy assumes memory survives a session. `install_engram` runs one `engram setup <agent>` per client, exactly as https://github.com/Gentleman-Programming/engram documents in `docs/AGENT-SETUP.md`, so both run modes reach it. Setup is idempotent, verified against engram 1.20.0 by running each agent's setup repeatedly in a throwaway `HOME` and checksumming the tree: every run exits 0, `[mcp_servers.engram]` stays single, and the tree is byte-identical from the second run on, the only delta being key and section reordering as the config is re-serialized.

A links-only run therefore reconciles Engram unconditionally rather than probing first. Probing was both longer and weaker: it could only see whether the plugin and MCP were present, never whether the absolute binary path each client pins still resolves, so a stale pin after a Homebrew prefix change passed the check. Running setup rewrites the pin every time.

```sh
engram setup claude-code < /dev/null
engram setup codex       < /dev/null
engram setup opencode    < /dev/null
```

Measured on a clean HOME, each command installs the full plugin, marketplace entry and all, so nothing here drives a client's plugin CLI by hand. The claude-code command asks whether to add engram's tools to the settings allowlist, so all three read from `/dev/null`: this installer never blocks on a prompt, and declining leaves the tools working under Claude Code's own permission handling. That command also writes `~/.claude/mcp/engram.json` pinned to the absolute path of the current binary, which is why `install_packages` upgrades engram before this runs: the pin is rewritten after the upgrade rather than left stale by it.

Setting up Codex also writes `[mcp_servers.engram]` in `config.toml`, which outranks the server the plugin declares in its `.mcp.json`. Nothing is lost by that: engram 1.20.0 writes `args = ["mcp", "--tools=agent"]` and the stable `/opt/homebrew/bin/engram` path, so the entry that wins carries the same agent tool profile the plugin asks for. Verified with `codex mcp list`. Upstream's configuration is kept as shipped.

The full installer uses Homebrew for Codex, OpenCode, GitHub CLI, Engram, UV, and Worktrunk; Anthropic's native latest channel for Claude Code; and official client setup commands for Engram. It never starts an interactive client or authenticates for you.

It runs on macOS and on Linux. Homebrew carries every tool on both, because three of them (OpenCode, Engram, and Worktrunk) ship only as taps, and packaging those a second way for Linux would mean three more update paths to keep honest. Codex is the single exception: its Homebrew formula is a macOS cask, so a Linux box takes `@openai/codex` from npm, which is the channel OpenAI publishes for exactly that case.

Python is the other exception, and it belongs to uv rather than to Homebrew:

```sh
uv python install 3.14
```

`PYTHON_VERSIONS` in `../lib/python.sh` is the one declaration; neither `Brewfile` nor `linux.sh` names a `python@` formula any more. That file is sourced from both sides and splits the duties: `../macos.sh` and `../linux.sh` call `install_pythons`, because packages are what those scripts are for, and this installer calls `assert_pythons` in `check_tools`, because the harness is what consumes the interpreters and so is where a missing one has to fail loudly. Neither half restates which versions those are, and the suite asserts there is no second `PYTHON_VERSIONS=(` anywhere.

Sourcing it is the one thing this installer reads from outside `harness/`. That is deliberate: the alternative was a second copy of the version list, which is exactly the drift the split exists to prevent.

uv resolves a managed version through its own registry rather than through `PATH`, so `uv run --python 3.14` finds it whatever pyenv or Homebrew have done to `python3`. That is also why `assert_pythons` asks `uv python find --managed-python` instead of testing `PATH`: a shadowing Homebrew `python3.14` would pass a `PATH` check while uv still had nothing to resolve. 3.11 was provisioned alongside it only for the SEO runtime's pin and went with it. `python-tk` is gone too, since uv's standalone builds already bundle tkinter.

`uv` therefore has to arrive before the interpreters do. On macOS it comes from `Brewfile`, on Linux from `linux.sh`'s own formula list, in both cases during the package step that runs before `install_pythons`.

What this deliberately does not do is claim the name `python3`. Each version also lands as `~/.local/bin/python3.14`, but that directory usually sits behind the pyenv shims on `PATH`, so bare `python3` keeps resolving wherever it already did. `uv python install --default` would take `python3` as well; it is experimental in uv 0.12, and taking over the interpreter every other project on the machine resolves is a bigger change than provisioning the harness needs. Run `uv python update-shell` by hand if you want uv's bin directory in front.

Homebrew still installs a `python@` of its own as a dependency of other formulae. That copy is nobody's declared interpreter, and nothing here reads it on purpose.

## Shell aliases

`aliases.sh` holds the yolo-mode launchers and is sourced from `~/.zshrc` through one managed line. The installer removes any hand-written definition of `ccyolo`, `cyolo`, or `oyolo` so the committed file is the only source, and leaves every other alias alone.

Zsh is the only shell either of the two shell-facing steps writes: the aliases go into `~/.zshrc`, and Worktrunk is asked for its zsh integration by name. A run whose `$SHELL` is something else warns and names both, rather than leaving the aliases quietly absent. Source `aliases.sh` from your own rc and run `wt config shell install` for that shell.

| Alias | Runs |
| --- | --- |
| `ccyolo` | `claude --dangerously-skip-permissions` |
| `cyolo` | `codex --dangerously-bypass-approvals-and-sandbox` |
| `oyolo` | `opencode` with `OPENCODE_PERMISSION` set to allow edit, bash, and webfetch |

OpenCode has no bypass flag: its permissions are configuration, and `OPENCODE_PERMISSION` overrides them for one run.

## Status line

The three clients expose three different amounts of surface here, so one committed script cannot serve all of them. `statusline/` holds one file per provider that has a status line at all, named after it:

| Client | File | Mechanism | What it does |
| --- | --- | --- | --- |
| Claude Code | `statusline/claude.sh` | Runs an arbitrary command and renders its stdout | Linked to `~/.claude/statusline.sh`, with `statusLine` in `settings.json` pointed at that path |
| Codex | `statusline/codex.sh` | Built in, and configured only by choosing from a fixed set of item ids | Writes `status_line` and `status_line_use_colors` into the `[tui]` table of `~/.codex/config.toml` |
| OpenCode | none | None | Nothing |

The two files are different kinds of thing, which is the whole point of the folder. `claude.sh` is a renderer Claude Code runs on every draw. `codex.sh` is a reconciler the installer runs once, because Codex draws its own line and takes item ids rather than a command. Whichever provider you are chasing, its file is the one named after it.

`claude.sh` renders the model, context-window percentage, directory and branch with a dirty marker, session duration, and reasoning effort on one line, then the five-hour and weekly rate-limit bars underneath, fetched from the OAuth usage endpoint and cached for sixty seconds in `/tmp/claude`.

`codex.sh` owns the item ids, so the installer never names them. It prints the reconciled `config.toml` on stdout and exits 3 when the file already says this, which is what lets `install.sh` take its backup only on a real change rather than mint a fresh backup root every run. Run it by hand to see the diff it would make:

```sh
./harness/statusline/codex.sh ~/.codex/config.toml
```

`status_line` takes an ordered list of built-in item ids, and the six chosen come closest to the Claude line:

```toml
[tui]
status_line = ["model-with-reasoning", "context-used", "current-dir", "git-branch", "five-hour-limit", "weekly-limit"]
status_line_use_colors = true
```

Session duration is dropped, because Codex has no item for it. `/statusline` inside Codex edits the same two keys, so a later choice made there survives until the next install run reconciles it back.

`config.toml` is hand-maintained and holds project trust decisions and hook trust hashes, so the reconciler rewrites only those two keys and leaves every other line byte for byte. Idempotence is textual: the reconciled file is a fixed point, so an unchanged run writes nothing and mints no backup. That also avoids `tomllib`, which needs Python 3.11 and so is absent from the system `python3` macOS ships.

OpenCode has no file in `statusline/` at all. Its configuration schema at https://opencode.ai/config.json has no status line field, and `@opencode-ai/plugin` exposes no hook for one, so there is nothing to render into and nothing to reconcile. A third-party TUI plugin can draw one, but it would be reverse-engineering an unsupported surface that any OpenCode release can break, which is a worse trade than doing without. An empty `opencode.sh` would only make the absence look like an oversight.

## Third-party skill updates

`.agents/skills` points to `harness/skills`. `locked-skills.sh` keeps the skills.sh call, `skills-lock.json`, and Claude bookkeeping link in one reviewed workflow:

```sh
./harness/locked-skills.sh add <owner/repo> <name>
./harness/locked-skills.sh update
./harness/locked-skills.sh remove <name>
./harness/locked-skills.sh check
```

`add` refuses invalid GitHub sources and existing lock, body, command, or bookkeeping paths before it delegates to skills.sh. `update` deliberately updates every locked body. `remove` accepts only a current lock entry and refuses unexpected body or Claude-link types. Every mutation prints the affected paths, while `check` runs Bash syntax, diff hygiene, and the harness acceptance suite.

The helper's `--help` is side-effect free. Do not probe the upstream update subcommand with `--help`: skills.sh currently treats that invocation as a full update.

Review every upstream body, security report, and diff, then commit only the approved change. Locked bodies stay pristine; behavior changes belong in a command or in `POLICY.md`. Provisioning never runs the helper, `skills add`, `skills update`, or a lockfile restore command.

A copied skill with unknown provenance remains an attributed local fork until its exact upstream is identified.

Engram and Orca-provided skills are runtime/plugin managed and never belong in `skills-lock.json`.

Binaries are the deliberate exception to all of this. Every prose body above is hash-locked and verified on each test run, while the clients themselves arrive unpinned: `curl -fsSL https://claude.ai/install.sh | bash`, `npm install --global @openai/codex@latest`, and two third-party Homebrew taps. That asymmetry is a choice, not an oversight. A locked body is a reviewed instruction this harness executes forever, so a change to one has to be read; a client is a moving target whose next version is the whole point of re-running the installer, and pinning it would freeze the harness against the clients it exists to drive. The trade is a supply chain that trusts Anthropic, OpenAI, and two tap owners at install time. Nothing else here does.

## Ponytail

Ponytail is a locked skill body, not a plugin. The plugin's mechanism was a `SessionStart` hook that turned lazy mode on for every session in every repository, plus `SubagentStart` and `UserPromptSubmit` trackers, six skills, and a config file. The harness installs none of it, and `check_links` asserts the skill body is present.

Provisioning once also uninstalled that plugin from all three clients. That code is gone: it removed a state no version of this repository ever created, since the plugin predates the harness and lived only in a hand-rolled setup. An installer that migrates away from states it never produced accumulates them forever.

What replaces it is one line in each command that writes code, `/yolo`, `/proto`, `/feedback`, and `/address-review`, saying to load and follow the skill, plus `adversarial-review` using ponytail violations as a review lens and its fix standard. That is a smaller and more precise surface than a session hook: lazy mode applies where code is written rather than to every conversation, and it costs one sentence per command rather than three hooks and five JS files. It also delivers more of the skill, because the hook injects a level-filtered condensation while the locked `SKILL.md` carries the full body, including the reuse-before-writing rung, the root-cause-not-symptom rule, and the read-fully-then-be-lazy boundary.

The trade is deliberate. `/ponytail lite|ultra` switching, the statusline, subagent inheritance, and the five auxiliary skills are gone; the intensity table survives in the body as reference prose with nothing to write the config it describes. In exchange the body is pinned in `skills-lock.json` and changes only through a reviewed `npx skills@1 update`, where the plugin previously moved 4.7.0 to 4.9.0 during an install with six agent-steering bodies changing unread.

## Roster

Commands are `/ask`, `/research`, `/triage`, `/spec`, `/create-ticket`, `/proto`, `/yolo`, `/feedback`, `/address-review`, `/land`, and `/squash-land`.

`/squash-land` is `/land` for the case where the human deciding to merge is the one typing the command: it squash merges and then lands. It is the only workflow in this harness that merges, and typing its name is the approval, so it never asks twice. What it does not do is append a merge step to `/land`: the merge is irreversible, so both the mergeability gate and the conformance check move ahead of it, and a blocking mismatch stops the merge instead of being reported after it, which is the best `/land` can manage. It also deliberately avoids `gh pr merge --delete-branch`, whose post-merge local checkout fails on a repository whose default branch is checked out in another worktree, reporting an error after the merge has already succeeded.

Local skills are `adversarial-review`, `evidence`, `grilling`, and `setup-harness`. `setup-harness` stays a skill because it installs bundled lifecycle assets that only a skill directory can carry; its guards keep it from firing on its own. `grilling` is maintained locally, under the name the routing table already used, and carries the three guards plus a self-grill mode. It replaced the locked Matt Pocock body, whose design-tree rounds ask a whole frontier at once: that is the batching this protocol exists to prevent, and it carried no self-grill mode for `/yolo` and `/triage` to call. The trade is that this body has no lock entry, so it is reviewed the way any other file here is rather than diffed against an upstream.

`/research` and `/proto` replace two locked bodies that were workflows wearing a skill's clothes: they could fire on description matching, and neither produced the artifacts `POLICY.md` now distinguishes. A `/research` finding ledger remains planning input until a planning route produces a complete contract. Publication confirmation alone does not make a research ticket implementation-ready; agreed behavior, acceptance criteria, and verification or test seams are also required. A finalized `/proto` requirements ledger is an implementation contract. As commands they are typed or they do not run, and each now emits the artifact the policy promised.

Locked Matt Pocock skills provide domain/module vocabulary, architecture surveys through `improve-codebase-architecture`, TDD, diagnosis, handoff, and conflict resolution. Locked `DietrichGebert/ponytail` provides lazy mode. Locked `pbakaus/impeccable` provides `impeccable`, the one frontend design body, covering landing pages, portfolios, and redesigns along with dashboards, data tables, and multi-step product UI. Like every locked body it is description-matchable, which is why the control on it is scope rather than a guard: no command or local skill loads it, so it never enters a workflow implicitly, and `POLICY.md` keeps the project's existing styling layer winning inside `/proto` and `/yolo` regardless. The acceptance suite asserts that no command and no local skill names it.

Impeccable comes through `locked-skills.sh` from the repository's `.agents/skills/impeccable`, like every locked body. Its own `npx impeccable install` is never used: it wires `PostToolUse` and `Stop` hook manifests into a project's client settings unasked, and it fetches an unpinned, unverified archive from the author's site, because the published npm package carries the detector CLI and no skill payload.

The body carries that hook machinery whatever installed it, plus three further routes that would break the lock, and `POLICY.md` forbids all of them. `$impeccable hooks on` runs `scripts/hook-admin.mjs`, which writes the manifests. `scripts/context.mjs` polls the author's site for a newer version and offers `npx impeccable update`, which rewrites the locked directory out from under `skills-lock.json`. `scripts/pin.mjs` mints a `$<command>` shortcut as a real skill directory in whichever harness skills directory it finds under the project root, which here is the tracked `harness/skills` that `.agents/skills` points at; `install.sh` links such a name everywhere and neither of its sweeps reclaims it, since `reconcile_orphans` skips a real directory and `retire_shadowed_skills` backs up only names on the harness roster.

The lock covers the body's bytes, not its runtime egress. Several of its scripts call the author's site for assets and generation, and its own documentation routes scans through the unpinned `npx impeccable detect`.

At 4.8 MB across 168 files it is the largest thing in `skills/` by a wide margin, against about 80 KB for every other body combined, roughly half of it a bundled font index and a browser detector. `locked-skills.sh update` re-churns all of it.

Locked `JuliusBrussee/caveman` provides `caveman-commit`, which carries the commit rules and their worked examples: subject shape, what never goes in a body, and how a breaking change or a linked issue is written. `POLICY.md` delegates to it rather than restating the rules in full. Only `skills/` is taken, which that repository licenses MIT; its compression engine is BSL and is not vendored here. Where the two disagree the policy wins, as it does for any locked body: the skill allows a 72-character subject as a hard cap, and `POLICY.md` allows 50.

`improve-codebase-architecture` produces planning input, never a change contract: keep its report and grilling read-only, do not edit `CONTEXT.md` or ADRs inline, and route a selected candidate through native plan mode, `/spec`, or `/proto` before changing files.

Deliberately removed: `to-spec` and `to-tickets`, whose templates now live inline in `/spec` and `/create-ticket` rather than behind a wrapper that overrode most of what it loaded; `code-review`, whose second axis is now a spec-conformance pass `/yolo` runs itself while holding the contract; the `grill-me` and `review` command wrappers, retired earlier, which is a separate thing from the `grill-me` skill body `grilling` now carries; the whole SEO group, twelve globally invocable names first and then the orchestrator and its locked roles, along with the `claude-seo` launcher and the 3.11 interpreter it pinned; and both frontend design bodies with the `/design` workflow and the `DESIGN.md` conformance rules that existed to serve them. `impeccable` is the one part of that group installed today, as a skill a human loads by name rather than as a workflow with conformance rules attached. No skill holds scope over a UI surface: `ponytail` claims none upstream and the policy assigns it none, so a UI surface with no design body loaded is built from the contract like any other work.

## Invocation guards

`POLICY.md` opens with the commands-and-skills split. Command storage carries it for the workflows; generated Codex adapters enforce explicit invocation through native metadata. For the four local skills, the three per-client guards carry it, and the acceptance suite asserts the full matrix. For a locked body, prose is the only control, which is why a body that must never fire on its own is not installed at all.

## GitHub lifecycle

`setup-harness` writes `docs/agents/harness.json`, creates the four configured labels, writes the Matt-skill tracker compatibility file, and copies the workflow and reconciler bundled in its skill directory. The workflow becomes active when that human-reviewed change reaches the default branch. GitHub native sub-issue and dependency relationships remain the source of truth. A blocker satisfies the ready frontier only when a merged pull request closed it; the parent closes only after every child has that same merge evidence. Closing or reopening a child always reconciles both states.

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
        frontier --> walk["walk to parents and dependents,<br>each issue reconciled once"]
        parentstate --> walk
    end

    GRAPH --> trigger

    subgraph AGENT["what the agent does with it"]
        ready --> yolo["/yolo picks up a ready ticket<br>branch: type/tracker-id-slug"]
        yolo --> inprogress["label: in-progress"]
        inprogress --> prready["pull request green and reviewed<br>label: ready-for-human"]
        prready --> humanmerge["a human decides to merge"]
        humanmerge -->|they merge it on GitHub| merged["merged, the closing reference<br>closes the ticket"]
        humanmerge -->|they type /squash-land| squashland["/squash-land<br>gates and conformance first,<br>then squash merge, then land"]
        squashland --> merged
        merged --> trigger
        merged -->|merged by someone else| land["/land reconciles the tracker<br>and retires the worktree"]
    end
```

A blocker counts as satisfied only when the issue is closed *and* a merged pull request closed it, which is why `blocker_satisfied` walks `closedByPullRequestsReferences` rather than trusting the closed state. Closing an issue by hand therefore does not open the frontier behind it.

Three contract routes converge on `/yolo`: `/spec` plus `/create-ticket` for a published ticket contract that is tracker-bound only when a tracker exists, an approved in-conversation contract from native plan mode, or `/proto` for a requirements ledger discovered by building. Contract source and tracker binding are independent: the source controls conformance, while the binding controls branch names, closing references, and label transitions. An in-conversation, `/proto`, or trackerless ticket contract is preserved in an inline `## Contract`; only a tracker-bound ticket-sourced contract can remain solely in the ticket.

`/land` is the local half of the same step: it resolves the pull request first, gates on the merge, prefers the inline contract for conformance, and falls back to the ticket when no inline contract exists. The ticket is optional, so trackerless work skips tracker transitions. A legacy trackerless pull request without either source reports that conformance cannot be reconstructed, verifies merge and default-branch health, and removes only a clean retained worktree.

`/squash-land` reaches the same local half by the other door, for the case where the human deciding to merge is the one typing the command. It runs the mergeability gate and the conformance check before the irreversible step, squash merges, and then lands exactly as above: tracker reconciled when bound, worktree retired. The reconciler sees no difference, because the closing reference closes the ticket either way.

## Validation

```sh
python3 -m unittest discover -s harness/tests -t harness/tests
```

One file per subject, and a single file runs on its own: `python3 harness/tests/test_commands.py`. Shared paths and readers live in `harness/tests/fixtures.py`; anything used by one file stays in that file.

A structural suite proves nothing about behavior. Validate a change to this directory against the sessions it actually produced, as `harness/bench/README.md` explains:

```sh
python3 harness/bench/measure.py --split <commit-date> --since <window-start>
```

Do not enable the Worktrunk Claude Code plugin. Its `UserPromptSubmit` hook rewrites the same per-branch slot `POLICY.md` uses for attempt and escalation counts, which would erase an escalation on the next prompt.

It reads Claude Code JSONL transcripts, Codex rollout JSONL, and the OpenCode SQLite database, and reports each client separately; `--client` narrows it. A metric a client does not record, such as a declined tool call in Codex or OpenCode, prints as `-` rather than zero.

Eight medians per cohort: `turns`, `tool_calls`, and `minutes` for cost, `interrupts`, `denials`, and `errors` for friction, and `commands` and `delegation` for the two things this policy actually claims to move, routing adoption and subagent use. A subagent gets a transcript of its own in both clients that delegate, and is counted as the parent's delegation rather than as a session of its own.

A hard week at work moves every one of those numbers without the harness changing. Copy `harness/bench/cohorts.example.json` to `cohorts.json` and list the project patterns that mean work, and the report splits work from personal so a deadline lands in one cohort and the other still reads the change. That file is gitignored: naming a client is the whole job of it.

Populations, not pairs. Cost and friction are the measured part; quality stays a human read of the sessions.

The suite validates shell/Python syntax, the locked-skill lifecycle helper, unique skill names, lock hashes, Claude bookkeeping links, local-vs-locked separation, command shape and task-data framing, command-versus-skill name disjointness, routing-table coverage, secret/generated-state exclusions, installer safety, collision backups, orphan retirement, idempotency, and GitHub close/reopen behavior.
