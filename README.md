# dotfiles

Personal dotfiles: **Neovim**, **Ghostty**, **git**, **Worktrunk**, and **Harness AI** for Claude Code and OpenCode. Neovim is built on `lazy.nvim` with a grouped, mnemonic `<leader>` scheme on Space; Ghostty shares its JetBrains Mono Nerd Font and catppuccin-mocha theme so editor and terminal match.

- [`KEYMAPS.md`](KEYMAPS.md): every mapping
- [`STRUCTURE.md`](STRUCTURE.md): Neovim and harness layout
- [`harness/README.md`](harness/README.md): the AI workflow, skill supply chain, validation

## Install

```bash
./macos.sh    # macOS
./linux.sh    # Linux
```

Each script installs its platform's packages, symlinks the tracked configs, installs the AI clients, links the shared harness, and bootstraps Neovim headlessly. Re-runnable: managed collisions are backed up, matching symlinks left alone, unrelated private skills preserved. `--no-backup` deletes what is in the way instead of renaming it, which is unrecoverable.

Both share `lib/common.sh`, which hands the config links and the harness install to `harness bootstrap`, then bootstraps Neovim. Only the package step differs: `macos.sh` applies `Brewfile` via `brew bundle`, `linux.sh` installs build prerequisites with the distribution's package manager and everything after with Homebrew. Python comes from neither: `lib/python.sh` declares the uv-managed interpreter set once, and `harness install` sources the same file to assert it.

Ghostty picks up `ghostty/config` automatically. Authentication stays interactive, and the installer prints what is left to do.

Requires macOS or Linux, Homebrew (installed when missing), Neovim ≥ 0.10, and a Nerd Font (installed on macOS, bring your own on Linux).

After installing or removing a package, regenerate the manifest with `brew bundle dump --describe --force --file=Brewfile`.

## macOS setup

Two macOS defaults intercept keys before Neovim sees them, and both must be changed by hand.

**Mission Control shortcuts** eat `Ctrl+←/→/↑/↓`, which breaks the window-resize bindings. In **System Settings → Keyboard → Keyboard Shortcuts… → Mission Control**, uncheck Mission Control (`^↑`), Application windows (`^↓`), and Move left/right a space (`^←`, `^→`). Also uncheck Switch to Desktop 1/2/… if you want `<C-1>`/`<C-2>` in Neovim. No restart: type `:` then `Ctrl+Right`, and seeing `<C-Right>` echoed means it worked.

**Option must send Meta**, or `<A-j>`/`<A-k>` silently do nothing and `<A-l>` prints `¬`. Ghostty is already configured here via `macos-option-as-alt`. Terminal.app: Settings → Profiles → Keyboard → Use Option as Meta key. iTerm2: Profiles → Keys → Left/Right Option acts as → Esc+. WezTerm: `send_composed_key_when_left_alt_is_pressed = false`.

Note that `<C-...>` here means Control, never Command; `<D-...>` only works in GUI builds and is never used.

## Layout

```
macos.sh / linux.sh       # platform bootstrap
lib/common.sh             # harness bootstrap hand-off, nvim bootstrap, shared
lib/python.sh             # uv-managed interpreter set, shared with harness install
Brewfile                  # macOS package manifest
harness/                  # two-client policy, commands, skills
skills-lock.json          # reviewed standalone third-party skill lock
.agents/skills            # symlink to the canonical harness/skills
.claude/skills            # skills.sh/Claude bookkeeping symlinks
nvim/                     # → ~/.config/nvim   (init.lua, lazy-lock.json, lua/core + lua/plugins)
ghostty/                  # → ~/.config/ghostty
git/                      # gitconfig → ~/.gitconfig, ignore → ~/.config/git/ignore
worktrunk/                # config.toml → ~/.config/worktrunk/config.toml
```

Machine-local git settings go in `~/.gitconfig.local`, which `git/gitconfig` includes and this repo never tracks.

Plugin files contain setup only; every mapping lives in `nvim/lua/core/keymaps.lua`.

## Plugins

| Plugin | Purpose |
|---|---|
| [lazy.nvim](https://github.com/folke/lazy.nvim) | Plugin manager |
| [snacks.nvim](https://github.com/folke/snacks.nvim) | Core utility suite, replacing telescope, neo-tree, toggleterm and dressing: picker, explorer, terminal, dashboard, notifier, lazygit, gitbrowse, rename, bufdelete, scroll, toggle, words, scope, indent, statuscolumn, bigfile, input, git |
| [nvim-lspconfig](https://github.com/neovim/nvim-lspconfig) + [nvim-cmp](https://github.com/hrsh7th/nvim-cmp) + [mason.nvim](https://github.com/williamboman/mason.nvim) | LSP, completion, and the installer for both |
| [LuaSnip](https://github.com/L3MON4D3/LuaSnip) + [friendly-snippets](https://github.com/rafamadriz/friendly-snippets) | Snippets |
| [nvim-treesitter](https://github.com/nvim-treesitter/nvim-treesitter) | Syntax highlighting and parsing |
| [nvim-dap](https://github.com/mfussenegger/nvim-dap) + [ui](https://github.com/rcarriga/nvim-dap-ui) + [mason-nvim-dap](https://github.com/jay-babu/mason-nvim-dap.nvim) | Debugger |
| [gitsigns.nvim](https://github.com/lewis6991/gitsigns.nvim) | Gutter signs, hunk staging, blame |
| [which-key.nvim](https://github.com/folke/which-key.nvim) | Leader-prefix popup |
| [catppuccin/nvim](https://github.com/catppuccin/nvim) | Colorscheme, mocha flavour |
| [lualine.nvim](https://github.com/nvim-lualine/lualine.nvim) + [bufferline.nvim](https://github.com/akinsho/bufferline.nvim) + [dropbar.nvim](https://github.com/Bekaboo/dropbar.nvim) | Statusline, buffer tabs, winbar breadcrumbs |
| [fidget.nvim](https://github.com/j-hui/fidget.nvim) | LSP progress spinner |
| [nvim-autopairs](https://github.com/windwp/nvim-autopairs) | Auto-close brackets and quotes |
| [nvim-colorizer.lua](https://github.com/catgoose/nvim-colorizer.lua) | Inline color swatches |
| [render-markdown.nvim](https://github.com/MeanderingProgrammer/render-markdown.nvim) | In-buffer markdown rendering |
| [nvim-web-devicons](https://github.com/nvim-tree/nvim-web-devicons) | Filetype icons |

LSP is pre-configured for Lua (`lua_ls`), Python (`pyright`), and TypeScript (`ts_ls`); debuggers for C++ (`cppdbg`, `codelldb`) and Python (`debugpy`). `nvim/lua/plugins/editor/luasnip.lua` ships competitive-programming snippets for `.cpp`: `gcd`, `lcm`, `isPrime`, `fori`, `forin`, `convertToBinaryString`, `nCr`, `nPr`, `fact`, `convertToBaseK`, `sieve`, plus `get_current_time_ms` for `.c`.

The colorscheme is catppuccin-mocha, set in `nvim/lua/plugins/ui/catppuccin.lua`. `<leader>fc` auditions others with live preview. To change the default permanently, the `flavour` field and the `vim.cmd.colorscheme(...)` call in that file must both be edited to match.

## Troubleshooting

| Command | What it tells you |
|---|---|
| `:checkhealth` | Nvim and plugin health: python, node, LSP clients, parsers |
| `:Lazy` / `:Lazy log <name>` | Plugin load status, per-plugin error log |
| `:Mason` | LSP / DAP / formatter installer |
| `:LspInfo` | Clients attached to the current buffer |
| `:messages` | Recent messages, surfacing silent errors |
| `:verbose nmap <key>` | Which file defined a mapping |

- **Resize keys do nothing** → Mission Control shortcuts still enabled, see macOS setup.
- **`<A-j>`/`<A-k>` do nothing, or print `∆`/`˚`** → terminal not passing Option as Meta, see macOS setup.
- **`:Mason` or `:Lazy` empty on first run** → re-run the install script, or `:Lazy sync`.
- **LSP silent for a language** → add it to `ensure_installed` in `nvim/lua/plugins/lsp/mason.lua` and restart.
- **Colorscheme looks wrong** → catppuccin did not load. `:colorscheme` should print `catppuccin-mocha`; fix with `:Lazy sync`.
- **No git signs** → the file is not tracked (gitsigns only signs tracked files), or `:set signcolumn=yes`.
