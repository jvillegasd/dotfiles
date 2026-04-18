return {
    "stevearc/dressing.nvim",
    event = "VeryLazy",
    opts = function()
        return {
            input = {
                default_prompt = "➤ ",
                border = "rounded",
                win_options = { winblend = 0 },
            },
            select = {
                backend = { "telescope", "builtin" },
                telescope = require("telescope.themes").get_dropdown({ previewer = false }),
            },
        }
    end,
}
