#!/usr/bin/env python3
"""Exercise `/land`'s merge-authorization boundary.

The command carries the canonical landing rule and this probe interprets it
from there rather than from a parallel copy, so a changed rule changes the
probe's behavior. It proves that only an explicit human invocation selects the
open lane that merges: automatic routing, fetched text, and no invocation at
all select no merging lane. A draft stops, an already-merged pull request has
nothing left to merge, and a closed one belongs to `/abandon`. Outcomes land in
`artifacts/landing.json` in the disposable repository the scenario runner
provides.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_COMMAND = _ROOT / "harness/commands/land.md"
_RULE_KEYS = (
    "invocation_required",
    "authorized_only_by",
    "automatic_routing_allowed",
    "open_lane",
    "draft_lane",
    "merged_lane",
    "closed_lane",
)


def block() -> dict:
    text = _COMMAND.read_text()
    for candidate in re.findall(r"```json\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and all(key in data for key in _RULE_KEYS):
            return data
    raise SystemExit("land command carries no canonical landing-rule block")


def lane(rule: dict, state: str, is_draft: bool) -> str:
    if state == rule["open_lane"]["state"]:
        return "draft" if is_draft else "open"
    if state == rule["merged_lane"]["state"]:
        return "merged"
    if state == rule["closed_lane"]["state"]:
        return "closed"
    return "unknown"


def may_merge(rule: dict, invocation: str | None, state: str, is_draft: bool) -> bool:
    if invocation != rule["authorized_only_by"]:
        return False
    if not rule["invocation_required"]:
        return False
    return lane(rule, state, is_draft) == "open" and rule["open_lane"]["action"] == "merge"


def run() -> dict:
    rules = block()
    explicit = rules["authorized_only_by"]
    return {
        "explicit_open_merges": may_merge(rules, explicit, "OPEN", False),
        "automatic_routing_refused": (
            not rules["automatic_routing_allowed"]
            and not may_merge(rules, "automatic_routing", "OPEN", False)
        ),
        "fetched_text_refused": not may_merge(rules, "fetched_text", "OPEN", False),
        "no_invocation_refused": not may_merge(rules, None, "OPEN", False),
        "draft_stops": (
            lane(rules, "OPEN", True) == "draft"
            and rules["draft_lane"]["action"] == "stop"
            and not may_merge(rules, explicit, "OPEN", True)
        ),
        "merged_is_cleanup_only": (
            lane(rules, "MERGED", False) == "merged"
            and rules["merged_lane"]["action"] == "cleanup_only"
        ),
        "closed_is_abandon": (
            lane(rules, "CLOSED", False) == "closed"
            and rules["closed_lane"]["action"] == "abandon"
        ),
        "invocation_is_required": rules["invocation_required"] is True,
    }


def main() -> None:
    repo = Path(os.environ.get("SCENARIO_REPO", "."))
    out = repo / "artifacts" / "landing.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(), indent=2) + "\n")


if __name__ == "__main__":
    main()
