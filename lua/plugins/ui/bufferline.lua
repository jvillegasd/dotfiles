return {
    "akinsho/bufferline.nvim",
    version = "*",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
        require("bufferline").setup({
            options = {
                mode = "buffers",
                diagnostics = "nvim_lsp",
                show_buffer_close_icons = false,
                show_close_icon = false,
                always_show_bufferline = true,
                offsets = {
                    {
                        filetype = "neo-tree",
                        text = "Explorer",
                        text_align = "left",
                        separator = true,
                    },
                },
            },
            highlights = require("catppuccin.special.bufferline").get_theme(),
        })
    end,
}
