"""Regression checks for the generated reviewer agents.

The canonical roles live beside adversarial-review, and clients/agents.py renders one definition per reviewer per client. These checks drive the generator through temporary directories the way install.sh calls it, and pin the protocol lines the skill, the roles, and the policy share. A pinned line is compared whole, so a deliberate paraphrase fails the pin, but a paraphrase added elsewhere beside an intact line does not.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_GENERATOR = _HARNESS / "clients/agents.py"
_SKILL = _HARNESS / "skills/adversarial-review/SKILL.md"
_ROLES = _HARNESS / "skills/adversarial-review/roles"
_POLICY = _HARNESS / "POLICY.md"
_INSTALL = _HARNESS / "install.sh"

ACCESS = "Read and search only. Read and search the repository to follow callers and context. Never edit a file, run a command, fetch from the web, or delegate to another agent, even where the client would let you."
CODEX_ACCESS = "Read and search only. Read and search the repository to follow callers and context. Never edit a file, fetch from the web, or delegate to another agent, even where the client would let you. Shell is how this client reads files, so run only commands that read or search, never one that changes state."

OUTPUTS = {
    "claude/reviewer-a.md",
    "claude/reviewer-b.md",
    "codex/reviewer_a.toml",
    "codex/reviewer_b.toml",
    "opencode/reviewer-a.md",
    "opencode/reviewer-b.md",
}


def run(*args):
    return subprocess.run(
        [sys.executable, str(_GENERATOR), *map(str, args)],
        capture_output=True,
        text=True,
    )


def tree(root):
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def lines(path):
    return path.read_text().splitlines()


def installer_agents(harness, home, uninstall):
    """Run install.sh's own agent functions, lifted verbatim, against a temporary HOME and checkout."""
    text = _INSTALL.read_text()
    parts = [re.search(r"^AGENT_OUT=.*?^\)\n", text, re.M | re.S).group(0)]
    for name in ("backup_existing", "link_managed", "ensure_managed_dir", "sweep_agent_links", "install_agents", "check_agents", "remove_agents", "check_agents_removed"):
        parts.append(re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.M | re.S).group(0))
    script = "\n".join(
        ["set -euo pipefail", "shopt -s nullglob", 'log() { :; }; die() { echo "$*" >&2; exit 1; }', *parts]
        + ["remove_agents; check_agents_removed" if uninstall else "install_agents >/dev/null; check_agents"]
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "HARNESS_DIR": str(harness),
        "CONFIG_HOME": str(home / ".config"),
        "UNINSTALL": "true" if uninstall else "false",
        "NO_BACKUP": "true",
    }
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)


class Generation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out = self.tmp / "out"

    def generate(self):
        result = run(_ROLES, self.out)
        self.assertIn(result.returncode, (0, 3), result.stderr)
        return result

    def test_one_definition_per_reviewer_per_client(self):
        self.assertEqual(self.generate().returncode, 0)
        self.assertEqual(set(tree(self.out)), OUTPUTS)

    def test_generation_is_idempotent(self):
        self.generate()
        first = tree(self.out)
        self.assertEqual(self.generate().returncode, 3)
        self.assertEqual(tree(self.out), first)

    def test_each_client_gets_its_supported_controls_and_the_whole_role(self):
        self.generate()
        for role in ("a", "b"):
            body = (_ROLES / f"reviewer-{role}.md").read_text().split("---\n", 2)[2].strip()
            claude = (self.out / f"claude/reviewer-{role}.md").read_text()
            codex = (self.out / f"codex/reviewer_{role}.toml").read_text()
            opencode = (self.out / f"opencode/reviewer-{role}.md").read_text()
            self.assertIn(f"\nname: reviewer-{role}\n", claude)
            self.assertIn("\ntools: Read, Grep, Glob\n", claude)
            self.assertIn(f'name = "reviewer_{role}"\n', codex)
            self.assertIn('\nsandbox_mode = "read-only"\n', codex)
            self.assertIn("\n[mcp_servers.agent-browser]\nenabled = false\n", codex)
            self.assertIn("\n[mcp_servers.engram]\nenabled = false\n", codex)
            self.assertIn("\nmode: subagent\npermission:\n  \"*\": deny\n", opencode)
            self.assertIn('\n    "*.env": deny\n', opencode)
            allowed = [line.split(":")[0].strip() for line in opencode.split("---")[1].splitlines() if line.startswith("  ") and line.endswith(": allow")]
            self.assertEqual(allowed, ['"*"', '"*.env.example"', "grep", "glob", "list"])
            self.assertIn(body, claude)
            self.assertIn(body, opencode)
            self.assertIn(body.replace(ACCESS, CODEX_ACCESS), codex)
            self.assertNotIn(ACCESS, codex)

    def test_gaps_and_unverified_capabilities_are_reported_apart(self):
        report = self.generate().stdout.splitlines()
        self.assertTrue(any(line.startswith("gap: codex: shell") for line in report), report)
        self.assertTrue(any(line.startswith("unverified: ") for line in report), report)
        self.assertFalse(any(line.startswith("gap: claude") for line in report), report)
        self.assertTrue(any(line.startswith("unverified: ") and "ccyolo" in line for line in report), report)

    def test_check_passes_on_fresh_output(self):
        self.generate()
        result = run("--check", _ROLES, self.out)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_check_detects_permission_widening(self):
        mutations = [
            ("claude/reviewer-a.md", "tools: Read, Grep, Glob\n", "tools: Read, Grep, Glob, Bash\n"),
            ("claude/reviewer-b.md", "tools: Read, Grep, Glob\n", ""),
            ("codex/reviewer_a.toml", 'sandbox_mode = "read-only"', 'sandbox_mode = "workspace-write"'),
            ("codex/reviewer_b.toml", "[mcp_servers.engram]\nenabled = false\n", ""),
            ("opencode/reviewer-a.md", '  "*": deny', '  "*": allow'),
            ("opencode/reviewer-b.md", "  list: allow\n", "  list: allow\n  bash: allow\n"),
            ("opencode/reviewer-b.md", "mode: subagent\n", "mode: subagent\ntools:\n  bash: true\n"),
        ]
        for path, old, new in mutations:
            with self.subTest(path=path, new=new):
                self.generate()
                target = self.out / path
                text = target.read_text()
                self.assertIn(old, text)
                target.write_text(text.replace(old, new))
                result = run("--check", _ROLES, self.out)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"widened: {path}", result.stdout)

    def test_check_detects_missing_and_drifted_output(self):
        self.generate()
        (self.out / "codex/reviewer_b.toml").unlink()
        target = self.out / "claude/reviewer-a.md"
        target.write_text(target.read_text() + "\nExtra instruction.\n")
        result = run("--check", _ROLES, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing: codex/reviewer_b.toml", result.stdout)
        self.assertIn("changed: claude/reviewer-a.md", result.stdout)

    def test_generation_removes_stale_outputs(self):
        (self.out / "codex").mkdir(parents=True)
        stale = self.out / "codex/retired.toml"
        stale.write_text("stale\n")
        self.generate()
        self.assertFalse(stale.exists())
        self.assertEqual(set(tree(self.out)), OUTPUTS)

    def test_symlinked_output_paths_are_refused_without_writes(self):
        for kind in ("file", "client", "output", "ancestor", "dangling"):
            with self.subTest(kind=kind):
                base = self.tmp / kind
                output = base / "parent/out"
                self.assertEqual(run(_ROLES, output).returncode, 0)
                link = {
                    "file": output / "claude/reviewer-a.md",
                    "client": output / "claude",
                    "output": output,
                    "ancestor": output.parent,
                    "dangling": output / "claude/reviewer-a.md",
                }[kind]
                external = base / "external"
                link.rename(external)
                if external.is_file():
                    external.write_text("private agent\n")
                link.symlink_to(base / "missing" if kind == "dangling" else external)
                before = tree(base)
                for flags in ((), ("--check",)):
                    result = run(*flags, _ROLES, output)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("symlink", result.stderr)
                    self.assertEqual(tree(base), before)
                    self.assertTrue(link.is_symlink())
                self.assertFalse((base / "missing").exists())

    def test_missing_duplicate_and_unknown_roles_preserve_outputs(self):
        self.generate()
        before = tree(self.out)
        for kind in ("missing", "duplicate", "unknown"):
            with self.subTest(kind=kind):
                roles = self.tmp / kind
                shutil.copytree(_ROLES, roles)
                if kind == "missing":
                    (roles / "reviewer-b.md").unlink()
                elif kind == "duplicate":
                    shutil.copy(roles / "reviewer-a.md", roles / "copy.md")
                else:
                    role = roles / "reviewer-b.md"
                    role.write_text(role.read_text().replace("name: reviewer-b", "name: other"))
                for flags in ((), ("--check",)):
                    result = run(*flags, roles, self.out)
                    self.assertEqual(result.returncode, 4, result.stdout)
                    self.assertIn("reviewer", result.stderr)
                    self.assertEqual(tree(self.out), before)

    def test_incomplete_or_widened_role_is_refused(self):
        edits = {
            "description": ("description: ", "summary: "),
            "access": ("access: read-search", "access: read-write"),
            "access line": (ACCESS, "Read anything."),
        }
        for label, (old, new) in edits.items():
            with self.subTest(label):
                roles = self.tmp / f"roles-{label}"
                shutil.copytree(_ROLES, roles)
                role = roles / "reviewer-b.md"
                role.write_text(role.read_text().replace(old, new, 1))
                output = self.tmp / f"out-{label}"
                result = run(roles, output)
                self.assertEqual(result.returncode, 4, result.stdout)
                self.assertIn("reviewer-b.md", result.stderr)
                self.assertFalse(output.exists())


class InstallerOwnership(unittest.TestCase):
    def test_install_and_uninstall_touch_only_this_checkouts_links(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        harness, home = tmp / "harness", tmp / "home"
        harness.mkdir()
        for name in ("clients", "skills"):
            (harness / name).symlink_to(_HARNESS / name)
        out = harness / ".generated/agents"
        roots = {"claude": home / ".claude/agents", "codex": home / ".codex/agents", "opencode": home / ".config/opencode/agents"}
        roots["claude"].mkdir(parents=True)
        private = roots["claude"] / "mine.md"
        private.write_text("mine\n")
        foreign = roots["claude"] / "foreign.md"
        foreign.symlink_to("/elsewhere/other-checkout/.generated/agents/claude/foreign.md")
        retired = roots["claude"] / "retired.md"
        retired.symlink_to(out / "claude/retired.md")

        result = installer_agents(harness, home, uninstall=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        for relative in OUTPUTS:
            client, name = relative.split("/")
            self.assertEqual(os.readlink(roots[client] / name), str(out / relative))
        self.assertFalse(retired.is_symlink())
        self.assertEqual(private.read_text(), "mine\n")
        self.assertTrue(foreign.is_symlink())

        result = installer_agents(harness, home, uninstall=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for root in roots.values():
            self.assertEqual({entry.name for entry in root.iterdir()} - {"mine.md", "foreign.md"}, set())
        self.assertFalse(out.exists())
        self.assertEqual(private.read_text(), "mine\n")
        self.assertTrue(foreign.is_symlink())


    def test_install_refuses_unowned_collisions_before_linking(self):
        for kind in ("file", "foreign-link", "root-link"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                tmp = Path(directory).resolve()
                harness, home = tmp / "harness", tmp / "home"
                harness.mkdir()
                for name in ("clients", "skills"):
                    (harness / name).symlink_to(_HARNESS / name)
                root = home / ".config/opencode/agents"
                root.parent.mkdir(parents=True)
                private = tmp / "private"
                private.mkdir()
                (private / "reviewer-b.md").write_text("private agent\n")
                if kind == "root-link":
                    root.symlink_to(private)
                else:
                    root.mkdir()
                    target = root / "reviewer-b.md"
                    if kind == "file":
                        target.write_text("private agent\n")
                    else:
                        target.symlink_to(private / "reviewer-b.md")
                result = installer_agents(harness, home, uninstall=False)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(str(root), result.stderr)
                self.assertEqual((root / "reviewer-b.md").read_text(), "private agent\n")
                self.assertEqual((private / "reviewer-b.md").read_text(), "private agent\n")
                self.assertFalse((home / ".claude/agents/reviewer-a.md").exists())
                if kind == "root-link":
                    self.assertTrue(root.is_symlink())
                elif kind == "foreign-link":
                    self.assertTrue((root / "reviewer-b.md").is_symlink())

    def test_uninstall_fails_by_name_on_a_link_inside_a_symlinked_root(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        harness, home = tmp / "harness", tmp / "home"
        harness.mkdir()
        for name in ("clients", "skills"):
            (harness / name).symlink_to(_HARNESS / name)
        self.assertEqual(installer_agents(harness, home, uninstall=False).returncode, 0)
        claude, elsewhere = home / ".claude/agents", tmp / "elsewhere"
        claude.rename(elsewhere)
        claude.symlink_to(elsewhere)

        result = installer_agents(harness, home, uninstall=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Reviewer agent link survived the uninstall", result.stderr)
        self.assertTrue((elsewhere / "reviewer-a.md").is_symlink())


class Protocol(unittest.TestCase):
    def test_roles_own_the_standing_instructions(self):
        a, b = (_ROLES / "reviewer-a.md").read_text(), (_ROLES / "reviewer-b.md").read_text()
        self.assertIn("\nAssume this diff fails to do what the requirements say. Find where.\n", a)
        self.assertIn("\nAssume this diff is wrong. Find the bug.\n", b)
        for text in (a, b):
            for heading in ("## Inputs", "## Access", "## Lenses", "## Output"):
                self.assertIn(f"\n{heading}\n", text)
        self.assertEqual(a.split("## Output\n", 1)[1], b.split("## Output\n", 1)[1])

    def test_skill_keeps_orchestration_without_the_role_text(self):
        skill = _SKILL.read_text()
        for heading in ("## Invocation", "## Diff delivery", "## Triage, by the implementer", "## Loop cap"):
            self.assertIn(f"\n{heading}\n", skill)
        self.assertNotIn("An unmet requirement", skill)
        self.assertNotIn("Callers of every touched symbol", skill)
        self.assertNotIn("a check that would still pass if the logic it covers were deleted", skill)
        self.assertNotIn("dead code and leftovers", skill)
        self.assertNotIn("Severity is one of", skill)

    def test_pinned_lines(self):
        unreadable = "When you cannot read the whole file, return exactly `unreadable: <path>` and nothing else, so the parent can supply the same diff inline. Never review part of a diff."
        pins = {
            _POLICY: [
                "Use ephemeral specialist roles. Do not create persistent client-specific personas when a command, a skill, or an isolated review context is enough. Role definitions generated from one canonical source, such as the reviewer agents, are shared instructions and client capability configuration, not personas.",
            ],
            _SKILL: [
                "Launch each reviewer as its named agent, in parallel, each with a fresh context: `reviewer-a` and `reviewer-b` in Claude Code and OpenCode, `reviewer_a` and `reviewer_b` in Codex. The installer generates them from `roles/reviewer-a.md` and `roles/reviewer-b.md` beside this skill, which own each reviewer's standing instructions, lenses, and output format.",
                "When a named agent is unavailable, say so, launch a general agent with the matching role file's full text as its instructions, and report that this fallback enforces only the general agent's own permissions rather than the named agent's read-search restrictions. Never skip or silently omit a review because a named agent is missing.",
                "In Codex, give that fallback the role text with its Access line replaced by `CODEX_ACCESS` from `clients/agents.py`, because shell is how Codex reads files.",
                "Give Reviewer A the requirements and the diff, never the implementation rationale. Nothing else.",
                "Give Reviewer B only the diff. No requirements, no rationale, no ticket.",
                "Snapshot the complete diff once per round into a readable temporary file outside the worktree, and give each reviewer that path. A reviewer that answers `unreadable: <path>` gets the same snapshot inline instead. Never truncate the diff: when neither the file nor inline text can carry the complete snapshot, stop and escalate per the escalation contract.",
            ],
            _ROLES / "reviewer-a.md": [unreadable, ACCESS],
            _ROLES / "reviewer-b.md": [unreadable, ACCESS],
        }
        for path, expected in pins.items():
            present = lines(path)
            for line in expected:
                with self.subTest(path=path.name, line=line[:60]):
                    self.assertIn(line, present)


if __name__ == "__main__":
    unittest.main()
