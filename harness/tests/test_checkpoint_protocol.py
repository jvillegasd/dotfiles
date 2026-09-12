"""Regression checks for the workflow-checkpoint protocol skill.

The skill is the single definition of the checkpoint protocol. These checks
enforce its invocation guards, its canonical protocol block, the absence of a
second continuity store, that the scenario probe reads its rules from the
skill, and that no command duplicates the schema.
"""

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_SKILL = _HARNESS / "skills/workflow-checkpoint/SKILL.md"
_GUARD = _HARNESS / "skills/workflow-checkpoint/agents/openai.yaml"
_COMMANDS = _HARNESS / "commands"
_MATRIX = _HARNESS / "scenarios/matrix.json"
_PROBE = _HARNESS / "scenarios/probes/checkpoint_protocol.py"
_TWO_SESSION_PROBE = _HARNESS / "scenarios/probes/checkpoint_two_session.py"

_SPEC = importlib.util.spec_from_file_location("checkpoint_protocol", _PROBE)
P = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(P)

REQUIRED_FIELDS = {
    "state",
    "branch_tip",
    "contract",
    "checks",
    "rationale",
    "next_action",
}
REQUIRED_STATES = ("active", "completed", "abandoned", "cancelled")
TERMINAL_STATES = ("completed", "abandoned", "cancelled")


def protocol_block(path):
    for block in re.findall(r"```json\n(.*?)```", path.read_text(), re.DOTALL):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and "fields" in data and "states" in data:
            return data
    return None


def duplicates_protocol(text, block):
    """True when a text restates the protocol or the record schema."""
    if "stale_invalidates" in text or "require_non_empty" in text:
        return True
    for fenced in re.findall(r"```json\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(fenced)
        except ValueError:
            continue
        if isinstance(data, dict) and set(data) in (
            set(block),
            set(block["fields"]),
        ):
            return True
    return False


class GuardTest(unittest.TestCase):
    def test_skill_carries_all_three_invocation_guards(self):
        frontmatter = _SKILL.read_text()
        self.assertIn("disable-model-invocation: true", frontmatter)
        self.assertIn('opencode/autoinvoke: "false"', frontmatter)
        self.assertIn("allow_implicit_invocation: false", _GUARD.read_text())

    def test_skill_is_installable_from_the_skills_root(self):
        self.assertEqual(_SKILL.parent.parent, _HARNESS / "skills")
        self.assertEqual(_SKILL.name, "SKILL.md")
        self.assertTrue(_SKILL.is_file())

    def test_no_second_continuity_store(self):
        entries = sorted(p.name for p in _SKILL.parent.iterdir())
        self.assertEqual(entries, ["SKILL.md", "agents"])
        self.assertFalse((_SKILL.parent / ".agent").exists())
        self.assertFalse((_SKILL.parent / ".agents").exists())


class SchemaTest(unittest.TestCase):
    def test_protocol_block_defines_the_required_fields_and_states(self):
        block = protocol_block(_SKILL)
        self.assertIsNotNone(block, "skill carries no canonical protocol block")
        shapes = block["fields"]
        self.assertEqual(set(shapes), REQUIRED_FIELDS)
        self.assertEqual(shapes["contract"], "array")
        self.assertEqual(shapes["checks"], "array")
        self.assertEqual(tuple(block["states"]), REQUIRED_STATES)
        self.assertEqual(tuple(block["terminal_states"]), TERMINAL_STATES)
        self.assertEqual(block["active_state"], "active")
        self.assertEqual(block["topic_key"], "checkpoint/<branch>")

    def test_states_are_active_plus_terminal(self):
        block = protocol_block(_SKILL)
        self.assertEqual(
            list(block["states"]),
            [block["active_state"]] + list(block["terminal_states"]),
        )

    def test_record_table_lists_the_canonical_fields(self):
        block = protocol_block(_SKILL)
        rows = re.findall(r"^\| `([a-z_]+)` \|", _SKILL.read_text(), re.M)
        self.assertEqual(set(rows), set(block["fields"]))

    def test_probe_reads_the_protocol_from_the_skill(self):
        block = protocol_block(_SKILL)
        self.assertEqual(P.schema_fields(), tuple(block["fields"]))
        self.assertEqual(P.shapes(), block["fields"])
        self.assertEqual(P.topic_key_prefix(), "checkpoint")
        self.assertEqual(P.topic_key("feat/x"), "checkpoint/feat/x")
        self.assertEqual(P.states(), REQUIRED_STATES)
        self.assertEqual(P.terminal_states(), TERMINAL_STATES)

    def test_probe_rules_follow_the_skill(self):
        original = _SKILL.read_text()
        mutated = original.replace(
            '"stale_invalidates": ["checks", "next_action"]',
            '"stale_invalidates": ["checks"]',
        )
        self.assertNotEqual(original, mutated, "skill changed under the test")
        with tempfile.TemporaryDirectory() as directory:
            patched = Path(directory) / "SKILL.md"
            patched.write_text(mutated)
            previous = P._SKILL
            P._SKILL = patched
            try:
                store = {}
                P.save(
                    store,
                    "b",
                    "tip",
                    "active",
                    ["https://x"],
                    ["lint: pass"],
                    "why",
                    "next",
                )
                usable, notes = P.recover(store, "b", "other", lambda ref: True)
            finally:
                P._SKILL = previous
        self.assertEqual(notes, ["stale tip; checks not reused"])
        self.assertEqual(usable["checks"], [])
        self.assertEqual(usable["next_action"], "next")

    def test_probe_required_fields_follow_the_skill(self):
        original = _SKILL.read_text()
        mutated = original.replace(
            '"require_non_empty": ["contract", "next_action"]',
            '"require_non_empty": ["contract", "next_action", "checks"]',
        )
        self.assertNotEqual(original, mutated, "skill changed under the test")
        with tempfile.TemporaryDirectory() as directory:
            patched = Path(directory) / "SKILL.md"
            patched.write_text(mutated)
            previous = P._SKILL
            P._SKILL = patched
            try:
                store = {}
                P.save(store, "b", "tip", "active", ["https://x"], [], "", "next")
                usable, notes = P.recover(store, "b", "tip", lambda ref: True)
            finally:
                P._SKILL = previous
        self.assertIsNone(usable)
        self.assertEqual(notes, ["required field checks is empty"])

    def test_duplication_detector_catches_a_copied_block(self):
        block = protocol_block(_SKILL)
        copied = _SKILL.read_text()[_SKILL.read_text().index("```json") :]
        self.assertTrue(duplicates_protocol(copied, block))
        self.assertFalse(duplicates_protocol("ordinary command prose", block))

    def test_commands_do_not_duplicate_the_schema(self):
        block = protocol_block(_SKILL)
        for command in _COMMANDS.glob("*.md"):
            self.assertFalse(
                duplicates_protocol(command.read_text(), block),
                f"{command.name} restates the checkpoint schema",
            )


class ProtocolTest(unittest.TestCase):
    def test_protocol_rules_hold(self):
        result = P.run()
        self.assertEqual(
            result,
            {
                "isolation": True,
                "stale_checks_dropped": True,
                "invalid_state_rejected": True,
                "terminal_excluded": True,
                "empty_contract_rejected": True,
                "shape_rejected": True,
                "contract_rejected": True,
                "contract_partial": True,
                "read_back": True,
                "read_back_detects_corruption": True,
            },
        )

    def test_matrix_declares_the_checkpoint_scenario(self):
        matrix = json.loads(_MATRIX.read_text())
        scenario = next(
            (s for s in matrix["scenarios"] if s["id"] == "checkpoint-protocol"),
            None,
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["mode"], "offline")
        check = scenario["check"]
        self.assertTrue(check.endswith("checkpoint_protocol.py\""))
        self.assertTrue(
            any("checkpoint_protocol.py" in entry for entry in scenario["harness_inputs"])
        )
        self.assertTrue(
            any(entry.endswith("agents/openai.yaml") for entry in scenario["harness_inputs"])
        )
        texts = [entry["text"] for entry in scenario["artifacts"]["contains"]]
        for key in (
            "isolation",
            "stale_checks_dropped",
            "invalid_state_rejected",
            "terminal_excluded",
            "empty_contract_rejected",
            "shape_rejected",
            "contract_rejected",
            "contract_partial",
            "read_back",
            "read_back_detects_corruption",
        ):
            self.assertIn(f'"{key}": true', texts)


class TwoSessionScenarioTest(unittest.TestCase):
    def load_probe(self):
        sys.path.insert(0, str(_TWO_SESSION_PROBE.parent))
        try:
            spec = importlib.util.spec_from_file_location(
                "checkpoint_two_session", _TWO_SESSION_PROBE
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(_TWO_SESSION_PROBE.parent))
        return module

    def test_two_session_probe_recovers_every_declared_outcome(self):
        result = self.load_probe().run()
        self.assertTrue(all(result.values()), result)
        self.assertEqual(len(result), 7)

    def test_matrix_declares_the_two_session_scenario(self):
        matrix = json.loads(_MATRIX.read_text())
        scenario = next(
            (s for s in matrix["scenarios"] if s["id"] == "checkpoint-two-session"),
            None,
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["mode"], "offline")
        self.assertTrue(scenario["check"].endswith("checkpoint_two_session.py\""))
        self.assertTrue(
            any(
                "checkpoint_two_session.py" in entry
                for entry in scenario["harness_inputs"]
            )
        )
        texts = [entry["text"] for entry in scenario["artifacts"]["contains"]]
        for key in (
            "two_session_recovers_requirement",
            "two_session_recovers_rationale",
            "two_session_recovers_contract",
            "branch_isolation",
            "stable_topic_key_upserts",
            "stale_tip_keeps_rationale",
            "terminal_excluded",
        ):
            self.assertIn(f'"{key}": true', texts)


class CommandWiringTest(unittest.TestCase):
    DELIVERY_COMMANDS = (
        "proto",
        "ship",
        "feedback",
        "address-review",
        "land",
        "abandon",
    )
    SAVE_BOUNDARY = {
        "proto": "save the branch checkpoint",
        "ship": "save the branch checkpoint",
        "feedback": "refresh the branch checkpoint",
        "address-review": "refresh the branch checkpoint",
        "land": "finalize the checkpoint as `completed`",
        "abandon": "finalize the checkpoint as",
    }

    def test_delivery_commands_load_and_retrieve_the_checkpoint(self):
        for name in self.DELIVERY_COMMANDS:
            text = (_COMMANDS / f"{name}.md").read_text().lower()
            self.assertIn(
                "load `workflow-checkpoint`",
                text,
                f"{name}.md does not load the checkpoint skill at its boundary",
            )
            self.assertIn(
                "retrieve",
                text,
                f"{name}.md does not retrieve the checkpoint",
            )

    def test_delivery_commands_save_or_finalize_at_their_return(self):
        for name, boundary in self.SAVE_BOUNDARY.items():
            text = (_COMMANDS / f"{name}.md").read_text().lower()
            self.assertIn(
                boundary,
                text,
                f"{name}.md does not save or finalize the checkpoint at its return",
            )

    def test_terminal_commands_name_their_terminal_states(self):
        self.assertIn("`completed`", (_COMMANDS / "land.md").read_text())
        abandon = (_COMMANDS / "abandon.md").read_text()
        self.assertIn("`abandoned`", abandon)
        self.assertIn("`cancelled`", abandon)


if __name__ == "__main__":
    unittest.main()
