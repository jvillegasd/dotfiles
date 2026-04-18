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
        dashboard = {
            enabled = true,
            preset = {
                header = [[

               ████ ██████           █████      ██
              ███████████             █████
              █████████ ███████████████████ ███   ███████████
             █████████  ███    █████████████ █████ ██████████████
            █████████ ██████████ █████████ █████ █████ ████ █████
          ███████████ ███    ███ █████████ █████ █████ ████ █████
         ██████  █████████████████████ ████ █████ █████ ████ ██████
      ]],
            },
            sections = {
                { section = "header" },
                { icon = " ", title = "Keymaps",      section = "keys",         indent = 2, padding = 1 },
                { icon = " ", title = "Recent Files", section = "recent_files", indent = 2, padding = 1 },
                { icon = " ", title = "Projects",     section = "projects",     indent = 2, padding = 1 },
                { section = "startup" },
            },
        },
    },
}
