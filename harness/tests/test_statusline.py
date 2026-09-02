#!/usr/bin/env python3

"""The per-provider status line files: Claude's renderer and Codex's
reconciler."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import ROOT, STATUSLINE, codex_status_items


class StatuslineTests(unittest.TestCase):
    def test_statusline_is_one_file_per_provider(self) -> None:
        # Claude's is a renderer it runs on every draw; Codex's is a reconciler,
        # because Codex draws its own and takes item ids rather than a command.
        # Different shapes, same folder, one file per provider that has a status
        # line at all. OpenCode has none, so it has no file here.
        scripts = sorted(path.name for path in STATUSLINE.glob("*.sh"))
        self.assertEqual(scripts, ["claude.sh", "codex.sh"])
        for path in STATUSLINE.glob("*.sh"):
            self.assertTrue(os.access(path, os.X_OK), path)

        # The item ids belong to the provider's own file, not to the installer,
        # which only calls it. Assert that against the ids codex.sh actually
        # declares, so renaming one cannot leave this passing on a stale name.
        installer = (ROOT / "harness" / "install.sh").read_text()
        items = codex_status_items()
        self.assertTrue(items)
        for item in items:
            self.assertNotIn(item, installer, item)
        self.assertIn('"$HARNESS_DIR/statusline/codex.sh"', installer)

    def test_codex_statusline_reconciler_is_idempotent(self) -> None:
        # Exit 1 with no output is how it says "already correct", which is what
        # keeps a re-run from minting a backup root and rewriting the file.
        reconciler = STATUSLINE / "codex.sh"
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            config.write_text(
                'model = "keep-me"\n\n'
                "[tui]\n"
                'status_line = [\n  "stale",\n]\n'
                'theme = "keep-me-too"\n\n'
                "[tui.model_availability_nux]\n"
                'status_line = "not-ours"\n'
            )
            first = subprocess.run(
                [reconciler, config], capture_output=True, text=True
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("status_line_use_colors = true", first.stdout)
            self.assertNotIn('"stale"', first.stdout)
            self.assertIn('theme = "keep-me-too"', first.stdout)
            self.assertIn('status_line = "not-ours"', first.stdout)

            config.write_text(first.stdout)
            second = subprocess.run(
                [reconciler, config], capture_output=True, text=True
            )
            self.assertEqual(second.returncode, 1, second.stdout)
            self.assertEqual(second.stdout, "")


if __name__ == "__main__":
    unittest.main()
