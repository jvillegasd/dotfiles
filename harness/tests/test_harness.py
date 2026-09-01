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
COMMANDS = ROOT / "harness" / "commands"
STATUSLINE = ROOT / "harness" / "statusline"
LOCKED_SKILLS = ROOT / "harness" / "locked-skills.sh"

# The two platform entry points plus the library they both source. They differ
# only in how packages arrive, so anything asserted about "the installer" has
# to read the library too.
ROOT_INSTALLERS = (
    ROOT / "macos.sh",
    ROOT / "linux.sh",
    ROOT / "lib" / "common.sh",
    ROOT / "lib" / "python.sh",
)
INSTALLERS = (*ROOT_INSTALLERS, ROOT / "harness" / "install.sh")
LOCAL_SKILLS = {
    "adversarial-review",
    "evidence",
    # Adopted out of the lock to gain the invocation guards the policy already
    # claimed it had, plus a self-grill mode two workflows call.
    "grilling",
    "seo",
    "setup-harness",
}

# A locked body cannot carry an invocation guard without drifting from
# upstream, so one that must never fire on its own is not installed as a skill
# at all. The `seo` orchestrator reads these from their paths instead.
UNLINKED_SKILLS = sorted(
    path.name for path in SKILLS.iterdir()
    if path.is_dir() and path.name.startswith("seo-")
)

# Workflows are commands, never skills: a client cannot select one by matching
# a description, so the invariant holds by construction rather than by prose.
COMMAND_NAMES = sorted(path.stem for path in COMMANDS.glob("*.md"))

# Every command that ingests text written elsewhere says that the text is data.
INGESTING_COMMANDS = {
    "address-review",
    "ask",
    "create-ticket",
    "feedback",
    "land",
    "proto",
    "research",
    "spec",
    "squash-land",
    "triage",
    "yolo",
}

# Ponytail replaced a SessionStart hook that applied to every session with an
# explicit load in each command that writes code. Nothing else enforces it, so
# dropping the line would silently turn lazy mode off everywhere.
PONYTAIL_COMMANDS = {"address-review", "feedback", "proto", "yolo"}


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

        # A bookkeeping link is an installed skill in this repository, so an
        # unlinked body must not have one either. That is the bug the
        # code-review exclusion had: excluded from a fresh HOME, live here.
        for name in names:
            link = ROOT / ".claude" / "skills" / name
            if name in UNLINKED_SKILLS:
                self.assertFalse(link.is_symlink() or link.exists(), name)
                continue
            self.assertTrue(link.is_symlink(), name)
            self.assertEqual(os.readlink(link), f"../../.agents/skills/{name}")

        # POLICY.md: "Skills never auto-invoke on description matching." Each
        # client gates that differently, so a local skill needs all three
        # guards. Locked bodies are never edited to add one: an edit inside a
        # locked directory is silently clobbered by the next skills update.
        for name in LOCAL_SKILLS:
            body = (SKILLS / name / "SKILL.md").read_text()
            self.assertIn("opencode/autoinvoke: \"false\"", body, name)
            self.assertIn("\ndisable-model-invocation: true\n", body, name)
            manifest = SKILLS / name / "agents" / "openai.yaml"
            self.assertTrue(manifest.is_file(), name)
            self.assertIn(
                "policy:\n  allow_implicit_invocation: false\n",
                manifest.read_text(),
                name,
            )

        # The unguardable ones are controlled by never linking them instead.
        installer = (ROOT / "harness" / "install.sh").read_text()
        self.assertIn('is_unlinked_skill() {\n    [[ "$1" == seo-* ]]', installer)
        for name in UNLINKED_SKILLS:
            self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)
            self.assertNotIn(name, LOCAL_SKILLS)

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
        text = "\n".join(path.read_text() for path in INSTALLERS)
        self.assertNotRegex(
            text,
            r"skills(?:@\d+)?\s+(?:add|update|experimental_install)",
        )
        # Every client is set up with its own documented command, and none of
        # them may block on a prompt.
        for command in ("claude-code", "codex", "opencode"):
            self.assertRegex(
                text, rf"(?m)^\s*engram setup {command} < /dev/null", command
            )

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

    def test_statusline_is_one_file_per_provider(self) -> None:
        # Claude's is a renderer it runs on every draw; Codex's is a reconciler,
        # because Codex draws its own and takes item ids rather than a command.
        # Different shapes, same folder, one file per provider that has a status
        # line at all. OpenCode has none, so it has no file here.
        scripts = sorted(path.name for path in STATUSLINE.glob("*.sh"))
        self.assertEqual(scripts, ["claude.sh", "codex.sh"])
        for path in STATUSLINE.glob("*.sh"):
            self.assertTrue(os.access(path, os.X_OK), path)

        # The item ids belong to the provider's own file, not to the installer.
        installer = (ROOT / "harness" / "install.sh").read_text()
        self.assertNotIn("model-with-reasoning", installer)
        self.assertIn("model-with-reasoning", (STATUSLINE / "codex.sh").read_text())
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

    def test_shell_and_python_syntax(self) -> None:
        statusline = sorted(STATUSLINE.glob("*.sh"))
        for script in (*INSTALLERS, ROOT / "harness" / "aliases.sh", LOCKED_SKILLS, *statusline):
            subprocess.run(["bash", "-n", script], check=True)
        scripts = list((ROOT / "harness").rglob("*.py"))
        with tempfile.TemporaryDirectory() as cache:
            subprocess.run(
                ["python3", "-m", "py_compile", *map(str, scripts)],
                check=True,
                env=os.environ | {"PYTHONPYCACHEPREFIX": cache},
            )

    def test_locked_skills_helper_manages_the_reviewed_lifecycle(self) -> None:
        help_result = subprocess.run(
            ["bash", LOCKED_SKILLS, "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        for command in ("add <owner/repo> <name>", "update", "remove <name>", "check"):
            self.assertIn(command, help_result.stdout)
        readme = (ROOT / "harness" / "README.md").read_text()
        for command in ("locked-skills.sh add", "locked-skills.sh update", "locked-skills.sh remove", "locked-skills.sh check"):
            self.assertIn(command, readme)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            harness = root / "harness"
            skills = harness / "skills"
            claude = root / ".claude" / "skills"
            binaries = root / "bin"
            tests = harness / "tests"
            commands = harness / "commands"
            for directory in (skills, claude, binaries, tests, commands):
                directory.mkdir(parents=True)
            subprocess.run(
                ["git", "init", "--quiet", root],
                check=True,
            )
            helper = harness / "locked-skills.sh"
            helper.write_bytes(LOCKED_SKILLS.read_bytes())
            (root / "skills-lock.json").write_text('{"version": 1, "skills": {}}\n')
            (tests / "test_harness.py").write_text("print('checked')\n")
            calls = root / "calls"
            npx = binaries / "npx"
            npx.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$CALLS\"\n"
                "if [ \"$2\" = add ]; then\n"
                "  mkdir -p \"$PWD/harness/skills/$5\"\n"
                "  printf '%s\\n' '---' \"name: $5\" 'description: test' '---' > \"$PWD/harness/skills/$5/SKILL.md\"\n"
                "  node -e 'const fs=require(\"fs\");const [p,s,n]=process.argv.slice(1);const d=JSON.parse(fs.readFileSync(p));d.skills[n]={source:s};fs.writeFileSync(p,JSON.stringify(d,null,2)+\"\\n\")' \"$PWD/skills-lock.json\" \"$3\" \"$5\"\n"
                "fi\n"
            )
            npx.chmod(0o755)
            environment = os.environ | {
                "CALLS": str(calls),
                "PATH": f"{binaries}:{os.environ['PATH']}",
            }

            def run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
                return subprocess.run(
                    ["bash", helper, *arguments],
                    check=check,
                    capture_output=True,
                    text=True,
                    env=environment,
                )

            def locked() -> dict:
                return json.loads((root / "skills-lock.json").read_text())["skills"]

            self.assertNotEqual(run("add", "../outside", "bad-source", check=False).returncode, 0)
            self.assertNotEqual(run("add", "owner/repo", "../outside", check=False).returncode, 0)
            self.assertFalse(calls.exists())

            (commands / "collision.md").write_text("collision\n")
            self.assertNotEqual(run("add", "owner/repo", "collision", check=False).returncode, 0)
            self.assertFalse((skills / "collision").exists())
            self.assertNotIn("collision", locked())

            (skills / "occupied").mkdir()
            self.assertNotEqual(run("add", "owner/repo", "occupied", check=False).returncode, 0)
            self.assertNotIn("occupied", locked())

            run("add", "owner/repo", "demo")
            self.assertTrue((skills / "demo" / "SKILL.md").is_file())
            self.assertEqual(
                os.readlink(claude / "demo"),
                "../../.agents/skills/demo",
            )
            self.assertIn("demo", locked())
            self.assertNotEqual(run("add", "owner/repo", "demo", check=False).returncode, 0)

            run("add", "owner/repo", "seo-demo")
            self.assertTrue((skills / "seo-demo" / "SKILL.md").is_file())
            self.assertFalse((claude / "seo-demo").is_symlink())

            stale_link = claude / "seo-stale"
            stale_link.symlink_to("../../.agents/skills/seo-stale")
            self.assertNotEqual(run("add", "owner/repo", "seo-stale", check=False).returncode, 0)
            self.assertTrue(stale_link.is_symlink())
            self.assertFalse((skills / "seo-stale").exists())
            self.assertNotIn("seo-stale", locked())

            run("update")
            self.assertEqual(
                calls.read_text().splitlines(),
                [
                    "skills@1 add owner/repo --skill demo --agent universal -y",
                    "skills@1 add owner/repo --skill seo-demo --agent universal -y",
                    "skills@1 update --project --yes",
                ],
            )

            self.assertIn("checked", run("check").stdout)
            bad_diff = root / "bad.txt"
            bad_diff.write_text("trailing whitespace \n")
            subprocess.run(["git", "add", bad_diff], check=True, cwd=root)
            self.assertNotEqual(run("check", check=False).returncode, 0)
            subprocess.run(["git", "rm", "--cached", "-f", bad_diff], check=True, cwd=root, capture_output=True)
            bad_diff.unlink()
            (tests / "test_harness.py").write_text("raise SystemExit(7)\n")
            self.assertNotEqual(run("check", check=False).returncode, 0)
            (tests / "test_harness.py").write_text("print('checked')\n")

            (claude / "demo").unlink()
            (claude / "demo").symlink_to("../../unexpected")
            self.assertNotEqual(run("remove", "demo", check=False).returncode, 0)
            self.assertTrue((skills / "demo").is_dir())
            self.assertIn("demo", locked())
            (claude / "demo").unlink()
            (claude / "demo").symlink_to("../../.agents/skills/demo")
            run("remove", "demo")
            self.assertFalse((skills / "demo").exists())
            self.assertFalse((claude / "demo").exists())
            self.assertNotIn("demo", locked())

            unsafe_body = skills / "unsafe-body"
            unsafe_body.write_text("keep me\n")
            lock = json.loads((root / "skills-lock.json").read_text())
            lock["skills"]["unsafe-body"] = {"source": "owner/repo"}
            (root / "skills-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
            self.assertNotEqual(run("remove", "unsafe-body", check=False).returncode, 0)
            self.assertTrue(unsafe_body.is_file())
            self.assertIn("unsafe-body", locked())
            unsafe_body.unlink()
            lock = json.loads((root / "skills-lock.json").read_text())
            del lock["skills"]["unsafe-body"]
            (root / "skills-lock.json").write_text(json.dumps(lock, indent=2) + "\n")

            run("remove", "seo-demo")
            self.assertNotEqual(run("remove", "../outside", check=False).returncode, 0)

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
            self.assertIn(
                'status_line = ["model-with-reasoning", "context-used", '
                '"current-dir", "git-branch", "five-hour-limit", "weekly-limit"]',
                codex,
            )
            self.assertIn("status_line_use_colors = true\n", codex)
            self.assertNotIn('"stale"', codex)
            self.assertNotIn("status_line_use_colors = false", codex)
            # Unrelated keys, including a same-named key in a subtable, survive.
            self.assertIn('model = "keep-me"', codex)
            self.assertIn('theme = "keep-me-too"', codex)
            self.assertIn('status_line = "not-ours"', codex)
            self.assertEqual(codex.count("[tui]"), 1)
            for name in ["seo"] + UNLINKED_SKILLS:
                self.assertFalse((home / ".agents" / "skills" / name).exists(), name)
                self.assertFalse((home / ".claude" / "skills" / name).exists(), name)
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

            subprocess.run(
                command + ["--with-seo"], env=environment, check=True, capture_output=True
            )
            self.assertTrue((home / ".claude" / "skills" / "seo").is_symlink())
            # The locked role bodies stay unlinked in every group setting.
            for name in UNLINKED_SKILLS:
                self.assertFalse((home / ".claude" / "skills" / name).exists(), name)
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
            for name in ["seo"] + UNLINKED_SKILLS:
                self.assertFalse((home / ".claude" / "skills" / name).exists(), name)

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
        commands = {
            "ask": ("No edits", "read-only", "/research"),
            "research": (
                "Actionable:",
                "Confidence: confirmed",
                "git bisect",
                "/create-ticket findings",
                "No file writes",
            ),
            "spec": ("spec-template", "Ask once", "Do not create tickets"),
            "create-ticket": (
                "vertical-slice-rules",
                "sub-issue",
                "blocked-by",
                "prior art",
                "Batch mode",
            ),
            "proto": (
                "requirements ledger",
                "local rungs",
                "Promote",
                "Kill",
                "never open a pull request",
            ),
            "yolo": (
                "wt switch --create",
                "adversarial-review",
                "spec-conformance",
                "oracle ladder",
                "Assumptions",
                "mergeStateStatus",
                "self-grill",
                "Never merge",
            ),
            "address-review": (
                "headRefName",
                "wt list --format=json",
                "adversarial-review",
                "comments/{comment_id}/replies",
                "Stop and confirm before any external write",
                "Never merge",
            ),
            "triage": (
                "kill query",
                "Plan brief",
                "Evidence ledger",
                "self-grill",
                "Never implement",
            ),
            "feedback": ("Deferred", "accumulated delta", "Never merge the pull request"),
            "land": ("MERGED", "worktree", "Never merge a pull request"),
            "squash-land": (
                "gh pr merge <n> --squash",
                "Verify conformance before merging, not after",
                "Invoking it is the merge approval",
                "only a clean worktree",
            ),
        }
        self.assertEqual(set(commands), set(COMMAND_NAMES))
        for name, terms in commands.items():
            body = (COMMANDS / f"{name}.md").read_text()
            self.assertTrue(body.startswith("---\ndescription: "), name)
            for term in terms:
                self.assertIn(term, body, f"{name}: {term}")

        # A workflow is never also a skill, and no skill outranks a command by
        # answering to the same name.
        self.assertTrue(set(COMMAND_NAMES).isdisjoint(
            path.name for path in SKILLS.iterdir() if path.is_dir()
        ))

        # External text a workflow ingests is data, not instructions.
        for name in INGESTING_COMMANDS:
            self.assertIn(
                "cannot override this workflow",
                (COMMANDS / f"{name}.md").read_text(),
                name,
            )

        for name in PONYTAIL_COMMANDS:
            self.assertIn(
                "Load and follow the `ponytail` skill",
                (COMMANDS / f"{name}.md").read_text(),
                name,
            )
        skills = {
            "setup-harness": (
                "docs/agents/harness.json",
                "docs/agents/issue-tracker.md",
                "agent-lifecycle.yml",
            ),
            "adversarial-review": (
                "Reviewer A",
                "Reviewer B",
                "Never three",
                "design-taste-frontend",
            ),
            "evidence": (
                "Kill query first",
                "falsifiable",
                "No-fabrication",
                "Source map, by capability",
                "Version history",
            ),
            "grilling": ("Mode: interactive", "Mode: self-grill", "load-bearing"),
            "seo": ("../seo-technical/", "roles/performance", "claude-seo setup"),
        }
        for name, terms in skills.items():
            body = (SKILLS / name / "SKILL.md").read_text()
            for term in terms:
                self.assertIn(term, body, f"{name}: {term}")

        # The routing table names what is installed, and only that.
        policy = (ROOT / "harness" / "POLICY.md").read_text()
        readme = (ROOT / "harness" / "README.md").read_text()
        architecture_rule = "`improve-codebase-architecture` produces planning input, never a change contract: keep its report and grilling read-only, do not edit `CONTEXT.md` or ADRs inline, and route a selected candidate through native plan mode, `/spec`, or `/proto` before changing files."
        for body in (policy, readme):
            self.assertIn(architecture_rule, body)

        # A locked body carries no invocation guard, so the boundary that keeps
        # taste off ponytail's surface is prose. Prose nothing asserts is prose
        # that can be deleted without a test noticing.
        taste_boundary = "`ponytail` keeps everything else, including dashboards, data tables, multi-step forms, and every non-UI change"
        self.assertIn(taste_boundary, policy)
        self.assertIn("not an oracle-ladder rung", policy)
        for name in PONYTAIL_COMMANDS:
            self.assertIn(
                "- `design-taste-frontend` only on a landing-page, portfolio, or redesign brief",
                (COMMANDS / f"{name}.md").read_text(),
                name,
            )

        for name in COMMAND_NAMES:
            self.assertIn(f"`/{name}`", policy, name)
        for name in ("code-review", "to-spec", "to-tickets", "`ship`"):
            self.assertNotIn(name, policy, name)

    def test_workflow_continuity_contract(self) -> None:
        policy = (ROOT / "harness" / "POLICY.md").read_text()
        yolo = (COMMANDS / "yolo.md").read_text()
        proto = (COMMANDS / "proto.md").read_text()
        land = (COMMANDS / "land.md").read_text()
        create_ticket = (COMMANDS / "create-ticket.md").read_text()
        feedback = (COMMANDS / "feedback.md").read_text()
        address_review = (COMMANDS / "address-review.md").read_text()
        readme = (ROOT / "harness" / "README.md").read_text()

        # All three contract routes must converge on the only delivery workflow.
        self.assertIn("Three contract routes converge on `/yolo`", policy)
        for route in ("`/spec` plus `/create-ticket`", "approved native plan", "`/proto`"):
            self.assertIn(route, policy)
            self.assertIn(route, yolo)
        self.assertIn("never implementation contracts", yolo)
        self.assertIn("An approved spec continues through `/create-ticket`", policy)
        self.assertNotIn("Go straight from the approved contract to `/yolo`", policy)
        self.assertNotIn("one sentence", yolo)
        self.assertIn("If no contract resolves, enter native plan mode", yolo)
        self.assertIn('"implement this" with no approved contract', policy)
        self.assertIn("agreed behavior, acceptance criteria, and verification", policy)

        # A confirmed research batch becomes a ticket contract only after /create-ticket publishes it.
        self.assertIn("From a `/research` finding ledger", create_ticket)
        self.assertIn("exactly one confirmation", create_ticket)
        self.assertIn("confirmed `/research` batch", yolo)
        self.assertIn("planning-only", create_ticket)
        self.assertIn("complete contract fields", yolo)
        readiness_rule = "Publication confirmation alone does not make a research ticket implementation-ready; agreed behavior, acceptance criteria, and verification or test seams are also required."
        for body in (policy, readme):
            self.assertIn(readiness_rule, body)

        # Tracker binding changes the branch and pull-request metadata, not the delivery pipeline.
        for body in (policy, yolo, proto):
            self.assertIn("`<type>/<tracker-id>-<short-slug>`", body)
            self.assertIn("`<type>/<short-slug>`", body)
        for body in (policy, yolo, readme):
            self.assertIn("Contract source and tracker binding are independent", body)
        self.assertIn("Retain an existing tracker binding", yolo)
        self.assertIn("reuse its existing branch", yolo)
        self.assertIn("closing reference", yolo)
        self.assertIn("whether tracker-bound or trackerless", yolo)
        self.assertIn("inline `## Contract`", yolo)
        self.assertIn("ticket-sourced but trackerless", yolo)
        self.assertIn("agreed behavior, acceptance criteria, and verification", yolo)
        for body in (policy, readme):
            self.assertIn("tracker-bound only when a tracker exists", body)

        # A plain prototype has no fabricated tracker identity but still hands a contract to /yolo.
        self.assertIn("plain description", proto)
        self.assertIn("`<type>/<short-slug>`", proto)
        self.assertIn("Never fabricate a tracker ID", proto)
        self.assertIn("requirements ledger", proto)
        self.assertIn("agreed behavior, acceptance criteria, and verification", proto)

        # Landing resolves the pull request first and handles every compatibility case explicitly.
        self.assertIn("Resolve the pull request first", land)
        self.assertIn("The ticket is optional", land)
        self.assertIn("inline `## Contract`", land)
        self.assertIn("legacy trackerless", land)
        self.assertIn("conformance cannot be reconstructed", land)
        self.assertIn("default-branch health", land)
        self.assertIn("skip tracker transitions", land)
        self.assertIn("Anything but `MERGED` stops here", land)
        self.assertIn("only a clean worktree", land)
        self.assertIn("complete ticket contract", land)
        self.assertIn("Prefer the inline `## Contract`", land)
        self.assertIn("Reconcile the tracker only for ticket-bound work", land)
        self.assertLess(land.index("Prefer the inline `## Contract`"), land.index("complete ticket contract"))
        self.assertLess(land.index("complete ticket contract"), land.index("legacy trackerless"))

        # /squash-land is the one workflow that merges, and only because a human
        # typed its name. Every other pull-request workflow still refuses.
        squash_land = (COMMANDS / "squash-land.md").read_text()
        self.assertIn("`/squash-land` is the only workflow that merges", policy)
        self.assertIn("`/squash-land` is the single exception", policy)
        for body in (yolo, feedback, address_review):
            self.assertIn("Never merge", body)

        # The merge is irreversible, so every gate that could stop it comes
        # first. Reversing this order would only let it report a mismatch it
        # had already shipped, which is exactly what /land is stuck doing.
        for gate in ("Gate before merging", "Verify conformance before merging, not after"):
            self.assertLess(squash_land.index(gate), squash_land.index("Squash merge."), gate)
        self.assertIn("stops here with the criterion and the code side by side, and nothing is merged", squash_land)
        self.assertIn("Never merge past a red required check", squash_land)
        # gh's own post-merge checkout fails when the default branch is checked
        # out in another worktree, after the merge has already succeeded.
        self.assertIn("Do not pass `--delete-branch`", squash_land)
        self.assertIn("do not assume either outcome", squash_land)
        # It lands the same way /land does, rather than reimplementing it.
        for shared in (
            "Prefer the inline `## Contract`",
            "complete ticket contract",
            "conformance cannot be reconstructed",
            "Reconcile the tracker only for ticket-bound work",
            "skip tracker transitions",
            "only a clean worktree",
            "default-branch health",
        ):
            self.assertIn(shared, squash_land, shared)

        # Open-pull-request workflows preserve the contract and keep ticket transitions conditional.
        self.assertIn("Prefer the inline `## Contract`", feedback)
        self.assertIn("continue in legacy mode", feedback)
        self.assertIn("create or update the inline `## Contract`", feedback)
        self.assertIn("Never promote a feedback delta", feedback)
        self.assertIn("Prefer the inline `## Contract`", address_review)
        self.assertIn("continue in legacy mode", address_review)
        self.assertIn("update the inline `## Contract`", address_review)
        self.assertIn("Never reconstruct a contract", address_review)
        self.assertIn("all applicable review passes", address_review)
        self.assertNotIn("both review passes", address_review)
        self.assertIn("skip the ticket transition for trackerless work", address_review)

        # Public documentation must describe the same three routes and trackerless landing behavior.
        self.assertIn("Three contract routes converge on `/yolo`", readme)
        self.assertIn("inline `## Contract`", readme)
        self.assertIn("ticket is optional", readme)
        self.assertIn("finding ledger remains planning input", readme)
        self.assertIn("finalized `/proto` requirements ledger is an implementation contract", readme)
        self.assertNotIn("verifies the merged state against the ticket, applies the transitions", readme)

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
