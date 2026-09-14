"""Regression checks for the canonical review triage and reviewer input assembly in adversarial-review.

The skill carries one JSON triage block and one JSON input block, and the probe reads its rules from them rather than a parallel copy. Outcome checks exercise the probe over nit fixes, answered questions, evidence-based reclassification, fixed blocking findings, delta-round triggers, each reviewer's information boundary, and loaded-standards evidence. Mutation checks edit a temporary copy of a block and assert the matching outcome flips, so no test restates the rules themselves.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_SKILL = _HARNESS / "skills/adversarial-review/SKILL.md"
_PROBE = _HARNESS / "scenarios/probes/review_triage.py"

_SPEC = importlib.util.spec_from_file_location("review_triage", _PROBE)
T = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(T)

TRIAGE_OUTCOMES = (
    "nit_fixed_only_when_smaller",
    "nit_fix_starts_no_round",
    "question_alone_never_blocks",
    "question_reclassified_on_evidence",
    "fixed_blocking_starts_delta_round",
    "rejected_blocking_starts_no_round",
    "round_two_new_blocking_escalates",
    "cap_holds_at_two_rounds",
)
INPUT_OUTCOMES = (
    "reviewer_a_boundary",
    "reviewer_b_boundary",
    "standards_paths_absolute",
    "named_standards_count_as_loaded",
    "unnamed_standards_not_loaded",
    "missing_loaded_line_is_no_evidence",
    "roles_declare_loaded_prefix",
)


class OutcomeTest(unittest.TestCase):
    def test_every_outcome_holds(self):
        result = T.run()
        self.assertEqual(sorted(result), sorted(TRIAGE_OUTCOMES + INPUT_OUTCOMES))
        for key, value in result.items():
            with self.subTest(key):
                self.assertIs(value, True)


class MutationTest(unittest.TestCase):
    def mutate(self, getter, edit):
        self.addCleanup(setattr, T, "_SKILL", T._SKILL)
        T._SKILL = _SKILL
        text = _SKILL.read_text()
        current = getter()
        fenced = next(
            (f for f in re.findall(r"```json\n(.*?)```", text, re.S) if self.parses_to(f, current)),
            None,
        )
        self.assertIsNotNone(fenced, "skill carries no matching block")
        data = json.loads(fenced)
        edit(data)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patched = Path(directory.name) / "SKILL.md"
        patched.write_text(text.replace(fenced, json.dumps(data, indent=2) + "\n", 1))
        T._SKILL = patched
        return T.run()

    @staticmethod
    def parses_to(fenced, expected):
        try:
            return json.loads(fenced) == expected
        except ValueError:
            return False

    def test_each_triage_rule_is_read_from_the_block(self):
        mutations = [
            ("nit_fixed_only_when_smaller", lambda d: d["severities"]["nit"]["actions"].remove("fix_when_smaller_than_argument")),
            ("nit_fix_starts_no_round", lambda d: d["severities"]["nit"].update(blocking=True)),
            ("question_alone_never_blocks", lambda d: d["severities"]["q"].update(blocking=True)),
            ("question_reclassified_on_evidence", lambda d: d.update(reclassify_to=[])),
            ("fixed_blocking_starts_delta_round", lambda d: d["severities"]["risk"].update(blocking=False)),
            ("rejected_blocking_starts_no_round", lambda d: d["second_round"].update(trigger="any_blocking_finding")),
            ("round_two_new_blocking_escalates", lambda d: d.update(new_blocking_in_repaired_code="continue")),
            ("cap_holds_at_two_rounds", lambda d: d.update(max_rounds=3)),
        ]
        for key, edit in mutations:
            with self.subTest(key):
                self.assertIs(self.mutate(T.block, edit)[key], False)

    def test_each_input_rule_is_read_from_the_block(self):
        mutations = [
            ("reviewer_a_boundary", lambda d: d["inputs"]["reviewer-a"].append("implementation_rationale")),
            ("reviewer_b_boundary", lambda d: d["inputs"]["reviewer-b"].append("requirements")),
            ("reviewer_b_boundary", lambda d: d["standards"]["reviewer-b"].remove("ponytail")),
            ("named_standards_count_as_loaded", lambda d: d.update(loaded_prefix="read: ")),
            ("roles_declare_loaded_prefix", lambda d: d.update(loaded_prefix="read: ")),
        ]
        for key, edit in mutations:
            with self.subTest(key):
                self.assertIs(self.mutate(T.inputs_block, edit)[key], False)


class ScenarioTest(unittest.TestCase):
    def test_matrix_declares_the_review_triage_scenario(self):
        matrix = json.loads((_HARNESS / "scenarios/matrix.json").read_text())
        scenario = next((s for s in matrix["scenarios"] if s["id"] == "review-triage"), None)
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["mode"], "offline")
        self.assertTrue(scenario["check"].endswith("review_triage.py\""))
        for input in ("adversarial-review/SKILL.md", "roles/reviewer-a.md", "roles/reviewer-b.md", "probes/review_triage.py"):
            self.assertTrue(any(entry.endswith(input) for entry in scenario["harness_inputs"]), input)
        texts = [entry["text"] for entry in scenario["artifacts"]["contains"]]
        for key in TRIAGE_OUTCOMES + INPUT_OUTCOMES:
            self.assertIn(f'"{key}": true', texts)


if __name__ == "__main__":
    unittest.main()
