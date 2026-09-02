#!/usr/bin/env python3

"""The installers: what they link into a HOME, what they archive, what they
delete, and whether they parse under the bash macOS actually ships.

The two tests that drive a real `install.sh --links-only` run dominate the
suite's runtime, which is why they sit in a file of their own.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import (
    COMMAND_NAMES,
    COMMANDS,
    INSTALLERS,
    ROOT,
    ROOT_INSTALLERS,
    SKILLS,
    STATUSLINE,
    codex_status_items,
)


class InstallerTests(unittest.TestCase):
    def test_python_versions_have_one_declaration(self) -> None:
        # The point of lib/python.sh: the platform scripts install the
        # interpreters and the harness asserts them, but neither restates which
        # versions those are. A second assignment anywhere is a drift waiting
        # to happen, and the two halves would disagree silently.
        shared = ROOT / "lib" / "python.sh"
        self.assertRegex(shared.read_text(), r"(?m)^PYTHON_VERSIONS=\(")
        for script in INSTALLERS:
            if script == shared:
                continue
            self.assertNotIn("PYTHON_VERSIONS=(", script.read_text(), script)

        # Installing belongs to the platform scripts, asserting to the harness.
        harness = (ROOT / "harness" / "install.sh").read_text()
        self.assertIn("assert_pythons", harness)
        self.assertNotIn("install_pythons", harness)
        for script in (ROOT / "macos.sh", ROOT / "linux.sh"):
            self.assertRegex(script.read_text(), r"(?m)^\s+install_pythons$", script)

    def test_installer_functions_parse_under_system_bash(self) -> None:
        # bash 3.2 ships on every macOS and cannot parse `case ... esac` inside
        # `$( )`. `bash -n` misses it, because a command substitution is parsed
        # only when it runs, so this has to execute the function. A full
        # install died here after every other step had already succeeded.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binaries = root / "bin"
            binaries.mkdir()
            for name in ("codex", "claude"):
                stub = binaries / name
                stub.write_text(
                    "#!/bin/sh\n"
                    "printf '{\"installed\":[{\"pluginId\":\"engram@engram\"}]}'\n"
                )
                stub.chmod(0o755)

            # Laid out like the repository, because the installer sources the
            # shared interpreter declaration as ../lib/python.sh relative to
            # itself. Flattening it here would only prove the copy parses.
            installer = (ROOT / "harness" / "install.sh").read_text()
            library = root / "harness" / "library.sh"
            library.parent.mkdir()
            library.write_text(installer[: installer.rindex("\nmain\n")])
            shared = root / "lib" / "python.sh"
            shared.parent.mkdir()
            shared.write_text((ROOT / "lib" / "python.sh").read_text())
            environment = os.environ | {
                "PATH": f"{binaries}:{os.environ['PATH']}"
            }

            def run(call: str) -> subprocess.CompletedProcess:
                return subprocess.run(
                    ["/bin/bash", "-c", f'source "{library}"; {call}'],
                    env=environment,
                    capture_output=True,
                    text=True,
                )

            for client in ("claude", "codex"):
                result = run(f"assert_plugin_count {client} engram 1")
                self.assertEqual(result.returncode, 0, result.stderr)
            # It really evaluates the listing rather than passing vacuously.
            self.assertNotEqual(run("assert_plugin_count claude engram 2").returncode, 0)

    def test_link_install_is_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            private = home / ".agents" / "skills" / "private"
            private.mkdir(parents=True)
            (private / "SKILL.md").write_text("---\nname: private\ndescription: private\n---\n")
            collision = home / ".agents" / "skills" / "evidence"
            collision.mkdir()
            (collision / "keep").write_text("collision")
            # A link this harness wrote for a name it no longer installs, and
            # one whose target it deleted outright. Both must go.
            orphan = home / ".agents" / "skills" / "ship"
            orphan.parent.mkdir(parents=True, exist_ok=True)
            orphan.symlink_to(SKILLS / "evidence")
            dangling = home / ".agents" / "skills" / "to-spec"
            dangling.symlink_to(SKILLS / "to-spec")
            # A hand-written duplicate of an alias the harness now owns.
            zshrc = home / ".zshrc"
            zshrc.write_text(
                "export PATH=/usr/bin\n"
                "alias cyolo='codex --old-flag'\n"
                "alias sail='sh sail'\n"
            )
            policy = home / ".codex" / "AGENTS.md"
            policy.parent.mkdir()
            policy.write_text("old policy")
            # config.toml carries trust decisions and hook hashes, so the
            # status line reconciler has to leave everything else alone.
            codex_config = home / ".codex" / "config.toml"
            codex_config.write_text(
                'model = "keep-me"\n\n'
                "[tui]\n"
                'status_line = [\n  "stale",\n]\n'
                "status_line_use_colors = false\n"
                'theme = "keep-me-too"\n\n'
                "[tui.model_availability_nux]\n"
                'status_line = "not-ours"\n'
            )
            legacy_skills = home / "legacy-claude-skills"
            (legacy_skills / "private-claude").mkdir(parents=True)
            (legacy_skills / "private-claude" / "SKILL.md").write_text(
                "---\nname: private-claude\ndescription: private\n---\n"
            )
            (home / ".claude").mkdir(exist_ok=True)
            (home / ".claude" / "skills").symlink_to(legacy_skills)
            opencode_private = home / ".config" / "opencode" / "skills" / "private-opencode"
            opencode_private.mkdir(parents=True)
            (opencode_private / "SKILL.md").write_text(
                "---\nname: private-opencode\ndescription: private\n---\n"
            )
            opencode_collision = home / ".config" / "opencode" / "skills" / "evidence"
            opencode_collision.mkdir()
            (opencode_collision / "keep").write_text("opencode collision")

            environment = os.environ | {
                "HOME": str(home),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
            command = ["bash", ROOT / "harness" / "install.sh", "--links-only"]
            subprocess.run(command, env=environment, check=True, capture_output=True)

            self.assertTrue(private.is_dir())
            # A symlinked skills root is moved aside for a real directory the
            # installer owns, and the link's target is left untouched.
            claude_skills = home / ".claude" / "skills"
            self.assertTrue(claude_skills.is_dir())
            self.assertFalse(claude_skills.is_symlink())
            self.assertTrue((legacy_skills / "private-claude" / "SKILL.md").is_file())
            self.assertTrue(opencode_private.is_dir())
            self.assertFalse(opencode_collision.exists())
            self.assertTrue((home / ".agents" / "skills" / "evidence").is_symlink())
            self.assertFalse(orphan.is_symlink())

            # One sourced line owns the yolo aliases; the hand-written
            # duplicate is gone and unrelated aliases are untouched.
            rc = zshrc.read_text()
            self.assertNotIn("--old-flag", rc)
            self.assertIn("alias sail=", rc)
            self.assertEqual(rc.count("portable-harness aliases"), 1)
            self.assertIn(f'source "{ROOT / "harness" / "aliases.sh"}"', rc)
            # The harness never creates the OpenCode skills root: it reads
            # ~/.agents/skills, so a second copy would double-list.
            self.assertFalse((home / ".config" / "opencode" / "skills" / "evidence").exists())
            aliases = (ROOT / "harness" / "aliases.sh").read_text()
            for name, flag in (
                ("ccyolo", "--dangerously-skip-permissions"),
                ("cyolo", "--dangerously-bypass-approvals-and-sandbox"),
                ("oyolo", "OPENCODE_PERMISSION="),
            ):
                self.assertIn(f"alias {name}=", aliases)
                self.assertIn(flag, aliases)
            self.assertFalse(dangling.is_symlink())
            for name in COMMAND_NAMES:
                for root in (
                    home / ".claude" / "commands",
                    home / ".codex" / "prompts",
                    home / ".config" / "opencode" / "command",
                ):
                    self.assertEqual(
                        os.path.realpath(root / f"{name}.md"),
                        str(COMMANDS / f"{name}.md"),
                        name,
                    )
                self.assertFalse((home / ".agents" / "skills" / name).exists(), name)
            self.assertEqual(
                os.path.realpath(policy), str(ROOT / "harness" / "POLICY.md")
            )
            # Claude runs statusline/claude.sh; Codex cannot run anything, so
            # statusline/codex.sh writes the equivalent built-in items into its
            # own [tui] table instead.
            self.assertEqual(
                os.path.realpath(home / ".claude" / "statusline.sh"),
                str(STATUSLINE / "claude.sh"),
            )
            claude_settings = json.loads(
                (home / ".claude" / "settings.json").read_text()
            )
            self.assertEqual(
                claude_settings["statusLine"],
                {"type": "command", "command": 'bash "$HOME/.claude/statusline.sh"'},
            )
            codex = codex_config.read_text()
            items = ", ".join(f'"{item}"' for item in codex_status_items())
            self.assertIn(f"status_line = [{items}]", codex)
            self.assertIn("status_line_use_colors = true\n", codex)
            self.assertNotIn('"stale"', codex)
            self.assertNotIn("status_line_use_colors = false", codex)
            # Unrelated keys, including a same-named key in a subtable, survive.
            self.assertIn('model = "keep-me"', codex)
            self.assertIn('theme = "keep-me-too"', codex)
            self.assertIn('status_line = "not-ours"', codex)
            self.assertEqual(codex.count("[tui]"), 1)
            self.assertFalse((home / ".local" / "bin" / "claude-seo").exists())
            backups = list((home / ".dotfiles-backups" / "harness").iterdir())
            self.assertEqual(len(backups), 1)
            self.assertTrue(
                (backups[0] / ".agents" / "skills" / "evidence" / "keep").is_file()
            )
            self.assertTrue((backups[0] / ".claude" / "skills.previous-link").is_symlink())
            self.assertTrue(
                (backups[0] / ".config" / "opencode" / "skills" / "evidence" / "keep").is_file()
            )

            subprocess.run(command, env=environment, check=True, capture_output=True)
            self.assertEqual(
                len(list((home / ".dotfiles-backups" / "harness").iterdir())),
                1,
            )
            self.assertEqual(zshrc.read_text(), rc)

    def test_no_backup_deletes_instead_of_archiving(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            # Something in the way at a managed path, and a private skill that
            # must survive either way.
            collision = home / ".agents" / "skills" / "evidence"
            collision.mkdir(parents=True)
            (collision / "keep").write_text("collision")
            private = home / ".agents" / "skills" / "private"
            private.mkdir(parents=True)
            (private / "SKILL.md").write_text(
                "---\nname: private\ndescription: private\n---\n"
            )

            environment = os.environ | {
                "HOME": str(home),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
            subprocess.run(
                ["bash", ROOT / "harness" / "install.sh", "--links-only", "--no-backup"],
                env=environment,
                check=True,
                capture_output=True,
            )

            self.assertFalse((home / ".dotfiles-backups").exists())
            self.assertTrue((home / ".agents" / "skills" / "evidence").is_symlink())
            self.assertTrue(private.is_dir())
            self.assertTrue((private / "SKILL.md").is_file())

    def test_no_backup_is_documented_in_every_installer(self) -> None:
        # The platform entry points offer the flag through their shared
        # library, so they are read together; the harness installer parses and
        # documents its own copy.
        for group in (ROOT_INSTALLERS, (ROOT / "harness" / "install.sh",)):
            text = "\n".join(path.read_text() for path in group)
            self.assertIn("--no-backup", text, group)
            # The flag is destructive, so the usage text has to say so.
            self.assertIn("Destructive and unrecoverable", text, group)


if __name__ == "__main__":
    unittest.main()
