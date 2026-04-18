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
        bufdelete = { enabled = true },
        scroll = { enabled = true },
        toggle = { enabled = true, which_key = true },
        rename = { enabled = true },
        lazygit = { enabled = true, configure = true },
        git = { enabled = true },
        gitbrowse = { enabled = true },
        input = { enabled = true },
        picker = { enabled = true, ui_select = true },
        explorer = { enabled = true },
        dashboard = {
            enabled = true,
            preset = {
                header = [[
███╗   ██╗███████╗ ██████╗ ██╗   ██╗██╗███╗   ███╗
████╗  ██║██╔════╝██╔═══██╗██║   ██║██║████╗ ████║
██╔██╗ ██║█████╗  ██║   ██║██║   ██║██║██╔████╔██║
██║╚██╗██║██╔══╝  ██║   ██║╚██╗ ██╔╝██║██║╚██╔╝██║
██║ ╚████║███████╗╚██████╔╝ ╚████╔╝ ██║██║ ╚═╝ ██║
╚═╝  ╚═══╝╚══════╝ ╚═════╝   ╚═══╝  ╚═╝╚═╝     ╚═╝
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
