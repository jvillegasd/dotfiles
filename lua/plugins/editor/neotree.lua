return {
    {
        "nvim-neo-tree/neo-tree.nvim",
        branch = "v3.x",
        dependencies = {
            "nvim-lua/plenary.nvim",
            "nvim-tree/nvim-web-devicons",
            "MunifTanjim/nui.nvim",
        },
        config = function()
            require("neo-tree").setup({
                window = {
                    position = "left",
                    width = 35,
                },
                default_component_configs = {
                    icon = {
                        folder_closed = icons.kinds.Folder,
                        folder_open = " ",
                        folder_empty = " ",
                        folder_empty_open = " ",
                        default = icons.kinds.File,
                        use_filtered_colors = true,
                    },
                    git_status = {
                        symbols = {
                            added     = icons.git.added,
                            modified  = icons.git.modified,
                            deleted   = icons.git.removed,
                            renamed   = "",
                            untracked = "",
                            ignored   = "",
                            unstaged  = "",
                            staged    = "",
                            conflict  = "",
                        },
                    },
                },
                filesystem = {
                    follow_current_file = {
                        enabled = true,
                    },
                    hijack_netrw_behavior = "open_current",
                    filtered_items = {
                        visible = true,
                        hide_dotfiles = false,
                        hide_gitignored = false,
                        hide_by_name = { "node_modules" },
                    },
                },
            })
        end,
    },
}
