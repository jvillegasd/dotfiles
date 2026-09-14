#!/usr/bin/env python3
"""Exercise the canonical review triage and reviewer input assembly declared by `adversarial-review`.

The skill carries one triage block and one input block, and this probe reads every rule from them rather than a parallel copy, so a change to a block changes the probe's behavior. It applies the triage block to nit fixes, answered questions, evidence-based reclassification, fixed and rejected blocking findings, and the second-round trigger and cap. It applies the input block to each reviewer's information boundary, absolute standards paths, and the `loaded:` line that is the only evidence a standard was read. Outcomes land in `artifacts/review.json` in the disposable repository the scenario runner provides.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / "harness/skills/adversarial-review/SKILL.md"
_ROLES = _ROOT / "harness/skills/adversarial-review/roles"


def _find(keys: tuple, name: str) -> dict:
    for candidate in re.findall(r"```json\n(.*?)```", _SKILL.read_text(), re.S):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and all(key in data for key in keys):
            return data
    raise SystemExit(f"adversarial-review carries no canonical {name} block")


def block() -> dict:
    return _find(("severities", "second_round"), "triage")


def inputs_block() -> dict:
    return _find(("inputs", "loaded_prefix"), "input")


def decide(severity: str, action: str | None = None, *, fix_smaller: bool = False, defect: str | None = None) -> dict:
    """Return the triage decision for one finding under the block's rules."""
    rules = block()
    actions = rules["severities"][severity]["actions"]
    if "reclassify_on_evidence" in actions and defect in rules["reclassify_to"]:
        return decide(defect, action)
    if "answer" in actions:
        action = "answer"
    elif "drop" in actions:
        action = "fix" if fix_smaller and "fix_when_smaller_than_argument" in actions else "drop"
    elif action not in actions:
        raise ValueError(f"{severity} does not permit {action}")
    blocking = rules["severities"][severity]["blocking"]
    trigger = rules["second_round"]["trigger"]
    if trigger == "fixed_blocking_finding":
        starts = blocking and action == "fix"
    elif trigger == "any_blocking_finding":
        starts = blocking
    else:
        raise SystemExit(f"unknown second-round trigger: {trigger}")
    return {"severity": severity, "action": action, "blocking": blocking, "second_round": starts}


def next_round(completed: int, decisions: list, new_blocking_in_repaired: bool = False) -> str:
    """Return what follows a completed review round: none, the delta round's scope, or the cap's action."""
    rules = block()
    if completed >= rules["max_rounds"]:
        return rules["new_blocking_in_repaired_code"] if new_blocking_in_repaired else "none"
    return rules["second_round"]["scope"] if any(d["second_round"] for d in decisions) else "none"


def assemble(role: str, available: dict, paths: dict) -> dict:
    """Return exactly what the input block lets one reviewer receive: its listed inputs plus absolute standards paths."""
    rules = inputs_block()
    standards = [paths[name] for name in rules["standards"][role]]
    if not all(Path(path).is_absolute() for path in standards):
        raise ValueError("standards paths must be absolute")
    given = {key: available[key] for key in rules["inputs"][role] if key in available}
    given["standards_paths"] = standards
    return given


def loaded(output: str, supplied: list) -> list:
    """Return the supplied standards paths that the reviewer's `loaded:` line names; every other path counts as unread."""
    prefix = inputs_block()["loaded_prefix"]
    line = next((line for line in output.splitlines() if line.startswith(prefix)), None)
    named = {name.strip() for name in line[len(prefix):].split(",")} if line is not None else set()
    return [path for path in supplied if path in named]


def run() -> dict:
    nit_fix, nit_drop = decide("nit", fix_smaller=True), decide("nit")
    question = decide("q")
    bug_fix, risk_fix = decide("bug", "fix"), decide("risk", "fix")
    outcomes = {
        "nit_fixed_only_when_smaller": nit_fix["action"] == "fix" and nit_drop["action"] == "drop",
        "nit_fix_starts_no_round": not nit_fix["blocking"] and next_round(1, [nit_fix]) == "none",
        "question_alone_never_blocks": not question["blocking"]
        and question["action"] == "answer"
        and next_round(1, [question]) == "none",
        "question_reclassified_on_evidence": decide("q", "fix", defect="bug") == bug_fix
        and decide("q", "fix")["severity"] == "q",
        "fixed_blocking_starts_delta_round": bug_fix["blocking"]
        and risk_fix["blocking"]
        and next_round(1, [bug_fix]) == next_round(1, [risk_fix]) == "repair_delta",
        "rejected_blocking_starts_no_round": next_round(1, [decide("risk", "reject")]) == "none",
        "round_two_new_blocking_escalates": next_round(2, [bug_fix], new_blocking_in_repaired=True) == "escalate",
        "cap_holds_at_two_rounds": next_round(2, [bug_fix]) == "none",
    }

    available = {
        "requirements": "the acceptance criteria",
        "diff_snapshot_path": "/tmp/round1.diff",
        "implementation_rationale": "why the implementer thought it was right",
        "ticket": "#1",
    }
    paths = {"ponytail": "/home/u/.claude/skills/ponytail/SKILL.md", "project_instruction_file": "/repo/AGENTS.md"}
    a, b = assemble("reviewer-a", available, paths), assemble("reviewer-b", available, paths)
    try:
        assemble("reviewer-a", available, {**paths, "project_instruction_file": "AGENTS.md"})
        relative_refused = False
    except ValueError:
        relative_refused = True
    supplied = b["standards_paths"]
    finding = "x.py:L1: nit: `x` is unused. Delete it."
    prefix = inputs_block()["loaded_prefix"]
    outcomes.update(
        {
            "reviewer_a_boundary": a
            == {
                "requirements": available["requirements"],
                "diff_snapshot_path": available["diff_snapshot_path"],
                "standards_paths": [paths["project_instruction_file"]],
            },
            "reviewer_b_boundary": b
            == {
                "diff_snapshot_path": available["diff_snapshot_path"],
                "standards_paths": [paths["ponytail"], paths["project_instruction_file"]],
            },
            "standards_paths_absolute": relative_refused,
            "named_standards_count_as_loaded": loaded(f"loaded: /repo/AGENTS.md\n{finding}", supplied) == ["/repo/AGENTS.md"],
            "unnamed_standards_not_loaded": paths["ponytail"] not in loaded("loaded: /repo/AGENTS.md", supplied)
            and loaded("loaded: none", supplied) == [],
            "missing_loaded_line_is_no_evidence": loaded(finding, supplied) == [],
            "roles_declare_loaded_prefix": all(
                f"`{prefix}" in (_ROLES / f"{name}.md").read_text() for name in ("reviewer-a", "reviewer-b")
            ),
        }
    )
    return outcomes


def main() -> None:
    repo = Path(os.environ.get("SCENARIO_REPO") or tempfile.mkdtemp(prefix="review-triage-scenario-"))
    out = repo / "artifacts" / "review.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(), indent=2) + "\n")


if __name__ == "__main__":
    main()
