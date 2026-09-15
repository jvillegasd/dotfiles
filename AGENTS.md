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
| `lib/common.sh` | The hand-off to `harness bootstrap` and the Neovim bootstrap, shared by both |
| `lib/python.sh` | The uv-managed interpreter set, also asserted by `harness install` |
| `Brewfile` | macOS package manifest |
| `go.mod`, `cmd/harness/` | The Go module and the `harness` command, the single entry point for operating the harness |
| `internal/state/` | The per-branch oracle ladder and rabbit-hole counters behind `harness state` |
| `internal/install/` | The installer and bootstrap behind `harness install` and `harness bootstrap` |
| `internal/locks/` | The third-party skill locks behind `harness locks` |
| `internal/bench/` | The session-population comparison behind `harness bench` |
| `harness/` | Canonical policy, commands, skills, status lines, client settings, bench, and tests |
| `harness/tests/` | Runnable regression checks for the lifecycle reconciler |
| `harness/bench/` | Cohort config and the manual for `harness bench` |
| `nvim/` | Neovim config: `init.lua`, `lua/core/`, `lua/plugins/<category>/` |
| `ghostty/`, `git/`, `worktrunk/` | Configs symlinked into the home directory |
| `docs/agents/` | This repository's tracker and lifecycle configuration |
| `.github/workflows/`, `.github/scripts/` | The agent-lifecycle workflow and reconciler |
| `skills-lock.json` | Reviewed third-party skill locks |
| `.agents/skills`, `.claude/skills` | Harness skills and the Claude bookkeeping links |

## Prerequisites

macOS or Linux with zsh, Homebrew, Go 1.26 or newer (from the `Brewfile`), Python 3 (the tests run on the system `python3`), Neovim 0.10 or newer, and a Nerd Font. The GitHub tracker operations need the `gh` CLI authenticated with issue write permission. Branch worktrees use Worktrunk (`wt`) 0.61 or newer, the first release with the `--config-set` flag `harness state` passes; Orca is optional. Managed Python interpreters come from `uv`.

## Task runners

None. There is no build or task-runner manifest at the root (`Makefile`, `justfile`, `package.json`, `pyproject.toml`), so run the commands below directly rather than through a wrapper.

## Deterministic local checks

These are safe and write no tracked files, and must all pass before a change is handed off:

```sh
go vet ./...
test -z "$(gofmt -l .)"
go test ./...
go build ./...
python3 -m unittest discover -s harness/tests
python3 -m py_compile .github/scripts/reconcile-agent-lifecycle.py
go run ./cmd/harness locks check
git diff --check
```

The first four are the Go rungs: vet, formatting, the command tests that build `harness` and run it against throwaway repositories and home directories, and a compile of every package. The installer tests compare every mode against the goldens in `cmd/harness/testdata/install/`, which list each managed link, so adding or removing a skill or command means rerecording them with `go test ./cmd/harness -run TestInstallerGolden -update` and reading the diff. The Python suite runs the reconciler regression suite. `python3 -m py_compile` syntax-checks the reconciler, and `go run ./cmd/harness locks check` syntax-checks the remaining shell entry points and runs diff-hygiene checks over tracked files, built from this checkout rather than whatever `harness bootstrap` last placed on PATH. `git diff --check` catches whitespace errors and conflict markers. The lifecycle workflow in `.github/workflows/agent-lifecycle.yml` runs the reconciler remotely; the unit suite is its local equivalent.

## Behavioral acceptance

Some changes cannot be settled by the checks above, because they act on machine state or on a running client: installer symlink reconciliation, the tracked client settings, interactive authentication, Neovim and terminal rendering, and the session metrics a harness change is meant to move. Accept those by running the affected tool and observing it, never by static inspection alone.

`macos.sh`, `linux.sh`, `harness bootstrap`, and `harness install` are provisioning surfaces. Run them when the intent is to change machine state, never merely to validate a change. `--no-backup` deletes collisions instead of archiving them and is unrecoverable.

`go run ./cmd/harness install --links-only`, run from the checkout root, is the same provisioning surface with the package step removed. `go run` builds the install code from the checkout it reconciles, while the `harness` on PATH carries whatever `harness bootstrap` last built. It reconciles the policy, command, skill, and role agent links, but it still rewrites the Engram and agent-browser MCP registrations and the tracked client settings, so `engram`, `agent-browser`, and `claude` must already be installed. Run it when links need reconciling, not as a validation step.

Neovim health is read through `:checkhealth`, `:Lazy`, `:Mason`, and `:LspInfo` inside the editor. Session-population measurement for a harness change is `harness bench --split <commit-date> --since <window-start>`, documented in `harness/bench/README.md`.

## Conventions

Markdown prose is never hard-wrapped. `.editorconfig` owns indentation: two spaces for Markdown, Lua, JSON, and YAML. One plugin per file under `nvim/lua/plugins/<category>/`. Global mappings live in `nvim/lua/core/keymaps.lua`; `KEYMAPS.md` catalogues them. Machine-local git settings belong in `~/.gitconfig.local`, which this repository never tracks. Regenerate the package manifest with `brew bundle dump --describe --force --file=Brewfile` after adding or removing a package.

Locked skill bodies under `harness/skills/` are not edited in place; use `harness locks` and commit only the reviewed change. This repository's tracker is GitHub, and its lifecycle configuration lives in `docs/agents/harness.json`.
