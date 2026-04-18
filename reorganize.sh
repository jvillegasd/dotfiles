#!/usr/bin/env bash
# Idempotent migration from the old flat layout to the categorized structure.
# Safe to re-run on an already-migrated checkout — moves nothing if the source
# paths no longer exist.
#
# Layout mapping:
#   lua/config/icons.lua   -> lua/core/icons.lua
#   lua/config/maps.lua    -> lua/core/keymaps.lua
#   lua/config/lazy.lua    -> lua/plugins.lua
#   lua/plugins/<flat>.lua -> lua/plugins/<category>/<flat>.lua

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

move() {
    local src="$1" dst="$2"
    if [[ -e "$src" && ! -e "$dst" ]]; then
        mkdir -p "$(dirname "$dst")"
        if git ls-files --error-unmatch "$src" >/dev/null 2>&1; then
            git mv "$src" "$dst"
        else
            mv "$src" "$dst"
        fi
        log "moved $src -> $dst"
    fi
}

# Core
move lua/config/icons.lua lua/core/icons.lua
move lua/config/maps.lua  lua/core/keymaps.lua
move lua/config/lazy.lua  lua/plugins.lua
[[ -d lua/config ]] && rmdir lua/config 2>/dev/null || true

# UI
for f in catppuccin lualine bufferline snacks dressing fidget dropbar web-devicons render-markdown; do
    move "lua/plugins/$f.lua" "lua/plugins/ui/$f.lua"
done
move lua/plugins/colorizer.lua lua/plugins/ui/nvim-colorizer.lua

# Editor
for f in treesitter autopairs which-key luasnip neotree telescope; do
    move "lua/plugins/$f.lua" "lua/plugins/editor/$f.lua"
done

# LSP (mason only — lsp.lua is hand-split into lsp-config.lua + completions.lua)
move lua/plugins/mason.lua lua/plugins/lsp/mason.lua
if [[ -e lua/plugins/lsp.lua && ! -e lua/plugins/lsp/lsp-config.lua ]]; then
    log "lua/plugins/lsp.lua present — split it manually into lsp/lsp-config.lua + lsp/completions.lua"
fi

# Git
move lua/plugins/gitsigns.lua lua/plugins/git/gitsigns.lua

# Tools
for f in toggleterm dap; do
    move "lua/plugins/$f.lua" "lua/plugins/tools/$f.lua"
done

log "reorganize.sh done"
