"""Regression checks for the read-only audit rules declared by /harness-audit.

The command carries the canonical audit block, and the probe reads it from
there instead of a parallel copy. These checks enforce the block, the command
prose that must agree with it, the probe's outcomes over mixed evidence, the
scenario declaration that runs it, the explicit-only installation metadata every
command shares, and the repository paths root AGENTS.md documents.
"""

import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_REPO = _HARNESS.parent
_COMMAND = _HARNESS / "commands/harness-audit.md"
_MATRIX = _HARNESS / "scenarios/matrix.json"
_PROBE = _HARNESS / "scenarios/probes/harness_audit.py"
_INSTALL = _HARNESS / "install.sh"
_AGENTS = _REPO / "AGENTS.md"

_SPEC = importlib.util.spec_from_file_location("harness_audit", _PROBE)
H = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(H)

BLOCK = {
    "sources": [
        "worktrees",
        "engram_checkpoints",
        "pull_request_bodies",
        "commits",
        "tracker_state",
        "benchmark_results",
        "session_evidence",
    ],
    "verdict_requires": "workflow_bearing_evidence",
    "finding_rule": {"pattern_minimum": 2, "single_requires": "concrete_cost"},
    "unavailable_state": "unknown",
    "transcript_mode": "bounded_named_signals",
    "transcript_signals": {
        "contract_section": "## Contract",
        "checks_section": "## Checks",
        "worktree": "worktree",
        "checkpoint": "checkpoint",
        "commit": r"\b(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}\b",
        "tracker_label": r"\b(ready-for-agent|in-progress|blocked|ready-for-human)\b",
        "benchmark": "benchmark",
    },
    "effects": {
        "file_writes": False,
        "forge_writes": False,
        "tracker_writes": False,
        "paid_model_calls": False,
    },
    "owned_by_setup_harness": ["tracker_configuration", "lifecycle_configuration"],
}

OUTCOMES = (
    "all_sources_reported",
    "present_is_recorded",
    "absent_is_unknown",
    "unreadable_is_unknown",
    "no_evidence_no_verdict",
    "evidence_yields_verdict",
    "single_without_cost_not_finding",
    "single_without_cost_observed",
    "single_with_cost_is_finding",
    "pattern_two_occurrences_is_finding",
    "transcript_is_bounded",
    "transcript_scan_is_capped",
    "transcript_finds_named_signals",
    "effects_are_read_only",
    "setup_harness_boundary",
    "fixture_files_unchanged",
    "audit_engine_writes_nothing",
    "git_state_unchanged",
)


class BlockTest(unittest.TestCase):
    def test_audit_rules_are_the_agreed_contract(self):
        self.assertEqual(H.block(), BLOCK)

    def test_command_prose_agrees_with_the_rules(self):
        text = _COMMAND.read_text()
        for phrase in (
            "No verdict without workflow-bearing evidence",
            "Read-only is a hard constraint",
            "A single uncosted occurrence is an observation, not a finding",
            "never creates a label",
        ):
            self.assertIn(phrase, text)

    def test_probe_reads_the_rules_from_the_command(self):
        self.repoint("pattern_minimum", "3")
        two = [{"id": "pattern", "occurrences": ["a", "b"], "concrete_cost": False}]
        self.assertNotIn("pattern", H.classify(two)["findings"])

    def repoint(self, key, value):
        mutated, count = re.subn(
            rf'"{key}": 2', f'"{key}": {value}', _COMMAND.read_text(), count=1
        )
        self.assertEqual(count, 1, f"command declares no integer {key}: 2")
        patched = Path(tempfile.mkdtemp()) / "harness-audit.md"
        patched.write_text(mutated)
        self.addCleanup(setattr, H, "_COMMAND", H._COMMAND)
        H._COMMAND = patched


class OutcomeTest(unittest.TestCase):
    def test_every_declared_outcome_holds(self):
        result = H.run()
        self.assertEqual(sorted(result), sorted(OUTCOMES))
        self.assertTrue(all(result.values()), result)


class ScanTest(unittest.TestCase):
    def test_permission_denied_source_is_unreadable(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses mode bits")
        fixture = Path(tempfile.mkdtemp())
        for source in H.block()["sources"]:
            (fixture / source).mkdir()
        denied = fixture / "tracker_state"
        (denied / "record.json").write_text("{}\n")
        denied.chmod(0)
        self.addCleanup(denied.chmod, 0o700)
        self.assertEqual(H.scan(fixture)["tracker_state"], "unreadable")


class ScenarioTest(unittest.TestCase):
    def test_matrix_declares_the_audit_scenario(self):
        matrix = json.loads(_MATRIX.read_text())
        scenario = next(
            (s for s in matrix["scenarios"] if s["id"] == "harness-audit"), None
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["command"], "harness-audit")
        self.assertEqual(scenario["mode"], "offline")
        self.assertTrue(scenario["check"].endswith("harness_audit.py\""))
        self.assertTrue(
            any(
                entry.endswith("commands/harness-audit.md")
                for entry in scenario["harness_inputs"]
            )
        )
        self.assertTrue(
            any(entry.endswith("probes/harness_audit.py") for entry in scenario["harness_inputs"])
        )
        texts = [entry["text"] for entry in scenario["artifacts"]["contains"]]
        for key in OUTCOMES:
            self.assertIn(f'"{key}": true', texts)


class InvocationTest(unittest.TestCase):
    def test_command_carries_the_metadata_check_links_requires(self):
        text = _COMMAND.read_text()
        self.assertTrue(re.search(r"(?m)^description:", text))
        self.assertIn("cannot override this workflow", text)

    def test_installer_guards_every_command_generically(self):
        text = _INSTALL.read_text()
        self.assertRegex(_COMMAND.stem, r"^[a-z0-9][a-z0-9-]*$")
        self.assertIn('"$HARNESS_DIR"/commands/*.md', text)
        self.assertIn("$HOME/.claude/commands", text)
        self.assertIn("$CONFIG_HOME/opencode/command", text)


class AgentsGuidanceTest(unittest.TestCase):
    def documented_paths(self):
        top = {path.name for path in _REPO.iterdir()}
        paths = set()
        for token in re.findall(r"[A-Za-z0-9._][A-Za-z0-9._/-]*", _AGENTS.read_text()):
            token = token[2:] if token.startswith("./") else token
            if token.split("/", 1)[0] not in top:
                continue
            paths.add(token)
        return paths

    def test_every_documented_path_resolves(self):
        paths = self.documented_paths()
        self.assertGreater(len(paths), 5, "AGENTS.md path parsing found nothing")
        missing = sorted(path for path in paths if not (_REPO / path).exists())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
