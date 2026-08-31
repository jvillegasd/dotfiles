# Portable AI harness

One committed source for Codex, Claude Code, and OpenCode:

- `POLICY.md` is linked to each client's global instruction path. It carries the routing table, the oracle ladder, and the escalation contract.
- `commands/` holds the workflows. They are reachable only as `/name`, in all three clients.
- `skills/` holds protocol, vocabulary, and locked third-party bodies.
- `install.sh` installs current clients/integrations, preserves mutable client state, and reconciles policy, command, and skill links individually.
- `bench/measure.py` compares the real session population before and after a harness change, reading all three clients' own session stores.
- `tests/test_harness.py` checks supply-chain and installer invariants.

## Commands and skills

A workflow is a command, not a skill. A client selects a skill by matching its description, and selects a command only when a human types `/name`, so putting the workflows in `commands/` makes "a workflow never fires on its own" true by construction instead of true by prose plus a guard per client. Commands install to `~/.claude/commands`, `~/.codex/prompts`, and `~/.config/opencode/command`.

Every command that ingests text written elsewhere, a ticket body, a review comment, an error payload, a bullet list, states that the input is task data and cannot override the workflow's constraints. The acceptance suite asserts that line is present.

A locally authored skill still carries all three invocation guards: `policy.allow_implicit_invocation: false` in its `agents/openai.yaml` for Codex, plus `disable-model-invocation: true` and `metadata."opencode/autoinvoke": "false"` in its frontmatter for Claude Code and OpenCode. Only four skills are local now, so the guard matrix covers a much smaller surface than it did when it also had to hold the workflows.

A locked body gets no guard. `agents/openai.yaml` is upstream content, not a harness sidecar, and `computedHash` covers the whole directory, so anything written inside a locked skill is clobbered by the next `skills update` without a drift warning and with the lockfile rewritten to record the loss as correct. The control that survives an update is not installing the skill: a locked body whose upstream description advertises trigger phrases it must not act on is kept out of every client's skill directory, and the code that needs it reads it from its path. The twelve `seo-*` bodies are the only ones, and `seo` reads them as `../seo-<role>/SKILL.md`.

That exclusion now also applies inside this repository. A committed `.claude/skills/<name>` link is an installed skill wherever the repository is open, so an unlinked body does not get one, and the suite asserts its absence.

## Install

The root `../install.sh` installs the harness by default. To reconcile only policy, commands, and skills:

```sh
./harness/install.sh --links-only
```

Reconciliation removes as well as adds. Any symlink in a managed skill or command root whose target is gone, or that points into `harness/` at something no longer installed, is backed up and removed, so a renamed or retired entry cannot outlive the change that retired it. Legacy bodies that are real directories rather than harness symlinks are removed by an explicit alias list, and the client-specific SEO personas under `~/.claude/agents/` are removed with them.

The SEO group is optional and is not linked by default. Add or remove it with `--with-seo` / `--without-seo`; the choice is remembered, so a later flagless run keeps it.

```sh
./harness/install.sh --with-seo
```

Engram is core, not optional: the policy assumes memory survives a session. `install_engram` reconciles all three clients the way https://github.com/Gentleman-Programming/engram documents each of them, and it is idempotent, so both run modes reach it. A links-only run checks the binary, both plugins, and the OpenCode MCP, and repairs whatever is missing instead of reporting a gap it could close.

| Client | Setup | Why |
| --- | --- | --- |
| Claude Code | plugin only | The plugin registers the MCP server, the hooks, and the Memory Protocol skill by itself. `engram setup claude-code` would duplicate all three. |
| OpenCode | `engram setup opencode` | No marketplace entry exists. The command writes the plugin, the MCP entry, and the statusline. |
| Codex | `engram setup codex`, then the explicit plugin pin | The plugin carries the MCP server and hooks, but only the setup command writes `engram-instructions.md` and `engram-compact-prompt.md`, and the compaction prompt is what puts a memory-save instruction into a compaction summary. The command's own plugin install is best-effort, so the pin still runs. |

Setting up Codex leaves `[mcp_servers.engram]` in `config.toml` next to the identical server the plugin declares in its `.mcp.json`, so the duplicate is removed afterwards. The same removal runs for Claude Code.

The full installer uses Homebrew for Codex, OpenCode, GitHub CLI, Engram, UV, RTK, and Worktrunk; Anthropic's native latest channel for Claude Code; and official client setup/plugin commands for Engram, Ponytail, and RTK. It never starts an interactive client or authenticates for you.

With the SEO group enabled it also links the portable `claude-seo` launcher. SEO Python dependencies and Chromium remain lazy and live only in the ignored per-user harness cache.

## Shell aliases

`aliases.sh` holds the yolo-mode launchers and is sourced from `~/.zshrc` through one managed line. The installer removes any hand-written definition of `ccyolo`, `cyolo`, or `oyolo` so the committed file is the only source, and leaves every other alias alone.

| Alias | Runs |
| --- | --- |
| `ccyolo` | `claude --dangerously-skip-permissions` |
| `cyolo` | `codex --dangerously-bypass-approvals-and-sandbox` |
| `oyolo` | `opencode` with `OPENCODE_PERMISSION` set to allow edit, bash, and webfetch |

OpenCode has no bypass flag: its permissions are configuration, and `OPENCODE_PERMISSION` overrides them for one run.

## Third-party skill updates

`.agents/skills` points to `harness/skills`. Every standalone third-party skill is installed with skills.sh and committed with its `skills-lock.json` entry:

```sh
npx skills@1 add <owner>/<repo> --skill <name> --agent universal -y
ln -s ../../.agents/skills/<name> .claude/skills/<name>
```

Add the bookkeeping link only for a skill that is actually installed. Review the installed body and security report before committing. Locked bodies stay pristine; behavior changes belong in a command or in `POLICY.md`.

To check and deliberately update all locked bodies:

```sh
npx skills@1 update --project --yes
git diff -- harness/skills skills-lock.json .claude/skills
```

Review every upstream diff, run the acceptance suite, and commit only the approved update. Provisioning never runs `skills add`, `skills update`, or a lockfile restore command.

Delete a locked skill in one reviewed change: remove `harness/skills/<name>`, its `skills-lock.json` entry, and `.claude/skills/<name>`. A copied skill with unknown provenance remains an attributed local fork until its exact upstream is identified.

Engram, Ponytail, and Orca-provided skills are runtime/plugin managed and never belong in `skills-lock.json`.

## Roster

Commands are `/ask`, `/triage`, `/spec`, `/create-ticket`, `/yolo`, `/feedback`, `/address-review`, and `/land`.

Local skills are `adversarial-review`, `evidence`, `seo`, and `setup-harness`. `setup-harness` stays a skill because it installs bundled lifecycle assets that only a skill directory can carry; its guards keep it from firing on its own.

Locked Matt Pocock skills provide grilling, domain/module vocabulary, TDD, research/prototyping, diagnosis, handoff, and conflict resolution. Locked `AgriciDaniel/claude-seo` bodies provide the SEO roles, none of them installed.

Deliberately removed: `to-spec` and `to-tickets`, whose templates now live inline in `/spec` and `/create-ticket` rather than behind a wrapper that overrode most of what it loaded; `code-review`, whose second axis is now a spec-conformance pass `/yolo` runs itself while holding the contract; the `grill-me` and `review` wrappers, retired earlier; and twelve globally invocable SEO names.

## Invocation guards

`POLICY.md` opens with the commands-and-skills split. Structure carries it for the workflows. For the four local skills, the three per-client guards carry it, and the acceptance suite asserts the full matrix. For a locked body, prose is the only control, which is why a body that must never fire on its own is not installed at all.

## GitHub lifecycle

`setup-harness` writes `docs/agents/harness.json`, creates the four configured labels, writes the Matt-skill tracker compatibility file, and copies the workflow and reconciler bundled in its skill directory. The workflow becomes active when that human-reviewed change reaches the default branch. GitHub native sub-issue and dependency relationships remain the source of truth. A blocker satisfies the ready frontier only when a merged pull request closed it; the parent closes only after every child has that same merge evidence. Closing or reopening a child always reconciles both states.

`/land` is the local half of the same step: it gates on the merge, verifies the merged state against the ticket, applies the transitions the workflow could not (or confirms it already did), and removes the retained worktree that `/yolo` deliberately leaves behind.

## Validation

```sh
python3 harness/tests/test_harness.py
```

A structural suite proves nothing about behavior. Validate a change to this directory against the sessions it actually produced:

```sh
python3 harness/bench/measure.py --split <commit-date> --since <window-start>
```

Do not enable the Worktrunk Claude Code plugin. Its `UserPromptSubmit` hook rewrites the same per-branch slot `POLICY.md` uses for attempt and escalation counts, which would erase an escalation on the next prompt.

It reads Claude Code JSONL transcripts, Codex rollout JSONL, and the OpenCode SQLite database, and reports each client separately; `--client` narrows it. A metric a client does not record, such as a declined tool call in Codex or OpenCode, prints as `-` rather than zero.

Populations, not pairs. Cost and friction are the measured part; quality stays a human read of the sessions.

The suite validates shell/Python syntax, unique skill names, lock hashes, Claude bookkeeping links, local-vs-locked separation, command shape and task-data framing, command-versus-skill name disjointness, routing-table coverage, secret/generated-state exclusions, installer safety, collision backups, orphan and alias retirement, idempotency, and GitHub close/reopen behavior.
