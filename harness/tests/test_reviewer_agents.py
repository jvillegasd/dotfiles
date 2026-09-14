"""Regression checks for the generated role agents.

`clients/assignments.json` names every role, its canonical definition, and its model and effort assignments, and clients/agents.py renders one definition per role per client. These checks drive the generator through temporary directories the way install.sh calls it, and pin the protocol lines the skill, the roles, the policy, and the delivery commands share. A pinned line is compared whole, with list indentation stripped only in command files, so a deliberate paraphrase fails the pin, but a paraphrase added elsewhere beside an intact line does not.
"""

import json
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
_CONFIG = _HARNESS / "clients/assignments.json"
_SKILL = _HARNESS / "skills/adversarial-review/SKILL.md"
_ROLES = _HARNESS / "skills/adversarial-review/roles"
_POLICY = _HARNESS / "POLICY.md"
_INSTALL = _HARNESS / "install.sh"

ACCESS = "Read and search only. Read and search the repository to follow callers and context. Never edit a file, run a command, fetch from the web, or delegate to another agent, even where the client would let you."

OUTPUTS = {
    "claude/executor.md",
    "claude/reviewer-a.md",
    "claude/reviewer-b.md",
    "opencode/executor.md",
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


def config_copy(directory, edit=None):
    """Copy the canonical assignments and each role definition into directory, pointing the copy at the copied definitions, then apply edit to the parsed config."""
    data = json.loads(_CONFIG.read_text())
    (directory / "roles").mkdir(parents=True, exist_ok=True)
    for name, role in data["roles"].items():
        if "definition" in role:
            copy = directory / "roles" / f"{name}.md"
            shutil.copy(_CONFIG.parent / role["definition"], copy)
            role["definition"] = str(copy)
    if edit:
        edit(data)
    path = directory / "assignments.json"
    path.write_text(json.dumps(data))
    return path


def frontmatter(text):
    return text.split("---\n")[1]


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


def checkout(tmp):
    harness = tmp / "harness"
    harness.mkdir()
    for name in ("clients", "roles", "skills"):
        (harness / name).symlink_to(_HARNESS / name)
    return harness


class Generation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out = self.tmp / "out"

    def generate(self, config=_CONFIG):
        result = run(config, self.out)
        self.assertIn(result.returncode, (0, 3), result.stderr)
        return result

    def test_one_definition_per_role_per_client(self):
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
            opencode = (self.out / f"opencode/reviewer-{role}.md").read_text()
            self.assertIn(f"\nname: reviewer-{role}\n", claude)
            self.assertIn("\ntools: Read, Grep, Glob\n", claude)
            self.assertIn("\nmode: subagent\npermission:\n  \"*\": deny\n", opencode)
            self.assertIn('\n    "*.env": deny\n', opencode)
            allowed = [line.split(":")[0].strip() for line in opencode.split("---")[1].splitlines() if line.startswith("  ") and line.endswith(": allow")]
            self.assertEqual(allowed, ['"*"', '"*.env.example"', "grep", "glob", "list"])
            self.assertIn(body, claude)
            self.assertIn(body, opencode)

    def test_executor_keeps_implementation_access(self):
        self.generate()
        body = (_HARNESS / "roles/executor.md").read_text().split("---\n", 2)[2].strip()
        claude = (self.out / "claude/executor.md").read_text()
        opencode = (self.out / "opencode/executor.md").read_text()
        self.assertIn("\nname: executor\n", claude)
        self.assertNotIn("tools:", frontmatter(claude))
        self.assertIn("\ndisallowedTools: Agent\n", claude)
        self.assertIn("\nmode: subagent\npermission:\n  task: deny\n  bash:\n", opencode)
        for pattern in ("git commit*", "git push*", "git worktree remove*", "wt remove*", "wt merge*", "wt step commit*", "gh *"):
            self.assertIn(f'\n    "{pattern}": deny\n', opencode)
        self.assertNotIn('"*": deny', opencode)
        self.assertIn(body, claude)
        self.assertIn(body, opencode)
        self.assertEqual(run("--check", _CONFIG, self.out).returncode, 0)

    def test_only_the_executor_may_implement(self):
        for name, access, status in (("review-refuter", "implement", 4), ("review-refuter", "read-search", 0), ("executor", "read-search", 4)):
            with self.subTest(name=name, access=access):
                directory = self.tmp / f"{name}-{access}"
                refuter = directory / "roles/review-refuter.md"
                config = config_copy(directory, lambda data: data["roles"]["review-refuter"].update(definition=str(refuter)))
                text = (directory / "roles/reviewer-b.md").read_text().replace("name: reviewer-b", "name: review-refuter")
                refuter.write_text(text.replace("access: read-search", f"access: {access}") if name == "review-refuter" else text)
                if name == "executor":
                    role = directory / "roles/executor.md"
                    role.write_text(role.read_text().replace("access: implement", "access: read-search"))
                result = run(config, directory / "out")
                self.assertEqual(result.returncode, status, result.stderr)
                if status:
                    self.assertIn(f"{name}.md: access must be", result.stderr)

    def test_gaps_and_unverified_capabilities_are_reported_apart(self):
        report = self.generate().stdout.splitlines()
        self.assertTrue(any(line.startswith("unverified: ") for line in report), report)
        claude_gaps = [line for line in report if line.startswith("gap: claude")]
        self.assertEqual(len(claude_gaps), 2, report)
        self.assertTrue(any(line.startswith("gap: claude: the executor keeps Bash") for line in claude_gaps), report)
        self.assertTrue(any(line.startswith("gap: claude: a model parameter passed at launch") for line in claude_gaps), report)
        self.assertTrue(any(line.startswith("unverified: ") and "ccyolo" in line for line in report), report)

    def test_check_passes_on_fresh_output(self):
        self.generate()
        result = run("--check", _CONFIG, self.out)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_check_detects_permission_widening(self):
        mutations = [
            ("claude/reviewer-a.md", "tools: Read, Grep, Glob\n", "tools: Read, Grep, Glob, Bash\n"),
            ("claude/reviewer-b.md", "tools: Read, Grep, Glob\n", ""),
            ("opencode/reviewer-a.md", '  "*": deny', '  "*": allow'),
            ("opencode/reviewer-b.md", "  list: allow\n", "  list: allow\n  bash: allow\n"),
            ("opencode/reviewer-b.md", "mode: subagent\n", "mode: subagent\ntools:\n  bash: true\n"),
            ("claude/executor.md", "disallowedTools: Agent\n", ""),
            ("opencode/executor.md", "  task: deny\n", "  task: allow\n"),
        ]
        for path, old, new in mutations:
            with self.subTest(path=path, new=new):
                self.generate()
                target = self.out / path
                text = target.read_text()
                self.assertIn(old, text)
                target.write_text(text.replace(old, new))
                result = run("--check", _CONFIG, self.out)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"widened: {path}", result.stdout)

    def test_check_detects_missing_and_drifted_output(self):
        self.generate()
        target = self.out / "claude/reviewer-a.md"
        target.write_text(target.read_text() + "\nExtra instruction.\n")
        result = run("--check", _CONFIG, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn("changed: claude/reviewer-a.md", result.stdout)

    def test_generation_removes_stale_outputs(self):
        (self.out / "gone").mkdir(parents=True)
        stale = self.out / "gone/retired.md"
        stale.write_text("stale\n")
        self.generate()
        self.assertFalse(stale.exists())
        self.assertEqual(set(tree(self.out)), OUTPUTS)

    def test_symlinked_output_paths_are_refused_without_writes(self):
        for kind in ("file", "client", "output", "ancestor", "dangling"):
            with self.subTest(kind=kind):
                base = self.tmp / kind
                output = base / "parent/out"
                self.assertEqual(run(_CONFIG, output).returncode, 0)
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
                    result = run(*flags, _CONFIG, output)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn("symlink", result.stderr)
                    self.assertEqual(tree(base), before)
                    self.assertTrue(link.is_symlink())
                self.assertFalse((base / "missing").exists())

    def test_missing_dropped_and_misnamed_roles_preserve_outputs(self):
        self.generate()
        before = tree(self.out)
        for kind in ("missing", "dropped", "misnamed"):
            with self.subTest(kind=kind):
                directory = self.tmp / kind
                config = config_copy(directory, (lambda data: data["roles"].pop("reviewer-b")) if kind == "dropped" else None)
                role = directory / "roles/reviewer-b.md"
                if kind == "missing":
                    role.unlink()
                elif kind == "misnamed":
                    role.write_text(role.read_text().replace("name: reviewer-b", "name: other"))
                for flags in ((), ("--check",)):
                    result = run(*flags, config, self.out)
                    self.assertEqual(result.returncode, 4, result.stdout)
                    self.assertIn("reviewer-b", result.stderr)
                    self.assertEqual(tree(self.out), before)

    def test_incomplete_or_widened_role_is_refused(self):
        edits = {
            "description": ("description: ", "summary: "),
            "access": ("access: read-search", "access: read-write"),
            "implement": ("access: read-search", "access: implement"),
            "access line": (ACCESS, "Read anything."),
        }
        for label, (old, new) in edits.items():
            with self.subTest(label):
                directory = self.tmp / f"roles-{label}"
                config = config_copy(directory)
                role = directory / "roles/reviewer-b.md"
                role.write_text(role.read_text().replace(old, new, 1))
                output = self.tmp / f"out-{label}"
                result = run(config, output)
                self.assertEqual(result.returncode, 4, result.stdout)
                self.assertIn("reviewer-b.md", result.stderr)
                self.assertFalse(output.exists())


class Assignments(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.out = self.tmp / "out"
        self.configs = 0

    def config(self, edit=None):
        self.configs += 1
        return config_copy(self.tmp / f"config-{self.configs}", edit)

    def generate(self, config=_CONFIG):
        result = run(config, self.out)
        self.assertIn(result.returncode, (0, 3), result.stderr)
        return result.stdout.splitlines()

    def head(self, relative):
        return frontmatter((self.out / relative).read_text()).splitlines()

    def test_inherit_is_explicit_and_translated_per_client(self):
        report = self.generate()
        self.assertIn("model: inherit", self.head("claude/reviewer-a.md"))
        self.assertFalse(any(line.startswith("effort:") for line in self.head("claude/reviewer-a.md")))
        self.assertFalse(any(line.startswith(("model:", "reasoningEffort:")) for line in self.head("opencode/reviewer-a.md")))
        self.assertIn("assignment: claude reviewer-a model=inherit (client default) effort=inherit (client default)", report)

    def test_role_overrides_win_over_client_defaults_per_client(self):
        def edit(data):
            data["clients"] = {"claude": {"model": "opus", "effort": "medium"}, "opencode": {"model": "openai/gpt-5.5", "effort": "low"}}
            data["roles"]["reviewer-b"]["claude"] = {"model": "sonnet"}
            data["roles"]["executor"]["opencode"] = {"effort": "high"}

        config = self.config(edit)
        report = self.generate(config)
        self.assertEqual([line for line in self.head("claude/reviewer-b.md") if line.startswith(("model:", "effort:"))], ["model: sonnet", "effort: medium"])
        self.assertEqual([line for line in self.head("claude/reviewer-a.md") if line.startswith(("model:", "effort:"))], ["model: opus", "effort: medium"])
        self.assertEqual([line for line in self.head("opencode/executor.md") if line.startswith(("model:", "reasoningEffort:"))], ["model: openai/gpt-5.5", "reasoningEffort: high"])
        self.assertEqual([line for line in self.head("opencode/reviewer-b.md") if line.startswith(("model:", "reasoningEffort:"))], ["model: openai/gpt-5.5", "reasoningEffort: low"])
        self.assertNotIn('  "*": deny', self.head("opencode/executor.md"))
        self.assertIn("assignment: claude reviewer-b model=sonnet (role) effort=medium (client default)", report)
        self.assertIn("assignment: opencode executor model=openai/gpt-5.5 (client default) effort=high (role)", report)
        self.assertEqual(run("--check", config, self.out).returncode, 0)

    def test_identical_reviewer_assignments_are_valid(self):
        def edit(data):
            for name in ("reviewer-a", "reviewer-b"):
                data["roles"][name]["claude"] = {"model": "opus", "effort": "high"}

        self.generate(self.config(edit))
        settings = [[line for line in self.head(f"claude/{name}.md") if line.startswith(("model:", "effort:"))] for name in ("reviewer-a", "reviewer-b")]
        self.assertEqual(settings, [["model: opus", "effort: high"]] * 2)

    def test_invalid_assignments_are_reported_before_writing(self):
        cases = {
            "gpt-5": lambda data: data["roles"]["reviewer-a"].update(claude={"model": "gpt-5"}),
            "extreme": lambda data: data["clients"]["claude"].update(effort="extreme"),
            "gpt-5.5": lambda data: data["clients"]["opencode"].update(model="gpt-5.5"),
            "openai/": lambda data: data["clients"]["opencode"].update(effort="high"),
            "anthropic/claude-opus-5": lambda data: data["clients"].update(opencode={"model": "anthropic/claude-opus-5", "effort": "high"}),
            "codex": lambda data: data["roles"]["reviewer-a"].update(codex={"model": "gpt-5"}),
            "temperature": lambda data: data["roles"]["reviewer-a"].update(claude={"temperature": 0}),
            "effort": lambda data: data["clients"]["claude"].pop("effort"),
            "opencode": lambda data: data["clients"].pop("opencode"),
            "review-refuter": lambda data: data["roles"]["review-refuter"].update(claude={"model": "gpt-5"}),
            "../x": lambda data: data["roles"].update({"../x": {}}),
            "roles.reviewer-a.definition": lambda data: data["roles"]["reviewer-a"].update(definition=5),
            "roles.executor.definition": lambda data: data["roles"]["executor"].update(definition=None),
        }
        self.generate()
        before = tree(self.out)
        for expected, edit in cases.items():
            with self.subTest(expected):
                config = self.config(edit)
                for flags in ((), ("--check",)):
                    result = run(*flags, config, self.out)
                    self.assertEqual(result.returncode, 4, result.stdout)
                    self.assertIn(expected, result.stderr.replace(str(config), ""))
                    self.assertEqual(tree(self.out), before)

    def test_duplicate_keys_are_refused(self):
        config = self.config()
        config.write_text(config.read_text().replace('"roles": {', '"roles": {"reviewer-a": {}, ', 1))
        result = run(config, self.out)
        self.assertEqual(result.returncode, 4, result.stdout)
        self.assertIn("duplicate", result.stderr)
        self.assertFalse(self.out.exists())

    def test_assignment_change_reaches_generated_output(self):
        config = self.config()
        self.generate(config)
        data = json.loads(config.read_text())
        data["roles"]["reviewer-a"]["claude"] = {"model": "sonnet"}
        config.write_text(json.dumps(data))
        result = run("--check", config, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn("changed: claude/reviewer-a.md", result.stdout)
        self.assertEqual(run(config, self.out).returncode, 0)
        self.assertIn("model: sonnet", self.head("claude/reviewer-a.md"))
        self.assertEqual(run("--check", config, self.out).returncode, 0)

    def test_assigned_role_without_definition_generates_nothing(self):
        report = self.generate()
        self.assertFalse(any("review-refuter" in relative for relative in tree(self.out)))
        self.assertTrue(any(line.startswith("pending: review-refuter") for line in report), report)
        self.assertIn("assignment: claude review-refuter model=inherit (client default) effort=inherit (client default)", report)

    def test_model_availability_is_reported_unverified(self):
        self.assertFalse(any("to this account" in line for line in self.generate()))
        report = self.generate(self.config(lambda data: data["roles"]["reviewer-b"].update(claude={"model": "sonnet", "effort": "max"})))
        self.assertIn("unverified: claude reviewer-b model sonnet is available to this account", report)
        self.assertIn("unverified: claude reviewer-b effort max is supported by its model", report)

    def test_generated_frontmatter_carries_only_agent_settings(self):
        def edit(data):
            data["clients"] = {"claude": {"model": "claude-opus-5", "effort": "high"}, "opencode": {"model": "openai/gpt-5.5", "effort": "high"}}

        self.generate(self.config(edit))
        allowed = {"claude": {"name", "description", "tools", "disallowedTools", "model", "effort"}, "opencode": {"description", "mode", "permission", "model", "reasoningEffort"}}
        for relative in tree(self.out):
            client = relative.split("/")[0]
            keys = {line.split(":")[0] for line in self.head(relative) if line and not line.startswith(" ")}
            self.assertLessEqual(keys, allowed[client], relative)

    def test_check_detects_widening_beside_assignments(self):
        config = self.config(lambda data: data["clients"].update(opencode={"model": "openai/gpt-5.5", "effort": "high"}))
        self.generate(config)
        target = self.out / "opencode/reviewer-a.md"
        target.write_text(target.read_text().replace('  "*": deny', '  "*": allow'))
        result = run("--check", config, self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn("widened: opencode/reviewer-a.md", result.stdout)


class InstallerOwnership(unittest.TestCase):
    def test_install_and_uninstall_touch_only_this_checkouts_links(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        harness, home = checkout(tmp), tmp / "home"
        out = harness / ".generated/agents"
        roots = {"claude": home / ".claude/agents", "opencode": home / ".config/opencode/agents"}
        roots["claude"].mkdir(parents=True)
        private = roots["claude"] / "mine.md"
        private.write_text("mine\n")
        foreign = roots["claude"] / "foreign.md"
        foreign.symlink_to("/elsewhere/other-checkout/.generated/agents/claude/foreign.md")
        retired = roots["claude"] / "retired.md"
        retired.symlink_to(out / "claude/retired.md")
        # Only install.sh's agent functions run here, so these prove the agent install and removal path leaves private settings and credentials alone; settings reconciliation is not exercised.
        configs = {home / ".claude/settings.json": '{"model": "opus", "effortLevel": "medium"}\n', home / ".config/opencode/opencode.json": '{"agent": {"mine": {"model": "openai/gpt-5.5"}}}\n', home / ".local/share/opencode/auth.json": '{"openai": "private-secret"}\n', home / ".claude/.credentials.json": '{"token": "private-secret"}\n'}
        for path, text in configs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

        result = installer_agents(harness, home, uninstall=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        for relative in OUTPUTS:
            client, name = relative.split("/")
            self.assertEqual(os.readlink(roots[client] / name), str(out / relative))
        self.assertFalse(retired.is_symlink())
        self.assertEqual(private.read_text(), "mine\n")
        self.assertTrue(foreign.is_symlink())
        self.assertEqual({path: path.read_text() for path in configs}, configs)
        generated = [path for path in out.rglob("*") if path.is_file()]
        self.assertEqual([path for path in generated if re.search(r"auth|credential", path.name) or "private-secret" in path.read_text()], [])

        result = installer_agents(harness, home, uninstall=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for root in roots.values():
            self.assertEqual({entry.name for entry in root.iterdir()} - {"mine.md", "foreign.md"}, set())
        self.assertFalse(out.exists())
        self.assertEqual(private.read_text(), "mine\n")
        self.assertTrue(foreign.is_symlink())
        self.assertEqual({path: path.read_text() for path in configs}, configs)


    def test_install_refuses_unowned_collisions_before_linking(self):
        for kind in ("file", "foreign-link", "root-link"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                tmp = Path(directory).resolve()
                harness, home = checkout(tmp), tmp / "home"
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
        harness, home = checkout(tmp), tmp / "home"
        self.assertEqual(installer_agents(harness, home, uninstall=False).returncode, 0)
        claude, elsewhere = home / ".claude/agents", tmp / "elsewhere"
        claude.rename(elsewhere)
        claude.symlink_to(elsewhere)

        result = installer_agents(harness, home, uninstall=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Role agent link survived the uninstall", result.stderr)
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
        unreadable = "When you cannot read the whole diff file, return exactly `unreadable: <path>` and nothing else, so the parent can supply the same diff inline. Never review part of a diff."
        loaded = "Begin with one line naming every standards file you actually opened with a tool during this review, as `loaded: <absolute path>, <absolute path>`, or `loaded: none`. Name a standard whose full text the parent pasted into your prompt as `inline:<absolute path>`. A path you were given but did not open, or a standard you recall without opening, does not belong on it."
        defer = "Triage every finding by `adversarial-review`'s canonical triage block: only `bug:` and `risk:` block, a `nit:` is fixed only when the fix is smaller than the argument and is otherwise dropped, a `q:` is answered and blocks only once evidence reclassifies it, and a second adversarial round runs only after a fixed blocking finding, over the repair delta alone."
        pins = {
            _POLICY: [
                "Use ephemeral specialist roles. Do not create persistent client-specific personas when a command, a skill, or an isolated review context is enough. Role definitions generated from one canonical source, such as the reviewer agents, are shared instructions and client capability configuration, not personas.",
                "When a workflow chooses to delegate implementation, launch the named `executor` agent, whose model and effort come from the harness's central role assignments. Delegation stays optional and changes nothing else: the delegating workflow keeps the approved scope, the commits, the review passes, the conformance check, and every gate. When the named agent is unavailable, say so and do the work inline rather than hand it to an agent without that assignment.",
                "Launch a named role agent without a model or effort override, so it runs on its central assignment.",
            ],
            _SKILL: [
                "Launch each reviewer as its named agent, in parallel, each with a fresh context: `reviewer-a` and `reviewer-b` in Claude Code and OpenCode. The installer generates them from `roles/reviewer-a.md` and `roles/reviewer-b.md` beside this skill, which own each reviewer's standing instructions, lenses, and output format.",
                "When a named agent is unavailable, say so, launch a general agent with the matching role file's full text as its instructions, and report that this fallback enforces only the general agent's own permissions rather than the named agent's read-search restrictions. Never skip or silently omit a review because a named agent is missing.",
                "Give Reviewer A the requirements, the diff snapshot path, and the exact absolute path of the project's own instruction file as its standards, never the implementation rationale. Nothing else.",
                "Give Reviewer B only the diff snapshot path and the exact absolute paths of its review standards: the loaded `ponytail` body and the project's own instruction file. No requirements, no rationale, no ticket.",
                "Standards are paths, never requirements or rationale, so supplying them leaves each reviewer's information boundary where it was. Count a standards file as read only when the reviewer's `loaded:` line names it: supplying a path, or a reviewer recalling what a standard says, is not evidence that it was read.",
                "The project's own instruction file is `AGENTS.md` at the repository root, or `CLAUDE.md` there when no `AGENTS.md` exists, and is left out when neither does. Where the client is known to refuse a standards path, such as OpenCode for a file outside the project, paste that file's text into the first launch instead of its path. When a supplied standards file is missing from a reviewer's `loaded:` line, relaunch that reviewer once with that file's text pasted in; the relaunch replaces that reviewer's output for the same round and never counts toward the cap. A reviewer names a pasted standard as `inline:<absolute path>`. If a standard is still unread, disclose it under the pull request's `## Checks`, or in the requirements ledger under `/proto`.",
                "Snapshot the complete diff once per round into a readable temporary file outside the worktree, and give each reviewer that path. A reviewer that answers `unreadable: <path>` gets the same snapshot inline instead. Never truncate the diff: when neither the file nor inline text can carry the complete snapshot, stop and escalate per the escalation contract.",
            ],
            _ROLES / "reviewer-a.md": [unreadable, ACCESS, loaded],
            _ROLES / "reviewer-b.md": [unreadable, ACCESS, loaded],
            _HARNESS / "commands/ship.md": [defer],
            _HARNESS / "commands/feedback.md": [defer],
            _HARNESS / "commands/address-review.md": [defer],
            _HARNESS / "commands/proto.md": [
                "Triage that pass by `adversarial-review`'s canonical triage block within this workflow's single-pass limit: fix, reject with the reason written into the requirements ledger, or escalate each blocking finding before presenting the slice, apply the nit and question rules unchanged, and never start a second round here.",
            ],
        }
        for path, expected in pins.items():
            present = [line.strip() for line in lines(path)] if path.parent.name == "commands" else lines(path)
            for line in expected:
                with self.subTest(path=path.name, line=line[:60]):
                    self.assertIn(line, present)


if __name__ == "__main__":
    unittest.main()
