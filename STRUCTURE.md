# Structure

Organization guide for this dotfiles repo. It holds two configs as siblings:

```
install.sh                      # macOS bootstrap (brew + symlinks + mason + treesitter)
README.md                       # User-facing docs
STRUCTURE.md                    # This file
reorganize.sh                   # Legacy migration helper (flat → categorized plugins/)
nvim/                           # → ~/.config/nvim  (symlinked by install.sh)
ghostty/                        # → ~/.config/ghostty (symlinked by install.sh)
    └── config                  # font, theme, padding, macOS Option-as-Alt
```

The rest of this document describes the `nvim/` subtree — the Neovim config.

## Neovim layout (inside `nvim/`)

```
init.lua                        # Entry point: loads core + plugins
lazy-lock.json                  # Plugin version lock (committed)

lua/
├── core/                       # Editor-level config (no plugins)
│   ├── icons.lua               # Global `icons` table (diagnostics, git, lsp kinds)
│   ├── options.lua             # vim.opt.*: numbers, indent, search, ui, files
│   └── keymaps.lua             # Global keymap scheme (leader groups)
│
├── plugins.lua                 # lazy.nvim bootstrap — imports each category below
│
└── plugins/                    # Plugin specs, one file per plugin
    ├── ui/                     # Appearance & chrome
    │   ├── catppuccin.lua        # Colorscheme (mocha flavour)
    │   ├── lualine.lua           # Statusline
    │   ├── bufferline.lua        # Top buffer tabs
    │   ├── dropbar.lua           # Winbar breadcrumbs
    │   ├── snacks.lua            # Picker + explorer + terminal + dashboard + notifier + lazygit + gitbrowse + rename + bufdelete + scroll + toggle + words + scope + indent + statuscolumn + bigfile + input + git
    │   ├── fidget.lua            # LSP progress spinner
    │   ├── nvim-colorizer.lua    # Inline #RRGGBB swatches
    │   ├── render-markdown.lua   # In-buffer markdown rendering
    │   └── web-devicons.lua      # Filetype icons
    │
    ├── editor/                 # Editing surface & navigation
    │   ├── treesitter.lua        # Parser management + highlight/fold/indent autocmds
    │   ├── which-key.lua         # Leader-prefix popup
    │   ├── luasnip.lua           # Snippet engine + custom C++ snippets
    │   └── autopairs.lua         # Auto-close brackets; cmp hook for ()
    │
    ├── lsp/                    # Language servers & completion
    │   ├── lsp-config.lua        # nvim-lspconfig + diagnostic config
    │   ├── completions.lua       # nvim-cmp + sources + cmdline completion
    │   └── mason.lua             # Mason + mason-lspconfig (lua_ls, pyright, ts_ls)
    │
    ├── git/                    # Git integration
    │   └── gitsigns.lua          # Gutter signs + hunk staging + blame
    │
    └── tools/                  # Development tools
        └── dap.lua               # Debug adapter + dap-ui + mason-nvim-dap
```

## Load order

`init.lua` loads in this sequence:

1. `require("core.icons")` — exposes a global `icons` table before any plugin references it.
2. `require("core.options")` — `vim.opt.*` settings. Safe to require before lazy because it doesn't touch any plugin.
3. `require("plugins")` — bootstraps lazy.nvim, sets `mapleader`, and imports each category in `lua/plugins/<category>/`.
4. `require("core.keymaps")` — keymaps last, so plugin commands like `Snacks.picker.*`, `Snacks.explorer`, `Snacks.terminal` are already registered.

## Adding a plugin

1. Decide the category: UI chrome → `ui/`, editing/navigation → `editor/`, LSP → `lsp/`, git → `git/`, otherwise → `tools/`.
2. Create `lua/plugins/<category>/<name>.lua` returning a lazy.nvim plugin spec.
3. That's it — lazy picks it up via `{ import = "plugins.<category>" }` in `lua/plugins.lua`.

Keymaps go in `lua/core/keymaps.lua`, not inside the plugin file.

## Rationale for this split

- **`core/` vs `plugins/`** — editor-level config that must exist regardless of plugins (options, leader, icons) is isolated from optional plugin specs.
- **One plugin per file** — easier to disable (delete / rename `.lua` → `.lua.off`), easier to grep, easier to review in a diff.
- **Categories instead of flat** — at ~20+ plugins, a flat directory becomes noisy. Categories mean you find LSP settings in `lsp/`, not scrolling past UI plugins.
- **Keymaps centralized** — one file answers "what does `<leader>…` do" without hunting through plugin configs. Plugin files stay focused on setup only.

## Catppuccin integration

Catppuccin ships per-plugin integration modules in its own source tree. With `auto_integrations = true` in `plugins/ui/catppuccin.lua`, it detects installed plugins from lazy's spec and enables the matching highlight groups automatically. Currently auto-enabled: `cmp, dap, dap_ui, dropbar, fidget, gitsigns, mason, snacks, which_key` (telescope/neo-tree removed now that snacks subsumes them).

Lualine is themed differently — it uses catppuccin's `lua/lualine/themes/catppuccin-mocha.lua` preset directly via `theme = "catppuccin-mocha"` in `plugins/ui/lualine.lua`, not via `integrations`.

Bufferline uses `require("catppuccin.special.bufferline").get_theme()` — a helper, not an integration.
