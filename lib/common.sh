#!/usr/bin/env bash
# Shared bootstrap logic for macos.sh and linux.sh.
#
# Sourced, never executed. The two entry points differ only in how packages
# arrive; everything after that (symlinks, the harness, Neovim bootstrap) is
# the same on both platforms, so it lives here once.

# Delete a config that is in the way instead of renaming it to
# <path>.backup.<timestamp>, and pass the same choice to the harness installer.
# Destructive and unrecoverable.
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

usage() {
    cat <<EOF
Usage: $(basename "$0") [--no-backup]

  --no-backup  Delete configs that are in the way instead of renaming them to
               <path>.backup.<timestamp>, and pass the same choice to the
               harness installer. Destructive and unrecoverable.
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
    if [[ -d "$SCRIPT_DIR/nvim" && -d "$SCRIPT_DIR/harness" ]]; then
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

# Symlinks one tracked path to its destination. A destination that already
# points where it should is left alone, so re-running is free; anything else is
# renamed to <path>.backup.<timestamp>, or deleted under --no-backup.
link_path() {
    local src="$1" dest="$2"
    [[ -e "$src" ]] || die "Missing config source: $src"

    if [[ -L "$dest" ]]; then
        local current
        current="$(readlink "$dest")"
        if [[ "$current" == "$src" ]]; then
            log "Symlink already in place: $dest -> $src"
            return
        fi
        log "Replacing existing symlink: $dest (was -> $current)"
        rm "$dest"
    elif [[ -e "$dest" ]]; then
        if $NO_BACKUP; then
            log "Removing existing $dest"
            rm -rf "$dest"
        else
            local backup="${dest}.backup.$(date +%Y%m%d-%H%M%S)"
            log "Backing up existing $dest to $backup"
            mv "$dest" "$backup"
        fi
    fi

    mkdir -p "$(dirname "$dest")"
    log "Linking $src -> $dest"
    ln -s "$src" "$dest"
}

place_configs() {
    link_path "$SCRIPT_DIR/nvim"                 "$CONFIG_HOME/nvim"
    link_path "$SCRIPT_DIR/ghostty"              "$CONFIG_HOME/ghostty"
    link_path "$SCRIPT_DIR/git/gitconfig"        "$HOME/.gitconfig"
    link_path "$SCRIPT_DIR/git/ignore"           "$CONFIG_HOME/git/ignore"
    link_path "$SCRIPT_DIR/worktrunk/config.toml" "$CONFIG_HOME/worktrunk/config.toml"
}

install_harness() {
    [[ -x "$SCRIPT_DIR/harness/install.sh" ]] || die "Missing harness installer: $SCRIPT_DIR/harness/install.sh"
    if $NO_BACKUP; then
        "$SCRIPT_DIR/harness/install.sh" --no-backup
    else
        "$SCRIPT_DIR/harness/install.sh"
    fi
}

bootstrap_nvim() {
    log "Syncing lazy.nvim plugins"
    nvim --headless "+Lazy! sync" +qa

    log "Installing Mason packages: ${MASON_PACKAGES[*]}"
    nvim --headless "+MasonInstall ${MASON_PACKAGES[*]}" +qa

    log "Updating tree-sitter parsers"
    nvim --headless "+TSUpdateSync" +qa
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
  AI harness policy and skills         -> Codex, Claude Code, and OpenCode

Next steps:
  1. Launch: nvim
  2. Sanity: :checkhealth   ·   :Lazy   ·   :Mason
  3. Authenticate when needed: codex login · claude auth login · opencode auth login · gh auth login
  4. Restart the three AI clients, then review and trust the Engram and RTK hooks in Codex /hooks.
  5. Machine-local git settings go in ~/.gitconfig.local, which git/gitconfig includes and this repo never tracks.

EOF
}
