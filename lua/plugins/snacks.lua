return {
    "folke/snacks.nvim",
    priority = 1000,
    lazy = false,
    opts = {
        bigfile = { enabled = true },
        quickfile = { enabled = true },
        notifier = { enabled = true, timeout = 3000 },
        indent = { enabled = true },
        scope = { enabled = true },
        words = { enabled = true },
        statuscolumn = { enabled = true },
        input = { enabled = false },
        picker = { enabled = false },
        dashboard = { enabled = false },
    },
}
