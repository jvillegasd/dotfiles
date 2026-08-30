#!/usr/bin/env bash

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINKS_ONLY=false
WITH_SEO=false
SEO_SET=false
BACKUP_ROOT=""
GROUPS_FILE="${XDG_CACHE_HOME:-$HOME/.cache}/portable-harness/groups"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: harness/install.sh [--links-only] [--with-seo|--without-seo]

  --links-only   Reconcile policy and skill links without packages/plugins.
  --with-seo     Also link the optional SEO skill group and its launcher.
  --without-seo  Unlink the optional SEO group (the default for a fresh install).

The SEO choice is remembered, so a later run without either flag keeps it.
EOF
}

for arg in "$@"; do
    case "$arg" in
        --links-only) LINKS_ONLY=true ;;
        --with-seo) WITH_SEO=true; SEO_SET=true ;;
        --without-seo) WITH_SEO=false; SEO_SET=true ;;
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

is_seo_skill() {
    [[ "$1" == seo || "$1" == seo-* ]]
}

# Locked bodies reachable only through a local wrapper that carries the
# invocation guards their hash-locked frontmatter cannot.
is_internal_skill() {
    [[ "$1" == code-review ]]
}

ensure_backup_root() {
    if [[ -z "$BACKUP_ROOT" ]]; then
        BACKUP_ROOT="$HOME/.dotfiles-backups/harness/$(date +%Y%m%d-%H%M%S)-$$"
        mkdir -p "$BACKUP_ROOT"
    fi
}

backup_existing() {
    local path="$1" relative backup
    [[ -e "$path" || -L "$path" ]] || return 0
    ensure_backup_root
    relative="${path#"$HOME"/}"
    backup="$BACKUP_ROOT/$relative"
    mkdir -p "$(dirname "$backup")"
    mv "$path" "$backup"
    log "Backed up $path -> $backup"
}

backup_copy() {
    local path="$1" relative backup
    [[ -f "$path" ]] || return 0
    ensure_backup_root
    relative="${path#"$HOME"/}"
    backup="$BACKUP_ROOT/$relative.pre-reconcile"
    mkdir -p "$(dirname "$backup")"
    cp -p "$path" "$backup"
}

backup_skill_dir_link() {
    local path="$1" relative backup
    ensure_backup_root
    relative="${path#"$HOME"/}"
    backup="$BACKUP_ROOT/$relative.previous-link"
    mkdir -p "$(dirname "$backup")"
    mv "$path" "$backup"
    log "Backed up $path -> $backup"
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

ensure_skill_dir() {
    local destination="$1" old_target entry
    if [[ -L "$destination" ]]; then
        old_target="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$destination")"
        backup_skill_dir_link "$destination"
        mkdir -p "$destination"
        if [[ -d "$old_target" ]]; then
            for entry in "$old_target"/*; do
                [[ -e "$entry" ]] || continue
                ln -s "$entry" "$destination/$(basename "$entry")"
            done
        fi
    elif [[ -e "$destination" && ! -d "$destination" ]]; then
        backup_existing "$destination"
        mkdir -p "$destination"
    else
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

json_contains() {
    local needle="$1"
    shift
    "$@" | python3 -c 'import json,sys; needle=sys.argv[1]; print(needle in json.dumps(json.load(sys.stdin)))' "$needle" |
        grep -q '^True$'
}

ensure_codex_plugin() {
    local marketplace="$1" source="$2" plugin="$3"
    if ! json_contains "\"name\": \"$marketplace\"" codex plugin marketplace list --json; then
        codex plugin marketplace add "$source"
    fi
    codex plugin marketplace upgrade "$marketplace"
    if ! json_contains "$plugin@$marketplace" codex plugin list --json; then
        codex plugin add "$plugin@$marketplace"
    fi
}

ensure_claude_plugin() {
    local marketplace="$1" source="$2" plugin="$3"
    if ! json_contains "\"name\": \"$marketplace\"" claude plugin marketplace list --json; then
        claude plugin marketplace add "$source" --scope user
    else
        claude plugin marketplace update "$marketplace"
    fi
    if json_contains "$plugin@$marketplace" claude plugin list --json; then
        claude plugin update "$plugin@$marketplace" --scope user --yes
    else
        claude plugin install "$plugin@$marketplace" --scope user --yes
    fi
}

remove_codex_legacy_engram_mcp() {
    local config="$HOME/.codex/config.toml"
    [[ -f "$config" ]] || return
    if grep -Eq '^\[mcp_servers\.engram(\.|\])' "$config"; then
        backup_copy "$config"
        python3 - "$config" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
text = re.sub(
    r"(?ms)^\[mcp_servers\.engram(?:\.[^]]+)?\]\n.*?(?=^\[|\Z)",
    "",
    text,
).rstrip() + "\n"
path.write_text(text)
PY
        log "Removed legacy direct Codex Engram MCP; the official plugin owns it"
    fi
}

remove_claude_legacy_engram_mcp() {
    local config="$HOME/.claude.json"
    [[ -f "$config" ]] || return 0
    if python3 - "$config" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
raise SystemExit(0 if "engram" in data.get("mcpServers", {}) else 1)
PY
    then
        backup_copy "$config"
        claude mcp remove engram --scope user
        log "Removed legacy direct Claude Engram MCP; the official plugin owns it"
    fi
}

install_integrations() {
    log "Reconciling Engram"
    ensure_codex_plugin engram Gentleman-Programming/engram engram
    ensure_claude_plugin engram Gentleman-Programming/engram engram
    engram setup opencode
    remove_codex_legacy_engram_mcp
    remove_claude_legacy_engram_mcp

    log "Reconciling Ponytail"
    ensure_codex_plugin ponytail DietrichGebert/ponytail ponytail
    ensure_claude_plugin ponytail DietrichGebert/ponytail ponytail
    opencode plugin --global --force @dietrichgebert/ponytail

    log "Reconciling RTK and Worktrunk"
    rtk init --global --hook-only --auto-patch --no-trust-filters
    rtk init --global --opencode --hook-only --auto-patch --no-trust-filters
    wt config shell install --yes zsh
}

retire_aliases() {
    local root name
    local aliases=(
        code-review
        design-an-interface
        diagnose
        grill-me
        grill-with-docs
        implement
        request-refactor-plan
        seo-performance
        seo-visual
        setup-matt-pocock-skills
        to-issues
        to-prd
        ubiquitous-language
    )
    for root in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.config/opencode/skills"; do
        [[ -d "$root" ]] || continue
        for name in "${aliases[@]}"; do
            backup_existing "$root/$name"
        done
    done
}

install_links() {
    local skill source
    ensure_skill_dir "$HOME/.agents/skills"
    ensure_skill_dir "$HOME/.claude/skills"
    ensure_skill_dir "$HOME/.config/opencode/skills"
    retire_aliases

    while IFS= read -r skill; do
        source="$HARNESS_DIR/skills/$skill"
        backup_existing "$HOME/.config/opencode/skills/$skill"
        if is_internal_skill "$skill"; then
            continue
        fi
        if is_seo_skill "$skill" && ! $WITH_SEO; then
            backup_existing "$HOME/.agents/skills/$skill"
            backup_existing "$HOME/.claude/skills/$skill"
            continue
        fi
        link_managed "$source" "$HOME/.agents/skills/$skill"
        link_managed "$source" "$HOME/.claude/skills/$skill"
    done < <(find "$HARNESS_DIR/skills" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)

    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.codex/AGENTS.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.claude/CLAUDE.md"
    link_managed "$HARNESS_DIR/POLICY.md" "$HOME/.config/opencode/AGENTS.md"
    if $WITH_SEO; then
        link_managed "$HARNESS_DIR/skills/seo/bin/claude-seo" "$HOME/.local/bin/claude-seo"
    else
        backup_existing "$HOME/.local/bin/claude-seo"
    fi
}

assert_plugin_count() {
    local client="$1" plugin="$2" expected="$3"
    local count
    count="$(
        case "$client" in
            codex) codex plugin list --json ;;
            claude) claude plugin list --json ;;
        esac |
            python3 -c 'import json,sys; d=json.load(sys.stdin); p=sys.argv[1]; items=d.get("installed",d) if isinstance(d,dict) else d; print(sum(p in (x.get("pluginId") or x.get("id") or "") for x in items))' "$plugin"
    )"
    [[ "$count" == "$expected" ]] || die "Expected $expected $plugin integration in $client; found $count."
}

smoke_check() {
    local command skill seo_status=0
    for command in codex claude opencode gh python3 uv engram rtk wt; do
        command -v "$command" >/dev/null || die "Missing required command: $command"
    done
    for skill in "$HARNESS_DIR"/skills/*; do
        local name; name="$(basename "$skill")"
        [[ -f "$skill/SKILL.md" ]] || die "Missing SKILL.md: $skill"
        if is_internal_skill "$name"; then
            [[ ! -e "$HOME/.agents/skills/$name" && ! -L "$HOME/.agents/skills/$name" ]] || die "Internal skill is still linked: $skill"
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
    [[ "$(readlink "$HOME/.codex/AGENTS.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing Codex policy link."
    [[ "$(readlink "$HOME/.claude/CLAUDE.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing Claude policy link."
    [[ "$(readlink "$HOME/.config/opencode/AGENTS.md")" == "$HARNESS_DIR/POLICY.md" ]] || die "Missing OpenCode policy link."
    assert_plugin_count codex engram 1
    assert_plugin_count codex ponytail 1
    assert_plugin_count claude engram 1
    assert_plugin_count claude ponytail 1

    opencode debug config |
        python3 -c 'import json,sys; d=json.load(sys.stdin); p=d.get("plugin",[]); assert sum("engram" in x for x in p)==1; assert sum("ponytail" in x for x in p)==1; assert "engram" in d.get("mcp",{})'
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
  6. In Codex, open /hooks and trust the Engram, Ponytail, and RTK hooks you reviewed.
  7. Invoke setup-harness in each project that should use the public lifecycle.

Skill groups: core$($WITH_SEO && printf ', seo')
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
    if ! $LINKS_ONLY; then
        smoke_check
    fi
    summary
}

main
