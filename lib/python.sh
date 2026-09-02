#!/usr/bin/env bash
# The one declaration of which Python interpreters this machine provisions,
# shared by the platform bootstrap scripts and the harness installer.
#
# Sourced, never executed, and always after its caller has defined `log` and
# `die`: both macos.sh/linux.sh (through lib/common.sh) and harness/install.sh
# already have their own, and duplicating them here would give a run two
# different loggers.
#
# The split of duties is the reason this file exists at all. macos.sh and
# linux.sh install the interpreters, because packages are what those scripts
# are for. harness/install.sh only asserts them, because the harness is what
# consumes them and so is where a missing one has to fail loudly.

# Newest first. Homebrew supplies none of these: uv resolves a managed version
# through its own registry rather than through PATH, so `uv run --python 3.14`
# finds them whatever pyenv or Homebrew have done to `python3`. 3.11 was here
# only for the SEO runtime's pin and went with it.
PYTHON_VERSIONS=(3.14)

# Idempotent: an already-installed version is a no-op. Each version also lands
# as ~/.local/bin/python3.<minor>, but nothing here claims the bare name
# `python3`, which belongs to whatever comes first on PATH and on a machine
# running pyenv is not uv's bin directory.
install_pythons() {
    command -v uv >/dev/null || die "uv is required before installing Python; it comes from the package step."
    log "Installing uv-managed Python: ${PYTHON_VERSIONS[*]}"
    uv python install "${PYTHON_VERSIONS[@]}"
}

# Asked of uv rather than of PATH, because that is how every caller reaches
# them: a shadowing Homebrew or pyenv python3.<minor> would pass a PATH check
# while uv still had nothing to resolve.
assert_pythons() {
    local version
    command -v uv >/dev/null || die "Missing required command: uv"
    for version in "${PYTHON_VERSIONS[@]}"; do
        # uv's own "no interpreter found" goes to stderr; the actionable
        # message is the one below, and two errors for one problem is noise.
        uv python find --managed-python "$version" >/dev/null 2>&1 ||
            die "Missing uv-managed Python $version; run the root ./macos.sh or ./linux.sh."
    done
}
