"""Regression checks for the recon citation protocol /triage and /research share.

Both commands carry an identical `## Recon citations` section. These checks assert the two copies agree and pin each protocol line whole, so a deliberate paraphrase of a pinned line fails. Literal prose assertions have a ceiling: a contradicting sentence added elsewhere beside an intact pin still passes, and no text check proves an agent follows the protocol. The probe exercises the rule itself over valid and invalid citations; transcripts remain the evidence that sessions obey it.
"""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_TRIAGE = _HARNESS / "commands/triage.md"
_RESEARCH = _HARNESS / "commands/research.md"
_MATRIX = _HARNESS / "scenarios/matrix.json"
_PROBE = _HARNESS / "scenarios/probes/recon_citations.py"

_SPEC = importlib.util.spec_from_file_location("recon_citations", _PROBE)
C = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(C)

OUTCOMES = (
    "valid_citation_grounded",
    "missing_file_refuted",
    "outside_repository_refuted",
    "stale_line_refuted",
    "wrong_symbol_refuted",
    "partial_symbol_refuted",
    "absent_field_refuted",
    "refuted_never_grounded",
    "trailing_tool_result_no_data",
)

PINS = [
    "A recon subagent that searches the repository ends on a text message holding only its findings, one per line in the shape `path:line | symbol | mechanism`: the cited location, the named symbol, a bare identifier, that location carries, and the mechanism it is claimed to show. A trailing tool result is not the report: re-run that track once, and if it again ends without one, record it as no data, a `no data` row in `/triage`'s evidence ledger or an entry under `/research`'s `Contradictions and unknowns`, never as refuted or as a track that found nothing.",
    "Before reusing a citation, read only the cited line and confirm the path resolves inside the repository and that line carries the named symbol as a whole identifier. That check grounds the location only, never the claimed runtime mechanism: a load-bearing mechanism claim still goes through `evidence`.",
    "Drop a citation whose path is missing or outside the repository, whose line does not carry the named symbol, or that lacks any of the three fields. Record it as refuted, as a verdict row in `/triage`'s evidence ledger or an entry under `/research`'s `Contradictions and unknowns`, and never reuse it as grounded evidence.",
]


def section(path):
    match = re.search(r"^## Recon citations\n(.*?)(?=^## )", path.read_text(), re.M | re.S)
    return match.group(1) if match else None


class ProtocolTest(unittest.TestCase):
    def test_both_commands_carry_the_same_section(self):
        triage, research = section(_TRIAGE), section(_RESEARCH)
        self.assertIsNotNone(triage, "triage.md carries no recon citations section")
        self.assertIsNotNone(research, "research.md carries no recon citations section")
        self.assertEqual(triage, research)

    def test_pinned_lines(self):
        for path in (_TRIAGE, _RESEARCH):
            present = (section(path) or "").splitlines()
            for line in PINS:
                with self.subTest(path=path.name, line=line[:60]):
                    self.assertIn(line, present)

    def test_delegation_steps_point_at_the_section(self):
        for path in (_TRIAGE, _RESEARCH):
            steps = path.read_text().split("## Steps\n", 1)[1].split("\n## ", 1)[0]
            with self.subTest(path=path.name):
                self.assertIn("`## Recon citations`", steps)


class CitationTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "app.py").write_text("def load_config(path):\n    return parse(path)\n")
        (self.root / "link.py").symlink_to("/etc/hosts")

    def test_probe_reads_the_shape_from_the_command(self):
        self.assertEqual(C.fields(), ["path:line", "symbol", "mechanism"])

    def test_valid_citation_is_grounded(self):
        report = {"type": "text", "text": "app.py:1 | load_config | defines the loader"}
        self.assertEqual(
            C.verify(report, self.root),
            {"grounded": ["app.py:1 | load_config | defines the loader"], "refuted": []},
        )

    def test_invalid_citations_are_refuted_and_never_grounded(self):
        cases = {
            "gone.py:1 | load_config | defines the loader": "missing file",
            "app.py:9 | load_config | defines the loader": "symbol not at line",
            "app.py:2 | load_config | defines the loader": "symbol not at line",
            "app.py:1 | load | defines the loader": "symbol not at line",
            "../app.py:1 | load_config | defines the loader": "outside repository",
            "/etc/hosts:1 | localhost | resolves host names": "outside repository",
            "link.py:1 | localhost | resolves host names": "outside repository",
            "app.py:1 | load_config": "missing field",
            "app.py | load_config | defines the loader": "missing field",
            "app.py:1 |  | defines the loader": "missing field",
        }
        for citation, reason in cases.items():
            with self.subTest(citation=citation):
                result = C.verify({"type": "text", "text": citation}, self.root)
                self.assertEqual(result["grounded"], [])
                self.assertEqual(result["refuted"], [{"citation": citation, "reason": reason}])

    def test_trailing_tool_result_is_no_data(self):
        report = {"type": "tool_result", "text": "app.py:1 | load_config | defines the loader"}
        self.assertEqual(
            C.verify(report, self.root),
            {"grounded": [], "refuted": [], "no_data": "no text report"},
        )

    def test_every_declared_outcome_holds(self):
        result = C.run()
        self.assertEqual(sorted(result), sorted(OUTCOMES))
        self.assertTrue(all(result.values()), result)


class ScenarioTest(unittest.TestCase):
    def test_matrix_declares_the_recon_citations_scenario(self):
        matrix = json.loads(_MATRIX.read_text())
        scenario = next((s for s in matrix["scenarios"] if s["id"] == "recon-citations"), None)
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario["mode"], "offline")
        self.assertTrue(scenario["check"].endswith("recon_citations.py\""))
        for input in ("commands/triage.md", "commands/research.md", "probes/recon_citations.py"):
            self.assertTrue(any(entry.endswith(input) for entry in scenario["harness_inputs"]), input)
        texts = [entry["text"] for entry in scenario["artifacts"]["contains"]]
        for key in OUTCOMES:
            self.assertIn(f'"{key}": true', texts)


if __name__ == "__main__":
    unittest.main()
