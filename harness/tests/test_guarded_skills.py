"""Checks that commands read guarded local skills from their installed path.

Claude Code refuses every model-initiated load of a skill whose frontmatter sets `disable-model-invocation: true`, so a command that tells the model to load one by name cannot be followed there. The guarded set comes from skill frontmatter and is pinned, so a dropped guard fails instead of silently shrinking the set. The path the policy names is checked by running the installer's own link line in a temporary HOME.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_COMMANDS = _HARNESS / "commands"
_POLICY = _HARNESS / "POLICY.md"
_INSTALL = _HARNESS / "install.sh"
_LOCK = _HARNESS.parent / "skills-lock.json"

EXPECTED = {"adversarial-review", "evidence", "grilling", "local-tracker", "setup-harness", "workflow-checkpoint"}
# "read and run" is the fixed form, and commands tell the user, not the model, to invoke setup-harness.
VERB = re.compile(r"\b(?:(?<!read and )run|load|(?<!user to )invoke|use)(?:s|ed|ing)?\b(?: and follow)?(?: the)? ((?:`[a-z-]+`(?:,? (?:and|or) |, )?)+)", re.I)


def frontmatter(path):
    match = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    return match.group(1) if match else ""


def guarded_names():
    """Every locally authored skill whose frontmatter disables model invocation; locked bodies keep their upstream wording."""
    locked = set(json.loads(_LOCK.read_text())["skills"])
    return {path.parent.name for path in _HARNESS.glob("skills/*/SKILL.md") if "disable-model-invocation: true" in frontmatter(path)} - locked


def guarded():
    """Guarded skills a command names."""
    commands = "\n".join(path.read_text() for path in _COMMANDS.glob("*.md"))
    return {name for name in guarded_names() if f"`{name}`" in commands}


def violations(text, names):
    """Return lines that load a guarded skill by name, or list one under Skills this loads without saying it is read from its path."""
    found, listing = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            listing = line == "## Skills this loads"
        if any(set(re.findall(r"`([a-z-]+)`", match.group(1))) & names for match in VERB.finditer(line)):
            found.append(line)
        elif listing and any(line.startswith(f"- `{name}`") and "read from its path" not in line for name in names):
            found.append(line)
    return found


class GuardedSkillsTest(unittest.TestCase):
    def test_guarded_set_is_derived_from_frontmatter(self):
        self.assertEqual(guarded(), EXPECTED)

    def test_every_guarded_skill_keeps_both_guards(self):
        for name in sorted(EXPECTED):
            with self.subTest(name):
                head = frontmatter(_HARNESS / "skills" / name / "SKILL.md")
                self.assertIn("disable-model-invocation: true", head)
                self.assertIn('opencode/autoinvoke: "false"', head)

    def test_no_command_or_policy_line_loads_a_guarded_skill(self):
        names = guarded_names()
        for path in [*sorted(_COMMANDS.glob("*.md")), _POLICY]:
            with self.subTest(path.name):
                self.assertEqual(violations(path.read_text(), names), [])

    def test_reverting_a_command_line_to_load_wording_is_caught(self):
        names = guarded_names()
        ship = (_COMMANDS / "ship.md").read_text()
        for old, new in (("Read `workflow-checkpoint`", "Load `workflow-checkpoint`"), ("Read and run `adversarial-review` first", "Run `adversarial-review` first")):
            with self.subTest(new):
                self.assertIn(old, ship)
                self.assertTrue(violations(ship.replace(old, new, 1), names))
        for text in ("Load and follow `evidence`: is it real.", "load the `local-tracker` skill first", "load `ponytail` and `grilling`", "use `ponytail`, `tdd`, and `evidence`", "read and load `evidence`", "invoke the `setup-harness` skill", "## Skills this loads\n\n- `adversarial-review`"):
            with self.subTest(text):
                self.assertTrue(violations(text, names))
        self.assertEqual(violations("Read and run `adversarial-review` first.\ntell the user to invoke the `setup-harness` skill\n## Skills this loads\n\n- `grilling`, read from its path\n- `ponytail`", names), [])

    def test_policy_path_is_the_installer_link(self):
        roots = re.findall(r"`~/([^`]+)/<name>/SKILL\.md`", _POLICY.read_text())
        self.assertEqual(len(roots), 1, roots)
        text = _INSTALL.read_text()
        link = f'link_managed "$source" "$HOME/{roots[0]}/$skill"'
        self.assertIn(link, re.search(r"^install_links\(\) \{\n.*?^\}\n", text, re.M | re.S).group(0))
        self.assertIn(f'[[ -L "$HOME/{roots[0]}/$name" ]]', text)
        helpers = [re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.M | re.S).group(0) for name in ("backup_existing", "link_managed", "ensure_managed_dir")]
        with tempfile.TemporaryDirectory() as home:
            script = "\n".join(
                ["set -euo pipefail", 'log() { :; }; die() { echo "$*" >&2; exit 1; }', *helpers, f'ensure_managed_dir "$HOME/{roots[0]}"']
                + [f'skill={name}; source="$HARNESS_DIR/skills/$skill"; {link}' for name in sorted(EXPECTED)]
            )
            env = {**os.environ, "HOME": home, "HARNESS_DIR": str(_HARNESS), "NO_BACKUP": "true"}
            result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in sorted(EXPECTED):
                self.assertTrue((Path(home) / roots[0] / name / "SKILL.md").is_file(), name)


if __name__ == "__main__":
    unittest.main()
