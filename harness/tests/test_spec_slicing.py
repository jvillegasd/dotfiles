"""Regression checks for the spec-slicing route declared by /create-ticket.

The command carries the canonical route table, and the probe reads it from
there instead of a parallel copy. These checks enforce the route table, the
probe's outcomes over zero-, one-, and many-slice fixtures, the command prose
that must agree with the table, and the scenario declaration that runs it.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_COMMAND = _HARNESS / "commands/create-ticket.md"
_MATRIX = _HARNESS / "scenarios/matrix.json"
_PROBE = _HARNESS / "scenarios/probes/spec_slicing.py"

_SPEC = importlib.util.spec_from_file_location("spec_slicing", _PROBE)
S = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(S)

OUTCOMES = (
    "zero_slice_publishes_nothing",
    "one_slice_creates_no_child",
    "one_slice_implementation_label",
    "multi_slice_preserves_parent",
    "multi_slice_preserves_children",
    "multi_slice_preserves_edges",
    "multi_slice_preserves_frontier",
    "research_batch_uses_child_dag",
    "single_slice_binding_is_one_artifact",
)


class BlockTest(unittest.TestCase):
    def test_route_table_is_the_agreed_contract(self):
        self.assertEqual(
            S.block(),
            {
                "empty_spec_route": "publish_nothing",
                "single_slice_route": "promote_spec_in_place",
                "multi_slice_route": "publish_child_dag",
                "research_input_route": "publish_child_dag",
                "projection_fields": [
                    "What to build",
                    "Acceptance criteria",
                    "Test seams and checks",
                ],
            },
        )

    def test_command_prose_agrees_with_the_table(self):
        text = _COMMAND.read_text()
        for phrase in (
            "Promote the published spec issue itself",
            "**Zero slices.**",
            "**One slice.**",
            "**Many slices.**",
            "never collapses",
            "no route adds an approval gate",
        ):
            self.assertIn(phrase, text)

    def test_probe_reads_the_route_table_from_the_command(self):
        self.repoint("single_slice_route", "publish_child_dag")
        self.assertEqual(S.route([{"id": "x"}]), "publish_child_dag")
        self.assertFalse(S.run()["one_slice_creates_no_child"])

    def repoint(self, key, value):
        mutated, count = re.subn(
            rf'"{key}":\s*"[^"]*"', f'"{key}": "{value}"', _COMMAND.read_text(), count=1
        )
        self.assertEqual(count, 1, f"command declares no {key}")
        patched = Path(tempfile.mkdtemp()) / "create-ticket.md"
        patched.write_text(mutated)
        self.addCleanup(setattr, S, "_COMMAND", S._COMMAND)
        S._COMMAND = patched


class OutcomeTest(unittest.TestCase):
    def test_every_declared_outcome_holds(self):
        result = S.run()
        self.assertEqual(sorted(result), sorted(OUTCOMES))
        self.assertTrue(all(result.values()), result)


class ScenarioTest(unittest.TestCase):
    def test_matrix_declares_the_spec_slicing_scenario(self):
        matrix = json.loads(_MATRIX.read_text())
        scenario = next(
            (s for s in matrix["scenarios"] if s["id"] == "spec-slicing"), None
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["mode"], "offline")
        self.assertTrue(scenario["check"].endswith("spec_slicing.py\""))
        self.assertTrue(
            any("spec_slicing.py" in entry for entry in scenario["harness_inputs"])
        )
        self.assertTrue(
            any(entry.endswith("commands/create-ticket.md") for entry in scenario["harness_inputs"])
        )
        self.assertTrue(
            any(entry.endswith("docs/agents/harness.json") for entry in scenario["harness_inputs"])
        )
        self.assertTrue(
            any(
                entry.endswith("skills/local-tracker/SKILL.md")
                for entry in scenario["harness_inputs"]
            )
        )
        texts = [entry["text"] for entry in scenario["artifacts"]["contains"]]
        for key in OUTCOMES:
            self.assertIn(f'"{key}": true', texts)


if __name__ == "__main__":
    unittest.main()
