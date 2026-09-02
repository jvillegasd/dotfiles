#!/usr/bin/env python3

"""The reviewed third-party skill supply chain: the lock, the bookkeeping
links, and the helper that adds, updates, removes, and checks a locked body."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from fixtures import INSTALLERS, LOCAL_SKILLS, LOCKED_SKILLS, ROOT, SKILLS


# Mirrors computeSkillFolderHash in the skills CLI, which is what writes
# computedHash into skills-lock.json. The algorithm is sha256 over each file's
# relative path then its bytes, and the only subtle part is the ordering: the
# CLI sorts with JavaScript's localeCompare, and ICU collation is not Python's
# casefold order. The two agree until a skill ships sibling filenames that
# differ only by punctuation, as test_core.py does against
# test_core_data_quality.py: ICU treats the "." and the "_" as equivalent at
# the primary level and orders that pair the other way round, after which
# every later byte lands in a different place. No locked body ships such a
# pair today, which is exactly why this was wrong for so long without
# failing. Reimplementing ICU here would be the same bug with more
# steps, so the ordering comes from the same engine the CLI used, including
# its bare localeCompare: pinning a collator would agree with the lock only on
# machines whose default locale happened to match the one that wrote it, which
# trades a rare mismatch for a systematic one. node is already required to
# install a locked skill at all. The .git and node_modules pruning and the
# separator normalization are the CLI's, not ours; dropping either makes this
# disagree with the lock on exactly the bodies that need it most.
_FOLDER_HASH_JS = """
const fs = require("fs"), path = require("path"), { createHash } = require("crypto");
// A node built --without-intl degrades localeCompare to code-unit order, which
// disagrees with the lock. Fail with that sentence instead of a hash mismatch.
if (!process.versions.icu) throw new Error("node without ICU cannot reproduce the lock's collation");
const root = process.argv[1], files = [];
(function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === ".git" || entry.name === "node_modules") continue;
      walk(full);
    } else if (entry.isFile()) {
      files.push(path.relative(root, full).split("\\\\").join("/"));
    }
  }
})(root);
files.sort((a, b) => a.localeCompare(b));
const digest = createHash("sha256");
for (const file of files) {
  digest.update(file);
  digest.update(fs.readFileSync(path.join(root, ...file.split("/"))));
}
process.stdout.write(digest.digest("hex"));
"""


def folder_hash(path: Path) -> str:
    try:
        result = subprocess.run(
            ["node", "-e", _FOLDER_HASH_JS, str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as error:  # pragma: no cover - environment guard
        raise AssertionError(
            "node is required to verify locked-skill hashes, because the lock's "
            "computedHash is written by the skills CLI under JavaScript collation."
        ) from error
    except subprocess.CalledProcessError as error:
        # Without this the drift test reports a node crash as a hash mismatch.
        raise AssertionError(f"hashing {path} failed: {error.stderr.strip()}") from error
    return result.stdout.strip()


class LockedSkillsTests(unittest.TestCase):
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

        for name, entry in lock.items():
            body = SKILLS / name
            self.assertTrue(body.is_dir(), name)
            self.assertEqual(folder_hash(body), entry["computedHash"], name)

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
            # `check` discovers this directory, and discovery exits 5 when it
            # collects nothing at all, so the stub carries a real test rather
            # than a bare print.
            passing_stub = (
                "import unittest\n"
                "print('checked')\n"
                "class Stub(unittest.TestCase):\n"
                "    def test_stub(self) -> None:\n"
                "        pass\n"
            )
            (tests / "test_stub.py").write_text(passing_stub)
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

            stale_link = claude / "stale"
            stale_link.symlink_to("../../.agents/skills/stale")
            self.assertNotEqual(run("add", "owner/repo", "stale", check=False).returncode, 0)
            self.assertTrue(stale_link.is_symlink())
            self.assertFalse((skills / "stale").exists())
            self.assertNotIn("stale", locked())

            run("update")
            self.assertEqual(
                calls.read_text().splitlines(),
                [
                    "skills@1 add owner/repo --skill demo --agent universal -y",
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
            (tests / "test_stub.py").write_text("raise SystemExit(7)\n")
            self.assertNotEqual(run("check", check=False).returncode, 0)
            (tests / "test_stub.py").write_text(passing_stub)

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

            self.assertNotEqual(run("remove", "../outside", check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
