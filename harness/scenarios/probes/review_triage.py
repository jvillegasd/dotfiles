#!/usr/bin/env python3
"""Exercise the canonical review triage and reviewer input assembly declared by `adversarial-review`.

The skill carries one triage block and one input block, and this probe reads every rule from them rather than a parallel copy, so a change to a block changes the probe's behavior. It applies the triage block to nit fixes, answered questions, evidence-based reclassification, fixed and rejected blocking findings, conformance repairs, and the second-round trigger and cap. It applies the refuter rules to every verdict a contested blocking finding can receive, including a missing, malformed, or unavailable result, and to the refuter's own input boundary. It applies the input block to each reviewer's information boundary, required and optional standards, and the `loaded:` line that is the only evidence a standard was read. Outcomes land in `artifacts/review.json` in the disposable repository the scenario runner provides.
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
# The verdicts a refuter can return; missing, malformed, and unavailable are what the parent derives when it returns none of them.
RETURNED = ("corroborated", "refuted", "inconclusive")


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


def adjudicate(results: list) -> tuple[str, list]:
    """Return the verdict and `path:Lline:` evidence for one contested finding from its refuter results, where None is a refuter that could not run."""
    rules = block()["refuter"]
    if not results:
        raise ValueError("a contested finding is rejected only after the refuter runs")
    # One leading `unreadable:` answer is the Diff delivery retry, so only the answer after it counts as the invocation.
    prefix = inputs_block()["unreadable_prefix"]
    retries = [index for index, result in enumerate(results) if (result or "").startswith(prefix)]
    if retries not in ([], [0]):
        raise ValueError("an unreadable answer is retried once inline, before the answer")
    answered = results[len(retries):]
    if len(answered) > rules["invocations_per_finding"]:
        raise ValueError("one refuter invocation per contested finding")
    if not answered or answered[-1] is None:
        return "unavailable", []
    lines = answered[-1].strip().splitlines()
    if not lines:
        return "missing", []
    prefix = inputs_block()["verdict_prefix"]
    verdict = lines[0].removeprefix(prefix) if lines[0].startswith(prefix) else None
    evidence = [line for line in lines[1:] if re.fullmatch(r"\S+:L\d+: .+", line)]
    if verdict not in RETURNED or (verdict in rules["evidence_required"] and not evidence):
        return "malformed", []
    return verdict, evidence


def decide(severity: str, action: str | None = None, *, fix_smaller: bool = False, defect: str | None = None, refuter: list | None = None, human: str | None = None) -> dict:
    """Return the triage decision for one finding under the block's rules; rejecting a contested finding takes its refuter results, and a human decision may close the escalation they produce."""
    rules = block()
    actions = rules["severities"][severity]["actions"]
    if "reclassify_on_evidence" in actions and defect in rules["reclassify_to"]:
        return decide(defect, action, refuter=refuter, human=human)
    verdict, evidence, closed_by = None, [], None
    if "answer" in actions:
        action = "answer"
    elif "drop" in actions:
        action = "fix" if fix_smaller and "fix_when_smaller_than_argument" in actions else "drop"
    elif action not in actions:
        raise ValueError(f"{severity} does not permit {action}")
    elif severity in rules["refuter"]["applies_to"] and action == rules["refuter"]["required_before"]:
        verdict, evidence = adjudicate(refuter or [])
        action = rules["refuter"]["verdicts"][verdict]
        if action == "escalate" and human is not None:
            if rules["refuter"]["escalation_closes_on"] != "human_decision" or human not in actions:
                raise ValueError("only a human decision the severity permits closes an escalated finding")
            action, closed_by = human, "human_decision"
    blocking = rules["severities"][severity]["blocking"]
    trigger = rules["second_round"]["trigger"]
    if trigger == "fixed_blocking_finding":
        starts = blocking and action == "fix"
    elif trigger == "any_blocking_finding":
        starts = blocking
    else:
        raise SystemExit(f"unknown second-round trigger: {trigger}")
    return {"severity": severity, "action": action, "blocking": blocking, "second_round": starts, "verdict": verdict, "evidence": evidence, "closed_by": closed_by}


def next_round(completed: int, decisions: list, new_blocking_in_repaired: bool = False, conformance_repair: bool = False, adjudications: int = 0) -> str:
    """Return what follows a completed review round: none, the delta round's scope, or an action the cap names."""
    rules = block()
    completed += adjudications if rules["refuter"]["counts_as_round"] else 0
    if completed >= rules["max_rounds"]:
        if new_blocking_in_repaired:
            return rules["new_blocking_in_repaired_code"]
        return rules["conformance_repair_after_cap"] if conformance_repair else "none"
    counts = conformance_repair and rules["conformance_repair"] == "counts_as_fixed_blocking_finding"
    return rules["second_round"]["scope"] if counts or any(d["second_round"] for d in decisions) else "none"


def assemble(role: str, available: dict, paths: dict) -> dict:
    """Return exactly what the input block lets one reviewer receive: its listed inputs plus absolute standards paths."""
    rules = inputs_block()
    missing = {name for name in rules["standards"][role] if name not in paths}
    if missing - set(rules["optional_standards"]):
        raise ValueError(f"required standards missing: {sorted(missing)}")
    standards = [paths[name] for name in rules["standards"][role] if name in paths]
    if not all(Path(path).is_absolute() for path in standards):
        raise ValueError("standards paths must be absolute")
    given = {key: available[key] for key in rules["inputs"][role] if key in available}
    given["standards_paths"] = standards
    return given


def loaded(output: str, supplied: list) -> list:
    """Return the supplied standards paths that the first-line `loaded:` report names, opened or pasted; every other path counts as unread."""
    rules = inputs_block()
    first = output.splitlines()[:1]
    if not first or not first[0].startswith(rules["loaded_prefix"]):
        return []
    named = {name.strip().removeprefix(rules["inline_prefix"]) for name in first[0][len(rules["loaded_prefix"]):].split(",")}
    return [path for path in supplied if path in named]


def refused(call) -> bool:
    try:
        call()
    except ValueError:
        return True
    return False


FINDING = "x.py:L3: bug: `y` is None when the cache misses. Guard it."
CORROBORATED = "verdict: corroborated\nx.py:L3: `y` is read before `load` fills the cache."
REFUTED = "verdict: refuted\nx.py:L2: `load` raises before `y` can be None."
INCONCLUSIVE = "verdict: inconclusive\nChecked `load`; whether the cache can miss decides it."
UNREADABLE = "unreadable: /tmp/round1.diff"
MALFORMED = ("looks fine", "verdict: refuted", "verdict: maybe\nx.py:L2: `load` raises.")


def escalates(results: list, verdict: str) -> bool:
    decision = decide("bug", "reject", refuter=results)
    return decision["verdict"] == verdict and decision["action"] == "escalate" and not decision["second_round"]


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
        "rejected_blocking_starts_no_round": next_round(1, [decide("risk", "reject", refuter=[REFUTED])]) == "none",
        "round_two_new_blocking_escalates": next_round(2, [bug_fix], new_blocking_in_repaired=True) == "escalate",
        "cap_holds_at_two_rounds": next_round(2, [bug_fix]) == "none",
        "conformance_repair_starts_delta_round": next_round(1, [], conformance_repair=True) == "repair_delta",
        "late_conformance_repair_is_disclosed": next_round(2, [], conformance_repair=True) == "recheck_and_disclose",
    }

    corroborated, refuted = decide("bug", "reject", refuter=[CORROBORATED]), decide("risk", "reject", refuter=[REFUTED])
    outcomes.update(
        {
            "corroborated_finding_is_fixed": corroborated["verdict"] == "corroborated"
            and corroborated["action"] == "fix"
            and next_round(1, [corroborated]) == "repair_delta",
            "refuted_finding_is_rejected_with_evidence": refuted["action"] == "reject"
            and refuted["evidence"] == [REFUTED.splitlines()[1]]
            and next_round(1, [refuted]) == "none",
            "inconclusive_result_escalates": escalates([INCONCLUSIVE], "inconclusive"),
            "missing_result_escalates": escalates([""], "missing"),
            "malformed_result_escalates": all(escalates([text], "malformed") for text in MALFORMED),
            "unavailable_refuter_escalates": escalates([None], "unavailable") and escalates([UNREADABLE], "unavailable"),
            "unreadable_relaunch_is_the_same_invocation": not refused(lambda: decide("bug", "reject", refuter=[UNREADABLE, REFUTED]))
            and decide("bug", "reject", refuter=[UNREADABLE, REFUTED])["action"] == "reject",
            "misplaced_unreadable_refused": refused(lambda: decide("bug", "reject", refuter=[REFUTED, UNREADABLE]))
            and refused(lambda: decide("bug", "reject", refuter=[UNREADABLE, UNREADABLE, REFUTED])),
            "human_decision_closes_escalation": not refused(lambda: decide("bug", "reject", refuter=[INCONCLUSIVE], human="reject"))
            and decide("bug", "reject", refuter=[INCONCLUSIVE], human="reject")["closed_by"] == "human_decision"
            and decide("risk", "reject", refuter=[None], human="fix")["action"] == "fix"
            and escalates([INCONCLUSIVE], "inconclusive"),
            "rejection_without_refutation_refused": refused(lambda: decide("bug", "reject"))
            and refused(lambda: decide("risk", "reject", refuter=[])),
            "one_refuter_invocation_per_finding": refused(lambda: decide("bug", "reject", refuter=[INCONCLUSIVE, REFUTED])),
            "refuter_consumes_no_round": next_round(1, [corroborated], adjudications=1) == "repair_delta"
            and next_round(2, [corroborated], adjudications=1) == "none",
        }
    )

    available = {
        "requirements": "the acceptance criteria",
        "diff_snapshot_path": "/tmp/round1.diff",
        "implementation_rationale": "why the implementer thought it was right",
        "ticket": "#1",
        "contested_finding": FINDING,
    }
    paths = {"ponytail": "/home/u/.claude/skills/ponytail/SKILL.md", "project_instruction_file": "/repo/AGENTS.md"}
    a, b = assemble("reviewer-a", available, paths), assemble("reviewer-b", available, paths)
    supplied = b["standards_paths"]
    finding = "x.py:L1: nit: `x` is unused. Delete it."
    rules = inputs_block()
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
            "standards_paths_absolute": refused(
                lambda: assemble("reviewer-a", available, {**paths, "project_instruction_file": "AGENTS.md"})
            ),
            "missing_standards_omitted": not refused(lambda: assemble("reviewer-a", available, {"ponytail": paths["ponytail"]}))
            and assemble("reviewer-a", available, {"ponytail": paths["ponytail"]})["standards_paths"] == [],
            "missing_ponytail_refused": refused(
                lambda: assemble("reviewer-b", available, {"project_instruction_file": paths["project_instruction_file"]})
            ),
            "named_standards_count_as_loaded": loaded(f"loaded: /repo/AGENTS.md\n{finding}", supplied) == ["/repo/AGENTS.md"],
            "inline_standards_count_as_loaded": loaded(f"loaded: /repo/AGENTS.md, inline:{paths['ponytail']}", supplied) == supplied,
            "unnamed_standards_not_loaded": paths["ponytail"] not in loaded("loaded: /repo/AGENTS.md", supplied)
            and loaded("loaded: none", supplied) == [],
            "loaded_line_must_be_first": loaded(f"{finding}\nloaded: /repo/AGENTS.md", supplied) == [],
            "missing_loaded_line_is_no_evidence": loaded(finding, supplied) == [],
            "refuter_boundary": assemble("review-refuter", available, paths)
            == {"contested_finding": FINDING, "diff_snapshot_path": available["diff_snapshot_path"], "standards_paths": []},
            "refuter_declares_verdicts": all(
                f"`{rules['verdict_prefix']}{verdict}`" in (_ROLES / "review-refuter.md").read_text() for verdict in RETURNED
            ),
            "roles_declare_loaded_prefix": all(
                f"`{rules['loaded_prefix']}" in text and f"`{rules['inline_prefix']}" in text
                for text in ((_ROLES / f"{name}.md").read_text() for name in ("reviewer-a", "reviewer-b"))
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
