#!/usr/bin/env python3
"""Codex adapter reconciliation, isolated from package and account setup."""

from __future__ import annotations

import json
import os
import select
import time
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import COMMAND_NAMES, ROOT


class CodexCommandTests(unittest.TestCase):
    def run_links(self, home, call, source=None):
        fixture = home / ".fixture"
        library = fixture / "harness/library.sh"
        library.parent.mkdir(parents=True, exist_ok=True)
        installer = (ROOT / "harness/install.sh").read_text()
        library.write_text(installer[:installer.rindex("\nmain\n")])
        shared = fixture / "lib/python.sh"
        shared.parent.mkdir(exist_ok=True)
        shared.write_text((ROOT / "lib/python.sh").read_text())
        return subprocess.run(
            ["/bin/bash", "-c", 'source "$1" --links-only; HARNESS_DIR="$2"; ' + call,
             "bash", str(library), str(source or ROOT / "harness")],
            env=os.environ | {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
            text=True, capture_output=True,
        )

    def test_foreign_adapter_installation_survives_uninstall(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result = self.run_links(home, "install_links")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_links(home, "NO_BACKUP=true; remove_codex_commands", home / "other/harness")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home / ".codex/skills/yolo/SKILL.md").is_file())

    def test_migration_backups_repeat_runs_and_uninstall(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            skills = home / ".codex/skills"
            collision = skills / "yolo"
            collision.mkdir(parents=True)
            (collision / "private.txt").write_text("keep collision")
            system = skills / ".system/private"
            system.mkdir(parents=True)
            (system / "SKILL.md").write_text("keep system")
            (skills / "private").symlink_to(home / "unmounted")
            prompts = home / ".codex/prompts"
            prompts.mkdir()
            (prompts / "yolo.md").symlink_to(ROOT / "harness/commands/yolo.md")
            (prompts / "spec.md").write_text("private prompt")
            (prompts / "foreign.md").symlink_to(home / "missing.md")
            call = "install_links; check_codex_commands"
            result = self.run_links(home, call)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((prompts / "yolo.md").is_symlink())
            self.assertEqual((prompts / "spec.md").read_text(), "private prompt")
            self.assertTrue((prompts / "foreign.md").is_symlink())
            backups = home / ".dotfiles-backups/harness"
            self.assertEqual(len(list(backups.glob("*/.codex/skills/yolo/private.txt"))), 1)
            self.assertEqual(len(list(backups.glob("*/.codex/prompts/yolo.md"))), 1)
            before = sorted(str(p) for p in backups.rglob("*"))
            timestamp = (skills / "yolo/SKILL.md").stat().st_mtime_ns
            result = self.run_links(home, call)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, sorted(str(p) for p in backups.rglob("*")))
            self.assertEqual(timestamp, (skills / "yolo/SKILL.md").stat().st_mtime_ns)
            result = self.run_links(home, "NO_BACKUP=true; UNINSTALL=true; uninstall_links")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((skills / "yolo").is_symlink())
            self.assertFalse((home / ".codex/harness-commands").exists())
            self.assertEqual((system / "SKILL.md").read_text(), "keep system")
            self.assertTrue((skills / "private").is_symlink())
            self.assertEqual((prompts / "spec.md").read_text(), "private prompt")
            self.assertTrue((prompts / "foreign.md").is_symlink())

    def test_command_update_retirement_and_damaged_adapter_repair(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            source = home / "checkout/harness"
            shutil.copytree(ROOT / "harness/commands", source / "commands")
            call = "install_codex_commands; check_codex_commands"
            result = self.run_links(home, call, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            skill = home / ".codex/skills/yolo"
            command = source / "commands/yolo.md"
            command.write_text(command.read_text() + "\nUpdated canonical command.\n")
            self.assertIn("Updated canonical command.", (skill / "command.md").read_text())
            (source / "commands/ask.md").unlink()
            (skill / "agents/openai.yaml").write_text("policy:\n  allow_implicit_invocation: true\n")
            result = self.run_links(home, "check_codex_commands", source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implicit invocation", result.stderr)
            result = self.run_links(home, call, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((home / ".codex/skills/ask").is_symlink())
            archived = list((home / ".dotfiles-backups/harness").glob("*/.codex/harness-commands/yolo/agents/openai.yaml"))
            self.assertEqual(len(archived), 1)
            self.assertIn("true", archived[0].read_text())
            self.assertIn("false", (skill / "agents/openai.yaml").read_text())
            foreign = home / "foreign-command.md"
            foreign.write_bytes(command.read_bytes())
            (skill / "command.md").unlink()
            (skill / "command.md").symlink_to(foreign)
            result = self.run_links(home, call, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((skill / "command.md").resolve(), command.resolve())

    def test_symlinked_roots_do_not_write_through_to_private_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            foreign = home / "private"
            foreign.mkdir()
            (foreign / "keep.md").write_text("keep")
            codex = home / ".codex"
            codex.mkdir()
            for name in ("skills", "prompts", "harness-commands"):
                (codex / name).symlink_to(foreign)
            result = self.run_links(home, "install_codex_commands; check_codex_commands")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([p.name for p in foreign.iterdir()], ["keep.md"])
            self.assertTrue((codex / "prompts").is_symlink())
            self.assertFalse((codex / "skills").is_symlink())
            self.assertFalse((codex / "harness-commands").is_symlink())

    @unittest.skipUnless(os.environ.get("HARNESS_CODEX_SMOKE") == "1", "opt-in real Codex discovery")
    def test_real_codex_discovers_installed_adapters(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            result = self.run_links(home, "install_codex_commands; check_codex_commands")
            self.assertEqual(result.returncode, 0, result.stderr)
            process = subprocess.Popen(
                ["codex", "app-server", "--stdio"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=home,
                env=os.environ | {"HOME": temporary, "CODEX_HOME": str(home / ".codex")},
            )
            try:
                requests = [
                    {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "harness-smoke", "version": "1"}}},
                    {"method": "initialized"},
                    {"id": 2, "method": "skills/list", "params": {"cwds": [temporary], "forceReload": True}},
                ]
                process.stdin.write("".join(json.dumps(r) + "\n" for r in requests).encode())
                process.stdin.flush()
                pending = b""
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if not select.select([process.stdout], [], [], 1)[0]:
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    self.assertTrue(chunk, "Codex exited before skills/list responded")
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        response = json.loads(line)
                        if response.get("id") != 2:
                            continue
                        self.assertNotIn("error", response, response)
                        data = response["result"]["data"][0]
                        self.assertEqual(data["errors"], [])
                        found = {s["name"]: s for s in data["skills"]}
                        for name in COMMAND_NAMES:
                            self.assertIn(name, found)
                            self.assertTrue(found[name]["enabled"])
                            self.assertEqual(found[name]["scope"], "user")
                            self.assertEqual(Path(found[name]["path"]).resolve(),
                                             (home / ".codex/skills" / name / "SKILL.md").resolve())
                        return
                self.fail("Codex skills/list timed out")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdin.close()
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
