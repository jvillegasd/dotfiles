local parsers = { "lua", "javascript", "python", "bash", "java", "c", "markdown", "markdown_inline", "vim", "vimdoc", "query" }

return {
    "nvim-treesitter/nvim-treesitter",
    branch = "main",
    build = ":TSUpdate",
    lazy = false,
    config = function()
        require("nvim-treesitter").setup({
            install_dir = vim.fn.stdpath("data") .. "/site",
        })

        require("nvim-treesitter").install(parsers)

        vim.api.nvim_create_autocmd("FileType", {
            pattern = parsers,
            callback = function(args)
                pcall(vim.treesitter.start, args.buf)
                vim.wo.foldexpr = "v:lua.vim.treesitter.foldexpr()"
                vim.bo[args.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
            end,
        })
    end,
}
