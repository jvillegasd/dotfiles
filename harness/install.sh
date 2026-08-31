#!/usr/bin/env bash

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINKS_ONLY=false
WITH_SEO=false
SEO_SET=false
NO_BACKUP=false
BACKUP_ROOT=""
GROUPS_FILE="${XDG_CACHE_HOME:-$HOME/.cache}/portable-harness/groups"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: harness/install.sh [--links-only] [--with-seo|--without-seo] [--no-backup]

  --links-only   Reconcile policy, command, and skill links without packages/plugins.
  --with-seo     Also link the optional SEO skill group and its launcher.
  --without-seo  Unlink the optional SEO group (the default for a fresh install).
  --no-backup    Delete whatever is in the way instead of moving it to
                 ~/.dotfiles-backups. Destructive and unrecoverable: a private
                 skill or a hand-edited config sitting at a managed path is
                 gone, not archived.

The SEO choice is remembered, so a later run without either flag keeps it.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --links-only) LINKS_ONLY=true ;;
        --with-seo) WITH_SEO=true; SEO_SET=true ;;
        --without-seo) WITH_SEO=false; SEO_SET=true ;;
        --no-backup) NO_BACKUP=true ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown argument: $arg" ;;
    esac
done

resolve_groups() {
    if ! $SEO_SET && [[ -f "$GROUPS_FILE" ]] && grep -qx seo "$GROUPS_FILE"; then
        WITH_SEO=true
    fi
    mkdir -p "$(dirname "$GROUPS_FILE")"
    if $WITH_SEO; then printf 'seo\n' > "$GROUPS_FILE"; else : > "$GROUPS_FILE"; fi
}

SKILL_ROOTS=(
    "$HOME/.agents/skills"
    "$HOME/.claude/skills"
    "$HOME/.config/opencode/skills"
)
COMMAND_ROOTS=(
    "$HOME/.claude/commands"
    "$HOME/.codex/prompts"
    "$HOME/.config/opencode/command"
)

# `seo` is the whole optional group: one orchestrator, one installed name.
is_seo_skill() {
    [[ "$1" == seo ]]
}

# Locked upstream bodies the `seo` orchestrator reads from a path. A locked
# body cannot carry an invocation guard without drifting from upstream, so one
# that must never fire on its own is never installed as a skill anywhere.
is_unlinked_skill() {
    [[ "$1" == seo-* ]]
}

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

backup_copy() {
    local path="$1" relative backup
    [[ -f "$path" ]] || return 0
    if $NO_BACKUP; then
        return
    fi
    ensure_backup_root
    relative="${path#"$HOME"/}"
    backup="$BACKUP_ROOT/$relative.pre-reconcile"
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

# The harness owns a real directory here, so its links and a user's private
# skills can sit side by side. Anything else at the path is moved aside; a
# symlink included, because linking into someone else's directory would write
# managed entries somewhere this installer never sweeps.
ensure_skill_dir() {
    local destination="$1"
    if [[ -L "$destination" ]]; then
        backup_existing "$destination" .previous-link
    elif [[ -e "$destination" && ! -d "$destination" ]]; then
        backup_existing "$destination"
    fi
    mkdir -p "$destination"
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

install_packages() {
    [[ "$(uname -s)" == "Darwin" ]] || die "The v1 harness installer supports macOS."
    command -v brew >/dev/null || die "Homebrew is required; run the root install.sh first."

    log "Installing current AI clients and harness tools"
    brew tap anomalyco/tap
    brew tap gentleman-programming/tap
    for formula in node gh python@3.11 uv rtk worktrunk anomalyco/tap/opencode gentleman-programming/tap/engram; do
        brew_latest_formula "$formula"
    done
    brew_latest_cask codex

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

install_integrations() {
    install_engram

    log "Reconciling RTK and Worktrunk"
    rtk init --global --hook-only --auto-patch --no-trust-filters
    rtk init --global --opencode --hook-only --auto-patch --no-trust-filters
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
install_aliases() {
    local rc="$HOME/.zshrc" reconciled
    [[ -f "$rc" ]] || touch "$rc"
    if reconciled="$(python3 - "$rc" "$HARNESS_DIR/aliases.sh" <<'PY'
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
    raise SystemExit(1)
sys.stdout.write(text)
PY
    )"; then
        backup_copy "$rc"
        printf '%s\n' "$reconciled" > "$rc"
        log "Reconciled harness aliases in $rc"
    fi
}

# The committed statusline is linked to the path Claude Code already reads, so
# settings.json only ever needs the one command line pointing at it. Rewritten
# only when it differs, which keeps a hand-edited settings.json otherwise alone.
# The reconciled file is emitted on stdout and written here, rather than
# written in place, so the backup is taken only when something actually
# changes. Backing up unconditionally minted a fresh backup root on every run.
point_statusline_at_link() {
    local settings="$HOME/.claude/settings.json" reconciled
    mkdir -p "$(dirname "$settings")"
    [[ -f "$settings" ]] || printf '{}\n' > "$settings"
    if reconciled="$(python3 - "$settings" <<'PY'
import json, sys

path = sys.argv[1]
with open(path) as handle:
    settings = json.load(handle)
wanted = {"type": "command", "command": 'bash "$HOME/.claude/statusline.sh"'}
if settings.get("statusLine") == wanted:
    raise SystemExit(1)
settings["statusLine"] = wanted
json.dump(settings, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
    )"; then
        backup_copy "$settings"
        printf '%s\n' "$reconciled" > "$settings"
        log "Pointed the Claude statusline at $HOME/.claude/statusline.sh"
    fi
}

install_links() {
    local skill source command root desired="|"
    ensure_skill_dir "$HOME/.agents/skills"
    ensure_skill_dir "$HOME/.claude/skills"
    mkdir -p "${COMMAND_ROOTS[@]}"
    retire_shadowed_skills

    while IFS= read -r skill; do
        if is_unlinked_skill "$skill"; then
            continue
        fi
        if is_seo_skill "$skill" && ! $WITH_SEO; then
            continue
        fi
        desired+="$HARNESS_DIR/skills/$skill|"
    done < <(skill_names)
    for command in "$HARNESS_DIR"/commands/*.md; do
        desired+="$command|"
    done
    if $WITH_SEO; then
        desired+="$HARNESS_DIR/skills/seo/bin/claude-seo|"
    fi
    reconcile_orphans "$desired"

    while IFS= read -r skill; do
        source="$HARNESS_DIR/skills/$skill"
        # OpenCode reads ~/.agents/skills, so a second copy would double-list.
        backup_existing "$HOME/.config/opencode/skills/$skill"
        [[ "$desired" == *"|$source|"* ]] || continue
        link_managed "$source" "$HOME/.agents/skills/$skill"
        link_managed "$source" "$HOME/.claude/skills/$skill"
    done < <(skill_names)

    for command in "$HARNESS_DIR"/commands/*.md; do
        for root in "${COMMAND_ROOTS[@]}"; do
            link_managed "$command" "$root/$(basename "$command")"
        done
    done

    link_managed "$HARNESS_DIR/statusline.sh" "$HOME/.claude/statusline.sh"
    point_statusline_at_link

    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.codex/AGENTS.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.claude/CLAUDE.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.config/opencode/AGENTS.md"
    if $WITH_SEO; then
        link_managed "$HARNESS_DIR/skills/seo/bin/claude-seo" "$HOME/.local/bin/claude-seo"
    else
        backup_existing "$HOME/.local/bin/claude-seo"
    fi
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

smoke_check() {
    local command skill root seo_status=0
    for command in codex claude opencode gh python3 uv engram rtk wt; do
        command -v "$command" >/dev/null || die "Missing required command: $command"
    done
    for skill in "$HARNESS_DIR"/skills/*; do
        local name; name="$(basename "$skill")"
        [[ -f "$skill/SKILL.md" ]] || die "Missing SKILL.md: $skill"
        if is_unlinked_skill "$name"; then
            for root in "${SKILL_ROOTS[@]}"; do
                [[ ! -e "$root/$name" && ! -L "$root/$name" ]] || die "Unlinked body is installed as a skill: $root/$name"
            done
            continue
        fi
        [[ ! -e "$HOME/.config/opencode/skills/$name" && ! -L "$HOME/.config/opencode/skills/$name" ]] || die "Duplicate OpenCode skill path: $skill"
        if is_seo_skill "$name" && ! $WITH_SEO; then
            [[ ! -e "$HOME/.agents/skills/$name" && ! -L "$HOME/.agents/skills/$name" ]] || die "Optional SEO skill is still linked: $skill"
            continue
        fi
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
    [[ "$(readlink "$HOME/.config/opencode/AGENTS.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing OpenCode policy link."
    assert_plugin_count codex engram 1
    assert_plugin_count claude engram 1
    [[ -f "$HARNESS_DIR/skills/ponytail/SKILL.md" ]] || die "Missing the ponytail skill body."

    opencode debug config |
        python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("plugin",[]); assert sum("engram" in x for x in p)==1; assert "engram" in d.get("mcp",{})'
    claude plugin validate "$HARNESS_DIR/skills" >/dev/null
    wt switch --help | grep -q -- '--no-cd'
    rtk --version >/dev/null
    if $WITH_SEO; then
        command -v claude-seo >/dev/null || die "Missing required command: claude-seo"
        claude-seo doctor --json >/dev/null || seo_status=$?
        [[ "$seo_status" == 0 || "$seo_status" == 3 ]] || die "Portable SEO runtime is invalid."
    fi
}

summary() {
    cat <<EOF

$(printf '\033[1;32m✓ Portable AI harness installed.\033[0m')

Next steps (interactive; not run by this installer):
  1. Authenticate: codex login
  2. Authenticate: claude auth login
  3. Authenticate: opencode auth login
  4. Authenticate: gh auth login
  5. Restart Codex, Claude Code, and OpenCode.
  6. In Codex, open /hooks and trust the Engram and RTK hooks you reviewed.
  7. Invoke setup-harness in each project that should use the public lifecycle.

Skill groups: core$($WITH_SEO && printf ', seo')
Commands are installed for all three clients as /name.
Yolo aliases (ccyolo, cyolo, oyolo) are sourced from harness/aliases.sh; open a
new shell or run: source ~/.zshrc
Toggle the optional SEO group with --with-seo or --without-seo.

Standalone third-party skills were not downloaded or updated. Their committed
bodies and skills-lock.json are the reviewed source of truth.
EOF
    if [[ -n "$BACKUP_ROOT" ]]; then
        printf '\nBackups: %s\n' "$BACKUP_ROOT"
    fi
}

main() {
    resolve_groups
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
    else
        smoke_check
    fi
    summary
}

main
