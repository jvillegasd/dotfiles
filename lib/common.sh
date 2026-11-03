#!/usr/bin/env bash
# Shared bootstrap logic for macos.sh and linux.sh.
#
# Sourced, never executed. The two entry points differ only in how packages arrive; everything after that (the config links, then the Neovim bootstrap) is the same on both platforms, so it lives here once.

# Delete a config that is in the way instead of renaming it to <path>.backup.<timestamp>. Destructive and unrecoverable.
NO_BACKUP=false

# If set by the entry point, it will clone the repo into $DOTFILES_DIR when run
# outside of it (e.g. on a fresh machine). Leave empty to require running from
# inside an existing checkout.
REPO_URL="${REPO_URL:-}"

DOTFILES_DIR="${DOTFILES_DIR:-$HOME/Desktop/projects/dotfiles}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

MASON_PACKAGES=(
    lua-language-server
    pyright
    typescript-language-server
    codelldb
    cpptools
    debugpy
)

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# After log and die, which it uses. Resolved against this file rather than
# against the caller, so sourcing common.sh is all an entry point has to do.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/python.sh"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--no-backup]

  --no-backup  Delete configs that are in the way instead of renaming them to
               <path>.backup.<timestamp>. Destructive and unrecoverable.
EOF
}

parse_args() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --no-backup) NO_BACKUP=true ;;
            -h|--help) usage; exit 0 ;;
            *) die "Unknown argument: $arg" ;;
        esac
    done
}

ensure_repo() {
    if [[ -d "$SCRIPT_DIR/nvim" && -d "$SCRIPT_DIR/ghostty" ]]; then
        return
    fi

    [[ -n "$REPO_URL" ]] || die "Run this script from inside the dotfiles repo, or set REPO_URL."

    if [[ -e "$DOTFILES_DIR" ]]; then
        die "$DOTFILES_DIR already exists, move it aside before bootstrapping."
    fi

    log "Cloning $REPO_URL into $DOTFILES_DIR"
    mkdir -p "$(dirname "$DOTFILES_DIR")"
    git clone "$REPO_URL" "$DOTFILES_DIR"
    SCRIPT_DIR="$DOTFILES_DIR"
}

# Symlinks one tracked config into place. A matching link is left alone, another link is replaced, and anything else is renamed to <path>.backup.<timestamp> or deleted under --no-backup.
link_config() {
    local source="$1" dest="$2"
    [[ -e "$source" ]] || die "Missing config source: $source"
    if [[ -L "$dest" ]]; then
        if [[ "$(readlink "$dest")" == "$source" ]]; then
            log "Symlink already in place: $dest -> $source"
            return
        fi
        log "Replacing existing symlink: $dest (was -> $(readlink "$dest"))"
        rm "$dest"
    elif [[ -e "$dest" ]]; then
        if $NO_BACKUP; then
            log "Removing existing $dest"
            rm -rf "$dest"
        else
            local backup="$dest.backup.$(date +%Y%m%d-%H%M%S)"
            log "Backing up existing $dest to $backup"
            mv "$dest" "$backup"
        fi
    fi
    mkdir -p "$(dirname "$dest")"
    log "Linking $source -> $dest"
    ln -s "$source" "$dest"
}

link_configs() {
    link_config "$SCRIPT_DIR/nvim" "$CONFIG_HOME/nvim"
    link_config "$SCRIPT_DIR/ghostty" "$CONFIG_HOME/ghostty"
    link_config "$SCRIPT_DIR/git/gitconfig" "$HOME/.gitconfig"
    link_config "$SCRIPT_DIR/git/ignore" "$CONFIG_HOME/git/ignore"
    link_config "$SCRIPT_DIR/worktrunk/config.toml" "$CONFIG_HOME/worktrunk/config.toml"
}

bootstrap_nvim() {
    log "Syncing lazy.nvim plugins"
    nvim --headless "+Lazy! sync" +qa

    log "Installing Mason packages: ${MASON_PACKAGES[*]}"
    nvim --headless "+MasonInstall ${MASON_PACKAGES[*]}" +qa

    log "Updating tree-sitter parsers"
    nvim --headless "+TSUpdateSync" +qa
}

install_harness() {
    local harness_dir="$(dirname "$DOTFILES_DIR")/harness"
    if [[ ! -d "$harness_dir/.git" ]]; then
        [[ ! -e "$harness_dir" ]] || die "$harness_dir exists but is not a Git checkout. Move it aside before installing Harness."
        log "Cloning https://github.com/jvillegasd/harness into $harness_dir"
        git clone https://github.com/jvillegasd/harness "$harness_dir"
    fi
    log "Bootstrapping Harness from $harness_dir"
    (cd "$harness_dir" && go run ./cmd/harness install)
}

summary() {
    cat <<EOF

$(printf '\033[1;32m✓ Dotfiles setup complete.\033[0m')

Configs linked:
  $CONFIG_HOME/nvim                    -> $SCRIPT_DIR/nvim
  $CONFIG_HOME/ghostty                 -> $SCRIPT_DIR/ghostty
  $HOME/.gitconfig                     -> $SCRIPT_DIR/git/gitconfig
  $CONFIG_HOME/git/ignore              -> $SCRIPT_DIR/git/ignore
  $CONFIG_HOME/worktrunk/config.toml   -> $SCRIPT_DIR/worktrunk/config.toml

Next steps:
  1. Launch: nvim
  2. Sanity: :checkhealth   ·   :Lazy   ·   :Mason
  3. Authenticate when needed: claude auth login · gh auth login · OpenCode: /connect,
     then OpenAI, then ChatGPT Plus/Pro ("Manually enter API Key" bills the API)
  4. Restart Claude Code and OpenCode.
  5. Machine-local git settings go in ~/.gitconfig.local, which git/gitconfig includes and this repo never tracks.

EOF
}
