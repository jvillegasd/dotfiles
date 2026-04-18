return {
    "folke/which-key.nvim",
    event = "VeryLazy",
    opts = {
        preset = "modern",
        delay = 400,
    },
    config = function(_, opts)
        local wk = require("which-key")
        wk.setup(opts)
        wk.add({
            { "<leader>b", group = "buffer" },
            { "<leader>f", group = "find" },
            { "<leader>g", group = "git" },
            { "<leader>gh", group = "hunks" },
            { "<leader>l", group = "lsp" },
            { "<leader>d", group = "dap" },
            { "<leader>t", group = "terminal" },
            { "<leader>s", group = "splits" },
            { "<leader>e", group = "explorer" },
        })
    end,
}
