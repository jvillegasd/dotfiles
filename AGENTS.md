# Repository guidance

This file tells an agent how to navigate, prepare, and verify this repository. It carries repository facts and conventions only.

The harness policy lives in the [harness repository](https://github.com/jvillegasd/harness) and is linked into each client's global instruction path, so it governs every repository including this one: workflow routing, the oracle ladder, planning, the escalation contract, and safety. Read that policy for process. This file never restates it, and where the two meet it is more specific: this repository's own commands, paths, and conventions win.

A nested `AGENTS.md` in a subtree, when one is added, scopes to that subtree and overrides this file there. Keep repository-wide rules here, not in a subtree, and do not widen a subtree's rules to the repository.

## What this repository is

Personal dotfiles, config-only: Neovim, Ghostty, git, and Worktrunk. The AI harness that used to live here was extracted into https://github.com/jvillegasd/harness, so this repository no longer ships policy, commands, or skills. `README.md` is the user-facing overview, `STRUCTURE.md` holds the tree and the Neovim layout, and `KEYMAPS.md` documents the mappings.

## Directories

| Path | Holds |
| --- | --- |
| `macos.sh`, `linux.sh` | Platform bootstrap and provisioning entry points |
| `lib/common.sh` | The config links and the Neovim bootstrap, shared by both |
| `lib/python.sh` | The uv-managed interpreter set, installed by both and consumed by the harness |
| `Brewfile` | macOS package manifest |
| `nvim/` | Neovim config: `init.lua`, `lua/core/`, `lua/plugins/<category>/` |
| `ghostty/`, `git/`, `worktrunk/` | Configs symlinked into the home directory |

## Prerequisites

macOS or Linux with zsh, Homebrew, Neovim 0.10 or newer, and a Nerd Font. `lib/python.sh` installs the uv-managed interpreters with `uv`. The AI harness is a separate checkout and brings its own prerequisites.

## Task runners

None. There is no build or task-runner manifest at the root (`Makefile`, `justfile`, `package.json`, `pyproject.toml`), so run the commands below directly rather than through a wrapper.

## Deterministic local checks

These are safe and write no tracked files, and must all pass before a change is handed off:

```sh
bash -n macos.sh linux.sh lib/common.sh lib/python.sh
git diff --check
```

`bash -n` syntax-checks every shell entry point, and `git diff --check` catches whitespace errors and conflict markers. There is no test suite in this repository; the harness carries its own checks in its checkout.

## Behavioral acceptance

Some changes cannot be settled by the checks above, because they act on machine state or on a running client: the config links, the tracked git config, and Neovim and terminal rendering. Accept those by running the affected tool and observing it, never by static inspection alone.

`macos.sh` and `linux.sh` are provisioning surfaces. Run them when the intent is to change machine state, never merely to validate a change. `--no-backup` deletes collisions instead of archiving them and is unrecoverable.

Neovim health is read through `:checkhealth`, `:Lazy`, `:Mason`, and `:LspInfo` inside the editor.

## Conventions

Markdown prose is never hard-wrapped. `.editorconfig` owns indentation: two spaces for Markdown, Lua, JSON, and YAML. One plugin per file under `nvim/lua/plugins/<category>/`. Global mappings live in `nvim/lua/core/keymaps.lua`; `KEYMAPS.md` catalogues them. Machine-local git settings belong in `~/.gitconfig.local`, which this repository never tracks. Regenerate the package manifest with `brew bundle dump --describe --force --file=Brewfile` after adding or removing a package.
