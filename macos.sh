#!/usr/bin/env bash
# macOS dotfiles installer — Neovim + Ghostty + git + worktrunk.
#
# Installs everything in Brewfile, symlinks the tracked configs, and bootstraps
# Neovim plugins and LSPs headlessly so the first `nvim` launch is instant.
#
# Safe to re-run: brew bundle is idempotent, existing real configs get backed
# up, and matching symlinks are left alone.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# If set, macos.sh clones the repo here when run outside a checkout.
REPO_URL=""

require_macos() {
    [[ "$(uname -s)" == "Darwin" ]] || die "macos.sh only supports macOS. On Linux run ./linux.sh."
}

ensure_xcode_clt() {
    if ! xcode-select -p >/dev/null 2>&1; then
        log "Installing Xcode Command Line Tools (accept the GUI prompt, then re-run this script)."
        xcode-select --install || true
        die "Re-run macos.sh after Xcode CLT finishes installing."
    fi
}

ensure_brew() {
    if ! have brew; then
        log "Homebrew not found. Installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
}

# Brewfile is the manifest for this machine, regenerated with `brew bundle dump --describe --force --file=Brewfile`. Formulae the harness itself needs are installed again by `harness install`, which keeps it runnable on its own.
install_packages() {
    log "Applying $SCRIPT_DIR/Brewfile"
    brew bundle --file "$SCRIPT_DIR/Brewfile"
}

main() {
    parse_args "$@"
    require_macos
    ensure_xcode_clt
    ensure_brew
    ensure_repo
    install_packages
    install_pythons
    link_configs
    bootstrap_nvim
    summary
    cat <<'EOF'
Ghostty: JetBrainsMono Nerd Font (default) plus the Catppuccin theme
(Mocha/Latte, following macOS appearance) are wired in via ghostty/config.
Monocraft is also installed; swap by editing `font-family` in that config.

EOF
}

main "$@"
