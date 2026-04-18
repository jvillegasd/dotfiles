return {
    "neovim/nvim-lspconfig",
    event = { "BufReadPre", "BufNewFile" },
    dependencies = {
        "hrsh7th/cmp-nvim-lsp",
    },
    config = function()
        vim.diagnostic.config({
            virtual_text = {
                spacing = 4,
                source = "if_many",
                prefix = "●",
            },
            signs = {
                text = {
                    [vim.diagnostic.severity.ERROR] = icons.diagnostics.Error,
                    [vim.diagnostic.severity.WARN] = icons.diagnostics.Warn,
                    [vim.diagnostic.severity.HINT] = icons.diagnostics.Hint,
                    [vim.diagnostic.severity.INFO] = icons.diagnostics.Info,
                },
            },
            update_in_insert = true,
            severity_sort = true,
        })

        vim.api.nvim_create_autocmd("CursorHold", {
            callback = function()
                vim.diagnostic.open_float(nil, { focusable = false })
            end,
        })
    end,
}
