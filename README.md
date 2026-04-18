# nvim-config

Personal Neovim configuration targeted at macOS. Built around `lazy.nvim` with a
grouped, mnemonic `<leader>` keymap scheme (Space as leader).

## Quick install (macOS)

```bash
./install.sh
```

The script installs Homebrew, the required formulae/casks, links this repo to
`~/.config/nvim`, and bootstraps plugins + Mason packages headlessly so the
first `nvim` launch is instant. Re-runnable.

After it finishes, set your terminal font to **JetBrains Mono Nerd Font**.

## Requirements

- macOS (Darwin)
- Homebrew
- Neovim ≥ 0.10 (installed by the script)
- A Nerd Font (JetBrains Mono Nerd Font is installed by the script)

Sanity check inside nvim: `:checkhealth`, `:Lazy`, `:Mason`.

## macOS-specific setup

Neovim runs in a terminal here, so a couple of macOS defaults get in the way
and must be adjusted manually:

### 1. Disable Mission Control `Ctrl+Arrow` shortcuts (required)

By default macOS intercepts `Ctrl+←/→/↑/↓` for Spaces / Mission Control
before nvim ever sees them, breaking the window-resize bindings.

**System Settings → Keyboard → Keyboard Shortcuts… → Mission Control**

Uncheck:

- **Mission Control** (`^↑`)
- **Application windows** (`^↓`)
- **Move left a space** (`^←`)
- **Move right a space** (`^→`)
- Optionally: **Switch to Desktop 1/2/…** (`^1`, `^2`, …) — these eat
  `<C-1>`/`<C-2>` inside nvim.

No restart needed. Test with `:` then press `Ctrl+Right` inside nvim — if you
see `<C-Right>` echoed instead of a Space switch, you're good.

### 2. Option-as-Meta (required for `<A-j>`/`<A-k>` line-move)

macOS terminals default to inserting special characters (`∆`, `˚`, …) when you
press Option. To make `<A-...>` keys reach nvim:

- **Terminal.app**: Settings → Profiles → Keyboard → **Use Option as Meta key**
- **iTerm2**: Profiles → Keys → **Left/Right Option acts as → Esc+**
- **Ghostty**: `macos-option-as-alt = true` in `~/.config/ghostty/config`
- **WezTerm**: `send_composed_key_when_left_alt_is_pressed = false` in the lua config

Without this, `<A-j>`/`<A-k>` silently do nothing and `<A-l>` prints `¬` into
the buffer. Everything else in the config works regardless of this setting.

### 3. Notes on Command (⌘) and Control (⌃)

- `<C-...>` in this config is **Control (⌃)**, not Command (⌘).
- `<D-...>` (Command) only works in GUI builds like MacVim/Neovide; never used here.
- `<C-h>` can collide with `<BS>` in some terminals. Modern terminals (iTerm2,
  WezTerm, Ghostty) handle it fine.

## Directory layout

```
init.lua                  # entry: loads icons, lazy, maps
install.sh                # macOS bootstrap
lazy-lock.json            # pinned plugin versions
lua/
├── config/
│   ├── icons.lua         # diagnostic/kind icons (global `icons` table)
│   ├── lazy.lua          # lazy.nvim bootstrap + plugin import
│   └── maps.lua          # single source of truth for all keymaps
└── plugins/
    ├── dap.lua           # debug adapter + dap-ui + mason-nvim-dap
    ├── lsp.lua           # nvim-lspconfig + nvim-cmp + cmp sources
    ├── luasnip.lua       # snippet engine + custom C++ problem-solving snippets
    ├── mason.lua         # mason.nvim + mason-lspconfig (lua_ls, pyright, ts_ls)
    ├── neotree.lua       # file explorer
    ├── telescope.lua     # fuzzy finder
    ├── toggleterm.lua    # floating terminal (F7)
    ├── treesitter.lua    # syntax parsing for lua/js/py/bash/java/c/markdown
    └── which-key.lua     # leader-prefix popup + group labels
```

All plugin files contain **setup only** — no keymaps. Every mapping lives in
`lua/config/maps.lua`.

## Plugins

| Plugin | Purpose |
|---|---|
| [lazy.nvim](https://github.com/folke/lazy.nvim) | Plugin manager |
| [telescope.nvim](https://github.com/nvim-telescope/telescope.nvim) | Fuzzy finder |
| [telescope-ui-select.nvim](https://github.com/nvim-telescope/telescope-ui-select.nvim) | Dropdown replacement for `vim.ui.select` |
| [nvim-lspconfig](https://github.com/neovim/nvim-lspconfig) | LSP client configs |
| [nvim-cmp](https://github.com/hrsh7th/nvim-cmp) + sources | Autocompletion |
| [mason.nvim](https://github.com/williamboman/mason.nvim) + [mason-lspconfig](https://github.com/williamboman/mason-lspconfig.nvim) | LSP/DAP/formatter installer |
| [LuaSnip](https://github.com/L3MON4D3/LuaSnip) + [friendly-snippets](https://github.com/rafamadriz/friendly-snippets) | Snippet engine |
| [nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter) | Syntax highlighting / parsing |
| [nvim-dap](https://github.com/mfussenegger/nvim-dap) + [nvim-dap-ui](https://github.com/rcarriga/nvim-dap-ui) + [mason-nvim-dap](https://github.com/jay-babu/mason-nvim-dap.nvim) | Debugger |
| [toggleterm.nvim](https://github.com/akinsho/toggleterm.nvim) | Floating terminal |
| [neo-tree.nvim](https://github.com/nvim-neo-tree/neo-tree.nvim) | File explorer |
| [which-key.nvim](https://github.com/folke/which-key.nvim) | Leader-prefix popup |
| [gitsigns.nvim](https://github.com/lewis6991/gitsigns.nvim) | Git gutter signs, hunk staging, blame |
| [catppuccin/nvim](https://github.com/catppuccin/nvim) | Colorscheme (mocha flavour) |
| [lualine.nvim](https://github.com/nvim-lualine/lualine.nvim) | Bottom statusline (mode, branch, diagnostics, LSP, position) |
| [dropbar.nvim](https://github.com/Bekaboo/dropbar.nvim) | Top winbar breadcrumbs (file > scope > symbol) |
| [bufferline.nvim](https://github.com/akinsho/bufferline.nvim) | Top buffer tabs with catppuccin styling |
| [nvim-web-devicons](https://github.com/nvim-tree/nvim-web-devicons) | Filetype icons (shared dependency) |
| [nvim-colorizer.lua](https://github.com/catgoose/nvim-colorizer.lua) | Inline color swatches for hex / rgb / hsl literals |
| [dressing.nvim](https://github.com/stevearc/dressing.nvim) | Prettier `vim.ui.input` / `vim.ui.select` (routes select to Telescope) |
| [snacks.nvim](https://github.com/folke/snacks.nvim) | Utility suite: bigfile perf, notifier, indent guides, scope, word highlight, statuscolumn |
| [fidget.nvim](https://github.com/j-hui/fidget.nvim) | LSP progress spinner in bottom-right |

Languages pre-configured for LSP: Lua (`lua_ls`), Python (`pyright`),
TypeScript (`ts_ls`). Debuggers: C++ (`cppdbg`, `codelldb`), Python (`debugpy`).

## Keymap reference

Leader is **Space**. Press `<leader>` and wait ~0.4s to see the which-key popup.
Use `<leader>fk` for a fuzzy-searchable Telescope view of every mapping.

### Core

| Key | Action |
|---|---|
| `<leader>w` | Save file |
| `<leader>q` | Quit window |
| `<leader>h` | Clear search highlight |

### Buffers — `<leader>b*`

| Key | Action |
|---|---|
| `]b` / `[b` | Next / previous buffer |
| `<leader>bd` | Delete buffer |

### Splits — `<leader>s*`

| Key | Action |
|---|---|
| `<leader>sv` | Vertical split |
| `<leader>sh` | Horizontal split |
| `<leader>sc` | Close window |
| `<leader>so` | Close other windows (`:only`) |

### Window navigation & resize

| Key | Action |
|---|---|
| `<C-h/j/k/l>` | Move between windows |
| `<C-Left/Right>` | Narrower / wider |
| `<C-Up/Down>` | Taller / shorter |

> Resize keys require the Mission Control shortcuts disabled (see setup above).

### Editing ergonomics

| Key | Mode | Action |
|---|---|---|
| `<C-d>` / `<C-u>` | n | Half-page down / up, cursor stays centered |
| `n` / `N` | n | Next / prev search match, centered + unfolded |
| `<` / `>` | v | Indent and keep the selection |
| `<A-j>` / `<A-k>` | n, v | Move line / block down / up |

### File explorer (NeoTree) — `<leader>e*`

| Key | Action |
|---|---|
| `<leader>e` | Toggle |
| `<leader>E` | Focus |
| `<leader>eh` | Toggle hidden / gitignored files |

### Find (Telescope) — `<leader>f*`

| Key | Action |
|---|---|
| `<leader>ff` | Find files |
| `<leader>fg` | Live grep |
| `<leader>fw` | Grep word under cursor |
| `<leader>fb` | Buffers |
| `<leader>fh` | Help tags |
| `<leader>fr` | Recent files (oldfiles) |
| `<leader>fk` | Keymaps (this config!) |
| `<leader>fd` | Workspace diagnostics |
| `<leader>fp` | Resume last picker |
| `<leader>fc` | Colorscheme picker (with preview) |

### Git — `<leader>g*`

| Key | Action |
|---|---|
| `<leader>ge` | NeoTree git status view |
| `<leader>gf` | Git files |
| `<leader>gb` | Git branches |
| `<leader>gs` | Git status |
| `<leader>gc` | Git commits |

### Git hunks (gitsigns) — `<leader>gh*` + `[h` / `]h`

| Key | Mode | Action |
|---|---|---|
| `]h` / `[h` | n | Next / previous hunk |
| `<leader>ghs` | n, v | Stage hunk (or selection) |
| `<leader>ghr` | n, v | Reset hunk (or selection) |
| `<leader>ghS` | n | Stage buffer |
| `<leader>ghR` | n | Reset buffer |
| `<leader>ghu` | n | Undo stage |
| `<leader>ghp` | n | Preview hunk |
| `<leader>ghd` | n | Diff this buffer |
| `<leader>ghb` | n | Blame line (full popup) |
| `<leader>ght` | n | Toggle inline line-blame |

### LSP — `gN` / `K` / `<leader>l*`

| Key | Action |
|---|---|
| `gd` / `gD` | Go to definition / declaration |
| `gi` | Go to implementation |
| `gr` | References |
| `K` | Hover docs |
| `<leader>ln` | Rename symbol |
| `<leader>la` | Code action (n, v) |
| `<leader>lf` | Format buffer (async) |
| `<leader>ls` | Signature help |
| `<leader>le` | Line diagnostic (float) |
| `<leader>ld` | Diagnostic loclist |
| `[d` / `]d` | Previous / next diagnostic |

### DAP — F-keys + `<leader>d*`

| Key | Action |
|---|---|
| `<F5>` | Continue |
| `<F10>` | Step over |
| `<F11>` | Step into |
| `<F12>` | Step out |
| `<leader>db` | Toggle breakpoint |
| `<leader>dB` | Conditional breakpoint |
| `<leader>dc` / `do` / `di` / `dO` | Continue / over / into / out |
| `<leader>dr` | Toggle REPL |
| `<leader>dl` | Run last |
| `<leader>du` | Toggle DAP UI |
| `<leader>dt` | Terminate |

### Terminal — `<F7>` + `<leader>t*`

| Key | Mode | Action |
|---|---|---|
| `<F7>` | n | Toggle floating terminal (toggleterm `open_mapping`) |
| `<leader>tf` | n | Float terminal |
| `<leader>th` | n | Horizontal terminal |
| `<leader>tv` | n | Vertical terminal |
| `<Esc><Esc>` | t | Exit terminal mode to normal mode |

### Snippets (LuaSnip) — insert / select mode

| Key | Action |
|---|---|
| `<C-k>` | Expand or jump forward |
| `<C-j>` | Jump backward |
| `<C-l>` | Next choice in a choice node |

### Breadcrumbs (dropbar)

| Key | Action |
|---|---|
| `<leader>;` | Pick a breadcrumb segment from the winbar |

## Completion (nvim-cmp)

Configured in `lua/plugins/lsp.lua`:

| Key | Action |
|---|---|
| `<Down>` / `<Up>` | Select next / prev item |
| `<CR>` | Confirm (selects first item if none highlighted) |
| `<C-e>` | Abort menu |

Sources: `nvim_lsp`, `luasnip`, `buffer`, `path`. Ghost text enabled.

## Colorscheme

Default: **catppuccin-mocha** (set in `lua/plugins/catppuccin.lua`).

### Verify the scheme is loaded

```vim
:colorscheme         " prints the active scheme
:echo g:colors_name  " same thing, lower level
:Lazy                " catppuccin should show a green dot (loaded)
```

Both commands should report `catppuccin-mocha`. Visually: a dark warm base
(`#1e1e2e`), lavender keywords, muted-green strings, muted-purple comments.

### Switch flavour temporarily

```vim
:colorscheme catppuccin-latte       " light
:colorscheme catppuccin-frappe
:colorscheme catppuccin-macchiato
:colorscheme catppuccin-mocha       " current default
```

### Change the default permanently

Edit `lua/plugins/catppuccin.lua`:

```lua
opts = {
    flavour = "macchiato",  -- latte | frappe | macchiato | mocha
    ...
},
config = function(_, opts)
    require("catppuccin").setup(opts)
    vim.cmd.colorscheme("catppuccin-macchiato")
end,
```

Both the `flavour` field and the `vim.cmd.colorscheme(...)` call must match.

### Pick from a fuzzy picker

`<leader>fc` opens Telescope's colorscheme picker with live preview — good for
auditioning other schemes without editing files.

## Sanity checks

| Command | What it tells you |
|---|---|
| `:checkhealth` | Nvim + plugin health (python, node, LSP clients, treesitter parsers, …) |
| `:Lazy` | Plugin installation / load status |
| `:Lazy log <name>` | Per-plugin error / commit log |
| `:Mason` | LSP / DAP / formatter installer UI |
| `:LspInfo` | Clients attached to the current buffer |
| `:messages` | Recent nvim messages (surface silent errors) |
| `:verbose nmap <key>` | Which file defined a mapping |

## Custom C++ snippets

`lua/plugins/luasnip.lua` ships competitive-programming helpers for `.cpp`
files: `gcd`, `lcm`, `isPrime`, `fori`, `forin`, `convertToBinaryString`, `nCr`,
`nPr`, `fact`, `convertToBaseK`, `sieve`. Also `get_current_time_ms` for `.c`.

## Troubleshooting

- **Window resize keys do nothing** → macOS Mission Control shortcuts still
  enabled. See setup step 1.
- **`<A-j>`/`<A-k>` do nothing (or print `∆`/`˚`)** → terminal not configured
  to pass Option as Meta. See setup step 2.
- **"Who overrode my keymap?"** → `:verbose nmap <leader>ff` shows the defining
  file and line. Everything should point at `lua/config/maps.lua`.
- **`:Mason` / `:Lazy` empty on first run** → re-run `./install.sh` or run
  `:Lazy sync` and `:MasonInstall lua-language-server pyright ...` manually.
- **LSP silent on a language not in the ensure_installed list** →
  `lua/plugins/mason.lua` → add to `ensure_installed`, restart nvim.
- **Colorscheme looks wrong / default black-on-white** → catppuccin didn't load.
  Check with `:colorscheme` (should print `catppuccin-mocha`) and `:Lazy log
  catppuccin`. First-launch fix: `:Lazy sync`.
- **No git signs in the gutter** → not a git-tracked file (gitsigns only signs
  tracked files), or signcolumn hidden. `:set signcolumn=yes` to force it on.
