return {
    "Bekaboo/dropbar.nvim",
    event = { "BufReadPost", "BufNewFile" },
    config = function()
        require("dropbar").setup()
        vim.keymap.set("n", "<leader>;", function()
            require("dropbar.api").pick()
        end, { silent = true, noremap = true, desc = "Dropbar: pick breadcrumb" })
    end,
}
