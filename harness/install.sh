#!/usr/bin/env bash

set -euo pipefail
# An unmatched glob would otherwise iterate its own pattern, and a link named
# `*.md` in three command roots is a worse failure than an empty loop.
shopt -s nullglob

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The same default lib/common.sh resolves. Restated rather than sourced: this
# installer runs on its own, and lib/python.sh is the one thing it may pull in.
# A machine that moves XDG_CONFIG_HOME moves OpenCode with it, so hardcoding
# ~/.config here would install half the harness and say it installed all of
# it.
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
LINKS_ONLY=false
NO_BACKUP=false
UNINSTALL=false
CLEAR_BACKUPS=false
BACKUP_ROOT=""
# Set when the uninstall could not remove the formula, so the summary reports
# what happened rather than what was attempted.
ENGRAM_FORMULA_KEPT=false
# Fully qualified, and it has to stay the name install_packages installs: the
# bare `engram` is ambiguous in that tap, and `brew uninstall engram` resolves
# it to a cask and refuses with "Refusing to load cask ... from untrusted tap".
ENGRAM_FORMULA="gentleman-programming/tap/engram"
AGENT_BROWSER_FORMULA_KEPT=false
# Unqualified because it is homebrew-core rather than a tap, so there is no
# second formula of this name to disambiguate against.
AGENT_BROWSER_FORMULA="agent-browser"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

# The interpreter set, shared with macos.sh and linux.sh so the versions have
# one declaration. After log and die, which it uses.
source "$(dirname "$HARNESS_DIR")/lib/python.sh"

usage() {
    cat <<'EOF'
Usage: harness/install.sh [--links-only] [--no-backup]
       harness/install.sh --uninstall
       harness/install.sh --clear-backups

  --links-only   Reconcile policy, command, and skill links without installing
                 packages. Engram and agent-browser are still reconciled,
                 so both have to be installed already; a full run is what
                 installs them.
  --no-backup    Delete whatever is in the way instead of moving it to
                 ~/.dotfiles-backups. Destructive and unrecoverable: a private
                 skill or a hand-edited config sitting at a managed path is
                 gone, not archived.
  --uninstall    Remove what this installer writes: every managed link, the
                 ~/.zshrc alias block, and the tracked keys in the Claude
                 config. It reverses the installer, it does not uninstall
                 your tools, with one exception: Engram, which a full install
                 installs and registers, is removed here too, formula
                 included. Your ~/.engram memory database is kept.
                 The other packages, ~/.dotfiles-backups, this checkout, and
                 every untracked key in the Claude config are left alone.
                 Destructive and unrecoverable: what it removes is deleted,
                 not archived, so --no-backup adds nothing to it. Reinstall
                 to get the harness back; anything of your own that was
                 sitting at a managed path is gone.
  --clear-backups
                 Delete every archive under ~/.dotfiles-backups/harness/,
                 which is where an install moves whatever was in the way of a
                 managed path. Destructive and unrecoverable, and it is the
                 only copy of anything of yours an install displaced. Touches
                 nothing else in ~/.dotfiles-backups and installs nothing;
                 runs on its own.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --links-only) LINKS_ONLY=true ;;
        --no-backup) NO_BACKUP=true ;;
        --uninstall) UNINSTALL=true ;;
        --clear-backups) CLEAR_BACKUPS=true ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $arg" ;;
    esac
done

# Contradictory rather than merely redundant: --links-only names a subset of
# the install to write, and --uninstall writes none of it. Silently letting one
# win would make the flag that lost look like it did something.
if $UNINSTALL && $LINKS_ONLY; then
    die "--uninstall and --links-only are contradictory; --uninstall removes every link."
fi
# An uninstall deletes rather than archives, so --no-backup is redundant beside
# it rather than contradictory, and passing it is not an error. Archiving is
# what an install does because it displaces things it did not put there and has
# to hand them back; an uninstall removes only what this installer wrote, and a
# backup of that is a copy of the checkout it can be reinstalled from.
# A mode of its own rather than a rider on another: it writes and removes no
# harness state at all, and deleting the only copy of what an install displaced
# is worth being the whole command rather than a side effect of one.
if $CLEAR_BACKUPS && { $UNINSTALL || $LINKS_ONLY; }; then
    die "--clear-backups runs on its own; it neither installs nor uninstalls."
fi
# An `if` rather than `$UNINSTALL && NO_BACKUP=true`, which exits the script
# under `set -e` on every install run, because a false test is a failed
# command at the top level.
if $UNINSTALL; then
    NO_BACKUP=true
fi

SKILL_ROOTS=(
    "$HOME/.agents/skills"
    "$HOME/.claude/skills"
    "$CONFIG_HOME/opencode/skills"
)
COMMAND_ROOTS=(
    "$HOME/.claude/commands"
    "$CONFIG_HOME/opencode/command"
)

# Role agents are rendered into this checkout's own untracked directory and linked into each client, so a link's text is what proves this checkout wrote it. Pairs are client|root, because bash 3.2 has no associative arrays.
AGENT_OUT="$HARNESS_DIR/.generated/agents"
AGENT_ROOTS=(
    "claude|$HOME/.claude/agents"
    "opencode|$CONFIG_HOME/opencode/agents"
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

# The first copy wins. Nothing reconciles one file twice in a run today; the guard keeps a future second writer from archiving the first one's output in place of the original.
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

# The inverse of link_managed, and it tests exactly what link_managed writes: a
# symlink whose text is this source. A path that is anything else, a real file
# the user put there or a link to somebody else's copy, is left alone rather
# than removed, because the uninstall has no claim on it. backup_existing does
# the removal, so --no-backup means the same thing here as everywhere else.
unlink_managed() {
    local source="$1" destination="$2"
    [[ -L "$destination" && "$(readlink "$destination")" == "$source" ]] || return 0
    backup_existing "$destination"
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

# Homebrew carries every tool here on both platforms, because three of them
# (opencode, engram, worktrunk) ship only as taps.
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
    for formula in node gh uv worktrunk "$AGENT_BROWSER_FORMULA" anomalyco/tap/opencode gentleman-programming/tap/engram; do
        brew_latest_formula "$formula"
    done

    # The formula's caveat, run rather than printed: without the download every
    # browser call through the MCP fails mid-session. Idempotent.
    log "Downloading Chrome for Testing for agent-browser"
    if [[ "$platform" == Darwin ]]; then
        agent-browser install
    else
        # Linux only, and mandatory there: without it the browser lands
        # without its system libraries and every call fails at runtime.
        agent-browser install --with-deps
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
# The claude-code command asks whether to add engram's tools to the settings allowlist, and it is answered yes rather than left to default, because declining means Claude Code prompts on every memory call and the policy assumes memory is always available. The `y` goes only to that command: the opencode one is not known to ask anything, and answering a blind yes to whatever a future version decides to ask is not the same as answering this question. It still takes a closed stdin, so the installer never blocks on a prompt.
#
# A here-string rather than a pipe: under `set -o pipefail` a version that exits without reading stdin gives the writer SIGPIPE, the pipeline reports 141, and `set -e` kills an install that actually succeeded.
#
# The allowlist itself is deliberately not tracked in clients/claude.json. Engram is what knows its own tool set, and a tracked copy is a second declaration that goes stale silently: the copy this repository briefly carried listed 15 tools per prefix while engram 1.20.0 writes 18, so tracking it would have removed three real tools on the next install.
#
# That command also writes ~/.claude/mcp/engram.json pinned to the absolute path of the current engram binary, which is why install_packages upgrades engram before this runs: the pin is rewritten after the upgrade rather than left stale by it.
install_engram() {
    log "Reconciling Engram"
    command -v engram >/dev/null || die "Engram is missing; run without --links-only to install it."
    engram setup claude-code <<< y
    engram setup opencode < /dev/null
}

# agent-browser ships no per-client registrar, so the two registrations are
# written here rather than delegated to a `setup` command. Remove then add, so
# a re-run is idempotent and the pinned path is rewritten rather than left
# stale. OpenCode takes a JSON edit because `opencode mcp add` is interactive.
# The README carries the global scope choice and the default tool profile.
install_agent_browser() {
    local binary
    log "Reconciling agent-browser"
    binary="$(command -v agent-browser)" ||
        die "agent-browser is missing; run without --links-only to install it."

    command -v claude >/dev/null ||
        die "Claude Code is missing; run without --links-only to install it."
    claude mcp remove --scope user agent-browser >/dev/null 2>&1 || true
    claude mcp add --scope user agent-browser -- "$binary" mcp >/dev/null

    python3 - "$CONFIG_HOME/opencode/opencode.json" "$binary" <<'PY'
import json, pathlib, sys

config, binary = pathlib.Path(sys.argv[1]), sys.argv[2]
data = json.loads(config.read_text()) if config.exists() else {}
servers = data.get("mcp") or {}
servers["agent-browser"] = {
    "command": [binary, "mcp"],
    "enabled": True,
    "type": "local",
}
data["mcp"] = servers
config.parent.mkdir(parents=True, exist_ok=True)
config.write_text(json.dumps(data, indent=2) + "\n")
PY
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
                # Left alone during an uninstall. An install archives what it
                # cannot prove is its own, and the owner can fetch it back; an
                # uninstall deletes, so the same guess becomes unrecoverable.
                # A link to an unmounted volume is the ordinary case.
                $UNINSTALL && continue
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
#
# Removal is this same pass with its last two lines dropped, because stripping the managed aliases is already the first thing installing them does. The one caller-visible difference is that an uninstall does not create a missing ~/.zshrc: writing a file in order to remove nothing from it would leave the machine with more than it started with.
reconcile_aliases() {
    local mode="$1" rc="$HOME/.zshrc" reconciled status
    if [[ "$mode" == remove ]]; then
        [[ -f "$rc" ]] || return 0
    else
        [[ -f "$rc" ]] || touch "$rc"
    fi
    reconciled="$(python3 - "$rc" "$HARNESS_DIR/aliases.sh" "$mode" <<'PY'
import pathlib, re, sys

rc, source = pathlib.Path(sys.argv[1]), sys.argv[2]
remove = sys.argv[3] == "remove"
marker = "# portable-harness aliases"
# oyolo is retired, not current: a name stays here after it is dropped so a
# hand-written copy is still stripped from the shell that has one.
managed = {"ccyolo", "oyolo", "ocyolo"}
current = rc.read_text()
kept, dropped = [], False
for line in current.splitlines():
    alias = re.match(r"\s*alias\s+([A-Za-z0-9_-]+)=", line)
    if alias and alias.group(1) in managed:
        dropped = True
        continue
    if marker in line or source in line:
        dropped = True
        continue
    kept.append(line)
# A removal that found nothing changes nothing. Falling through would still
# normalize trailing blank lines and the final newline, so a ~/.zshrc that
# never had the block was rewritten and the run reported removing aliases it
# had not removed.
if remove and not dropped:
    raise SystemExit(3)
while kept and not kept[-1].strip():
    kept.pop()
if not remove:
    kept += [marker, f'[ -f "{source}" ] && source "{source}"']
kept.append("")
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
        if [[ "$mode" == remove ]]; then
            log "Removed the harness aliases from $rc"
        else
            log "Reconciled harness aliases in $rc"
        fi
    fi
}

install_aliases() { reconcile_aliases install; }
uninstall_aliases() { reconcile_aliases remove; }

# clients/claude.json declares the settings this harness owns, and every other key in a live settings.json is left alone: Orca writes hook manifests into it and `engram setup` writes permissions.allow, the plugin entry, and the marketplace entry. Those are machine state, so they are reconciled here rather than tracked, and a whole-file symlink would either version them or lose them on the next write.
#
# A tracked key replaces the live value outright, so removing a deny from the tracked file removes it from the machine. `permissions` is the one key merged a level down, which is what keeps the engram allowlist `engram setup` writes, and any class this harness does not track, while `deny` stays owned. Rewritten only when the result differs, which keeps a hand-edited settings.json otherwise alone, formatting included.
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

# The inverse of reconcile_claude_settings, and it deletes exactly what that function writes. `permissions` is merged a level down on the way in, so it is unmerged a level down on the way out: only the tracked classes go, and a class this harness never tracked stays. An emptied `permissions` is dropped rather than left as `{}`, because a key the harness introduced and no longer fills is still the harness's leftover.
#
# The status codes are the reconciler's, for the same reason it has them: exit 3 is a settings.json that already carries none of these keys, and a crash must not be able to pass for it.
remove_claude_settings() {
    local settings="$HOME/.claude/settings.json" reconciled status
    [[ -f "$settings" ]] || return 0
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
        for name in value:
            live.pop(name, None)
        if not live:
            settings.pop(key)
    else:
        settings.pop(key, None)
if json.dumps(settings, sort_keys=True) == before:
    raise SystemExit(3)
json.dump(settings, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
    )" && status=0 || status=$?
    [[ "$status" != 2 ]] || die "$settings is not a JSON object; fix it and re-run."
    [[ "$status" != 4 ]] || die "$HARNESS_DIR/clients/claude.json is unreadable or not a JSON object."
    [[ "$status" == 0 || "$status" == 3 ]] ||
        die "Removing the tracked settings from $settings failed with status $status."
    if [[ "$status" == 0 ]]; then
        backup_copy "$settings"
        printf '%s\n' "$reconciled" > "$settings"
        log "Removed the tracked Claude settings from $settings"
    fi
}

# A link is this checkout's only when its text points into AGENT_OUT, the exact-text ownership unlink_managed uses, so a private agent, a foreign link, and another checkout's dangling link are never touched. An install removes the links whose definition was retired; an uninstall removes all of them.
sweep_agent_links() {
    local pair root entry target
    for pair in "${AGENT_ROOTS[@]}"; do
        root="${pair#*|}"
        [[ -d "$root" && ! -L "$root" ]] || continue
        for entry in "$root"/*; do
            [[ -L "$entry" ]] || continue
            target="$(readlink "$entry")"
            [[ "$target" == "$AGENT_OUT/"* ]] || continue
            if $UNINSTALL || [[ ! -e "$target" ]]; then
                backup_existing "$entry"
            fi
        done
    done
}

# The generator prints every enforcement gap on each run, so what a client cannot restrict is never reported as enforced.
install_agents() {
    local pair client root entry destination status
    "$HARNESS_DIR/clients/agents.py" "$HARNESS_DIR/clients/assignments.json" "$AGENT_OUT" && status=0 || status=$?
    [[ "$status" == 0 || "$status" == 3 ]] || die "Generating the role agents failed with status $status."
    for pair in "${AGENT_ROOTS[@]}"; do
        client="${pair%%|*}" root="${pair#*|}"
        [[ ! -L "$root" && ( ! -e "$root" || -d "$root" ) ]] ||
            die "Unowned role agent root: $root"
        for entry in "$AGENT_OUT/$client"/*; do
            destination="$root/$(basename "$entry")"
            if [[ -e "$destination" || -L "$destination" ]]; then
                [[ -L "$destination" && "$(readlink "$destination")" == "$entry" ]] ||
                    die "Unowned role agent collision: $destination"
            fi
        done
    done
    for pair in "${AGENT_ROOTS[@]}"; do
        ensure_managed_dir "${pair#*|}"
    done
    sweep_agent_links
    for pair in "${AGENT_ROOTS[@]}"; do
        client="${pair%%|*}" root="${pair#*|}"
        for entry in "$AGENT_OUT/$client"/*; do
            link_managed "$entry" "$root/$(basename "$entry")"
        done
    done
}

check_agents() {
    local pair client root entry
    "$HARNESS_DIR/clients/agents.py" --check "$HARNESS_DIR/clients/assignments.json" "$AGENT_OUT" ||
        die "Role agents in $AGENT_OUT are missing, drifted, or widened."
    for pair in "${AGENT_ROOTS[@]}"; do
        client="${pair%%|*}" root="${pair#*|}"
        for entry in "$AGENT_OUT/$client"/*; do
            [[ "$(readlink "$root/$(basename "$entry")")" == "$entry" ]] ||
                die "Missing role agent link: $root/$(basename "$entry")"
        done
    done
}

remove_agents() {
    sweep_agent_links
    rm -rf "$AGENT_OUT"
    rmdir "$HARNESS_DIR/.generated" 2>/dev/null || true
}

# Follows a symlinked root on purpose. The sweep never writes through a directory this checkout does not own, so a link it left inside one fails here by name instead of passing silently.
check_agents_removed() {
    local pair root entry
    for pair in "${AGENT_ROOTS[@]}"; do
        root="${pair#*|}"
        [[ -d "$root" ]] || continue
        for entry in "$root"/*; do
            [[ ! -L "$entry" || "$(readlink "$entry")" != "$AGENT_OUT/"* ]] ||
                die "Role agent link survived the uninstall: $entry"
        done
    done
    [[ ! -e "$AGENT_OUT" ]] || die "Generated role agents survived the uninstall: $AGENT_OUT"
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

    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.claude/CLAUDE.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$CONFIG_HOME/opencode/AGENTS.md"
    install_agents
    # The SEO group is gone. Its launcher lives outside the roots the orphan
    # sweep covers, so retiring it stays an explicit line.
    backup_existing "$HOME/.local/bin/claude-seo"
}

# The two writers of a mutable client config, kept together because both have
# to run after `engram setup`. Engram rewrites settings.json and opencode.json
# from its own template: it overwrites keys this harness
# declares, drops keys it does not know, and would silently undo a reconcile
# that ran before it. The harness is the last writer, which is what makes the
# tracked values the ones a client actually reads.
reconcile_clients() {
    install_agent_browser
    reconcile_claude_settings
}

assert_plugin_count() {
    local plugin="$1" expected="$2" count
    count="$(
        claude plugin list --json |
            python3 -c 'import json,sys; d=json.load(sys.stdin); p=sys.argv[1]; items=d.get("installed",d) if isinstance(d,dict) else d; print(sum(p in (x.get("pluginId") or x.get("id") or "") for x in items))' "$plugin"
    )"
    [[ "$count" == "$expected" ]] || die "Expected $expected $plugin integration in Claude Code; found $count."
}

# What every run installs, checked on every run. The link half of the old
# smoke_check: a links-only run writes all of this and used to verify none of
# it, which left the mode that exists for reconciling links as the one mode
# that never confirmed a link landed.
check_links() {
    local command skill root
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
        # A workflow that reads external text says so, or a ticket body becomes
        # an instruction. Every command is checked, because a list to maintain
        # is a list that silently stops covering a new command.
        grep -q 'cannot override this workflow' "$command" ||
            die "Command missing the task-data constraint: $command"
    done
    [[ "$(readlink "$HOME/.claude/CLAUDE.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing Claude policy link."
    [[ "$(readlink "$CONFIG_HOME/opencode/AGENTS.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing OpenCode policy link."
    [[ -f "$HARNESS_DIR/skills/ponytail/SKILL.md" ]] || die "Missing the ponytail skill body."
    check_agents
    # Every tracked key reached the live config.
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
    [[ "$(readlink "$HOME/.claude/statusline.sh")" == "$HARNESS_DIR/statusline/claude.sh" ]] || die "Missing the Claude statusline link."
    # Claude Code executes it on every draw, so a lost mode bit breaks the status line.
    [[ -x "$HARNESS_DIR/statusline/claude.sh" ]] || die "Status line is not executable: $HARNESS_DIR/statusline/claude.sh"
}

# What only a full run installs. Separate from check_links because every
# assertion here needs a client or a package on PATH, which is exactly what
# --links-only does not install.
check_tools() {
    local command config scope
    for command in claude opencode gh python3 uv engram wt agent-browser; do
        command -v "$command" >/dev/null || die "Missing required command: $command"
    done
    assert_plugin_count engram 1
    # Installed by the root script, asserted here: the harness is what consumes
    # them, so this is where a missing one has to fail loudly.
    assert_pythons

    # Both servers, not just the new one: install_agent_browser rewrites the
    # files `engram setup` wrote, so a run that clobbered engram has to fail.
    # Engram reaches Claude Code as a plugin plus a file rather than an mcp
    # entry, so that half is the file; assert_plugin_count above covers the
    # plugin. The scope is asserted too: a leftover project-scoped entry would
    # satisfy a bare `get` while the user scope this writes stayed empty.
    scope="$(claude mcp get agent-browser)"
    grep -q 'Scope: User config' <<< "$scope" ||
        die "agent-browser is not registered in the Claude Code user scope."
    [[ -f "$HOME/.claude/mcp/engram.json" ]] ||
        die "Engram's Claude Code MCP file is missing: $HOME/.claude/mcp/engram.json"

    # Through a file: `opencode debug config` stops at the 64 KiB pipe capacity
    # whenever stdout is not a regular file, and this config passed 64 KiB, so
    # the piped form died on a JSON parse error instead of on the assertion.
    config="$(mktemp)"
    trap 'rm -f "$config"' EXIT
    opencode debug config > "$config"
    # The resolved config proves what OpenCode loads; the global file proves
    # this installer is what put it there, since a project-root opencode.json
    # merges into the resolved view and would satisfy it on its own.
    if ! python3 - "$config" "$CONFIG_HOME/opencode/opencode.json" "$(command -v agent-browser)" <<'PY'
import json, pathlib, sys

resolved = json.load(open(sys.argv[1]))
assert sum("engram" in plugin for plugin in resolved.get("plugin", [])) == 1
servers = resolved.get("mcp") or {}
assert "engram" in servers
agent_browser = servers.get("agent-browser")
assert agent_browser is not None
assert agent_browser.get("type") == "local"
assert agent_browser.get("enabled") is True
assert agent_browser.get("command") == [sys.argv[3], "mcp"]
global_config = pathlib.Path(sys.argv[2])
assert global_config.exists(), f"{global_config} is missing"
global_servers = json.loads(global_config.read_text()).get("mcp") or {}
assert global_servers.get("agent-browser", {}).get("command") == [sys.argv[3], "mcp"]
PY
    then
        die "OpenCode is missing an expected plugin or MCP server."
    fi
    rm -f "$config"
    trap - EXIT
    claude plugin validate "$HARNESS_DIR/skills" >/dev/null
    wt switch --help | grep -q -- '--no-cd'
}

summary() {
    cat <<EOF

$(printf '\033[1;32m✓ Harness AI installed.\033[0m')

Next steps (interactive; not run by this installer):
  1. Authenticate: claude auth login
  2. Authenticate OpenCode natively: /connect inside OpenCode, then OpenAI, then
     ChatGPT Plus/Pro. "Manually enter API Key" bills the API instead.
  3. Authenticate: gh auth login
  4. Restart Claude Code and OpenCode.
  5. Invoke setup-harness in each project that should use the public lifecycle.

Status line: harness/statusline/claude.sh, which Claude Code runs on every draw.
OpenCode exposes no status line surface, so it gets none.

Commands use /name in Claude Code and OpenCode.
Yolo aliases (ccyolo, ocyolo) are sourced from harness/aliases.sh; open a
new shell or run: source ~/.zshrc

Standalone third-party skills were not downloaded or updated. Their committed
bodies and skills-lock.json are the reviewed source of truth.
EOF
    if [[ -n "$BACKUP_ROOT" ]]; then
        printf '\nBackups: %s\n' "$BACKUP_ROOT"
    fi
}

# Engram, taken back off. install_packages installs it and install_engram
# registers it, so the uninstall owes both halves; leaving a registration
# behind is worse than leaving nothing, because every entry engram writes pins
# the absolute path of a binary that is about to stop existing.
#
# `brew uninstall` does none of this on its own. The formula is GoReleaser
# generated and does nothing but `bin.install "engram"`: no uninstall block, no
# post_uninstall, and `zap` is a cask stanza a formula cannot carry. So the
# package removal is last, and the configuration is removed while the binary it
# names is still on disk.
#
# ~/.engram is deliberately untouched. It is the memory database, it is the
# user's own data rather than anything this installer put there, and an
# uninstall that no longer archives is the last thing that should be deleting
# it. `engram export` is the documented way out; reinstalling finds the
# database where it was.
#
# Each client's own CLI removes what that client owns, because the plugin and
# marketplace registries are several files apiece and hand-deleting another
# tool's registry is how an uninstall goes stale. They are best effort: a
# plugin that is already gone is the state being asked for, not a failure.
uninstall_engram() {
    log "Removing Engram"
    if command -v claude >/dev/null; then
        claude plugin uninstall engram@engram >/dev/null 2>&1 || true
        claude plugin marketplace remove engram >/dev/null 2>&1 || true
    fi
    remove_engram_config
    rm -f "$HOME/.claude/mcp/engram.json"
    rm -f "$CONFIG_HOME/opencode/plugins/engram.ts"
    # engram's own docs/AGENT-SETUP.md lists three things `engram setup
    # opencode` writes, and this is the third: an OpenCode built-in enabled in
    # tui.json. It is the one entry engram writes that is not named after
    # engram, so it survives a search for the word and has to be named.
    # Last, and only what Homebrew actually has: a machine that installed
    # engram some other way keeps whatever it installed, and `brew uninstall`
    # on a formula that is not there exits non-zero for no reason worth
    # failing the run over.
    if command -v brew >/dev/null && brew list --formula "$ENGRAM_FORMULA" >/dev/null 2>&1; then
        brew uninstall "$ENGRAM_FORMULA" || {
            ENGRAM_FORMULA_KEPT=true
            warn "Could not uninstall the engram formula. Remove it with: brew uninstall $ENGRAM_FORMULA"
        }
    fi
}

# agent-browser, taken back off, in the order uninstall_engram uses and for the
# same reason: the two registrations pin the absolute path of a binary this
# function is about to delete, so they go while it still exists.
#
# Registrations before the formula, as in uninstall_engram: each one pins the
# path of the binary about to be deleted. ~/.agent-browser stays: it holds the
# browser download and whatever profiles the CLI has saved, and this installer
# does not delete another tool's data directory.
uninstall_agent_browser() {
    log "Removing agent-browser"
    # Each client's own CLI, and nothing else. Editing the config behind a
    # client that is gone means hand-rolling the format it owns, which is how
    # an uninstall corrupts a file instead of tidying it. A client removed
    # before this runs keeps its entry, so the removal says so and names the
    # file; check_agent_browser_removed reports the survivor rather than
    # failing a run that could not have removed it.
    if command -v claude >/dev/null; then
        claude mcp remove --scope user agent-browser >/dev/null 2>&1 || true
    else
        warn "Claude Code is not installed, so its agent-browser entry stays."
        warn "Remove it by hand from $HOME/.claude.json under mcpServers."
    fi
    # Read rather than let a raw traceback abort the uninstall mid-way.
    remove_agent_browser_config ||
        die "Could not edit $CONFIG_HOME/opencode/opencode.json; fix it and re-run --uninstall."''
    if command -v brew >/dev/null && brew list --formula "$AGENT_BROWSER_FORMULA" >/dev/null 2>&1; then
        brew uninstall "$AGENT_BROWSER_FORMULA" || {
            AGENT_BROWSER_FORMULA_KEPT=true
            warn "Could not uninstall the agent-browser formula. Remove it with: brew uninstall $AGENT_BROWSER_FORMULA"
        }
    fi
}

# The OpenCode half, which has no CLI to delegate to. An emptied `mcp` is
# dropped rather than left as `{}`, the rule remove_engram_config states.
remove_agent_browser_config() {
    python3 - "$CONFIG_HOME/opencode/opencode.json" <<'PY'
import json, pathlib, sys

config = pathlib.Path(sys.argv[1])
if not config.exists():
    raise SystemExit(0)
try:
    data = json.loads(config.read_text())
except ValueError as error:
    print(f"{config}: {error}", file=sys.stderr)
    raise SystemExit(2)
servers = data.get("mcp") or {}
# Nothing to remove means nothing to write. Rewriting would reformat a config
# this installer never touched, on a machine that never had the entry.
if "agent-browser" not in servers:
    raise SystemExit(0)
del servers["agent-browser"]
if servers:
    data["mcp"] = servers
else:
    data.pop("mcp", None)
config.write_text(json.dumps(data, indent=2) + "\n")
PY
}

# What the client CLIs do not own: the entries `engram setup` writes directly
# into each client's config. One pass over every file, because
# the surgery is the same shape in each and a caller that had to sequence several
# reconcilers would be the interesting part rather than the edit.
#
# Every edit is keyed on the name engram, never on position, and an emptied
# container is dropped rather than left behind as `{}`. A file that does not
# exist is a file with nothing to remove.
remove_engram_config() {
    python3 - "$HOME/.claude/settings.json" "$CONFIG_HOME/opencode/opencode.json" "$CONFIG_HOME/opencode" <<'PY'
import json, pathlib, sys

settings, opencode = (pathlib.Path(argument) for argument in sys.argv[1:3])
opencode_dir = pathlib.Path(sys.argv[3])
# Named rather than matched: this is the one thing `engram setup` writes that
# is not called engram, so nothing that searches for the word would find it.
SUBAGENT_STATUSLINE = "opencode-subagent-statusline"
# The two MCP server ids engram registers, per its docs/AGENT-SETUP.md: the
# durable user-level one and the plugin-scoped one older installs use. A
# permission entry is engram's when it names one of these, never when it merely
# contains the word: `Bash(cd ~/src/engram && cargo test)` is the user's.
TOOL_PREFIXES = ("mcp__engram__", "mcp__plugin_engram_engram__")


def rewrite(path, edit):
    """Apply `edit` to a file's text, writing only when it removed something.

    `edit` returns None for "nothing of engram's was here". That is the whole
    contract: comparing the rendered text instead would count a reformat as a
    change, rewriting a file that had no engram entries and logging that its
    engram entries were removed.
    """
    if not path.exists():
        return
    try:
        updated = edit(path.read_text())
    except (OSError, ValueError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        raise SystemExit(2)
    if updated is not None:
        path.write_text(updated)
        print(f"Removed the engram entries from {path}")


def prune_json(text, prune):
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError("expected a JSON object")
    if not prune(document):
        return None
    return json.dumps(document, indent=2) + "\n"


def drop_named(section, matches):
    """Remove matching names from a dict or list, reporting whether it did."""
    if isinstance(section, dict):
        names = [name for name in section if matches(name)]
        for name in names:
            section.pop(name)
        return bool(names), not section
    if isinstance(section, list):
        kept = [item for item in section if not matches(str(item))]
        removed = len(kept) != len(section)
        section[:] = kept
        return removed, not section
    return False, False


def claude(text):
    def prune(document):
        removed = False
        permissions = document.get("permissions")
        if isinstance(permissions, dict):
            allow = permissions.get("allow")
            if isinstance(allow, list):
                kept = [
                    entry for entry in allow
                    if not entry.startswith(TOOL_PREFIXES)
                ]
                if len(kept) != len(allow):
                    removed = True
                    if kept:
                        permissions["allow"] = kept
                    else:
                        permissions.pop("allow")
            if not permissions:
                document.pop("permissions")
        for key in ("enabledPlugins", "extraKnownMarketplaces"):
            section = document.get(key)
            # A plugin id is `engram@engram` and a marketplace is `engram`, so
            # the name is matched on its own rather than as a substring of
            # somebody else's plugin.
            dropped, empty = drop_named(
                section, lambda name: name == "engram" or name.startswith("engram@")
            )
            removed = removed or dropped
            if empty and key in document:
                document.pop(key)
        return removed

    return prune_json(text, prune)


def opencode_config(text):
    def prune(document):
        removed = False
        for key in ("mcp", "plugin"):
            dropped, empty = drop_named(
                document.get(key),
                lambda name: name == "engram" or name.endswith("/engram.ts") or name == "engram.ts",
            )
            removed = removed or dropped
            if empty and key in document:
                document.pop(key)
        return removed

    return prune_json(text, prune)


def tui(text):
    """Drop the OpenCode built-in `engram setup opencode` enables.

    Tolerant of a file it cannot parse: tui.jsonc may carry comments, and an
    uninstall is the wrong moment to fail over somebody else's editor
    settings. Leaving the entry is recoverable, refusing to finish is worse.
    """
    try:
        document = json.loads(text)
    except ValueError:
        print(f"Could not parse it, so its {SUBAGENT_STATUSLINE} entry was left", file=sys.stderr)
        return None
    if not isinstance(document, dict):
        return None
    plugins = document.get("plugin")
    if not isinstance(plugins, list) or SUBAGENT_STATUSLINE not in plugins:
        return None
    kept = [entry for entry in plugins if entry != SUBAGENT_STATUSLINE]
    if kept:
        document["plugin"] = kept
    else:
        document.pop("plugin")
    return json.dumps(document, indent=2) + "\n"


rewrite(settings, claude)
rewrite(opencode, opencode_config)
for name in ("tui.json", "tui.jsonc"):
    rewrite(opencode_dir / name, tui)
PY
}

# Everything install_links wrote, in one sweep plus three named links.
#
# reconcile_orphans with an empty desired set is the sweep: its ownership test
# is already "this link resolves into $HARNESS_DIR", which is exactly what
# makes a link this installer's to remove, so an uninstall is that function
# told that nothing is desired. Writing a second ownership predicate here is
# what would let install and uninstall disagree about what the harness owns.
#
# It carries that function's documented defect unchanged, and does not extend
# it: a dangling symlink it cannot prove is its own is archived too. At
# uninstall time the checkout is still on disk, so no link this harness wrote
# is dangling, and the case is the one already reached on every install run.
#
# The three named links are not in either root set, so the sweep never sees
# them. They go through unlink_managed, which removes a path only when it is
# still a symlink to the source the installer gave it.
uninstall_links() {
    reconcile_orphans ""
    unlink_managed "$HARNESS_DIR/POLICY.md" "$HOME/.claude/CLAUDE.md"
    unlink_managed "$HARNESS_DIR/POLICY.md" "$CONFIG_HOME/opencode/AGENTS.md"
    unlink_managed "$HARNESS_DIR/statusline/claude.sh" "$HOME/.claude/statusline.sh"
    remove_agents
}

# The mirror of check_links: the mode that removes things confirms the removal
# the way the mode that writes them confirms the write. Without it an uninstall
# that silently skipped a root would still report success, and the leftover
# would surface as a client loading a policy from a checkout that has moved.
check_removed() {
    local root entry target
    check_agents_removed
    for root in "${SKILL_ROOTS[@]}" "${COMMAND_ROOTS[@]}"; do
        [[ -d "$root" ]] || continue
        for entry in "$root"/*; do
            [[ -L "$entry" ]] || continue
            target="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$entry")"
            [[ "$target" != "$HARNESS_DIR"/* ]] || die "Managed link survived the uninstall: $entry"
        done
    done
    for entry in "$HOME/.claude/CLAUDE.md" "$CONFIG_HOME/opencode/AGENTS.md" \
        "$HOME/.claude/statusline.sh"; do
        if [[ -L "$entry" ]]; then
            target="$(readlink "$entry")"
            [[ "$target" != "$HARNESS_DIR"/* ]] || die "Managed link survived the uninstall: $entry"
        fi
    done
    if [[ -f "$HOME/.zshrc" ]]; then
        ! grep -q '# portable-harness aliases' "$HOME/.zshrc" || die "Harness aliases survived the uninstall in $HOME/.zshrc."
        ! grep -qE '^\s*alias (ccyolo|oyolo|ocyolo)=' "$HOME/.zshrc" || die "A yolo alias survived the uninstall in $HOME/.zshrc."
    fi
    # Every tracked key is gone from the live settings, and the untracked keys
    # beside them are not. Asserted by re-running the remover, where only exit
    # 3 means "the file already carries none of these": exit 0 is a key that
    # would still be deleted, and anything else is the remover failing to
    # answer the question.
    if [[ -f "$HOME/.claude/settings.json" ]]; then
        if ! python3 - "$HOME/.claude/settings.json" "$HARNESS_DIR/clients/claude.json" <<'PY'
import json, sys

live, tracked = (json.load(open(path)) for path in sys.argv[1:3])
for key, value in tracked.items():
    if key == "permissions":
        assert not set(live.get(key) or {}) & set(value), key
    else:
        assert key not in live, key
PY
        then
            die "Tracked Claude settings survived the uninstall in $HOME/.claude/settings.json."
        fi
    fi
    check_engram_removed
    check_agent_browser_removed
}

# Each surviving entry pins the path of a deleted binary. `mcp get` succeeding
# is the failure, so its exit code is read rather than ignored.
check_agent_browser_removed() {
    # The files rather than the CLIs: the removal has a file fallback for a
    # client that is gone, so a check that needs the CLI would skip exactly
    # the machines that fallback exists for. Scoped to what the uninstall
    # removes, so an unrelated project-scoped entry cannot fail the last step
    # of a run that already deleted the formula.
    local survivors
    survivors="$(python3 - "$HOME/.claude.json" <<'PY'
import json, pathlib, sys

claude = pathlib.Path(sys.argv[1])
if claude.exists():
    try:
        data = json.loads(claude.read_text())
    except ValueError:
        data = {}
    if "agent-browser" in ((data if isinstance(data, dict) else {}).get("mcpServers") or {}):
        print(claude)
PY
)"
    # A survivor beside a client that is still installed means the CLI removal
    # failed, which is this uninstall's bug. Beside one that is gone it is the
    # documented consequence of not editing another tool's config by hand.
    while IFS= read -r survivor; do
        [[ -n "$survivor" ]] || continue
        case "$survivor" in
            *.claude.json) command -v claude >/dev/null &&
                die "The agent-browser MCP survived the uninstall in $survivor." ;;
        esac
        warn "An agent-browser entry stays in $survivor; its client is not installed."
    done <<< "$survivors"
    if ! python3 - "$CONFIG_HOME/opencode/opencode.json" <<'PY'
import json, pathlib, sys

# Quietly: the caller turns a false into a message, and a traceback beside it
# only buries the one line that names the file.
config = pathlib.Path(sys.argv[1])
if config.exists() and "agent-browser" in (json.loads(config.read_text()).get("mcp") or {}):
    raise SystemExit(1)
PY
    then
        die "The agent-browser MCP survived the uninstall in $CONFIG_HOME/opencode/opencode.json."
    fi
}

# Engram leaves entries in two client configs and two loose files, and a
# survivor is worse than a leftover link: each one names the absolute path of a
# binary this uninstall just deleted, so the client fails at startup rather
# than quietly doing less.
check_engram_removed() {
    local path
    for path in "$HOME/.claude/mcp/engram.json" "$CONFIG_HOME/opencode/plugins/engram.ts"; do
        [[ ! -e "$path" ]] || die "Engram file survived the uninstall: $path"
    done
    # The containers remove_engram_config prunes, not the whole file. A grep
    # for the word died on any unrelated mention, and it died after the
    # formula and every link were already gone, so the run had no summary and
    # re-running repeated the failure.
    if ! python3 - "$HOME/.claude/settings.json" "$CONFIG_HOME/opencode/opencode.json" <<'PY'
import json, pathlib, sys

settings, opencode = (pathlib.Path(argument) for argument in sys.argv[1:3])
PREFIXES = ("mcp__engram__", "mcp__plugin_engram_engram__")


def names(section):
    return list(section) if isinstance(section, dict) else [str(i) for i in section or []]


if settings.exists():
    document = json.loads(settings.read_text())
    allow = (document.get("permissions") or {}).get("allow") or []
    assert not [e for e in allow if e.startswith(PREFIXES)], "permissions.allow"
    for key in ("enabledPlugins", "extraKnownMarketplaces"):
        assert not [n for n in names(document.get(key)) if n == "engram" or n.startswith("engram@")], key
if opencode.exists():
    document = json.loads(opencode.read_text())
    for key in ("mcp", "plugin"):
        assert "engram" not in names(document.get(key)), key
PY
    then
        die "Engram entries survived the uninstall in one of the client configs."
    fi
    for path in "$CONFIG_HOME/opencode/tui.json" "$CONFIG_HOME/opencode/tui.jsonc"; do
        [[ -f "$path" ]] || continue
        ! grep -q 'opencode-subagent-statusline' "$path" ||
            die "The engram-enabled OpenCode statusline survived the uninstall in $path"
    done
}

uninstall() {
    log "Removing the harness from this machine"
    uninstall_engram
    uninstall_agent_browser
    uninstall_links
    uninstall_aliases
    remove_claude_settings
    check_removed
    uninstall_summary
}

uninstall_summary() {
    cat <<EOF

$(printf '\033[1;32m✓ Harness AI removed.\033[0m')

Gone: every managed skill and command link, both POLICY.md links, the Claude
status line link, the role agent links and their generated definitions,
the ~/.zshrc alias block, the tracked keys in ~/.claude/settings.json, Engram:
its plugin, marketplace, and MCP registration in both clients, plus the
formula, and agent-browser: its MCP registration in both clients, plus the
formula.

Kept: ~/.engram, which is your memory database rather than anything this
installer wrote. Reinstalling finds it where it was. To take it with you:
engram export <file>   (before uninstalling, while the binary still exists)

$([[ -d "$HOME/.agent-browser" ]] && printf '%s' "
Also kept: ~/.agent-browser ($(du -sh "$HOME/.agent-browser" 2>/dev/null | cut -f1 | tr -d " ")),
the browser download and any profiles agent-browser saved beside it.
Reinstalling reuses it. Delete it yourself to reclaim the space; a fresh
machine gets the browser back from: agent-browser install")
$($ENGRAM_FORMULA_KEPT && printf '%s' "
The engram formula could not be removed and is still installed; the warning
above says so. Its configuration is gone either way.")$($AGENT_BROWSER_FORMULA_KEPT && printf '%s' "
The agent-browser formula could not be removed and is still installed; the
warning above says so. Its configuration is gone either way.")

Also left alone: the other packages (claude, opencode, worktrunk, gh, uv,
node), every untracked key in the Claude config, ~/.dotfiles-backups, and this
checkout.

Nothing was archived: an uninstall deletes what it removes. Everything above
comes back from this checkout.

Open a new shell to drop the aliases from the one you are in.
Reinstall with: $HARNESS_DIR/install.sh
EOF
}

# Every archive an install left, and nothing else in ~/.dotfiles-backups.
#
# Scoped to the harness subtree on purpose: this installer writes only under
# .../harness/, and a sibling directory there belongs to whatever wrote it. A
# command that cleared the parent would be deleting other tools' archives on
# the strength of owning one directory inside it.
#
# Each timestamped root goes separately rather than the subtree in one `rm`,
# so the log names what was deleted. That listing is the only record left
# afterwards, which is the point: there is nothing to restore from.
clear_backups() {
    local root="$HOME/.dotfiles-backups/harness" entry size count=0
    if [[ ! -d "$root" ]]; then
        log "No harness backups to delete at $root"
        return
    fi
    # `tr -d` because the du every macOS ships right-pads its size column.
    # `|| true` because `set -o pipefail` makes an unreadable subdirectory
    # under the backup root abort the command before it deletes anything, and
    # a size for the log is never worth that.
    size="$(du -sh "$root" 2>/dev/null | cut -f1 | tr -d ' ' || true)"
    for entry in "$root"/*; do
        rm -rf "$entry"
        log "Deleted $entry"
        count=$((count + 1))
    done
    # Only when it is empty, and never the parent: `rmdir` refusing a
    # non-empty directory is the guard, so a file this loop did not match
    # keeps the directory rather than being swept with it.
    rmdir "$root" 2>/dev/null || true
    log "Deleted $count harness backup(s), ${size:-unknown} reclaimed."
}

main() {
    # Ahead of the uninstall, which is itself ahead of the install: this mode
    # touches no client and no package, so none of what follows applies to it.
    if $CLEAR_BACKUPS; then
        clear_backups
        return
    fi
    # Ahead of everything, including warn_unless_zsh: an uninstall runs none of
    # the two steps that warning is about.
    if $UNINSTALL; then
        uninstall
        return
    fi
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
    # Both after Engram: `engram setup` rewrites settings.json and opencode.json,
    # so reconciling ahead of it would write a state Engram then overwrites,
    # and verifying ahead of it would check one.
    reconcile_clients
    check_links
    $LINKS_ONLY || check_tools
    summary
}

main
