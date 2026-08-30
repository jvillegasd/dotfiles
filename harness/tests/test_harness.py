#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
SKILLS = ROOT / "harness" / "skills"
LOCAL_SKILLS = {
    "address-review",
    "adversarial-review",
    "evidence",
    "feedback",
    "review",
    "seo",
    "setup-harness",
    "ship",
    "spec",
    "tickets",
    "triage",
}

# Locked bodies linked nowhere: reachable only through a local wrapper that
# carries the invocation guards their hash-locked frontmatter cannot.
INTERNAL_SKILLS = {"code-review"}


SEO_SKILLS = sorted(
    path.name
    for path in SKILLS.iterdir()
    if path.is_dir() and (path.name == "seo" or path.name.startswith("seo-"))
)


def folder_hash(path: Path) -> str:
    digest = hashlib.sha256()
    files = (item for item in path.rglob("*") if item.is_file())
    for file in sorted(files, key=lambda item: item.relative_to(path).as_posix().casefold()):
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_lifecycle_module():
    return load_module(
        "agent_lifecycle",
        SKILLS / "setup-harness" / "scripts" / "reconcile-agent-lifecycle.py",
    )


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

        # POLICY.md: "Skills never auto-invoke on description matching." Each
        # client gates that differently, so the rule needs all three guards.
        for name in names:
            manifest = SKILLS / name / "agents" / "openai.yaml"
            self.assertTrue(manifest.is_file(), name)
            self.assertIn(
                "policy:\n  allow_implicit_invocation: false\n",
                manifest.read_text(),
                name,
            )

        for name in LOCAL_SKILLS:
            body = (SKILLS / name / "SKILL.md").read_text()
            self.assertIn("opencode/autoinvoke: \"false\"", body, name)
            self.assertIn("\ndisable-model-invocation: true\n", body, name)

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

            environment = os.environ | {
                "HOME": str(home),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
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
            for name in SEO_SKILLS:
                self.assertFalse((home / ".agents" / "skills" / name).exists(), name)
                self.assertFalse((home / ".claude" / "skills" / name).exists(), name)
            self.assertFalse((home / ".local" / "bin" / "claude-seo").exists())
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

            subprocess.run(
                command + ["--with-seo"], env=environment, check=True, capture_output=True
            )
            for name in SEO_SKILLS:
                self.assertTrue((home / ".claude" / "skills" / name).is_symlink(), name)
            self.assertEqual(
                os.path.realpath(home / ".local" / "bin" / "claude-seo"),
                str(SKILLS / "seo" / "bin" / "claude-seo"),
            )

            # The choice is remembered, so a later flagless run keeps the group.
            subprocess.run(command, env=environment, check=True, capture_output=True)
            self.assertTrue((home / ".claude" / "skills" / "seo").is_symlink())

            subprocess.run(
                command + ["--without-seo"], env=environment, check=True, capture_output=True
            )
            for name in SEO_SKILLS:
                self.assertFalse((home / ".claude" / "skills" / name).exists(), name)

    def test_bench_reads_every_client_session_store(self) -> None:
        measure = load_module("measure", ROOT / "harness" / "bench" / "measure.py")

        def lines(*records: dict) -> str:
            return "\n".join(json.dumps(record) for record in records)

        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)

            claude = home / ".claude" / "projects" / "repo"
            claude.mkdir(parents=True)
            (claude / "old.jsonl").write_text(lines(
                {"type": "user", "timestamp": "2026-01-01T00:00:00Z",
                 "message": {"content": [{"type": "text", "text": "go"}]}},
                {"type": "assistant",
                 "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
                {"type": "user",
                 "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
                {"type": "user", "message": {"content": [
                    {"type": "text", "text": "[Request interrupted by user]"}]}},
            ))
            (claude / "new.jsonl").write_text(lines(
                {"type": "user", "timestamp": "2026-03-01T00:00:00Z",
                 "message": {"content": [{"type": "text", "text": "go"}]}},
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Bash"},
                    {"type": "tool_use", "name": "Read"}]}},
            ))
            (claude / "junk.jsonl").write_text("not json\n")

            codex = home / ".codex" / "sessions" / "2026" / "03" / "01"
            codex.mkdir(parents=True)
            (codex / "rollout-2026-03-01T00-00-00-abc.jsonl").write_text(lines(
                {"type": "session_meta", "timestamp": "2026-03-01T00:00:00Z"},
                {"type": "response_item", "payload": {"type": "message", "role": "user"}},
                {"type": "response_item", "payload": {"type": "message", "role": "developer"}},
                {"type": "response_item", "payload": {"type": "function_call"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call"}},
                {"type": "event_msg",
                 "payload": {"type": "turn_aborted", "reason": "interrupted"}},
            ))

            opencode = home / ".local" / "share" / "opencode"
            opencode.mkdir(parents=True)
            connection = sqlite3.connect(opencode / "opencode.db")
            connection.executescript(
                "create table session (id text, time_created integer);"
                "create table message (id text, session_id text, data text);"
                "create table part (id text, session_id text, data text);"
            )
            created = int(
                datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000
            )
            connection.execute("insert into session values ('s1', ?)", (created,))
            connection.executemany(
                "insert into message values (?, 's1', ?)",
                [("m1", '{"role": "user"}'), ("m2", '{"role": "assistant"}')],
            )
            connection.executemany(
                "insert into part values (?, 's1', ?)",
                [("p1", '{"type": "tool"}'), ("p2", '{"type": "text"}')],
            )
            connection.commit()
            connection.close()

            sessions = measure.collect(home, ["claude", "codex", "opencode"])
            by_client: dict[str, list[dict]] = {}
            for entry in sessions:
                by_client.setdefault(entry["client"], []).append(entry)

            self.assertEqual(len(by_client["claude"]), 2)
            self.assertEqual(
                [s["tool_calls"] for s in by_client["claude"]], [2, 1]
            )
            self.assertEqual(sum(s["turns"] for s in by_client["claude"]), 3)
            self.assertEqual(sum(s["interrupts"] for s in by_client["claude"]), 1)

            self.assertEqual(len(by_client["codex"]), 1)
            self.assertEqual(
                by_client["codex"][0]
                | {"client": "codex", "date": date(2026, 3, 1)},
                {"client": "codex", "date": date(2026, 3, 1), "turns": 1,
                 "tool_calls": 2, "interrupts": 1, "denials": None},
            )

            self.assertEqual(len(by_client["opencode"]), 1)
            self.assertEqual(by_client["opencode"][0]["turns"], 1)
            self.assertEqual(by_client["opencode"][0]["tool_calls"], 1)
            self.assertIsNone(by_client["opencode"][0]["interrupts"])

            text = measure.report(sessions, date(2026, 2, 1), None)
            self.assertRegex(text, r"tool_calls\s+1\.0\s+2\.0\s+\+1\.0")
            # A metric a client never records is reported as absent, not zero.
            self.assertRegex(text, r"denials\s+-\s+-\s+-")
            self.assertIn("fewer than", text)

    def test_public_workflow_contracts_are_wired(self) -> None:
        required = {
            "setup-harness": (
                "docs/agents/harness.json",
                "docs/agents/issue-tracker.md",
                "agent-lifecycle.yml",
            ),
            "spec": ("to-spec", "Ask once", "Do not create tickets"),
            "tickets": ("to-tickets", "sub-issue", "blocked-by"),
            "ship": (
                "wt switch --create",
                "adversarial-review",
                "review",
                "oracle ladder",
                "Assumptions",
                "Never merge",
            ),
            "address-review": (
                "headRefName",
                "wt list --format=json",
                "adversarial-review",
                "Never merge",
            ),
            "adversarial-review": ("Reviewer A", "Reviewer B", "Never three"),
            "review": ("code-review", "Standards and Spec", "explicit human invocation"),
            "triage": ("kill query", "Plan brief", "Evidence ledger", "Never implement"),
            "feedback": ("Deferred", "accumulated delta", "Never merge the pull request"),
            "evidence": ("Kill query first", "falsifiable", "No-fabrication"),
            "seo": ("seo-technical", "roles/performance", "claude-seo setup"),
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
