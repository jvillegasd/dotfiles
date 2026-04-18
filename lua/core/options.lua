local opt = vim.opt

-- Line numbers
opt.number = true
opt.relativenumber = true

-- Indentation
opt.expandtab = true
opt.shiftwidth = 4
opt.tabstop = 4
opt.softtabstop = 4
opt.smartindent = true

-- Search
opt.ignorecase = true
opt.smartcase = true
opt.incsearch = true

-- UI
opt.termguicolors = true
opt.signcolumn = "yes"
opt.cursorline = true
opt.scrolloff = 8
opt.sidescrolloff = 8
opt.wrap = false
opt.splitright = true
opt.splitbelow = true

-- Files
opt.undofile = true
opt.swapfile = false
opt.updatetime = 250
opt.timeoutlen = 400

-- Completion
opt.completeopt = { "menu", "menuone", "noinsert" }

-- Clipboard sync with system
opt.clipboard = "unnamedplus"
