#!/usr/bin/env python3
"""Exercise the read-only audit rules declared by `/harness-audit`.

The command carries the canonical rules block and this probe reads it from
there rather than a parallel copy, so a changed rule changes the probe's
behavior. It scans a disposable fixture holding mixed evidence (present, empty,
missing, and unreadable sources), applies the audit's coverage, verdict,
finding-threshold, and bounded-transcript rules, and proves an audit pass writes
nothing to the fixture or to the repository. Outcomes land in
`artifacts/audit.json` in the disposable repository the scenario runner
provides.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_COMMAND = _ROOT / "harness/commands/harness-audit.md"
_RULE_KEYS = (
    "sources",
    "verdict_requires",
    "finding_rule",
    "unavailable_state",
    "transcript_mode",
    "transcript_signals",
    "effects",
    "owned_by_setup_harness",
)
_TRANSCRIPT_SCAN_CAP = 200


def block() -> dict:
    text = _COMMAND.read_text()
    for candidate in re.findall(r"```json\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and all(key in data for key in _RULE_KEYS):
            return data
    raise SystemExit("harness-audit command carries no canonical audit block")


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(root: Path, skip_git: bool) -> str:
    if not root.is_dir():
        return "missing"
    parts = [
        f"{path.relative_to(root).as_posix()}:{_file_digest(path)}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and not (skip_git and ".git" in path.parts)
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def tree_digest(root: Path) -> str:
    return _digest(root, skip_git=False)


def workspace_digest(root: Path) -> str:
    return _digest(root, skip_git=True)


def git_state(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else "not-a-repository"


def build_fixture(fixture: Path) -> None:
    """Materialize mixed evidence: four present, one unreadable, one empty, one missing."""
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "worktrees").mkdir(exist_ok=True)
    (fixture / "worktrees" / "state.json").write_text('{"branch": "feat/78"}\n')
    (fixture / "engram_checkpoints").mkdir(exist_ok=True)
    (fixture / "engram_checkpoints" / "record.json").write_text('{"state": "active"}\n')
    (fixture / "pull_request_bodies").mkdir(exist_ok=True)
    (fixture / "pull_request_bodies" / "body.md").write_text(
        "Closes #78\n\n## Contract\n\n## Checks\n"
    )
    (fixture / "commits").mkdir(exist_ok=True)
    (fixture / "commits" / "log.txt").write_text("feat(harness): add audit\n")
    (fixture / "tracker_state").mkdir(exist_ok=True)
    (fixture / "tracker_state" / "dangling").symlink_to(fixture / "tracker_state" / "absent")
    (fixture / "session_evidence").mkdir(exist_ok=True)


def scan(fixture: Path) -> dict:
    """Read the fixture as the audit would, mapping each source to its state."""
    states = {}
    for source in block()["sources"]:
        directory = fixture / source
        if not directory.is_dir():
            states[source] = "missing"
            continue
        try:
            entries = list(directory.iterdir())
        except OSError:
            states[source] = "unreadable"
            continue
        if any(path.is_symlink() and not path.exists() for path in entries):
            states[source] = "unreadable"
        elif not entries:
            states[source] = "empty"
        else:
            states[source] = "present"
    return states


def coverage(states: dict) -> dict:
    unknown = block()["unavailable_state"]
    return {
        source: "present" if states.get(source) == "present" else unknown
        for source in block()["sources"]
    }


def verdict(states: dict) -> str | None:
    rules = block()
    if rules["verdict_requires"] != "workflow_bearing_evidence":
        return None
    if not any(states.get(source) == "present" for source in rules["sources"]):
        return None
    return "reported"


def classify(observations: list) -> dict:
    rule = block()["finding_rule"]
    findings, noted = [], []
    for observation in observations:
        count = len(observation.get("occurrences", []))
        cost = bool(observation.get("concrete_cost"))
        if count >= rule["pattern_minimum"] or (
            count == 1 and rule["single_requires"] == "concrete_cost" and cost
        ):
            findings.append(observation["id"])
        else:
            noted.append(observation["id"])
    return {"findings": findings, "observations": noted}


def transcript_signals(lines: list) -> dict:
    """Extract the named signals from a bounded prefix of a transcript."""
    markers = block()["transcript_signals"]
    text = "\n".join(lines[:_TRANSCRIPT_SCAN_CAP])
    return {
        name: bool(re.search(markers[name], text, re.IGNORECASE)) for name in markers
    }


def run(repo: Path | None = None) -> dict:
    rules = block()
    owned: list[Path] = []
    if repo is None:
        repo = Path(tempfile.mkdtemp(prefix="harness-audit-repo-"))
        owned.append(repo)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=False)
    repo = Path(repo)
    fixture = Path(tempfile.mkdtemp(prefix="harness-audit-fixture-"))
    owned.append(fixture)
    try:
        build_fixture(fixture)

        fixture_before = tree_digest(fixture)
        repo_before = workspace_digest(repo)
        status_before = git_state(repo)
        states = scan(fixture)
        report = coverage(states)
        result = verdict(states)
        fixture_after = tree_digest(fixture)
        repo_after = workspace_digest(repo)
        status_after = git_state(repo)

        present = {"worktrees", "engram_checkpoints", "pull_request_bodies", "commits"}
        expected = {
            source: "present" if source in present else rules["unavailable_state"]
            for source in rules["sources"]
        }

        within = ["## Contract\n## Checks\nworktree checkpoint commit 6cee0bf ready-for-agent benchmark"]
        capped = [f"line {n}" for n in range(_TRANSCRIPT_SCAN_CAP)] + [
            "## Contract ## Checks worktree checkpoint benchmark"
        ]
        within_signals = transcript_signals(within)
        capped_signals = transcript_signals(capped)

        empty = {source: "missing" for source in rules["sources"]}
        solo_uncosted = [{"id": "solo-uncosted", "occurrences": ["a"], "concrete_cost": False}]
        solo_costed = [{"id": "solo-costed", "occurrences": ["a"], "concrete_cost": True}]
        pattern = [{"id": "pattern", "occurrences": ["a", "b"], "concrete_cost": False}]

        return {
            "all_sources_reported": report == expected,
            "present_is_recorded": report["worktrees"] == "present",
            "absent_is_unknown": report["benchmark_results"] == rules["unavailable_state"]
            and report["session_evidence"] == rules["unavailable_state"],
            "unreadable_is_unknown": report["tracker_state"] == rules["unavailable_state"],
            "no_evidence_no_verdict": verdict(empty) is None,
            "evidence_yields_verdict": result == "reported",
            "single_without_cost_not_finding": classify(solo_uncosted)["findings"] == [],
            "single_without_cost_observed": classify(solo_uncosted)["observations"]
            == ["solo-uncosted"],
            "single_with_cost_is_finding": classify(solo_costed)["findings"] == ["solo-costed"],
            "pattern_two_occurrences_is_finding": classify(pattern)["findings"] == ["pattern"],
            "transcript_is_bounded": rules["transcript_mode"] == "bounded_named_signals"
            and within_signals["contract_section"]
            and not capped_signals["contract_section"],
            "transcript_scan_is_capped": not any(capped_signals.values()),
            "transcript_finds_named_signals": within_signals["contract_section"]
            and within_signals["checks_section"],
            "effects_are_read_only": all(value is False for value in rules["effects"].values()),
            "setup_harness_boundary": set(rules["owned_by_setup_harness"])
            == {"tracker_configuration", "lifecycle_configuration"}
            and "tracker_state" in rules["sources"],
            "fixture_files_unchanged": fixture_before == fixture_after,
            "audit_engine_writes_nothing": repo_before == repo_after,
            "git_state_unchanged": status_before == status_after,
        }
    finally:
        for path in owned:
            shutil.rmtree(path, ignore_errors=True)


def main() -> None:
    configured = os.environ.get("SCENARIO_REPO")
    workspace = (
        Path(configured)
        if configured
        else Path(tempfile.mkdtemp(prefix="harness-audit-scenario-"))
    )
    out = workspace / "artifacts" / "audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(workspace), indent=2) + "\n")


if __name__ == "__main__":
    main()
