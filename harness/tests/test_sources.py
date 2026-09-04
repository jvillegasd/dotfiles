#!/usr/bin/env python3

"""Repository hygiene: what is committed, whether every source parses, and
whether the suite and the documentation still point at things that exist."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import CLIENTS, INSTALLERS, LOCKED_SKILLS, ROOT, STATUSLINE


TESTS = ROOT / "harness" / "tests"


class SourceTests(unittest.TestCase):
    def test_sources_exclude_generated_and_secret_state(self) -> None:
        forbidden = {
            ".venv",
            "__pycache__",
            ".cache",
            "browsers",
            "screenshots",
        }
        # What is committed, not what the working tree happens to hold. Walking
        # the tree also saw ignored state, including the __pycache__ that
        # importing this very module creates, so it failed on every second run.
        # The .gitignore assertions below are what keep that state out.
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split("\0")
        for name in filter(None, tracked):
            self.assertFalse(forbidden & set(Path(name).parts), name)

        ignored = (ROOT / ".gitignore").read_text()
        for pattern in (
            ".env",
            "**/.venv/",
            "**/__pycache__/",
            "**/screenshots/",
            ".claude/settings",
        ):
            self.assertIn(pattern, ignored)

    def test_shell_and_python_syntax(self) -> None:
        shell = sorted(STATUSLINE.glob("*.sh")) + sorted(CLIENTS.glob("*.sh"))
        for script in (*INSTALLERS, ROOT / "harness" / "aliases.sh", LOCKED_SKILLS, *shell):
            subprocess.run(["bash", "-n", script], check=True)
        scripts = list((ROOT / "harness").rglob("*.py"))
        with tempfile.TemporaryDirectory() as cache:
            subprocess.run(
                ["python3", "-m", "py_compile", *map(str, scripts)],
                check=True,
                env=os.environ | {"PYTHONPYCACHEPREFIX": cache},
            )

    def test_every_test_file_is_discovered(self) -> None:
        # The suite runs under `unittest discover`, which silently ignores a
        # file whose name does not match the pattern. A test file nobody runs
        # reports success forever, which is a worse failure than a large file.
        suite = unittest.defaultTestLoader.discover(
            str(TESTS), top_level_dir=str(TESTS)
        )

        def ids(case) -> list[str]:
            if isinstance(case, unittest.TestSuite):
                return [found for child in case for found in ids(child)]
            return [case.id()]

        collected = ids(suite)
        # A module that fails to import is collected as `_FailedTest`, which
        # would otherwise satisfy the membership check below while running
        # none of that file's assertions.
        for found in collected:
            self.assertNotIn("_FailedTest", found, found)
        modules = {found.split(".")[0] for found in collected}
        for path in sorted(TESTS.glob("test_*.py")):
            self.assertIn(path.stem, modules, path.name)

    def test_documented_harness_paths_exist(self) -> None:
        # POLICY.md is loaded into every session through the global
        # instruction link, so a path that goes stale there is wrong advice
        # given to every client. Nothing else notices when one moves.
        for name in ("harness/POLICY.md", "harness/README.md", "STRUCTURE.md"):
            document = ROOT / name
            for reference in sorted(set(re.findall(
                r"harness/[A-Za-z0-9._/-]+", document.read_text()
            ))):
                self.assertTrue(
                    (ROOT / reference.rstrip(".")).exists(),
                    f"{name}: {reference}",
                )


if __name__ == "__main__":
    unittest.main()
