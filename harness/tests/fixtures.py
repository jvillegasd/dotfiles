#!/usr/bin/env python3

"""Paths, name sets, and readers shared by two or more test files.

Anything used by exactly one test file lives in that file instead. A shared
module that also holds single-owner helpers is the old single test file with
an import statement in front of it.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
SKILLS = ROOT / "harness" / "skills"
COMMANDS = ROOT / "harness" / "commands"
STATUSLINE = ROOT / "harness" / "statusline"
CLIENTS = ROOT / "harness" / "clients"
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
    "setup-harness",
}

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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def codex_status_items() -> list[str]:
    """The Codex status line item ids, read from the file that declares them.

    Both the installer check and the reconciled-config check compare against
    this rather than against a literal copy. A literal is what went stale when
    the combined `model-with-reasoning` split into `model` and `reasoning`:
    one assertion started failing and its sibling kept passing on the comment
    that explains the id's absence.
    """
    block = re.search(
        r"(?m)^ITEMS=\(\n(.*?)^\)", (STATUSLINE / "codex.sh").read_text(), re.S
    )
    assert block is not None, "codex.sh no longer declares an ITEMS array"
    return block.group(1).split()
