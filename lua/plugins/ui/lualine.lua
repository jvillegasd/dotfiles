return {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
        require("lualine").setup({
            options = {
                theme = "catppuccin-mocha",
                globalstatus = true,
                disabled_filetypes = {
                    statusline = { "neo-tree", "dapui_scopes", "dapui_breakpoints",
                        "dapui_stacks", "dapui_watches", "dap-repl" },
                },
            },
            sections = {
                lualine_y = { "location", "progress" },
                lualine_z = {
                    { function() return os.date("%H:%M") end, icon = "" },
                },
            },
        })

        if _G.Statusline_timer == nil then
            _G.Statusline_timer = vim.loop.new_timer()
        else
            _G.Statusline_timer:stop()
        end
        _G.Statusline_timer:start(0, 30000, vim.schedule_wrap(function()
            vim.api.nvim_command("redrawstatus")
        end))
    end,
}
