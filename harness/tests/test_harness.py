#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
SKILLS = ROOT / "harness" / "skills"
LOCAL_SKILLS = {
    "address-review",
    "grill-me",
    "seo",
    "seo-performance",
    "seo-visual",
    "setup-harness",
    "ship",
    "spec",
    "tickets",
}


def folder_hash(path: Path) -> str:
    digest = hashlib.sha256()
    files = (item for item in path.rglob("*") if item.is_file())
    for file in sorted(files, key=lambda item: item.relative_to(path).as_posix().casefold()):
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def load_lifecycle_module():
    path = (
        SKILLS
        / "setup-harness"
        / "scripts"
        / "reconcile-agent-lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location("agent_lifecycle", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeIssues:
    def __init__(self) -> None:
        self.issues = {
            1: {"number": 1, "state": "open", "labels": [{"name": "in-progress"}]},
            2: {"number": 2, "state": "closed", "labels": []},
            3: {"number": 3, "state": "closed", "labels": []},
            4: {"number": 4, "state": "open", "labels": [{"name": "blocked"}]},
        }
        self.parents = {2: 1, 3: 1}
        self.children = {1: [2, 3]}
        self.blocked_by = {4: [3]}
        self.blocking = {3: [4]}
        self.merged = {2, 3}

    def issue(self, number: int) -> dict:
        return self.issues[number]

    def related(self, number: int, relation: str) -> list[dict]:
        mappings = {
            "parent": {key: [value] for key, value in self.parents.items()},
            "sub_issues": self.children,
            "blocked_by": self.blocked_by,
            "blocking": self.blocking,
        }
        return [
            self.issues[related]
            for related in mappings[relation].get(number, [])
        ]

    def blocker_satisfied(self, issue: dict) -> bool:
        return issue["state"] == "closed" and issue["number"] in self.merged

    def update(self, number: int, **changes: object) -> None:
        issue = self.issues[number]
        if "state" in changes:
            issue["state"] = changes["state"]
        if "labels" in changes:
            issue["labels"] = [
                {"name": label} for label in changes["labels"]  # type: ignore[union-attr]
            ]


class HarnessTests(unittest.TestCase):
    def test_skill_lock_and_bookkeeping_are_consistent(self) -> None:
        lock = json.loads((ROOT / "skills-lock.json").read_text())["skills"]
        names: set[str] = set()

        for directory in sorted(path for path in SKILLS.iterdir() if path.is_dir()):
            body = directory / "SKILL.md"
            self.assertTrue(body.is_file(), directory)
            match = re.search(r"^name:\s*['\"]?([^'\"\n]+)", body.read_text(), re.M)
            self.assertIsNotNone(match, directory)
            name = match.group(1).strip()  # type: ignore[union-attr]
            self.assertEqual(name, directory.name)
            self.assertNotIn(name, names)
            names.add(name)

        self.assertTrue(LOCAL_SKILLS.isdisjoint(lock))
        self.assertEqual(names, set(lock) | LOCAL_SKILLS)
        self.assertTrue((ROOT / ".agents" / "skills").is_symlink())
        self.assertEqual(
            os.readlink(ROOT / ".agents" / "skills"), "../harness/skills"
        )

        for name in names:
            link = ROOT / ".claude" / "skills" / name
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(os.readlink(link), f"../../.agents/skills/{name}")

        for name in LOCAL_SKILLS:
            skill = SKILLS / name
            self.assertIn("opencode/autoinvoke: \"false\"", (skill / "SKILL.md").read_text())
            self.assertEqual(
                (skill / "agents" / "openai.yaml").read_text(),
                "policy:\n  allow_implicit_invocation: false\n",
            )

        for name, entry in lock.items():
            body = SKILLS / name
            self.assertTrue(body.is_dir(), name)
            self.assertEqual(folder_hash(body), entry["computedHash"], name)

        referenced_scripts = set()
        for name in lock:
            referenced_scripts.update(
                re.findall(
                    r"claude-seo run ([A-Za-z0-9_.-]+)",
                    (SKILLS / name / "SKILL.md").read_text(),
                )
            )
        for script in referenced_scripts:
            self.assertTrue((SKILLS / "seo" / "scripts" / script).is_file(), script)

    def test_sources_exclude_generated_and_secret_state(self) -> None:
        forbidden = {
            ".venv",
            "__pycache__",
            ".cache",
            "browsers",
            "screenshots",
        }
        for path in ROOT.rglob("*"):
            if ".git" in path.parts:
                continue
            self.assertFalse(forbidden & set(path.relative_to(ROOT).parts), path)

        ignored = (ROOT / ".gitignore").read_text()
        for pattern in (
            ".env",
            "**/.venv/",
            "**/__pycache__/",
            "**/screenshots/",
            ".claude/settings",
        ):
            self.assertIn(pattern, ignored)

    def test_installers_do_not_fetch_standalone_skills(self) -> None:
        text = "\n".join(
            path.read_text()
            for path in (ROOT / "install.sh", ROOT / "harness" / "install.sh")
        )
        self.assertNotRegex(
            text,
            r"skills(?:@\d+)?\s+(?:add|update|experimental_install)",
        )
        self.assertNotIn("engram setup codex", text)
        self.assertNotIn("engram setup claude-code", text)

    def test_shell_and_python_syntax(self) -> None:
        for script in (ROOT / "install.sh", ROOT / "harness" / "install.sh"):
            subprocess.run(["bash", "-n", script], check=True)
        scripts = list((ROOT / "harness").rglob("*.py"))
        with tempfile.TemporaryDirectory() as cache:
            subprocess.run(
                ["python3", "-m", "py_compile", *map(str, scripts)],
                check=True,
                env=os.environ | {"PYTHONPYCACHEPREFIX": cache},
            )

    def test_link_install_is_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            private = home / ".agents" / "skills" / "private"
            private.mkdir(parents=True)
            (private / "SKILL.md").write_text("---\nname: private\ndescription: private\n---\n")
            collision = home / ".agents" / "skills" / "spec"
            collision.mkdir()
            (collision / "keep").write_text("collision")
            retired = home / ".agents" / "skills" / "implement"
            retired.mkdir()
            (retired / "keep").write_text("retired")
            policy = home / ".codex" / "AGENTS.md"
            policy.parent.mkdir()
            policy.write_text("old policy")
            legacy_skills = home / "legacy-claude-skills"
            (legacy_skills / "private-claude").mkdir(parents=True)
            (legacy_skills / "private-claude" / "SKILL.md").write_text(
                "---\nname: private-claude\ndescription: private\n---\n"
            )
            (home / ".claude").mkdir()
            (home / ".claude" / "skills").symlink_to(legacy_skills)
            opencode_private = home / ".config" / "opencode" / "skills" / "private-opencode"
            opencode_private.mkdir(parents=True)
            (opencode_private / "SKILL.md").write_text(
                "---\nname: private-opencode\ndescription: private\n---\n"
            )
            opencode_collision = home / ".config" / "opencode" / "skills" / "spec"
            opencode_collision.mkdir()
            (opencode_collision / "keep").write_text("opencode collision")

            environment = os.environ | {"HOME": str(home)}
            command = ["bash", ROOT / "harness" / "install.sh", "--links-only"]
            subprocess.run(command, env=environment, check=True, capture_output=True)

            self.assertTrue(private.is_dir())
            self.assertTrue((home / ".claude" / "skills" / "private-claude").is_symlink())
            self.assertTrue((legacy_skills / "private-claude" / "SKILL.md").is_file())
            self.assertTrue(opencode_private.is_dir())
            self.assertFalse(opencode_collision.exists())
            self.assertTrue((home / ".agents" / "skills" / "spec").is_symlink())
            self.assertFalse(retired.exists())
            self.assertEqual(
                os.path.realpath(policy), str(ROOT / "harness" / "POLICY.md")
            )
            self.assertEqual(
                os.path.realpath(home / ".local" / "bin" / "claude-seo"),
                str(SKILLS / "seo" / "bin" / "claude-seo"),
            )
            backups = list((home / ".dotfiles-backups" / "harness").iterdir())
            self.assertEqual(len(backups), 1)
            self.assertTrue(
                (backups[0] / ".agents" / "skills" / "spec" / "keep").is_file()
            )
            self.assertTrue(
                (backups[0] / ".agents" / "skills" / "implement" / "keep").is_file()
            )
            self.assertTrue((backups[0] / ".claude" / "skills.previous-link").is_symlink())
            self.assertTrue(
                (backups[0] / ".config" / "opencode" / "skills" / "spec" / "keep").is_file()
            )

            subprocess.run(command, env=environment, check=True, capture_output=True)
            self.assertEqual(
                len(list((home / ".dotfiles-backups" / "harness").iterdir())),
                1,
            )

    def test_public_workflow_contracts_are_wired(self) -> None:
        required = {
            "setup-harness": (
                "docs/agents/harness.json",
                "docs/agents/issue-tracker.md",
                "agent-lifecycle.yml",
            ),
            "spec": ("to-spec", "Ask once", "Do not create tickets"),
            "tickets": ("to-tickets", "sub-issue", "blocked-by"),
            "ship": ("wt switch --create", "code-review", "Never merge"),
            "address-review": ("headRefName", "wt list --format=json", "Never merge"),
            "seo": ("seo-technical", "seo-performance", "claude-seo setup"),
        }
        for name, terms in required.items():
            body = (SKILLS / name / "SKILL.md").read_text()
            for term in terms:
                self.assertIn(term, body, f"{name}: {term}")

    def test_github_close_and_reopen_reconcile_frontier(self) -> None:
        lifecycle = load_lifecycle_module()
        api = FakeIssues()
        lifecycle.reconcile(api, 3, lifecycle.DEFAULT_LABELS)
        self.assertEqual(api.issues[1]["state"], "closed")
        self.assertEqual(
            {label["name"] for label in api.issues[4]["labels"]},
            {"ready-for-agent"},
        )

        api.merged.remove(3)
        api.issues[4]["labels"] = [{"name": "ready-for-agent"}]
        lifecycle.reconcile(api, 3, lifecycle.DEFAULT_LABELS)
        self.assertEqual(
            {label["name"] for label in api.issues[4]["labels"]},
            {"blocked"},
        )
        self.assertEqual(api.issues[1]["state"], "open")
        api.issues[1]["state"] = "closed"
        lifecycle.reconcile(api, 1, lifecycle.DEFAULT_LABELS)
        self.assertEqual(api.issues[1]["state"], "open")
        api.merged.add(3)
        lifecycle.reconcile(api, 1, lifecycle.DEFAULT_LABELS, "reopened")
        self.assertEqual(api.issues[1]["state"], "closed")

        api.issues[3]["state"] = "open"
        api.issues[3]["labels"] = [{"name": "ready-for-human"}]
        lifecycle.reconcile(api, 3, lifecycle.DEFAULT_LABELS, "reopened")
        self.assertEqual(api.issues[1]["state"], "open")
        self.assertIn(
            "in-progress",
            {label["name"] for label in api.issues[1]["labels"]},
        )
        self.assertEqual(
            {label["name"] for label in api.issues[3]["labels"]},
            {"ready-for-agent"},
        )
        self.assertEqual(
            {label["name"] for label in api.issues[4]["labels"]},
            {"blocked"},
        )


if __name__ == "__main__":
    unittest.main()
