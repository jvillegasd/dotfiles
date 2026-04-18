return {
    "nvim-treesitter/nvim-treesitter",
    branch = "master",
    build = ":TSUpdate",
    event = { "BufReadPost", "BufNewFile" },
    config = function()
        require("nvim-treesitter.configs").setup({
            ensure_installed = { "lua", "javascript", "python", "bash", "java", "c", "markdown" },
            highlight = { enable = true },
            indent = { enable = true },
        })
    end,
}
