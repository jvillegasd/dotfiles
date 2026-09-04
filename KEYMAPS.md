# Keymaps

Leader is **Space**. Press `<leader>` and wait ~0.4s for the which-key popup.
Use `<leader>fk` for a fuzzy-searchable snacks.picker view of every mapping.

Every mapping is defined in `nvim/lua/core/keymaps.lua`; plugin files contain
setup only. See [`STRUCTURE.md`](STRUCTURE.md) for why.

## Core

| Key | Action |
|---|---|
| `<leader>w` | Save file |
| `<leader>q` | Quit window |
| `<leader>h` | Clear search highlight |

## Buffers — `<leader>b*`

| Key | Action |
|---|---|
| `]b` / `[b` | Next / previous buffer |
| `<leader>bd` | Delete current buffer (keep window split) |
| `<leader>bo` | Delete all other buffers |
| `<leader>ba` | Delete all buffers |

## Splits — `<leader>s*`

| Key | Action |
|---|---|
| `<leader>sv` | Vertical split |
| `<leader>sh` | Horizontal split |
| `<leader>sc` | Close window |
| `<leader>so` | Close other windows (`:only`) |

## Window navigation & resize

| Key | Action |
|---|---|
| `<C-h/j/k/l>` | Move between windows |
| `<C-Left/Right>` | Narrower / wider |
| `<C-Up/Down>` | Taller / shorter |

> Resize keys need the macOS Mission Control shortcuts disabled. See [`README.md`](README.md#macos-setup).

## Editing ergonomics

| Key | Mode | Action |
|---|---|---|
| `<C-d>` / `<C-u>` | n | Half-page down / up, cursor stays centered |
| `n` / `N` | n | Next / prev search match, centered + unfolded |
| `<` / `>` | v | Indent and keep the selection |
| `<A-j>` / `<A-k>` | n, v | Move line / block down / up |

## File explorer (snacks.explorer) — `<leader>e`

| Key | Action |
|---|---|
| `<leader>e` | Toggle the explorer pane |

Inside the explorer the snacks defaults apply: `l`/`<CR>` open, `h` collapse, `a` add, `r` rename (LSP-aware via `snacks.rename`), `d` delete, `y`/`p` yank/paste, `H` toggle hidden, `I` toggle gitignored, `]g`/`[g` jump to git changes, `]d`/`[d` jump to diagnostics.

## Find (snacks.picker) — `<leader>f*`

| Key | Action |
|---|---|
| `<leader>ff` | Files |
| `<leader>fg` | Live grep |
| `<leader>fw` | Grep word under cursor |
| `<leader>fb` | Buffers |
| `<leader>fh` | Help tags |
| `<leader>fr` | Recent files |
| `<leader>fk` | Keymaps (this config!) |
| `<leader>fd` | Workspace diagnostics |
| `<leader>fp` | Resume last picker |
| `<leader>fc` | Colorscheme picker (with preview) |

## Git — `<leader>g*`

| Key | Action |
|---|---|
| `<leader>ge` | Git status picker (alias for `<leader>gs`) |
| `<leader>gf` | Git files |
| `<leader>gb` | Git branches |
| `<leader>gs` | Git status |
| `<leader>gc` | Git log |
| `<leader>gl` | Lazygit (floating, themed) |
| `<leader>gB` | Open current file on remote (GitHub/GitLab) in browser |

## Git hunks (gitsigns) — `<leader>gh*` + `[h` / `]h`

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

## LSP — `gN` / `K` / `<leader>l*`

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

## DAP — F-keys + `<leader>d*`

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

## Terminal (snacks.terminal) — `<F7>` + `<leader>t*`

| Key | Mode | Action |
|---|---|---|
| `<F7>` | n | Toggle floating terminal |
| `<leader>tf` | n | Float terminal |
| `<leader>th` | n | Bottom terminal (horizontal split) |
| `<leader>tv` | n | Right terminal (vertical split) |
| `<Esc><Esc>` | t | Exit terminal mode to normal mode |

## Snippets (LuaSnip) — insert / select mode

| Key | Action |
|---|---|
| `<C-k>` | Expand or jump forward |
| `<C-j>` | Jump backward |
| `<C-l>` | Next choice in a choice node |

## Breadcrumbs (dropbar)

| Key | Action |
|---|---|
| `<leader>;` | Pick a breadcrumb segment from the winbar |

## Completion (nvim-cmp)

Configured in `nvim/lua/plugins/lsp/lsp-config.lua`:

| Key | Action |
|---|---|
| `<Down>` / `<Up>` | Select next / prev item |
| `<CR>` | Confirm (selects first item if none highlighted) |
| `<C-e>` | Abort menu |

Sources: `nvim_lsp`, `luasnip`, `buffer`, `path`. Ghost text enabled.
