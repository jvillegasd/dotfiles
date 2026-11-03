#!/usr/bin/env bash
# Linux dotfiles installer — Neovim + git + worktrunk.
#
# Same end state as macos.sh, reached differently: the distribution's package
# manager supplies the build prerequisites, Homebrew on Linux supplies
# everything after that, and the macOS-only pieces (Xcode CLT, casks, fonts,
# Ghostty) are skipped.
#
# Homebrew is not optional here: it supplies the formulae below on Linux, and the AI harness installs its own clients from taps on top of it.
#
# Safe to re-run: package installs are idempotent, existing real configs get
# backed up, and matching symlinks are left alone.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# If set, linux.sh clones the repo here when run outside a checkout.
REPO_URL=""

# Homebrew on Linux builds more from source than it does on macOS, so the
# distribution has to supply a compiler and the usual headers first. This is
# exactly Homebrew's own documented prerequisite list.
APT_PACKAGES=(build-essential procps curl file git ca-certificates unzip)
DNF_PACKAGES=(procps-ng curl file git ca-certificates unzip)

# The macOS side installs from Brewfile, which also carries casks and fonts that do not exist on Linux. This is the subset a Linux box actually needs. No python@ formula on either side: install_pythons provisions the interpreters with uv, which is why uv is here. go is here so the AI harness builds from source.
BREW_FORMULAE=(
    neovim
    ripgrep
    fd
    wget
    lazygit
    tree
    make
    node
    go
    uv
    tree-sitter
    tree-sitter-cli
)

require_linux() {
    [[ "$(uname -s)" == "Linux" ]] || die "linux.sh only supports Linux. On macOS run ./macos.sh."
}

install_base_packages() {
    if have apt-get; then
        log "Installing base packages with apt-get: ${APT_PACKAGES[*]}"
        sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT_PACKAGES[@]}"
    elif have dnf; then
        log "Installing base packages with dnf: ${DNF_PACKAGES[*]}"
        sudo dnf install -y "${DNF_PACKAGES[@]}"
        sudo dnf group install -y development-tools
    else
        warn "Neither apt-get nor dnf found. Install a compiler, curl, git, and unzip yourself, then re-run."
    fi
}

ensure_brew() {
    if ! have brew; then
        log "Homebrew not found. Installing..."
        NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    local prefix
    for prefix in /home/linuxbrew/.linuxbrew "$HOME/.linuxbrew"; do
        if [[ -x "$prefix/bin/brew" ]]; then
            eval "$("$prefix/bin/brew" shellenv)"
            break
        fi
    done
    have brew || die "Homebrew is installed but not on PATH. Add its shellenv line to your shell rc and re-run."
}

install_packages() {
    log "Installing Homebrew formulae: ${BREW_FORMULAE[*]}"
    brew install "${BREW_FORMULAE[@]}"
}

main() {
    parse_args "$@"
    require_linux
    install_base_packages
    ensure_brew
    ensure_repo
    install_packages
    install_pythons
    link_configs
    bootstrap_nvim
    install_harness
    summary
    cat <<'EOF'
Not installed here, unlike on macOS: Ghostty, JetBrainsMono Nerd Font, and
Monocraft. ghostty/config is still linked, so it applies if you install Ghostty
yourself. Install a Nerd Font through your distribution or from
https://github.com/ryanoasis/nerd-fonts so the Neovim icons render.

EOF
}

main "$@"
