# Repository guidance

This file tells an agent how to navigate, prepare, and verify this repository. It carries repository facts and conventions only.

The harness policy in `harness/POLICY.md` is linked into each client's global instruction path and governs every repository: workflow routing, the oracle ladder, planning, the escalation contract, and safety. Read that policy for process. This file never restates it, and where the two meet it is more specific: this repository's own commands, paths, and conventions win.

A nested `AGENTS.md` in a subtree, when one is added, scopes to that subtree and overrides this file there. Keep repository-wide rules here, not in a subtree, and do not widen a subtree's rules to the repository.

## What this repository is

Personal dotfiles plus the one Harness AI installation that serves Claude Code and OpenCode. The editor and terminal configs are Neovim, Ghostty, git, and Worktrunk. `README.md` is the user-facing overview, `STRUCTURE.md` holds the full tree and the Neovim layout, and `KEYMAPS.md` documents the mappings.

## Directories

| Path | Holds |
| --- | --- |
| `macos.sh`, `linux.sh` | Platform bootstrap and provisioning entry points |
| `lib/common.sh` | Symlinking, harness call, and Neovim bootstrap, shared by both |
| `lib/python.sh` | The uv-managed interpreter set, also sourced by `harness/install.sh` |
| `Brewfile` | macOS package manifest |
| `harness/` | Canonical policy, commands, skills, installer, status lines, client settings, bench, and tests |
| `harness/tests/` | Runnable regression checks for the lifecycle reconciler |
| `harness/bench/` | Session-population measurement for harness changes |
| `nvim/` | Neovim config: `init.lua`, `lua/core/`, `lua/plugins/<category>/` |
| `ghostty/`, `git/`, `worktrunk/` | Configs symlinked into the home directory |
| `docs/agents/` | This repository's tracker and lifecycle configuration |
| `.github/workflows/`, `.github/scripts/` | The agent-lifecycle workflow and reconciler |
| `skills-lock.json` | Reviewed third-party skill locks |
| `.agents/skills`, `.claude/skills` | Harness skills and the Claude bookkeeping links |

## Prerequisites

macOS or Linux with zsh, Homebrew, Python 3 (the tests run on the system `python3`), Neovim 0.10 or newer, and a Nerd Font. The GitHub tracker operations need the `gh` CLI authenticated with issue write permission. Branch worktrees use Worktrunk (`wt`); Orca is optional. Managed Python interpreters come from `uv`.

## Task runners

None. There is no build or task-runner manifest at the root (`Makefile`, `justfile`, `package.json`, `pyproject.toml`), so run the commands below directly rather than through a wrapper.

## Deterministic local checks

These are safe and write no tracked files, and must all pass before a change is handed off:

```sh
python3 -m unittest discover -s harness/tests
python3 -m py_compile .github/scripts/reconcile-agent-lifecycle.py
bash -n macos.sh linux.sh lib/common.sh lib/python.sh harness/install.sh harness/locked-skills.sh
./harness/locked-skills.sh check
git diff --check
```

The first runs the reconciler regression suite. The next two are syntax checks for the Python reconciler and the shell entry points. `locked-skills.sh check` runs a shell syntax check and diff-hygiene checks over tracked files. `git diff --check` catches whitespace errors and conflict markers. The lifecycle workflow in `.github/workflows/agent-lifecycle.yml` runs the reconciler remotely; the unit suite is its local equivalent.

## Behavioral acceptance

Some changes cannot be settled by the checks above, because they act on machine state or on a running client: installer symlink reconciliation, the tracked client settings, interactive authentication, Neovim and terminal rendering, and the session metrics a harness change is meant to move. Accept those by running the affected tool and observing it, never by static inspection alone.

`macos.sh`, `linux.sh`, and `harness/install.sh` are provisioning surfaces. Run them when the intent is to change machine state, never merely to validate a change. `--no-backup` deletes collisions instead of archiving them and is unrecoverable.

`./harness/install.sh --links-only` is the same provisioning surface with the package step removed. It reconciles the policy, command, skill, and role agent links, but it still rewrites the Engram and agent-browser MCP registrations and the tracked client settings, so `engram`, `agent-browser`, and `claude` must already be installed. Run it when links need reconciling, not as a validation step.

Neovim health is read through `:checkhealth`, `:Lazy`, `:Mason`, and `:LspInfo` inside the editor. Session-population measurement for a harness change is `python3 harness/bench/measure.py --split <commit-date> --since <window-start>`, documented in `harness/bench/README.md`.

## Conventions

Markdown prose is never hard-wrapped. `.editorconfig` owns indentation: two spaces for Markdown, Lua, JSON, and YAML. One plugin per file under `nvim/lua/plugins/<category>/`. Global mappings live in `nvim/lua/core/keymaps.lua`; `KEYMAPS.md` catalogues them. Machine-local git settings belong in `~/.gitconfig.local`, which this repository never tracks. Regenerate the package manifest with `brew bundle dump --describe --force --file=Brewfile` after adding or removing a package.

Locked skill bodies under `harness/skills/` are not edited in place; use `harness/locked-skills.sh` and commit only the reviewed change. This repository's tracker is GitHub, and its lifecycle configuration lives in `docs/agents/harness.json`.
