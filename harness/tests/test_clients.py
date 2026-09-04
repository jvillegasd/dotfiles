#!/usr/bin/env python3

"""The tracked client settings: what they declare, and what the Codex
reconciler does to a config it does not own the rest of.

The Claude half is reconciled inline by harness/install.sh, so its behaviour is
asserted where the installer runs, in test_installers.py. Everything here is
cheap enough to keep out of that file's temporary-HOME runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import CLIENTS, ROOT


def reconcile(config: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(CLIENTS / "codex.sh"), str(config)], capture_output=True, text=True
    )


class TrackedSettingsTests(unittest.TestCase):
    def test_tracked_files_declare_only_what_the_harness_owns(self) -> None:
        claude = json.loads((CLIENTS / "claude.json").read_text())
        # The engram allowlist and the Orca hook manifests are machine state.
        # Tracking either would commit a generated absolute path, and the
        # merge rule only protects what is not named here. The allowlist in
        # particular is engram's own tool set: a copy here is a second
        # declaration that goes stale without saying so, and the install then
        # deletes whatever tools the copy predates.
        self.assertNotIn("allow", claude["permissions"])
        for key in ("hooks", "enabledPlugins", "extraKnownMarketplaces"):
            self.assertNotIn(key, claude, key)
        # The statusline pointer lives here rather than in the installer, so
        # the file Claude Code runs has one declaration.
        self.assertEqual(
            claude["statusLine"],
            {"type": "command", "command": 'bash "$HOME/.claude/statusline.sh"'},
        )
        # A sentinel from the destructive half of the list. `gh pr merge` is
        # deliberately not denied: /squash-land is a human typing the command,
        # and the workflow's own gates are what keep an unreviewed merge out,
        # not a permission the merge step then cannot get past.
        self.assertIn("Bash(git push --force:*)", claude["permissions"]["deny"])
        self.assertNotIn("Bash(gh pr merge:*)", claude["permissions"]["deny"])

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

            # Exit 3 is "the config already says this", which is what keeps
            # install.sh from minting a backup on an unchanged run.
            self.assertEqual(reconcile(config).returncode, 3)

    def test_codex_reconcile_is_a_fixed_point_on_odd_separators(self) -> None:
        # A blank line and a whitespace-only line are different text. Putting
        # them back in the order they were popped off swapped the two on every
        # run, so the reconciler never settled: every install rewrote the
        # config, and check_links then died on a file it had just written.
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            config.write_text('unrelated = "x"\n   \n\n[tui]\nfoo = 1\n')
            first = reconcile(config)
            self.assertEqual(first.returncode, 0, first.stderr)
            config.write_text(first.stdout)
            self.assertEqual(reconcile(config).returncode, 3, config.read_text())

    def test_codex_reconcile_separates_a_crash_from_no_change(self) -> None:
        # Exit 1 meant both, so install.sh read an unreadable config as
        # "already reconciled", wrote nothing, and reported success. The
        # check_links assertion re-runs this same script, so it would have
        # confirmed that silence.
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            config.write_bytes(b'model = "\xff"\n')
            unreadable = reconcile(config)
            self.assertEqual(unreadable.returncode, 2, unreadable.stdout)
            self.assertIn(str(config), unreadable.stderr)

            # A defect in the tracked file is 4, not 2: it is a repository
            # bug, and dying with the user's config path sends them to the
            # wrong file to fix it.
            missing = subprocess.run(
                [str(CLIENTS / "codex.sh"), str(config), str(config.parent / "gone")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 4, missing.stdout)
            self.assertIn("gone", missing.stderr)

    def test_every_reconciler_is_executable_and_checked(self) -> None:
        # install.sh executes these directly, so a lost mode bit is exit 126.
        scripts = sorted(CLIENTS.glob("*.sh"))
        self.assertTrue(scripts)
        for script in scripts:
            self.assertTrue(os.access(script, os.X_OK), script)
        # Asserting the mode bit here only describes the checkout. What has to
        # hold is that the installer checks it, and checks it before the loop
        # that executes them, where 126 would otherwise read as a
        # reconciliation failure.
        installer = (ROOT / "harness" / "install.sh").read_text()
        guard = installer.index('for script in "$HARNESS_DIR"/statusline/*.sh "$HARNESS_DIR"/clients/*.sh')
        rerun = installer.index('for script in "$HARNESS_DIR/clients/codex.sh"')
        self.assertLess(guard, rerun)

    def test_the_installer_dies_on_an_unreadable_codex_config(self) -> None:
        # The Claude half has test_installers.py's unusable-settings test. This
        # is its Codex twin: exit 2 has to stop the run and name the file,
        # rather than being read as a config that needed nothing.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            config = home / ".codex" / "config.toml"
            config.parent.mkdir(parents=True)
            config.write_bytes(b'model = "\xff"\n')
            # No `permissions` key either: check_links used to raise KeyError
            # on that instead of failing with its own message.
            settings = home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text('{"hooks": {}}')

            result = subprocess.run(
                ["bash", str(ROOT / "harness" / "install.sh"), "--links-only"],
                env=os.environ
                | {
                    "HOME": str(home),
                    "XDG_CONFIG_HOME": str(home / ".config"),
                    "XDG_CACHE_HOME": str(home / ".cache"),
                },
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(str(config), result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            # Still undecodable: the reconciler refused it rather than
            # rewriting it. `engram setup` appends its own keys before this
            # runs, so the file is not byte-identical, only still broken.
            self.assertIn(b'model = "\xff"', config.read_bytes())

    def test_codex_reconcile_writes_a_config_that_does_not_exist_yet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            result = reconcile(config)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('model_reasoning_effort = "medium"', result.stdout)
            self.assertFalse(config.exists(), "the caller owns the write")


if __name__ == "__main__":
    unittest.main()
