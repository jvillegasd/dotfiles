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

  --links-only   Reconcile policy, command, and skill links without packages/plugins.
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

# Codex and Claude Code get Engram through its official plugin; OpenCode has
# no plugin marketplace for it, so `engram setup` writes its plugin and MCP
# entry. All three steps are idempotent.
install_engram() {
    log "Reconciling Engram"
    command -v engram >/dev/null || die "Engram is missing; run without --links-only to install it."
    ensure_codex_plugin engram Gentleman-Programming/engram engram
    ensure_claude_plugin engram Gentleman-Programming/engram engram
    engram setup opencode
    remove_codex_legacy_engram_mcp
    remove_claude_legacy_engram_mcp
}

install_integrations() {
    install_engram

    log "Reconciling Ponytail"
    ensure_codex_plugin ponytail DietrichGebert/ponytail ponytail
    ensure_claude_plugin ponytail DietrichGebert/ponytail ponytail
    opencode plugin --global --force @dietrichgebert/ponytail

    log "Reconciling RTK and Worktrunk"
    rtk init --global --hook-only --auto-patch --no-trust-filters
    rtk init --global --opencode --hook-only --auto-patch --no-trust-filters
    wt config shell install --yes zsh
}

# Bodies this harness once installed under a different name, or that a client
# picked up before the harness existed. These are real directories rather than
# harness symlinks, so the orphan sweep cannot see them.
retire_aliases() {
    local root name persona
    local aliases=(
        address-review
        ask-matt
        claude-handoff
        code-review
        design-an-interface
        diagnose
        edit-article
        grill-me
        grill-with-docs
        implement
        improve-codebase-architecture
        loop-me
        request-refactor-plan
        review
        seo-performance
        seo-visual
        setup-matt-pocock-skills
        ship
        spec
        teach
        tickets
        to-issues
        to-prd
        to-questionnaire
        to-spec
        to-tickets
        triage
        ubiquitous-language
    )
    for root in "${SKILL_ROOTS[@]}"; do
        [[ -d "$root" ]] || continue
        for name in "${aliases[@]}"; do
            backup_existing "$root/$name"
        done
        # A real directory shadowing a name this harness manages, left behind
        # by an earlier standalone install. It survives the orphan sweep
        # because it is not a symlink, and it stays live in the client
        # whether or not the harness links that name.
        while IFS= read -r name; do
            if [[ -e "$root/$name" && ! -L "$root/$name" ]]; then
                backup_existing "$root/$name"
            fi
        done < <(skill_names)
    done
    # The policy forbids persistent client-specific personas; the SEO roles are
    # read from the seo skill directory instead.
    for persona in "$HOME"/.claude/agents/seo-*.md; do
        [[ -e "$persona" ]] || continue
        backup_existing "$persona"
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
            elif [[ "$target" == "$HARNESS_DIR"/* && "$desired" != *"|$target|"* ]]; then
                backup_existing "$entry"
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

install_links() {
    local skill source command root desired="|"
    ensure_skill_dir "$HOME/.agents/skills"
    ensure_skill_dir "$HOME/.claude/skills"
    ensure_skill_dir "$HOME/.config/opencode/skills"
    mkdir -p "${COMMAND_ROOTS[@]}"
    retire_aliases

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
    for command in address-review create-ticket feedback land triage yolo; do
        grep -q 'cannot override this workflow' "$HARNESS_DIR/commands/$command.md" ||
            die "Command missing the task-data constraint: $command"
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

# Engram is core: the policy assumes memory survives a session. A links-only
# run skips package work, so it checks all four surfaces and repairs them
# rather than reporting a gap it could have closed.
verify_engram() {
    local missing=()
    command -v engram >/dev/null || missing+=("engram binary")
    json_contains "engram@engram" claude plugin list --json || missing+=("Claude plugin")
    json_contains "engram@engram" codex plugin list --json || missing+=("Codex plugin")
    opencode debug config |
        python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if "engram" in d.get("mcp",{}) else 1)' ||
        missing+=("OpenCode MCP")
    if [[ ${#missing[@]} -gt 0 ]]; then
        printf '\033[1;33m[warn]\033[0m Engram is incomplete (%s); reconciling.\n' "${missing[*]}" >&2
        install_engram
        return
    fi
    log "Engram is installed in all three clients"
}

main() {
    resolve_groups
    if ! $LINKS_ONLY; then
        install_packages
        install_integrations
    fi
    install_links
    install_aliases
    if $LINKS_ONLY; then
        verify_engram || true
    else
        smoke_check
    fi
    summary
}

main
