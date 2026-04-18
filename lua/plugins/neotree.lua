return {
    {
        "nvim-neo-tree/neo-tree.nvim",
        branch = "v3.x",
        dependencies = {
            "nvim-lua/plenary.nvim",
            "nvim-tree/nvim-web-devicons", -- Optional, for file icons
            "MunifTanjim/nui.nvim",
        },
        config = function()
            require("neo-tree").setup({
                -- Use custom icons for different components
                default_component_configs = {
                    window = {
                        position = "left", -- Position NeoTree on the left
                        width = 35, -- Adjust width based on your preference
                    },
                    icon = {
                        folder_closed = icons.kinds.Folder,
                        folder_open = " ",
                        folder_empty = " ",
                        default = icons.kinds.File,
                    },
                    git_status = {
                        symbols = {
                            added     = icons.git.added,
                            modified  = icons.git.modified,
                            deleted   = icons.git.removed,
                            renamed   = "", -- icon for renamed files
                            untracked = "",
                            ignored   = "",
                            unstaged  = "",
                            staged    = "",
                            conflict  = "",
                        },
                    },
                },
                filesystem = {
                    follow_current_file = {
                        enabled = true,
                    },   -- Automatically focus the file in the explorer
                    hijack_netrw_behavior = "open_current", -- Replace netrw
                    filtered_items = {
                        visible = true,  -- Show hidden files
                        hide_dotfiles = false,  -- Show dotfiles (e.g., `.gitignore`, `.env`)
                        hide_gitignored = false, -- Show files ignored by Git
                        hide_by_name = { "node_modules" }, -- You can customize which folders to hide
                    },
                },
            })
        end
    }
}

