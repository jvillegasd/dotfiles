#!/usr/bin/env bash
# macOS dotfiles installer — Neovim + Ghostty.
# Installs Homebrew dependencies, symlinks the configs under this repo into
# ~/.config/{nvim,ghostty}, and bootstraps plugins/LSPs headlessly so the
# first `nvim` launch is instant.
#
# Safe to re-run: brew installs are idempotent, existing real configs get
# backed up, and matching symlinks are left alone.

set -euo pipefail

# If set, install.sh will clone the repo into $DOTFILES_DIR when run outside
# of it (e.g. on a fresh Mac). Leave empty to require running from inside
# an existing checkout.
REPO_URL=""

DOTFILES_DIR="${HOME}/Desktop/projects/dotfiles"
NVIM_CONFIG_DIR="${HOME}/.config/nvim"
GHOSTTY_CONFIG_DIR="${HOME}/.config/ghostty"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BREW_FORMULAE=(
    neovim
    git
    ripgrep
    fd
    wget
    lazygit
    tree
    make
    python@3.11
    node
    tree-sitter
    tree-sitter-cli
)

BREW_CASKS=(
    font-jetbrains-mono-nerd-font
    ghostty
)

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

require_macos() {
    [[ "$(uname -s)" == "Darwin" ]] || die "This script only supports macOS."
}

ensure_xcode_clt() {
    if ! xcode-select -p >/dev/null 2>&1; then
        log "Installing Xcode Command Line Tools (accept the GUI prompt, then re-run this script)."
        xcode-select --install || true
        die "Re-run install.sh after Xcode CLT finishes installing."
    fi
}

ensure_brew() {
    if ! command -v brew >/dev/null 2>&1; then
        log "Homebrew not found. Installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [[ -x /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -x /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi
}

install_formulae() {
    log "Installing Homebrew formulae: ${BREW_FORMULAE[*]}"
    brew install "${BREW_FORMULAE[@]}"
}

install_casks() {
    log "Installing Homebrew casks: ${BREW_CASKS[*]}"
    brew install --cask "${BREW_CASKS[@]}"
}

ensure_repo() {
    if [[ -d "$SCRIPT_DIR/nvim" && -d "$SCRIPT_DIR/ghostty" ]]; then
        return
    fi

    [[ -n "$REPO_URL" ]] || die "install.sh must be run from inside the dotfiles repo, or REPO_URL must be set."

    if [[ -e "$DOTFILES_DIR" ]]; then
        die "$DOTFILES_DIR already exists — move it aside before bootstrapping."
    fi

    log "Cloning $REPO_URL into $DOTFILES_DIR"
    mkdir -p "$(dirname "$DOTFILES_DIR")"
    git clone "$REPO_URL" "$DOTFILES_DIR"
    SCRIPT_DIR="$DOTFILES_DIR"
}

link_config() {
    local src="$1" dest="$2"
    [[ -d "$src" ]] || die "Missing config source: $src"

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
        local backup="${dest}.backup.$(date +%Y%m%d-%H%M%S)"
        log "Backing up existing $dest to $backup"
        mv "$dest" "$backup"
    fi

    mkdir -p "$(dirname "$dest")"
    log "Linking $src -> $dest"
    ln -s "$src" "$dest"
}

place_configs() {
    link_config "$SCRIPT_DIR/nvim"    "$NVIM_CONFIG_DIR"
    link_config "$SCRIPT_DIR/ghostty" "$GHOSTTY_CONFIG_DIR"
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
  $NVIM_CONFIG_DIR     -> $SCRIPT_DIR/nvim
  $GHOSTTY_CONFIG_DIR  -> $SCRIPT_DIR/ghostty

Next steps:
  1. Open Ghostty — JetBrainsMono Nerd Font + Catppuccin theme (Mocha/Latte, follows macOS appearance) are wired in via $GHOSTTY_CONFIG_DIR/config.
  2. Launch: nvim
  3. Sanity: :checkhealth   ·   :Lazy   ·   :Mason

Tools installed via brew:
  ${BREW_FORMULAE[*]}
  ${BREW_CASKS[*]}

EOF
}

main() {
    require_macos
    ensure_xcode_clt
    ensure_brew
    install_formulae
    install_casks
    ensure_repo
    place_configs
    bootstrap_nvim
    summary
}

main "$@"
