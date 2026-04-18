return {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    opts = {
        options = {
            theme = "catppuccin-mocha",
            globalstatus = true,
            disabled_filetypes = {
                statusline = { "neo-tree", "dapui_scopes", "dapui_breakpoints",
                    "dapui_stacks", "dapui_watches", "dap-repl" },
            },
        },
    },
}
