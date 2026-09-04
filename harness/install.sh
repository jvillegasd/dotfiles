#!/usr/bin/env bash

set -euo pipefail
# An unmatched glob would otherwise iterate its own pattern, and a link named
# `*.md` in three command roots is a worse failure than an empty loop.
shopt -s nullglob

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The same default lib/common.sh resolves. Restated rather than sourced: this
# installer runs on its own, and lib/python.sh is the one thing it may pull in.
# A machine that moves XDG_CONFIG_HOME moves OpenCode with it, so hardcoding
# ~/.config here would install two thirds of the harness and say it installed
# all of it.
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
LINKS_ONLY=false
NO_BACKUP=false
BACKUP_ROOT=""

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

# The interpreter set, shared with macos.sh and linux.sh so the versions have
# one declaration. After log and die, which it uses.
source "$(dirname "$HARNESS_DIR")/lib/python.sh"

usage() {
    cat <<'EOF'
Usage: harness/install.sh [--links-only] [--no-backup]

  --links-only   Reconcile policy, command, and skill links without installing
                 packages. Engram is still reconciled, so it has to be
                 installed already; a full run is what installs it.
  --no-backup    Delete whatever is in the way instead of moving it to
                 ~/.dotfiles-backups. Destructive and unrecoverable: a private
                 skill or a hand-edited config sitting at a managed path is
                 gone, not archived.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --links-only) LINKS_ONLY=true ;;
        --no-backup) NO_BACKUP=true ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $arg" ;;
    esac
done

SKILL_ROOTS=(
    "$HOME/.agents/skills"
    "$HOME/.claude/skills"
    "$CONFIG_HOME/opencode/skills"
)
COMMAND_ROOTS=(
    "$HOME/.claude/commands"
    "$HOME/.codex/prompts"
    "$CONFIG_HOME/opencode/command"
)

skill_names() {
    find "$HARNESS_DIR/skills" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort
}

ensure_backup_root() {
    if [[ -z "$BACKUP_ROOT" ]]; then
        BACKUP_ROOT="$HOME/.dotfiles-backups/harness/$(date +%Y%m%d-%H%M%S)-$$"
        mkdir -p "$BACKUP_ROOT"
    fi
}

# A directory symlink is backed up under a suffixed name: parking it at the
# plain path would leave a symlink where a later backup expects a directory,
# and that backup would then write through it into the link's target.
backup_existing() {
    local path="$1" suffix="${2-}" relative backup
    [[ -e "$path" || -L "$path" ]] || return 0
    if $NO_BACKUP; then
        rm -rf "$path"
        log "Removed $path"
        return
    fi
    ensure_backup_root
    relative="${path#"$HOME"/}"
    backup="$BACKUP_ROOT/$relative$suffix"
    mkdir -p "$(dirname "$backup")"
    mv "$path" "$backup"
    log "Backed up $path -> $backup"
}

# The first copy wins. Two functions reconcile ~/.codex/config.toml, the status
# line and the tracked settings, so a second copy would archive the first one's
# output and the backup would no longer be the file this run started with.
backup_copy() {
    local path="$1" relative backup
    [[ -f "$path" ]] || return 0
    if $NO_BACKUP; then
        return
    fi
    ensure_backup_root
    relative="${path#"$HOME"/}"
    backup="$BACKUP_ROOT/$relative.pre-reconcile"
    if [[ -f "$backup" ]]; then
        return 0
    fi
    mkdir -p "$(dirname "$backup")"
    cp -p "$path" "$backup"
}

link_managed() {
    local source="$1" destination="$2"
    if [[ -L "$destination" && "$(readlink "$destination")" == "$source" ]]; then
        return
    fi
    backup_existing "$destination"
    mkdir -p "$(dirname "$destination")"
    ln -s "$source" "$destination"
    log "Linked $destination -> $source"
}

# The harness owns a real directory at every root it links into or sweeps, so
# its links and a user's private entries can sit side by side. Anything else at
# the path is moved aside; a symlink included, because linking into someone
# else's directory would write managed entries somewhere this installer never
# sweeps, and the orphan sweep would then archive that directory's own entries.
#
# `create` is false for a root the harness reads but never populates: normalize
# what is already there, and leave the path absent otherwise.
ensure_managed_dir() {
    local destination="$1" create="${2:-true}"
    if [[ -L "$destination" ]]; then
        backup_existing "$destination" .previous-link
    elif [[ -e "$destination" && ! -d "$destination" ]]; then
        backup_existing "$destination"
    fi
    if [[ "$create" == true ]]; then
        mkdir -p "$destination"
    fi
}

brew_latest_formula() {
    local formula="$1"
    if brew list --formula "$formula" >/dev/null 2>&1; then
        brew upgrade "$formula"
    else
        brew install "$formula"
    fi
}

brew_latest_cask() {
    local cask="$1"
    if brew list --cask "$cask" >/dev/null 2>&1; then
        brew upgrade --cask "$cask"
    else
        brew install --cask "$cask"
    fi
}

# Homebrew carries every tool here on both platforms, because three of them
# (opencode, engram, worktrunk) ship only as taps. Codex is the one
# exception: its Homebrew formula is a macOS cask, so a Linux box takes the npm
# package OpenAI publishes for exactly that case.
install_packages() {
    local platform
    platform="$(uname -s)"
    case "$platform" in
        Darwin|Linux) ;;
        *) die "The harness installer supports macOS and Linux, not $platform." ;;
    esac
    command -v brew >/dev/null || die "Homebrew is required; run the root ./macos.sh or ./linux.sh first."

    log "Installing current AI clients and harness tools"
    brew tap anomalyco/tap
    brew tap gentleman-programming/tap
    for formula in node gh uv worktrunk anomalyco/tap/opencode gentleman-programming/tap/engram; do
        brew_latest_formula "$formula"
    done
    if [[ "$platform" == Darwin ]]; then
        brew_latest_cask codex
    else
        log "Installing Codex from npm (the Homebrew cask is macOS only)"
        npm install --global @openai/codex@latest
    fi

    log "Installing Claude Code from Anthropic's latest native channel"
    curl -fsSL https://claude.ai/install.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
}

# Per-agent setup, exactly as https://github.com/Gentleman-Programming/engram
# documents it in docs/AGENT-SETUP.md: one `engram setup <agent>` per client,
# and nothing else. Measured on a clean HOME, each command installs the full
# plugin, marketplace entry and all, so nothing here drives a client's plugin
# CLI by hand.
#
# The claude-code command asks whether to add engram's tools to the settings
# allowlist, so all three read from /dev/null: this installer never blocks on a
# prompt, and declining leaves the tools working with Claude Code's own
# permission handling. That command also writes ~/.claude/mcp/engram.json
# pinned to the absolute path of the current engram binary, which is why
# install_packages upgrades engram before this runs: the pin is rewritten after
# the upgrade rather than left stale by it.
#
# Setting up Codex also writes `[mcp_servers.engram]` in config.toml, which
# outranks the server the plugin declares in its .mcp.json. Nothing is lost:
# engram 1.20.0 writes `args = ["mcp", "--tools=agent"]` and the stable
# /opt/homebrew/bin/engram path, so the entry that wins carries the same agent
# tool profile the plugin asks for. Upstream's configuration is kept as
# shipped.
install_engram() {
    log "Reconciling Engram"
    command -v engram >/dev/null || die "Engram is missing; run without --links-only to install it."
    engram setup claude-code < /dev/null
    engram setup codex < /dev/null
    engram setup opencode < /dev/null
}

# Both of these write zsh and only zsh: the aliases go into ~/.zshrc, and
# worktrunk is asked for its zsh integration by name. Neither is worth a second
# implementation, but a user on another shell has to be told what they did not
# get, or the aliases are simply missing and nothing says why.
warn_unless_zsh() {
    [[ "${SHELL##*/}" != zsh ]] || return 0
    warn "Your login shell is ${SHELL:-unknown}, not zsh. The yolo aliases go into"
    warn "~/.zshrc and Worktrunk gets its zsh integration. Source"
    warn "$HARNESS_DIR/aliases.sh from your own shell rc, and run"
    warn "\`wt config shell install\` for the shell you use."
}

install_integrations() {
    install_engram

    log "Reconciling Worktrunk"
    wt config shell install --yes zsh
}

# A real directory shadowing a name this harness manages. It survives the
# orphan sweep because it is not a symlink, and it stays live in the client
# whether or not the harness links that name.
retire_shadowed_skills() {
    local root name
    for root in "${SKILL_ROOTS[@]}"; do
        [[ -d "$root" ]] || continue
        while IFS= read -r name; do
            if [[ -e "$root/$name" && ! -L "$root/$name" ]]; then
                backup_existing "$root/$name"
            fi
        done < <(skill_names)
    done
}

# Anything this harness installed and no longer installs is removed, so a
# renamed, retired, or unlinked entry cannot outlive the change that retired
# it. A dangling symlink is removed wherever it points.
#
# That last sentence is a known defect, deliberately left alone here: the sweep
# cannot tell its own dangling links from a user's, because a dangling target
# resolves to nothing to test. Two attempts to infer ownership from the link
# text failed in opposite directions, an absolute-path test that a moved
# checkout defeats and a path-shape test that claims other checkouts, so the
# fix is a different way of deciding ownership rather than a third
# predicate, and it needs its own contract. Tracked separately; do not
# patch it in passing.

reconcile_orphans() {
    local desired="$1" root entry target
    for root in "${SKILL_ROOTS[@]}" "${COMMAND_ROOTS[@]}"; do
        [[ -d "$root" ]] || continue
        for entry in "$root"/*; do
            [[ -L "$entry" ]] || continue
            target="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$entry")"
            if [[ ! -e "$target" ]]; then
                backup_existing "$entry"
            elif [[ "$target" == "$HARNESS_DIR"/* ]]; then
                # A managed link is always named after its target, so a name
                # this harness no longer installs is an orphan even when it
                # still points at a body that is installed under its own name.
                if [[ "$desired" != *"|$target|"* ]] ||
                    [[ "$(basename "$entry")" != "$(basename "$target")" ]]; then
                    backup_existing "$entry"
                fi
            fi
        done
    done
}

# One sourced line rather than copied aliases, so the committed file stays the
# only definition. Hand-written duplicates of the same aliases are removed:
# two definitions of a yolo alias is one too many to reason about.
#
# "Unchanged" is exit 3, so a crash cannot pass for it. The overloaded 1 read
# an unreadable ~/.zshrc, or a missing python3, as "nothing to do" and left the
# aliases silently uninstalled while the run reported success.
install_aliases() {
    local rc="$HOME/.zshrc" reconciled status
    [[ -f "$rc" ]] || touch "$rc"
    reconciled="$(python3 - "$rc" "$HARNESS_DIR/aliases.sh" <<'PY'
import pathlib, re, sys

rc, source = pathlib.Path(sys.argv[1]), sys.argv[2]
marker = "# portable-harness aliases"
managed = {"ccyolo", "cyolo", "oyolo"}
current = rc.read_text()
kept = []
for line in current.splitlines():
    alias = re.match(r"\s*alias\s+([A-Za-z0-9_-]+)=", line)
    if alias and alias.group(1) in managed:
        continue
    if marker in line or source in line:
        continue
    kept.append(line)
while kept and not kept[-1].strip():
    kept.pop()
kept += [marker, f'[ -f "{source}" ] && source "{source}"', ""]
text = "\n".join(kept)
if text == current:
    raise SystemExit(3)
sys.stdout.write(text)
PY
    )" && status=0 || status=$?
    [[ "$status" == 0 || "$status" == 3 ]] || die "Could not reconcile aliases in $rc."
    if [[ "$status" == 0 ]]; then
        backup_copy "$rc"
        printf '%s\n' "$reconciled" > "$rc"
        log "Reconciled harness aliases in $rc"
    fi
}

# clients/claude.json declares the settings this harness owns, and every other
# key in a live settings.json is left alone: Orca writes hook manifests into it
# and `engram setup` writes permissions.allow, the plugin entry, and the
# marketplace entry. Those are machine state, so they are reconciled here
# rather than tracked, and a whole-file symlink would either version them or
# lose them on the next write.
#
# A tracked key replaces the live value outright, so removing a deny from the
# tracked file removes it from the machine. `permissions` is the one key merged
# a level down, which is what keeps the engram allowlist while `deny` stays
# owned. Rewritten only when the result differs, which keeps a hand-edited
# settings.json otherwise alone, formatting included.
#
# The reconciled file is emitted on stdout and written here, rather than
# written in place, so the backup is taken only when something actually
# changes. Backing up unconditionally minted a fresh backup root on every run.
#
# "Already correct" is its own exit code rather than the catch-all 1, so a
# settings.json that cannot be read at all is fatal and says which file. The
# overloaded 1 read every crash as "nothing to do": a file that was valid JSON
# but not an object, or unreadable, or a missing python3, all left the settings
# unreconciled while the run went on to report success.
reconcile_claude_settings() {
    local settings="$HOME/.claude/settings.json" reconciled status
    mkdir -p "$(dirname "$settings")"
    [[ -f "$settings" ]] || printf '{}\n' > "$settings"
    reconciled="$(python3 - "$settings" "$HARNESS_DIR/clients/claude.json" <<'PY'
import json, sys

path, tracked_path = sys.argv[1], sys.argv[2]
try:
    with open(path) as handle:
        settings = json.load(handle)
    if not isinstance(settings, dict):
        raise TypeError(f"expected a JSON object, found {type(settings).__name__}")
except (OSError, ValueError, TypeError) as error:
    print(error, file=sys.stderr)
    raise SystemExit(2)
# Its own status, because a defect in the tracked file is a repository bug and
# telling the user to fix their settings.json names the wrong file.
try:
    with open(tracked_path) as handle:
        tracked = json.load(handle)
    if not isinstance(tracked, dict):
        raise TypeError(f"expected a JSON object, found {type(tracked).__name__}")
except (OSError, ValueError, TypeError) as error:
    print(error, file=sys.stderr)
    raise SystemExit(4)
before = json.dumps(settings, sort_keys=True)
for key, value in tracked.items():
    live = settings.get(key)
    if key == "permissions" and isinstance(live, dict):
        settings[key] = {**live, **value}
    else:
        settings[key] = value
if json.dumps(settings, sort_keys=True) == before:
    raise SystemExit(3)
json.dump(settings, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
    )" && status=0 || status=$?
    [[ "$status" != 2 ]] || die "$settings is not a JSON object; fix it and re-run."
    [[ "$status" != 4 ]] || die "$HARNESS_DIR/clients/claude.json is unreadable or not a JSON object."
    [[ "$status" == 0 || "$status" == 3 ]] ||
        die "Reconciling $settings failed with status $status."
    if [[ "$status" == 0 ]]; then
        backup_copy "$settings"
        printf '%s\n' "$reconciled" > "$settings"
        log "Reconciled the tracked Claude settings in $settings"
    fi
}

# Both writers of ~/.codex/config.toml, the tracked settings and the status
# line. Each provider's status line lives in statusline/, one file per
# provider: claude.sh is the renderer Claude Code runs on every draw, while
# codex.sh is a reconciler, because Codex draws its own line and takes a list
# of built-in item ids instead of a command. Either way the write stays here,
# so the backup is taken only on a real change.
#
# Both print their reconciled file and exit 3 when the config already says
# this. Anything but 0 or 3 is fatal rather than "nothing to do": a bare `if`
# read an unreadable config, and a missing python3, as already reconciled, and
# the run went on to report success having written nothing. Exit 4 is a defect
# in the tracked file, which is a repository bug rather than the user's.
write_reconciled_codex() {
    local reconciler="$1" what="$2" config="$HOME/.codex/config.toml"
    local reconciled status
    mkdir -p "$(dirname "$config")"
    reconciled="$("$reconciler" "$config")" && status=0 || status=$?
    [[ "$status" != 4 ]] || die "$HARNESS_DIR/clients/codex.toml is unreadable."
    [[ "$status" == 0 || "$status" == 3 ]] ||
        die "Reconciling $what in $config failed with status $status."
    if [[ "$status" == 0 ]]; then
        backup_copy "$config"
        printf '%s\n' "$reconciled" > "$config"
        log "Reconciled $what in $config"
    fi
}

install_links() {
    local skill source command root desired="|"
    ensure_managed_dir "$HOME/.agents/skills"
    ensure_managed_dir "$HOME/.claude/skills"
    # Never created, only normalized: OpenCode reads ~/.agents/skills, so this
    # root exists here just to be swept, and a symlink standing in for it would
    # aim that sweep at a directory the harness does not own.
    ensure_managed_dir "$CONFIG_HOME/opencode/skills" false
    for root in "${COMMAND_ROOTS[@]}"; do
        ensure_managed_dir "$root"
    done
    retire_shadowed_skills

    while IFS= read -r skill; do
        desired+="$HARNESS_DIR/skills/$skill|"
    done < <(skill_names)
    for command in "$HARNESS_DIR"/commands/*.md; do
        desired+="$command|"
    done
    reconcile_orphans "$desired"

    while IFS= read -r skill; do
        source="$HARNESS_DIR/skills/$skill"
        # OpenCode reads ~/.agents/skills, so a second copy would double-list.
        backup_existing "$CONFIG_HOME/opencode/skills/$skill"
        [[ "$desired" == *"|$source|"* ]] || continue
        link_managed "$source" "$HOME/.agents/skills/$skill"
        link_managed "$source" "$HOME/.claude/skills/$skill"
    done < <(skill_names)

    for command in "$HARNESS_DIR"/commands/*.md; do
        for root in "${COMMAND_ROOTS[@]}"; do
            link_managed "$command" "$root/$(basename "$command")"
        done
    done

    link_managed "$HARNESS_DIR/statusline/claude.sh" "$HOME/.claude/statusline.sh"

    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.codex/AGENTS.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.claude/CLAUDE.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$CONFIG_HOME/opencode/AGENTS.md"
    # The SEO group is gone. Its launcher lives outside the roots the orphan
    # sweep covers, so retiring it stays an explicit line.
    backup_existing "$HOME/.local/bin/claude-seo"
}

# The three writers of a mutable client config, kept together because all three
# have to run after `engram setup`. Engram rewrites settings.json and
# config.toml from its own template: it overwrites keys this harness declares,
# drops keys it does not know, and would silently undo a reconcile that ran
# before it. The harness is the last writer, which is what makes the tracked
# values the ones a client actually reads.
reconcile_clients() {
    reconcile_claude_settings
    write_reconciled_codex "$HARNESS_DIR/clients/codex.sh" "the tracked Codex settings"
    write_reconciled_codex "$HARNESS_DIR/statusline/codex.sh" "the Codex status line"
}

# The listing is fetched before the substitution rather than inside a `case`
# within one: bash 3.2, which is the system bash every macOS ships, cannot
# parse `case ... esac` inside `$( )`. `bash -n` does not catch it, because a
# command substitution is parsed when it runs.
assert_plugin_count() {
    local client="$1" plugin="$2" expected="$3" listing count
    if [[ "$client" == codex ]]; then
        listing="$(codex plugin list --json)"
    else
        listing="$(claude plugin list --json)"
    fi
    count="$(
        printf '%s' "$listing" |
            python3 -c 'import json,sys; d=json.load(sys.stdin); p=sys.argv[1]; items=d.get("installed",d) if isinstance(d,dict) else d; print(sum(p in (x.get("pluginId") or x.get("id") or "") for x in items))' "$plugin"
    )"
    [[ "$count" == "$expected" ]] || die "Expected $expected $plugin integration in $client; found $count."
}

# What every run installs, checked on every run. The link half of the old
# smoke_check: a links-only run writes all of this and used to verify none of
# it, which left the mode that exists for reconciling links as the one mode
# that never confirmed a link landed.
check_links() {
    local command skill root script status
    for skill in "$HARNESS_DIR"/skills/*; do
        local name; name="$(basename "$skill")"
        [[ -f "$skill/SKILL.md" ]] || die "Missing SKILL.md: $skill"
        [[ ! -e "$CONFIG_HOME/opencode/skills/$name" && ! -L "$CONFIG_HOME/opencode/skills/$name" ]] || die "Duplicate OpenCode skill path: $skill"
        [[ -L "$HOME/.agents/skills/$name" ]] || die "Missing shared skill link: $skill"
        [[ -L "$HOME/.claude/skills/$name" ]] || die "Missing Claude skill link: $skill"
    done
    for command in "$HARNESS_DIR"/commands/*.md; do
        for root in "${COMMAND_ROOTS[@]}"; do
            [[ -L "$root/$(basename "$command")" ]] || die "Missing command link: $root/$(basename "$command")"
        done
        grep -q '^description:' "$command" || die "Command without a description: $command"
    done
    # A workflow that reads external text says so, or a ticket body becomes an
    # instruction.
    for command in address-review create-ticket feedback land proto research triage yolo; do
        grep -q 'cannot override this workflow' "$HARNESS_DIR/commands/$command.md" ||
            die "Command missing the task-data constraint: $command"
    done
    [[ "$(readlink "$HOME/.codex/AGENTS.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing Codex policy link."
    [[ "$(readlink "$HOME/.claude/CLAUDE.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing Claude policy link."
    [[ "$(readlink "$CONFIG_HOME/opencode/AGENTS.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing OpenCode policy link."
    [[ -f "$HARNESS_DIR/skills/ponytail/SKILL.md" ]] || die "Missing the ponytail skill body."
    # Every tracked key reached the live config. Each TOML half asserts by
    # re-running its own reconciler, where only exit 3 means "the config
    # already says this": exit 0 is a key that would still change, and
    # anything else is the reconciler failing to answer the question.
    if ! python3 - "$HOME/.claude/settings.json" "$HARNESS_DIR/clients/claude.json" <<'PY'
import json, sys

live, tracked = (json.load(open(path)) for path in sys.argv[1:3])
for key, value in tracked.items():
    if key == "permissions":
        owned = live.get(key) or {}
        assert all(owned.get(name) == entry for name, entry in value.items()), key
    else:
        assert live.get(key) == value, key
PY
    then
        die "Tracked Claude settings are not reconciled in $HOME/.claude/settings.json."
    fi
    # Ahead of the re-run below, which executes these directly: a lost mode bit
    # is exit 126 there, and "reports 126, expected 3" reads as a
    # reconciliation failure rather than the permission problem it is.
    for script in "$HARNESS_DIR"/statusline/*.sh "$HARNESS_DIR"/clients/*.sh; do
        [[ -x "$script" ]] || die "Reconciler is not executable: $script"
    done
    for script in "$HARNESS_DIR/clients/codex.sh" "$HARNESS_DIR/statusline/codex.sh"; do
        "$script" "$HOME/.codex/config.toml" >/dev/null && status=0 || status=$?
        [[ "$status" == 3 ]] ||
            die "$script reports $status against $HOME/.codex/config.toml; expected 3, already reconciled."
    done
    [[ "$(readlink "$HOME/.claude/statusline.sh")" == "$HARNESS_DIR/statusline/claude.sh" ]] || die "Missing the Claude statusline link."
    grep -q '^status_line = \[' "$HOME/.codex/config.toml" || die "Missing the Codex status line."
}

# What only a full run installs. Separate from check_links because every
# assertion here needs a client or a package on PATH, which is exactly what
# --links-only does not install.
check_tools() {
    local command
    for command in codex claude opencode gh python3 uv engram wt; do
        command -v "$command" >/dev/null || die "Missing required command: $command"
    done
    assert_plugin_count codex engram 1
    assert_plugin_count claude engram 1
    # Installed by the root script, asserted here: the harness is what consumes
    # them, so this is where a missing one has to fail loudly.
    assert_pythons

    opencode debug config |
        python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("plugin",[]); assert sum("engram" in x for x in p)==1; assert "engram" in d.get("mcp",{})'
    claude plugin validate "$HARNESS_DIR/skills" >/dev/null
    wt switch --help | grep -q -- '--no-cd'
}

summary() {
    cat <<EOF

$(printf '\033[1;32m✓ Harness AI installed.\033[0m')

Next steps (interactive; not run by this installer):
  1. Authenticate: codex login
  2. Authenticate: claude auth login
  3. Authenticate: opencode auth login
  4. Authenticate: gh auth login
  5. Restart Codex, Claude Code, and OpenCode.
  6. In Codex, open /hooks and trust the Engram hooks you reviewed.
  7. Invoke setup-harness in each project that should use the public lifecycle.

Status line: one file per provider under harness/statusline/. Claude Code runs
claude.sh on every draw; codex.sh wrote the matching built-in items into [tui]
status_line in ~/.codex/config.toml. OpenCode exposes no status line surface,
so it gets none.

Commands are installed for all three clients as /name.
Yolo aliases (ccyolo, cyolo, oyolo) are sourced from harness/aliases.sh; open a
new shell or run: source ~/.zshrc

Standalone third-party skills were not downloaded or updated. Their committed
bodies and skills-lock.json are the reviewed source of truth.
EOF
    if [[ -n "$BACKUP_ROOT" ]]; then
        printf '\nBackups: %s\n' "$BACKUP_ROOT"
    fi
}

main() {
    # First, so the warning precedes the two steps it is about rather than
    # reporting them after both have already skipped what they skip.
    warn_unless_zsh
    if ! $LINKS_ONLY; then
        install_packages
        install_integrations
    fi
    install_links
    install_aliases
    # Engram is core: the policy assumes memory survives a session. A links-only
    # run skips package work, so it reconciles Engram unconditionally rather
    # than probing first. Probing only ever saw presence, never the absolute
    # binary path pinned in each client's config, so a stale pin passed the
    # check; setup rewrites the pin every time.
    if $LINKS_ONLY; then
        install_engram
    fi
    # Both after Engram: `engram setup` rewrites config.toml and settings.json,
    # so reconciling ahead of it would write a state Engram then overwrites,
    # and verifying ahead of it would check one.
    reconcile_clients
    check_links
    $LINKS_ONLY || check_tools
    summary
}

main
