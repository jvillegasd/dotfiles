return {
    "lewis6991/gitsigns.nvim",
    event = { "BufReadPre", "BufNewFile" },
    opts = {
        signs = {
            add          = { text = icons.git.added },
            change       = { text = icons.git.modified },
            delete       = { text = icons.git.removed },
            topdelete    = { text = icons.git.removed },
            changedelete = { text = icons.git.modified },
            untracked    = { text = icons.git.added },
        },
        current_line_blame = false,
        current_line_blame_opts = {
            virt_text = true,
            virt_text_pos = "eol",
            delay = 400,
        },
        preview_config = {
            border = "rounded",
        },
    },
}
