vim.g.mapleader = " "

local function map(mode, lhs, rhs, opts)
    opts = vim.tbl_extend("force", { silent = true, noremap = true }, opts or {})
    vim.keymap.set(mode, lhs, rhs, opts)
end

local function telescope(name)
    return function() require("telescope.builtin")[name]() end
end

local function dap_call(fn)
    return function() require("dap")[fn]() end
end


-- Core
map("n", "<leader>w", "<CMD>update<CR>")
map("n", "<leader>q", "<CMD>q<CR>")


-- Splits — <leader>s*
map("n", "<leader>sv", "<CMD>vsplit<CR>")
map("n", "<leader>sh", "<CMD>split<CR>")
map("n", "<leader>sc", "<CMD>close<CR>")
map("n", "<leader>so", "<CMD>only<CR>")


-- Window navigation & resize
map("n", "<C-h>", "<C-w>h")
map("n", "<C-l>", "<C-w>l")
map("n", "<C-k>", "<C-w>k")
map("n", "<C-j>", "<C-w>j")

map("n", "<C-Left>", "<C-w><")
map("n", "<C-Right>", "<C-w>>")
map("n", "<C-Up>", "<C-w>+")
map("n", "<C-Down>", "<C-w>-")


-- NeoTree — <leader>e*
map("n", "<leader>e", "<CMD>Neotree toggle<CR>")
map("n", "<leader>E", "<CMD>Neotree focus<CR>")
map("n", "<leader>eh", function()
    local state = require("neo-tree.sources.manager").get_state("filesystem")
    if state then
        local filters = state.filtered_items
        filters.visible = not filters.visible
        filters.hide_dotfiles = not filters.hide_dotfiles
        filters.hide_gitignored = not filters.hide_gitignored
        require("neo-tree.sources.filesystem")._navigate_internal(state, nil, nil)
    end
end, { desc = "Toggle hidden files" })


-- Telescope — <leader>f* (find)
map("n", "<leader>ff", telescope("find_files"))
map("n", "<leader>fg", telescope("live_grep"))
map("n", "<leader>fb", telescope("buffers"))
map("n", "<leader>fh", telescope("help_tags"))
map("n", "<leader>fr", telescope("oldfiles"))
map("n", "<leader>fk", telescope("keymaps"))
map("n", "<leader>fd", telescope("diagnostics"))
map("n", "<leader>fc", function()
    require("telescope.builtin").colorscheme({ enable_preview = true })
end)


-- Git — <leader>g*
map("n", "<leader>ge", "<CMD>Neotree toggle git_status<CR>")
map("n", "<leader>gf", telescope("git_files"))
map("n", "<leader>gb", telescope("git_branches"))
map("n", "<leader>gs", telescope("git_status"))
map("n", "<leader>gc", telescope("git_commits"))


-- LSP — gN / K / <leader>l*
map("n", "gd", vim.lsp.buf.definition)
map("n", "gD", vim.lsp.buf.declaration)
map("n", "gi", vim.lsp.buf.implementation)
map("n", "gr", vim.lsp.buf.references)
map("n", "K", vim.lsp.buf.hover)
map("n", "<leader>ln", vim.lsp.buf.rename)
map({ "n", "v" }, "<leader>la", vim.lsp.buf.code_action)
map("n", "<leader>lf", function() vim.lsp.buf.format({ async = true }) end)
map("n", "<leader>ls", vim.lsp.buf.signature_help)
map("n", "<leader>le", vim.diagnostic.open_float)
map("n", "<leader>ld", vim.diagnostic.setloclist)
map("n", "[d", vim.diagnostic.goto_prev)
map("n", "]d", vim.diagnostic.goto_next)


-- DAP — F-keys + <leader>d*
map("n", "<F5>", dap_call("continue"))
map("n", "<F10>", dap_call("step_over"))
map("n", "<F11>", dap_call("step_into"))
map("n", "<F12>", dap_call("step_out"))

map("n", "<leader>db", dap_call("toggle_breakpoint"))
map("n", "<leader>dB", function()
    require("dap").set_breakpoint(vim.fn.input("Condition: "))
end)
map("n", "<leader>dc", dap_call("continue"))
map("n", "<leader>do", dap_call("step_over"))
map("n", "<leader>di", dap_call("step_into"))
map("n", "<leader>dO", dap_call("step_out"))
map("n", "<leader>dr", function() require("dap").repl.toggle() end)
map("n", "<leader>dl", dap_call("run_last"))
map("n", "<leader>du", function() require("dapui").toggle() end)
map("n", "<leader>dt", dap_call("terminate"))


-- Terminal — <F7> handled by toggleterm; <leader>t* for directional variants
map("n", "<leader>tf", "<CMD>ToggleTerm direction=float<CR>")
map("n", "<leader>th", "<CMD>ToggleTerm direction=horizontal<CR>")
map("n", "<leader>tv", "<CMD>ToggleTerm direction=vertical<CR>")


-- Luasnip — insert/select mode jumps
map({ "i", "s" }, "<C-k>", function()
    local ls = require("luasnip")
    if ls.expand_or_jumpable() then ls.expand_or_jump() end
end)
map({ "i", "s" }, "<C-j>", function()
    local ls = require("luasnip")
    if ls.jumpable(-1) then ls.jump(-1) end
end)
map({ "i", "s" }, "<C-l>", function()
    local ls = require("luasnip")
    if ls.choice_active() then ls.change_choice(1) end
end)
