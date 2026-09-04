#!/usr/bin/env python3

"""The tracked client settings: what they declare, and what the Codex
reconciler does to a config it does not own the rest of.

The Claude half is reconciled inline by harness/install.sh, so its behaviour is
asserted where the installer runs, in test_installers.py. Everything here is
cheap enough to keep out of that file's temporary-HOME runs.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import CLIENTS


def reconcile(config: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(CLIENTS / "codex.sh"), str(config)], capture_output=True, text=True
    )


class TrackedSettingsTests(unittest.TestCase):
    def test_tracked_files_declare_only_what_the_harness_owns(self) -> None:
        claude = json.loads((CLIENTS / "claude.json").read_text())
        # The engram allowlist and the Orca hook manifests are machine state.
        # Tracking either would commit a generated absolute path, and the
        # merge rule only protects what is not named here.
        self.assertNotIn("allow", claude["permissions"])
        for key in ("hooks", "enabledPlugins", "extraKnownMarketplaces"):
            self.assertNotIn(key, claude, key)
        # The statusline pointer lives here rather than in the installer, so
        # the file Claude Code runs has one declaration.
        self.assertEqual(
            claude["statusLine"],
            {"type": "command", "command": 'bash "$HOME/.claude/statusline.sh"'},
        )
        self.assertIn("Bash(gh pr merge:*)", claude["permissions"]["deny"])

        # The [tui] table belongs to statusline/codex.sh. Two writers of one
        # key would each undo the other on alternate runs.
        codex = (CLIENTS / "codex.toml").read_text()
        body = "\n".join(
            line for line in codex.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn("[", body)
        self.assertIn('model = "', body)

    def test_codex_reconcile_owns_its_keys_and_nothing_else(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            # A stale value, a comment between the keys, a duplicate of a key
            # this reconciler owns, and the same key name inside somebody
            # else's table.
            original = (
                'model = "stale"\n'
                "# keep this line\n"
                'model = "stale twice"\n'
                'unrelated = "keep-me"\n'
                "\n"
                "[tui]\n"
                'model = "not-ours"\n'
                "\n"
                '[projects."/somewhere"]\n'
                'trust_level = "trusted"\n'
            )
            config.write_text(original)

            first = reconcile(config)
            self.assertEqual(first.returncode, 0, first.stderr)
            config.write_text(first.stdout)
            reconciled = config.read_text()

            for line in (CLIENTS / "codex.toml").read_text().splitlines():
                if line and not line.startswith("#"):
                    self.assertIn(f"\n{line}\n", f"\n{reconciled}", line)
            self.assertNotIn("stale", reconciled)
            self.assertIn("# keep this line", reconciled)
            self.assertIn('unrelated = "keep-me"', reconciled)
            self.assertIn('model = "not-ours"', reconciled)
            # The trust decisions and hook hashes that dominate a real
            # config.toml are why this reconciles rather than symlinking.
            self.assertIn('[projects."/somewhere"]\ntrust_level = "trusted"', reconciled)
            # A repeated key is invalid TOML, so the duplicate is dropped
            # rather than reconciled into two winners.
            self.assertEqual(reconciled.count('model = "gpt'), 1)

            # Exit 1 is "the config already says this", which is what keeps
            # install.sh from minting a backup on an unchanged run.
            self.assertEqual(reconcile(config).returncode, 1)

    def test_codex_reconcile_writes_a_config_that_does_not_exist_yet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            result = reconcile(config)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('model_reasoning_effort = "medium"', result.stdout)
            self.assertFalse(config.exists(), "the caller owns the write")


if __name__ == "__main__":
    unittest.main()
