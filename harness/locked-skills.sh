#!/usr/bin/env bash

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HARNESS_DIR/.." && pwd)"
LOCK_FILE="$ROOT/skills-lock.json"
SKILLS_DIR="$HARNESS_DIR/skills"
COMMANDS_DIR="$HARNESS_DIR/commands"
CLAUDE_DIR="$ROOT/.claude/skills"

die() { printf '[err] %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Usage: harness/locked-skills.sh <command> [arguments]

  add <owner/repo> <name>  Install and lock one upstream skill.
  update                   Update every locked skill from upstream.
  remove <name>            Remove one locked body, lock entry, and Claude link.
  check                    Run syntax, diff, and harness acceptance checks.
EOF
}

require_count() {
    local expected="$1" actual="$2" command="$3"
    [[ "$actual" == "$expected" ]] || die "$command expects $expected argument(s)."
}

validate_name() {
    [[ "$1" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "Invalid skill name: $1"
}

validate_source() {
    local owner="${1%%/*}" repo="${1#*/}"
    [[ "$1" == */* ]] || die "Source must be owner/repo: $1"
    [[ "$owner" =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$ ]] || die "Invalid GitHub owner: $owner"
    [[ "$repo" =~ ^[A-Za-z0-9_.][A-Za-z0-9_.-]*$ && "$repo" != "." && "$repo" != ".." ]] || die "Invalid GitHub repository: $repo"
}

is_locked() {
    node -e 'const fs=require("fs");const [p,n]=process.argv.slice(1);const d=JSON.parse(fs.readFileSync(p,"utf8"));process.exit(Object.prototype.hasOwnProperty.call(d.skills,n)?0:1)' "$LOCK_FILE" "$1"
}

is_unlinked() {
    [[ "$1" == seo-* ]]
}

review_paths() {
    if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        printf '\nLocked-skill changes:\n'
        git -C "$ROOT" status --short -- harness/skills skills-lock.json .claude/skills
    fi
    printf '\nReview the upstream body and run: harness/locked-skills.sh check\n'
}

add_skill() {
    require_count 2 "$#" add
    local source="$1" name="$2" link="$CLAUDE_DIR/$2"
    validate_source "$source"
    validate_name "$name"
    ! is_locked "$name" || die "$name is already locked; use update."
    [[ ! -e "$SKILLS_DIR/$name" && ! -L "$SKILLS_DIR/$name" ]] || die "Skill path already exists: $SKILLS_DIR/$name"
    [[ ! -e "$COMMANDS_DIR/$name.md" && ! -L "$COMMANDS_DIR/$name.md" ]] || die "Command name already exists: $COMMANDS_DIR/$name.md"
    [[ ! -e "$link" && ! -L "$link" ]] || die "Claude path already exists: $link"

    (cd "$ROOT" && npx skills@1 add "$source" --skill "$name" --agent universal -y)
    [[ -f "$SKILLS_DIR/$name/SKILL.md" ]] || die "skills.sh did not install $name."
    is_locked "$name" || die "skills.sh did not lock $name."
    if ! is_unlinked "$name"; then
        mkdir -p "$CLAUDE_DIR"
        ln -s "../../.agents/skills/$name" "$link"
    fi
    review_paths
}

update_skills() {
    require_count 0 "$#" update
    (cd "$ROOT" && npx skills@1 update --project --yes)
    review_paths
}

remove_skill() {
    require_count 1 "$#" remove
    local name="$1" body="$SKILLS_DIR/$1" link="$CLAUDE_DIR/$1"
    validate_name "$name"
    is_locked "$name" || die "$name is not in skills-lock.json."
    if [[ -e "$body" || -L "$body" ]]; then
        [[ -d "$body" && ! -L "$body" ]] || die "Refusing to remove non-directory skill path: $body"
    fi
    if [[ -e "$link" || -L "$link" ]]; then
        [[ -L "$link" ]] || die "Refusing to remove non-symlink Claude path: $link"
        [[ "$(readlink "$link")" == "../../.agents/skills/$name" ]] || die "Refusing to remove unexpected Claude link: $link"
    fi

    node -e 'const fs=require("fs");const [p,n]=process.argv.slice(1);const d=JSON.parse(fs.readFileSync(p,"utf8"));delete d.skills[n];fs.writeFileSync(p,JSON.stringify(d,null,2)+"\n")' "$LOCK_FILE" "$name"
    rm -rf "$body"
    rm -f "$link"
    review_paths
}

check_skills() {
    require_count 0 "$#" check
    bash -n "$0"
    git -C "$ROOT" diff --check
    git -C "$ROOT" diff --cached --check
    python3 "$HARNESS_DIR/tests/test_harness.py"
}

main() {
    local command="${1-}"
    [[ -n "$command" ]] || { usage >&2; exit 2; }
    shift
    case "$command" in
        add) add_skill "$@" ;;
        update) update_skills "$@" ;;
        remove) remove_skill "$@" ;;
        check) check_skills "$@" ;;
        help|-h|--help) require_count 0 "$#" "$command"; usage ;;
        *) usage >&2; die "Unknown command: $command" ;;
    esac
}

main "$@"
