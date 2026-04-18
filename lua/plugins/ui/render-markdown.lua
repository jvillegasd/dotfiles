return {
    "MeanderingProgrammer/render-markdown.nvim",
    ft = { "markdown" },
    dependencies = {
        "nvim-treesitter/nvim-treesitter",
        "nvim-tree/nvim-web-devicons",
    },
    opts = {
        completions = { lsp = { enabled = true } },
        heading = { icons = { " ", " ", " ", " ", " ", " " } },
        code = { style = "normal", width = "block", border = "thin" },
        bullet = { icons = { "●", "○", "◆", "◇" } },
        checkbox = {
            unchecked = { icon = " 󰄱 " },
            checked = { icon = " 󰱒 " },
        },
    },
}
