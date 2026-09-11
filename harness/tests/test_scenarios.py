"""Regression checks for the artifact-based scenario runner.

Every state the runner can report is exercised independently against a
synthetic attempt, the forge guard is proven to intercept a real call, and the
shipped matrix runs offline through recorded fixtures.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "scenario_runner", _HARNESS / "scenarios/runner.py"
)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


def scenario(**overrides):
    base = {
        "id": "s",
        "command": "c",
        "prompt": "p",
        "artifacts": {"tree_unchanged": True},
    }
    base.update(overrides)
    return base


def write_attempt(path, digest="abc", ok=True, review=False):
    path.mkdir(parents=True, exist_ok=True)
    (path / "prompts.txt").write_text("prompt\n")
    (path / "provenance.json").write_text(
        json.dumps({"input_digest": digest, "recorded_at": "now"})
    )
    (path / "events.jsonl").write_text("")
    (path / "artifacts.json").write_text(
        json.dumps({"ok": ok, "results": [{"name": "x", "ok": ok}]})
    )
    (path / "transcript.jsonl").write_text("")
    if review:
        (path / "review.json").write_text(json.dumps({"reviewed": True, "by": "test"}))


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scenario = scenario()

    def evaluate(self, **kwargs):
        digest = kwargs.pop("digest", "abc")
        current = kwargs.pop("current", "abc")
        attempt = self.tmp / "attempt"
        write_attempt(attempt, digest=digest, **kwargs)
        return R.evaluate(attempt, self.scenario, current)[0]

    def test_incomplete_when_evidence_missing(self):
        attempt = self.tmp / "attempt"
        write_attempt(attempt)
        (attempt / "transcript.jsonl").unlink()
        self.assertEqual(R.evaluate(attempt, self.scenario, "abc")[0], "incomplete")

    def test_stale_when_inputs_changed(self):
        self.assertEqual(self.evaluate(digest="old", current="new"), "stale")

    def test_fail_when_artifact_checks_fail(self):
        self.assertEqual(self.evaluate(ok=False), "fail")

    def test_unreviewed_when_no_review_record(self):
        self.assertEqual(self.evaluate(), "unreviewed")

    def test_pass_when_artifacts_and_review_agree(self):
        self.assertEqual(self.evaluate(review=True), "pass")


class DeclarationTest(unittest.TestCase):
    def test_shipped_matrix_is_valid(self):
        matrix = R.load_matrix(R.DEFAULT_MATRIX)
        self.assertEqual(R.validate_matrix(matrix), [])

    def test_scenario_without_artifacts_is_rejected(self):
        matrix = {"scenarios": [{"id": "s", "command": "c", "prompt": "p", "artifacts": {}}]}
        self.assertTrue(any("artifacts" in error for error in R.validate_matrix(matrix)))

    def test_offline_scenario_without_check_is_rejected(self):
        matrix = {"scenarios": [scenario(mode="offline")]}
        self.assertTrue(any("check" in error for error in R.validate_matrix(matrix)))

    def test_duplicate_id_is_rejected(self):
        matrix = {"scenarios": [scenario(), scenario()]}
        self.assertTrue(any("duplicate" in error for error in R.validate_matrix(matrix)))

    def test_malformed_contains_entry_is_rejected(self):
        matrix = {"scenarios": [scenario(artifacts={"contains": [{"path": "x"}]})]}
        self.assertTrue(any("contains" in error for error in R.validate_matrix(matrix)))

    def test_non_mapping_artifacts_is_rejected(self):
        matrix = {"scenarios": [scenario(artifacts=["x"])]}
        self.assertTrue(any("artifacts" in error for error in R.validate_matrix(matrix)))

    def test_contains_cannot_escape_the_repository(self):
        repo = Path(tempfile.mkdtemp())
        (repo.parent / "outside.txt").write_text("secret")
        declaration = scenario(
            artifacts={"contains": [{"path": "../outside.txt", "text": "secret"}]}
        )
        entries = R.evaluate_artifacts(declaration, {}, {}, repo, [])
        self.assertFalse(entries[0]["ok"])


class DigestTest(unittest.TestCase):
    def test_digest_changes_when_harness_input_changes(self):
        root = Path(tempfile.mkdtemp())
        (root / "input.txt").write_text("one")
        declaration = scenario(harness_inputs=["input.txt"])
        first = R.scenario_digest(declaration, root)
        (root / "input.txt").write_text("two")
        self.assertNotEqual(first, R.scenario_digest(declaration, root))

    def test_digest_changes_when_declaration_changes(self):
        root = Path(tempfile.mkdtemp())
        first = R.scenario_digest(scenario(), root)
        self.assertNotEqual(first, R.scenario_digest(scenario(prompt="other"), root))


class ForgeGuardTest(unittest.TestCase):
    def test_guard_intercepts_a_real_forge_call(self):
        workspace = Path(tempfile.mkdtemp())
        shim, log = R.install_forge_guard(workspace)
        env = R.forge_env(shim)
        result = subprocess.run(["gh", "issue", "list"], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("issue list", log.read_text())


class PaidCapTest(unittest.TestCase):
    def test_cap_is_retained_across_runs(self):
        out = Path(tempfile.mkdtemp())
        R.claim_session(out, 2)
        R.claim_session(out, None)
        with self.assertRaises(RuntimeError):
            R.claim_session(out, None)
        with self.assertRaises(RuntimeError):
            R.claim_session(out, 5)


class OfflineRunTest(unittest.TestCase):
    def test_matrix_runs_offline_and_review_promotes_to_pass(self):
        out = Path(tempfile.mkdtemp())
        matrix = R.load_matrix(R.DEFAULT_MATRIX)
        for declaration in matrix["scenarios"]:
            state, where = R.run_one(
                declaration, _HARNESS.parent, out, R.DEFAULT_FIXTURES, False, None
            )
            self.assertEqual(state, "unreviewed", where)
            attempt = Path(where)
            (attempt / "review.json").write_text(json.dumps({"reviewed": True}))
            digest = R.scenario_digest(declaration, _HARNESS.parent)
            self.assertEqual(R.evaluate(attempt, declaration, digest)[0], "pass")

    def test_failing_check_fails_the_attempt(self):
        out = Path(tempfile.mkdtemp())
        declaration = scenario(id="bad-check", mode="offline", check="exit 3")
        state, where = R.run_one(
            declaration, _HARNESS.parent, out, R.DEFAULT_FIXTURES, False, None
        )
        self.assertEqual(state, "fail", where)


class ReportTest(unittest.TestCase):
    def test_local_tooling_reported_separately(self):
        out = Path(tempfile.mkdtemp())
        text = R.report(R.load_matrix(R.DEFAULT_MATRIX), out, _HARNESS.parent)
        self.assertIn("local-tooling: pass", text)
        self.assertIn("behavioral-acceptance:", text)
        self.assertIn("incomplete (no attempt)", text)


class BenchTest(unittest.TestCase):
    def test_measure_stays_green_on_an_empty_home(self):
        home = Path(tempfile.mkdtemp())
        result = subprocess.run(
            [
                sys.executable, str(_HARNESS / "bench/measure.py"),
                "--split", "2026-01-01", "--since", "2026-01-01",
                "--home", str(home), "--client", "claude",
            ],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no sessions found", result.stdout)


if __name__ == "__main__":
    unittest.main()
