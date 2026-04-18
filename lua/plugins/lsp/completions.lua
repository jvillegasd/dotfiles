return {
    "hrsh7th/nvim-cmp",
    event = { "InsertEnter", "CmdlineEnter" },
    dependencies = {
        "hrsh7th/cmp-nvim-lsp",
        "hrsh7th/cmp-buffer",
        "hrsh7th/cmp-path",
        "hrsh7th/cmp-cmdline",
        "hrsh7th/cmp-nvim-lsp-signature-help",
        "L3MON4D3/LuaSnip",
        "saadparwaiz1/cmp_luasnip",
        "rafamadriz/friendly-snippets",
    },
    config = function()
        local cmp = require("cmp")
        local luasnip = require("luasnip")

        cmp.setup({
            snippet = {
                expand = function(args)
                    luasnip.lsp_expand(args.body)
                end,
            },
            mapping = {
                ["<Down>"] = cmp.mapping.select_next_item(),
                ["<Up>"] = cmp.mapping.select_prev_item(),
                ["<C-e>"] = cmp.mapping.abort(),
                ["<CR>"] = cmp.mapping.confirm({ select = true }),
            },
            sources = cmp.config.sources({
                { name = "nvim_lsp" },
                { name = "luasnip" },
                { name = "nvim_lsp_signature_help" },
            }, {
                { name = "buffer" },
                { name = "path" },
            }),
            completion = {
                completeopt = "menu,menuone,noinsert",
            },
            experimental = {
                ghost_text = true,
            },
            formatting = {
                format = function(entry, item)
                    local kinds = icons.kinds
                    if kinds[item.kind] then
                        item.kind = kinds[item.kind] .. item.kind
                    end

                    local widths = {
                        abbr = vim.g.cmp_widths and vim.g.cmp_widths.abbr or 40,
                        menu = vim.g.cmp_widths and vim.g.cmp_widths.menu or 30,
                    }

                    for key, width in pairs(widths) do
                        if item[key] and vim.fn.strdisplaywidth(item[key]) > width then
                            item[key] = vim.fn.strcharpart(item[key], 0, width - 1) .. "…"
                        end
                    end

                    return item
                end,
            },
        })

        cmp.setup.cmdline("/", {
            mapping = cmp.mapping.preset.cmdline(),
            sources = { { name = "buffer" } },
        })

        cmp.setup.cmdline(":", {
            mapping = cmp.mapping.preset.cmdline(),
            sources = cmp.config.sources({
                { name = "path" },
            }, {
                { name = "cmdline" },
            }),
        })

        require("luasnip.loaders.from_vscode").lazy_load()
    end,
}
