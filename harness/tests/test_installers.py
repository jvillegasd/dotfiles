#!/usr/bin/env python3

"""The installers: what they link into a HOME, what they archive, what they
delete, and whether they parse under the bash macOS actually ships.

The two tests that drive a real `install.sh --links-only` run dominate the
suite's runtime, which is why they sit in a file of their own.
"""

from __future__ import annotations

import json
import os
import re
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


def harness_packages() -> tuple[list[str], str]:
    """The Homebrew formulae and cask harness/install.sh installs, read from it.

    Parsed rather than copied for the same reason as `codex_status_items`: a
    literal would keep passing under a renamed formula, and the whole point of
    the assertion below is that two declarations of one tool set have to agree.
    """
    installer = (ROOT / "harness" / "install.sh").read_text()
    formulae = re.search(r"(?m)^\s*for formula in (.+?); do", installer)
    cask = re.search(r"(?m)^\s*brew_latest_cask (\S+)", installer)
    assert formulae is not None, "install.sh no longer loops over a formula list"
    assert cask is not None, "install.sh no longer installs a cask"
    return formulae.group(1).split(), cask.group(1)


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

    def test_brewfile_carries_every_tool_the_harness_installs(self) -> None:
        # The two lists are duplicated on purpose: Brewfile is the machine's
        # manifest, and the harness installer restates its own tools so it
        # stays runnable alone. Nothing made them agree, and Brewfile is
        # regenerated wholesale by `brew bundle dump`, so a formula uninstalled
        # from the machine silently disappears from the manifest while the
        # harness keeps installing it.
        brewfile = (ROOT / "Brewfile").read_text()
        formulae, cask = harness_packages()
        self.assertIn("worktrunk", formulae)
        for formula in formulae:
            self.assertIn(f'brew "{formula}"', brewfile, formula)
        # Codex is the one client Homebrew carries as a cask, and only on macOS.
        self.assertIn(f'cask "{cask}"', brewfile, cask)

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
            # settings.json is written by Orca and by `engram setup` too, so
            # the reconciler owns the tracked keys and has to leave the rest
            # alone. The stale deny is the case that matters most: a tracked
            # list replaces the live one, so removing an entry upstream
            # removes it from the machine.
            settings = home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(
                json.dumps(
                    {
                        "permissions": {
                            "allow": ["mcp__engram__mem_save"],
                            "deny": ["Bash(retired:*)"],
                        },
                        "hooks": {"Stop": []},
                        "enabledPlugins": {"engram@engram": True},
                    }
                )
            )
            # config.toml carries trust decisions and hook hashes, so the
            # status line reconciler has to leave everything else alone.
            codex_config = home / ".codex" / "config.toml"
            codex_config.write_text(
                'unrelated = "keep-me"\n\n'
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
            # A symlinked command root. Linking into it would put managed
            # commands in a directory the installer never sweeps, and the
            # orphan sweep would then archive that directory's own entries.
            shared_prompts = home / "shared-prompts"
            shared_prompts.mkdir()
            (shared_prompts / "theirs.md").write_text("theirs\n")
            (home / ".codex").mkdir(exist_ok=True)
            (home / ".codex" / "prompts").symlink_to(shared_prompts)

            environment = os.environ | {
                "HOME": str(home),
                "XDG_CACHE_HOME": str(home / ".cache"),
                "XDG_CONFIG_HOME": str(home / ".config"),
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
            # A symlinked command root becomes a real directory the installer
            # owns, and the directory it pointed at keeps its own file.
            codex_prompts = home / ".codex" / "prompts"
            self.assertTrue(codex_prompts.is_dir())
            self.assertFalse(codex_prompts.is_symlink())
            self.assertTrue((shared_prompts / "theirs.md").is_file())
            self.assertFalse((codex_prompts / "theirs.md").exists())

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
            claude_settings = json.loads(settings.read_text())
            tracked = json.loads(
                (ROOT / "harness" / "clients" / "claude.json").read_text()
            )
            self.assertEqual(
                claude_settings["statusLine"],
                {"type": "command", "command": 'bash "$HOME/.claude/statusline.sh"'},
            )
            self.assertEqual(
                claude_settings["permissions"]["deny"],
                tracked["permissions"]["deny"],
            )
            self.assertNotIn("Bash(retired:*)", claude_settings["permissions"]["deny"])
            # Machine state survives: the engram allowlist beside the deny list
            # this harness owns, and the keys other tools write beside it. The
            # seeded entry is one `engram setup` also writes, so the assertion
            # is that the class was merged rather than replaced.
            self.assertIn("mcp__engram__mem_save", claude_settings["permissions"]["allow"])
            self.assertEqual(claude_settings["hooks"], {"Stop": []})
            self.assertEqual(
                claude_settings["enabledPlugins"], {"engram@engram": True}
            )
            for key, value in tracked.items():
                if key != "permissions":
                    self.assertEqual(claude_settings[key], value, key)
            for line in (
                (ROOT / "harness" / "clients" / "codex.toml").read_text().splitlines()
            ):
                if line and not line.startswith("#"):
                    self.assertIn(f"\n{line}\n", f"\n{codex_config.read_text()}", line)
            codex = codex_config.read_text()
            items = ", ".join(f'"{item}"' for item in codex_status_items())
            self.assertIn(f"status_line = [{items}]", codex)
            self.assertIn("status_line_use_colors = true\n", codex)
            self.assertNotIn('"stale"', codex)
            self.assertNotIn("status_line_use_colors = false", codex)
            # Unrelated keys, including a same-named key in a subtable, survive.
            self.assertIn('unrelated = "keep-me"', codex)
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
            self.assertTrue((backups[0] / ".codex" / "prompts.previous-link").is_symlink())
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
                "XDG_CONFIG_HOME": str(home / ".config"),
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

    def test_opencode_paths_follow_xdg_config_home(self) -> None:
        # lib/common.sh honors XDG_CONFIG_HOME for every config the root
        # scripts place, and OpenCode honors it too. An installer that
        # hardcoded ~/.config wrote a third of the harness nowhere OpenCode
        # reads, then asserted against the same wrong path and passed.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            config = home / "xdg"
            # Normalized but never created: OpenCode reads ~/.agents/skills, so
            # a symlinked skills root is moved aside and nothing replaces it.
            theirs = home / "their-skills"
            theirs.mkdir()
            (theirs / "keep").write_text("theirs")
            (config / "opencode").mkdir(parents=True)
            (config / "opencode" / "skills").symlink_to(theirs)

            environment = os.environ | {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(config),
                "XDG_CACHE_HOME": str(home / ".cache"),
            }
            subprocess.run(
                ["bash", ROOT / "harness" / "install.sh", "--links-only"],
                env=environment,
                check=True,
                capture_output=True,
            )

            self.assertEqual(
                os.path.realpath(config / "opencode" / "AGENTS.md"),
                str(ROOT / "harness" / "POLICY.md"),
            )
            for name in COMMAND_NAMES:
                self.assertEqual(
                    os.path.realpath(config / "opencode" / "command" / f"{name}.md"),
                    str(COMMANDS / f"{name}.md"),
                    name,
                )
            self.assertFalse((home / ".config" / "opencode").exists())
            self.assertFalse((config / "opencode" / "skills").exists())
            self.assertTrue((theirs / "keep").is_file())
            # Only OpenCode follows XDG. Claude and Codex read fixed paths, so
            # a change that moved all six roots would otherwise pass this test.
            self.assertTrue((home / ".claude" / "commands").is_dir())
            self.assertTrue((home / ".codex" / "prompts").is_dir())
            self.assertTrue((home / ".agents" / "skills").is_dir())

    def test_unusable_claude_settings_fails_with_the_path(self) -> None:
        # json.load raising inside a heredoc ended the run on a traceback, from
        # a function whose whole job is to leave a hand-edited settings.json
        # alone. The run still has to stop; it has to say which file.
        #
        # Both shapes are here because they exercise different halves: the
        # first does not parse, the second parses into something that is not a
        # settings object. The second is the one the old code let through, by
        # reading every crash as "already correct, nothing to do".
        for content in ("{ not json\n", "[]\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary_home:
                home = Path(temporary_home)
                settings = home / ".claude" / "settings.json"
                settings.parent.mkdir(parents=True)
                settings.write_text(content)

                result = subprocess.run(
                    ["bash", ROOT / "harness" / "install.sh", "--links-only"],
                    env=os.environ | {
                        "HOME": str(home),
                        "XDG_CACHE_HOME": str(home / ".cache"),
                        "XDG_CONFIG_HOME": str(home / ".config"),
                    },
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(settings), result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(settings.read_text(), content)

    def test_no_backup_is_documented_in_every_installer(self) -> None:
        # The platform entry points offer the flag through their shared
        # library, so they are read together; the harness installer parses and
        # documents its own copy.
        for group in (ROOT_INSTALLERS, (ROOT / "harness" / "install.sh",)):
            text = "\n".join(path.read_text() for path in group)
            self.assertIn("--no-backup", text, group)
            # The flag is destructive, so the usage text has to say so.
            self.assertIn("Destructive and unrecoverable", text, group)


class EngramRemovalTests(unittest.TestCase):
    """The engram config surgery, exercised directly.

    Every case here is a defect that shipped in review: the remover matched
    the word "engram" wherever it appeared, so it took a user's Codex trust
    decision, a user's permission rule, and a user's plugin with it. These
    drive remove_engram_config on its own rather than through a full install,
    because the input that breaks it is somebody else's config, not ours.
    """

    def remove(self, home: Path) -> subprocess.CompletedProcess:
        installer = (ROOT / "harness" / "install.sh").read_text()
        body = re.search(r"(?ms)^remove_engram_config\(\) \{.*?^\}", installer)
        assert body is not None, "install.sh no longer defines remove_engram_config"
        script = f'set -euo pipefail\nHOME="{home}"\nCONFIG_HOME="{home}/.config"\n{body.group(0)}\nremove_engram_config\n'
        return subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, check=True
        )

    def test_a_codex_table_merely_named_after_engram_is_kept(self) -> None:
        # The one that mattered: a substring test on the table header deleted
        # `[projects."…/engram-fork"]` and the trust decision inside it.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            (home / ".codex").mkdir(parents=True)
            config = home / ".codex" / "config.toml"
            config.write_text(
                '[projects."/Users/me/code/engram-fork"]\n'
                'trust_level = "trusted"\n'
                "\n"
                "[mcp_servers.engram]\n"
                'command = "/opt/homebrew/bin/engram"\n'
                "\n"
                '[projects."/Users/me/code/other"]\n'
                'trust_level = "trusted"\n'
            )

            self.remove(home)

            kept = config.read_text()
            self.assertIn('[projects."/Users/me/code/engram-fork"]', kept)
            self.assertIn('[projects."/Users/me/code/other"]', kept)
            self.assertEqual(kept.count("trust_level"), 2)
            self.assertNotIn("[mcp_servers.engram]", kept)

    def test_a_user_permission_rule_naming_engram_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            (home / ".claude").mkdir(parents=True)
            settings = home / ".claude" / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "permissions": {
                            "allow": [
                                "Bash(cd ~/src/engram && cargo test)",
                                "mcp__engram__mem_save",
                                "mcp__plugin_engram_engram__mem_search",
                            ]
                        },
                        "enabledPlugins": {"engram@engram": True, "engram-helper@x": True},
                    }
                )
            )

            self.remove(home)

            kept = json.loads(settings.read_text())
            self.assertEqual(
                kept["permissions"]["allow"], ["Bash(cd ~/src/engram && cargo test)"]
            )
            # A plugin whose name merely starts with the word is not engram's.
            self.assertEqual(kept["enabledPlugins"], {"engram-helper@x": True})

    def test_a_file_without_engram_entries_is_left_byte_for_byte(self) -> None:
        # The remover round-tripped JSON through its own formatter, so a
        # hand-formatted file was reindented and the run reported removing
        # entries that were never there.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            (home / ".config" / "opencode").mkdir(parents=True)
            (home / ".claude").mkdir(parents=True)
            opencode = home / ".config" / "opencode" / "opencode.json"
            original = '{\n    "mcp": {\n        "other": {"command": ["y"]}\n    }\n}\n'
            opencode.write_text(original)
            settings = home / ".claude" / "settings.json"
            settings.write_text('{\n\t"model": "opus"\n}\n')

            result = self.remove(home)

            self.assertEqual(opencode.read_text(), original)
            self.assertEqual(settings.read_text(), '{\n\t"model": "opus"\n}\n')
            self.assertNotIn("Removed the engram entries", result.stdout)

    def test_an_unparseable_tui_file_does_not_stop_the_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            (home / ".config" / "opencode").mkdir(parents=True)
            tui = home / ".config" / "opencode" / "tui.jsonc"
            tui.write_text('// a comment\n{"plugin": ["opencode-subagent-statusline"]}\n')

            self.remove(home)

            self.assertIn("comment", tui.read_text())


class UninstallTests(unittest.TestCase):
    """`--uninstall`: what it takes back, what it must not touch, and the
    argument handling around it.

    Each case seeds a HOME with state the uninstall has no claim on, installs
    with --links-only, then removes. Asserting only that the managed paths are
    gone would pass just as well for `rm -rf ~`, so every case checks the
    foreign state too.
    """

    def environment(self, home: Path) -> dict[str, str]:
        return os.environ | {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "PATH": f"{self.stubs(home)}:{os.environ['PATH']}",
        }

    def stubs(self, home: Path) -> Path:
        """Recording stubs for the three commands the uninstall shells out to.

        `brew` is the one that has to be stubbed rather than merely recorded:
        it is the only global this uninstall touches, and a real run would take
        the machine's own engram with it on every pass of the suite. `claude`
        and `codex` are stubbed alongside it because their plugin registries
        are slow to drive and prove nothing the config assertions do not.

        Each call is appended to calls.log, so a test can assert the installer
        asked for the right thing rather than that something happened.
        """
        binaries = home / ".stubs"
        if binaries.is_dir():
            return binaries
        binaries.mkdir(parents=True)
        for name in ("brew", "claude", "codex"):
            stub = binaries / name
            # `brew list --formula engram` exits 0 so the uninstall reaches the
            # `brew uninstall` it guards.
            stub.write_text(
                "#!/bin/sh\n"
                f'echo "{name} $*" >> "$HOME/.stubs/calls.log"\n'
                "exit 0\n"
            )
            stub.chmod(0o755)
        return binaries

    def calls(self, home: Path) -> str:
        log = home / ".stubs" / "calls.log"
        return log.read_text() if log.exists() else ""

    def run_installer(
        self, home: Path, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", ROOT / "harness" / "install.sh", *arguments],
            env=self.environment(home),
            check=check,
            capture_output=True,
            text=True,
        )

    def backups(self, home: Path) -> list[str]:
        """What the harness has archived, scoped to its own subtree.

        The parent holds other tools' archives, so walking it would make
        "the harness archived nothing" false for reasons that have nothing to
        do with the harness.
        """
        root = home / ".dotfiles-backups" / "harness"
        return sorted(str(path.relative_to(home)) for path in root.rglob("*")) if root.exists() else []

    def seed(self, home: Path) -> None:
        """A HOME carrying state from every source the uninstall must respect:
        a private skill, somebody else's command, a hand-written alias, the
        untracked permission class, machine state Orca and `engram setup`
        write, and an unrelated top-level Codex key.
        """
        private = home / ".agents" / "skills" / "private"
        private.mkdir(parents=True)
        (private / "SKILL.md").write_text("---\nname: private\ndescription: private\n---\n")
        prompts = home / ".codex" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "theirs.md").write_text("theirs\n")
        (home / ".zshrc").write_text("export PATH=/usr/bin\nalias sail='sh sail'\n")
        settings = home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(
            json.dumps(
                {
                    "permissions": {"ask": ["WebFetch"], "allow": ["Bash(ls:*)"]},
                    "hooks": {"Stop": []},
                    # A neighbour in each container the engram removal prunes.
                    # Without one, "pruned engram" and "emptied the file" are
                    # the same assertion.
                    "enabledPlugins": {"engram@engram": True, "other@x": True},
                    "extraKnownMarketplaces": {"engram": {}, "keep": {}},
                }
            )
        )
        (home / ".codex" / "config.toml").write_text(
            'unrelated = "keep-me"\n\n[tui]\ntheme = "keep-me-too"\n'
        )

    def assert_nothing_managed_survives(self, home: Path) -> None:
        harness = ROOT / "harness"
        roots = [
            home / ".agents" / "skills",
            home / ".claude" / "skills",
            home / ".config" / "opencode" / "skills",
            home / ".claude" / "commands",
            home / ".codex" / "prompts",
            home / ".config" / "opencode" / "command",
        ]
        for root in roots:
            if not root.is_dir():
                continue
            for entry in root.iterdir():
                self.assertFalse(
                    entry.is_symlink() and harness in entry.resolve().parents,
                    f"managed link survived: {entry}",
                )
        for path in (
            home / ".codex" / "AGENTS.md",
            home / ".claude" / "CLAUDE.md",
            home / ".config" / "opencode" / "AGENTS.md",
            home / ".claude" / "statusline.sh",
        ):
            self.assertFalse(path.is_symlink(), f"managed link survived: {path}")
        zshrc = (home / ".zshrc").read_text()
        self.assertNotIn("portable-harness aliases", zshrc)
        self.assertNotIn("alias cyolo=", zshrc)

    def assert_foreign_state_survives(self, home: Path) -> None:
        self.assertTrue((home / ".agents" / "skills" / "private" / "SKILL.md").is_file())
        self.assertTrue((home / ".codex" / "prompts" / "theirs.md").is_file())
        self.assertIn("alias sail=", (home / ".zshrc").read_text())
        settings = json.loads((home / ".claude" / "settings.json").read_text())
        # The untracked permission class and the machine state beside it. The
        # `ask` list is the case the merge exists for: `permissions` is owned a
        # class at a time, not whole.
        self.assertEqual(settings["permissions"]["ask"], ["WebFetch"])
        self.assertEqual(settings["hooks"], {"Stop": []})
        # The engram removal prunes by name, so a neighbour in the same
        # container survives while the engram entry beside it goes.
        self.assertEqual(settings["permissions"]["allow"], ["Bash(ls:*)"])
        self.assertEqual(settings["enabledPlugins"], {"other@x": True})
        self.assertEqual(settings["extraKnownMarketplaces"], {"keep": {}})
        config = (home / ".codex" / "config.toml").read_text()
        self.assertIn('unrelated = "keep-me"', config)
        self.assertIn('theme = "keep-me-too"', config)

    def test_uninstall_removes_the_harness_and_nothing_else(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            self.run_installer(home, "--links-only")

            # The install has to have written something, or the removal below
            # would pass against a HOME the harness never reached.
            self.assertTrue((home / ".claude" / "CLAUDE.md").is_symlink())
            self.assertIn("portable-harness aliases", (home / ".zshrc").read_text())
            installed = json.loads((home / ".claude" / "settings.json").read_text())
            self.assertIn("deny", installed["permissions"])

            # The install archives what it displaced, so the claim below is
            # that the uninstall added nothing to that, not that the machine
            # has no backups at all.
            before = self.backups(home)
            self.run_installer(home, "--uninstall")
            after = self.backups(home)

            self.assert_nothing_managed_survives(home)
            self.assert_foreign_state_survives(home)
            self.assertEqual(after, before, "the uninstall archived something")

    def test_uninstall_leaves_no_tracked_key_in_either_client(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            self.run_installer(home, "--links-only")
            self.run_installer(home, "--uninstall")

            tracked = json.loads((ROOT / "harness" / "clients" / "claude.json").read_text())
            settings = json.loads((home / ".claude" / "settings.json").read_text())
            for key, value in tracked.items():
                if key == "permissions":
                    self.assertFalse(set(settings.get(key, {})) & set(value), key)
                else:
                    self.assertNotIn(key, settings)

            config = (home / ".codex" / "config.toml").read_text()
            for line in (ROOT / "harness" / "clients" / "codex.toml").read_text().splitlines():
                key = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=", line)
                if key:
                    self.assertNotRegex(config, rf"(?m)^{key.group(1)}\s*=")
            # The status line half of the same file, whose items live in one
            # declaration the tests read rather than restate.
            for item in codex_status_items():
                self.assertNotIn(f'"{item}"', config)
            self.assertNotRegex(config, r"(?m)^\s*status_line\s*=")

    def test_uninstall_is_idempotent_and_needs_no_prior_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            # A HOME the harness never touched. Nothing to remove is a clean
            # exit, not a failure, or a partially installed machine could not
            # be cleaned up.
            self.run_installer(home, "--uninstall")

            self.seed(home)
            self.run_installer(home, "--links-only")
            self.run_installer(home, "--uninstall")
            first = (home / ".codex" / "config.toml").read_text()
            self.run_installer(home, "--uninstall")

            self.assert_nothing_managed_survives(home)
            self.assert_foreign_state_survives(home)
            # A second pass is a fixed point, which is what check_removed
            # asserts by re-running both Codex reconcilers for exit 3.
            self.assertEqual((home / ".codex" / "config.toml").read_text(), first)

    def test_install_after_uninstall_restores_the_machine(self) -> None:
        # The round trip is the real contract: an uninstall that could not be
        # undone would be a migration, not a mode of the installer.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            self.run_installer(home, "--links-only")
            installed = {
                "settings": (home / ".claude" / "settings.json").read_text(),
                "config": (home / ".codex" / "config.toml").read_text(),
                "zshrc": (home / ".zshrc").read_text(),
            }

            self.run_installer(home, "--uninstall")
            self.run_installer(home, "--links-only")

            # settings.json is compared by the keys the harness owns rather
            # than whole, for the reason config.toml is below and one more:
            # `engram setup` registers its plugin by shelling out to the
            # client's own CLI, which is stubbed here, so engram's half of the
            # file cannot come back in this environment. The real round trip
            # is exercised on a real machine.
            def owned(text: str) -> dict:
                settings = json.loads(text)
                keys = set(json.loads((ROOT / "harness" / "clients" / "claude.json").read_text()))
                kept = {key: settings[key] for key in keys & set(settings) if key != "permissions"}
                kept["deny"] = settings["permissions"]["deny"]
                kept["ask"] = settings["permissions"]["ask"]
                return kept

            self.assertEqual(
                owned((home / ".claude" / "settings.json").read_text()),
                owned(installed["settings"]),
            )
            self.assertEqual((home / ".zshrc").read_text(), installed["zshrc"])
            self.assertTrue((home / ".claude" / "CLAUDE.md").is_symlink())
            # config.toml is compared by the lines the harness owns rather than
            # whole: `engram setup` runs on every install and orders its own
            # tables differently once they already exist, so asserting the
            # whole file here would be asserting engram's idempotency instead
            # of this installer's.
            def owned(text: str) -> list[str]:
                keys = ("model", "model_reasoning_effort", "plan_mode_reasoning_effort",
                        "status_line", "status_line_use_colors")
                return [
                    line for line in text.splitlines()
                    if re.match(rf"\s*({'|'.join(keys)})\s*=", line)
                ]

            self.assertEqual(
                owned((home / ".codex" / "config.toml").read_text()),
                owned(installed["config"]),
            )

    def test_uninstall_ignores_the_redundant_no_backup(self) -> None:
        # --uninstall already deletes, so --no-backup beside it is redundant
        # rather than contradictory: accepted, and changing nothing. Asserted
        # by running both and comparing, because "it is implied" is exactly
        # the kind of claim that stops being true when the flag parsing moves.
        results = []
        for arguments in (("--uninstall",), ("--uninstall", "--no-backup")):
            with tempfile.TemporaryDirectory() as temporary_home:
                home = Path(temporary_home)
                self.seed(home)
                self.run_installer(home, "--links-only")
                before = self.backups(home)
                self.run_installer(home, *arguments)

                self.assertEqual(self.backups(home), before, arguments)
                self.assert_nothing_managed_survives(home)
                self.assert_foreign_state_survives(home)
                results.append(
                    (
                        (home / ".claude" / "settings.json").read_text(),
                        (home / ".zshrc").read_text(),
                    )
                )
        self.assertEqual(*results)

    def test_uninstall_refuses_the_contradictory_flag(self) -> None:
        # --links-only names a subset of the install to write and --uninstall
        # writes none of it, so letting one win silently would make the other
        # look like it did something.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            self.run_installer(home, "--links-only")
            result = self.run_installer(home, "--uninstall", "--links-only", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--uninstall", result.stderr)
            self.assertIn("--links-only", result.stderr)
            # It refused before removing anything.
            self.assertTrue((home / ".claude" / "CLAUDE.md").is_symlink())

    def test_argument_handling_writes_nothing(self) -> None:
        for arguments, expect_success in ((["--help"], True), (["-h"], True), (["--bogus"], False)):
            with self.subTest(arguments=arguments):
                with tempfile.TemporaryDirectory() as temporary_home:
                    home = Path(temporary_home)
                    result = self.run_installer(home, *arguments, check=False)
                    self.assertEqual(result.returncode == 0, expect_success)
                    if expect_success:
                        self.assertIn("--uninstall", result.stdout)
                        self.assertIn("--clear-backups", result.stdout)
                    else:
                        self.assertIn("--bogus", result.stderr)
                    # Neither branch reaches an install or a removal.
                    # .stubs is the harness of the test, not the installer's
                    # output, so it is the one permitted entry.
                    written = [path.name for path in home.iterdir() if path.name != ".stubs"]
                    self.assertEqual(written, [])

    def test_uninstall_removes_engram_from_every_client(self) -> None:
        # install_packages installs engram and install_engram registers it, so
        # the uninstall owes both halves. A surviving entry is worse than a
        # leftover link: every one names the absolute path of a binary that is
        # now gone, so the client fails rather than quietly doing less.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            self.run_installer(home, "--links-only")

            # The install has to have registered engram, or there is nothing
            # here to remove and the assertions below are vacuous.
            settings = home / ".claude" / "settings.json"
            self.assertIn("engram", settings.read_text())
            self.assertTrue((home / ".claude" / "mcp" / "engram.json").is_file())

            self.run_installer(home, "--uninstall")

            for path in (
                settings,
                home / ".config" / "opencode" / "opencode.json",
                home / ".codex" / "config.toml",
            ):
                if path.exists():
                    self.assertNotIn("engram", path.read_text().lower(), path)
            for path in (
                home / ".claude" / "mcp" / "engram.json",
                home / ".codex" / "engram-instructions.md",
                home / ".codex" / "engram-compact-prompt.md",
                home / ".config" / "opencode" / "plugins" / "engram.ts",
            ):
                self.assertFalse(path.exists(), path)
            # The third thing `engram setup opencode` writes, per engram's own
            # docs/AGENT-SETUP.md. It is not named after engram, so a search
            # for the word would have left it behind.
            tui = home / ".config" / "opencode" / "tui.json"
            if tui.exists():
                self.assertNotIn("opencode-subagent-statusline", tui.read_text())

            # It asked each client to remove what that client owns, and asked
            # Homebrew for the formula, rather than hand-deleting registries.
            calls = self.calls(home)
            self.assertIn("claude plugin uninstall engram@engram", calls)
            self.assertIn("claude plugin marketplace remove engram", calls)
            self.assertIn("codex plugin remove engram@engram", calls)
            # Fully qualified, and the same name install_packages installs.
            # The bare `engram` resolves to a cask in that tap and `brew
            # uninstall` refuses it, which is a failure the warning reports
            # and the summary then has to admit.
            formula, _ = harness_packages()
            engram = next(name for name in formula if name.endswith("/engram"))
            self.assertIn(f"brew uninstall {engram}", calls)

    def test_uninstall_keeps_a_foreign_opencode_statusline_plugin(self) -> None:
        # The tui.json entry is removed by name, so a neighbour in the same
        # array has to survive it, and a file that is not ours to parse has to
        # survive being unparseable.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            tui = home / ".config" / "opencode" / "tui.json"
            tui.parent.mkdir(parents=True, exist_ok=True)
            tui.write_text(json.dumps({"plugin": ["theirs"], "theme": "dark"}))

            self.run_installer(home, "--links-only")
            self.run_installer(home, "--uninstall")

            kept = json.loads(tui.read_text())
            self.assertEqual(kept["plugin"], ["theirs"])
            self.assertEqual(kept["theme"], "dark")

    def test_uninstall_keeps_a_dangling_symlink_it_cannot_claim(self) -> None:
        # An install archives a dangling link it cannot prove is its own, and
        # the owner can fetch it back. An uninstall deletes, so the same guess
        # is unrecoverable: a link into an unmounted volume is the ordinary
        # case, and it has to survive.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            self.run_installer(home, "--links-only")
            dangling = home / ".claude" / "skills" / "mine"
            dangling.symlink_to("/Volumes/not-mounted/mine")

            self.run_installer(home, "--uninstall")

            self.assertTrue(dangling.is_symlink())
            self.assertEqual(os.readlink(dangling), "/Volumes/not-mounted/mine")

    def test_uninstall_creates_no_config_it_did_not_find(self) -> None:
        # Both Codex reconcilers rendered a bare newline against an empty
        # config, so removal reported a change and the caller created
        # ~/.codex/config.toml on a machine that had none.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.run_installer(home, "--uninstall")

            self.assertFalse((home / ".codex" / "config.toml").exists())
            self.assertFalse((home / ".zshrc").exists())

    def test_uninstall_leaves_an_unrelated_zshrc_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            # No trailing newline, and a trailing blank line: the two shapes
            # the reconciler normalizes, which made "nothing to remove" look
            # like a change.
            zshrc = home / ".zshrc"
            original = "export PATH=/usr/bin\n\nalias sail='sh sail'"
            zshrc.write_text(original)

            self.run_installer(home, "--uninstall")

            self.assertEqual(zshrc.read_text(), original)

    def test_uninstall_keeps_the_engram_database(self) -> None:
        # ~/.engram is the user's memories, not something this installer wrote,
        # and an uninstall that no longer archives is the last thing that
        # should be deleting it.
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            database = home / ".engram" / "engram.db"
            database.parent.mkdir(parents=True)
            database.write_text("memories")

            self.run_installer(home, "--links-only")
            self.run_installer(home, "--uninstall")

            self.assertEqual(database.read_text(), "memories")
            self.assertTrue((home / ".engram").is_dir())

    def test_clear_backups_deletes_only_the_harness_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            self.seed(home)
            # A collision, so the install has something to archive and the
            # command has something to delete.
            collision = home / ".agents" / "skills" / "evidence"
            collision.mkdir(parents=True, exist_ok=True)
            (collision / "keep").write_text("mine")
            # A sibling under ~/.dotfiles-backups written by something else.
            # The harness owns one directory in there, not the parent.
            theirs = home / ".dotfiles-backups" / "private-skills" / "archive"
            theirs.mkdir(parents=True)
            (theirs / "keep").write_text("not the harness's")

            self.run_installer(home, "--links-only")
            self.assertTrue(self.backups(home), "the install archived nothing to delete")

            self.run_installer(home, "--clear-backups")

            self.assertEqual(self.backups(home), [])
            self.assertEqual((theirs / "keep").read_text(), "not the harness's")
            # It removed archives, not the harness.
            self.assertTrue((home / ".claude" / "CLAUDE.md").is_symlink())

    def test_clear_backups_is_a_clean_no_op_and_runs_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            # Nothing archived yet is a clean exit, not a failure.
            self.run_installer(home, "--clear-backups")
            self.assertFalse((home / ".dotfiles-backups").exists())

            for other in ("--uninstall", "--links-only"):
                with self.subTest(other=other):
                    result = self.run_installer(
                        home, "--clear-backups", other, check=False
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("--clear-backups", result.stderr)

    def test_install_accepts_the_engram_allowlist_prompt(self) -> None:
        # Declining means Claude Code prompts on every memory call, and the
        # policy assumes memory is always available. The `y` goes to the one
        # command known to ask; piping a blind yes into the other two would be
        # answering questions this repository has not read.
        installer = (ROOT / "harness" / "install.sh").read_text()
        self.assertIn("engram setup claude-code <<< y", installer)
        for agent in ("codex", "opencode"):
            self.assertIn(f"engram setup {agent} < /dev/null", installer)
        # And the allowlist is engram's to declare, not this repository's.
        tracked = json.loads((ROOT / "harness" / "clients" / "claude.json").read_text())
        self.assertNotIn("allow", tracked["permissions"])

    def test_uninstall_is_documented_in_the_usage(self) -> None:
        installer = (ROOT / "harness" / "install.sh").read_text()
        self.assertIn("--uninstall", installer)
        # The scope is the part a user gets wrong, so the usage has to state
        # that this reverses the installer rather than uninstalling their
        # tools.
        self.assertIn("it does not\n                 uninstall your tools", installer)
        # Deleting rather than archiving is the surprising half, so the usage
        # has to warn about it in the same words --no-backup does.
        uninstall = installer.split("  --uninstall")[1].split("  --clear-backups")[0]
        self.assertIn("Destructive and unrecoverable", uninstall)
        # --clear-backups deletes the only copy of what an install displaced,
        # so it carries the same warning in the same words.
        clear = installer.split("  --clear-backups")[1].split("EOF")[0]
        self.assertIn("Destructive and unrecoverable", clear)


if __name__ == "__main__":
    unittest.main()
