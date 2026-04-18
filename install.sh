#!/usr/bin/env bash
# Neovim auto-install for macOS.
# Installs Homebrew dependencies, a Nerd Font, links this config to ~/.config/nvim,
# and bootstraps plugins/LSPs headlessly so the first `nvim` launch is instant.
#
# Safe to re-run: brew installs are idempotent, existing configs get backed up.

set -euo pipefail

# If you later push this repo to a remote, set REPO_URL so the script can clone
# itself onto a fresh Mac. Leave empty to require running in-place.
REPO_URL=""

NVIM_CONFIG_DIR="${HOME}/.config/nvim"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BREW_FORMULAE=(
    neovim
    git
    ripgrep
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
        # Add brew to PATH for the rest of this script on Apple Silicon.
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

place_config() {
    if [[ "$SCRIPT_DIR" == "$NVIM_CONFIG_DIR" ]]; then
        log "Running in-place from $NVIM_CONFIG_DIR — no config copy needed."
        return
    fi

    if [[ -e "$NVIM_CONFIG_DIR" && ! -L "$NVIM_CONFIG_DIR" ]]; then
        local backup="${NVIM_CONFIG_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
        log "Backing up existing $NVIM_CONFIG_DIR to $backup"
        mv "$NVIM_CONFIG_DIR" "$backup"
    fi

    mkdir -p "$(dirname "$NVIM_CONFIG_DIR")"

    if [[ -n "$REPO_URL" ]]; then
        log "Cloning $REPO_URL into $NVIM_CONFIG_DIR"
        git clone "$REPO_URL" "$NVIM_CONFIG_DIR"
    else
        log "Linking $SCRIPT_DIR -> $NVIM_CONFIG_DIR"
        ln -s "$SCRIPT_DIR" "$NVIM_CONFIG_DIR"
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

$(printf '\033[1;32m✓ Neovim setup complete.\033[0m')

Next steps:
  1. Set your terminal font to "JetBrains Mono Nerd Font" (Ghostty/iTerm2/Alacritty/etc).
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
    place_config
    bootstrap_nvim
    summary
}

main "$@"
