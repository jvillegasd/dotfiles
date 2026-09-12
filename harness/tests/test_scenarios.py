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


def write_attempt(path, digest="abc", ok=True, review=False, metrics=None):
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
    if metrics is None:
        metrics = {
            "scenario": "s",
            "model": None,
            "input_tokens": None,
            "output_tokens": None,
            "cached_input": None,
            "tool_calls": 0,
            "command_output_bytes": 0,
            "wall_seconds": 0.0,
            "terminal_status": "ok",
        }
    (path / "metrics.json").write_text(json.dumps(metrics))
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


class MetricsTest(unittest.TestCase):
    def test_complete_usage_from_a_summary_event(self):
        events = [
            {
                "type": "result",
                "model": "claude-x",
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 340,
                    "cache_read_input_tokens": 800,
                },
            }
        ]
        self.assertEqual(
            R.parse_usage(events),
            {"input_tokens": 1200, "output_tokens": 340, "cached_input": 800},
        )
        self.assertEqual(R.model_from_events(events), "claude-x")

    def test_missing_usage_is_unknown_not_zero(self):
        self.assertEqual(
            R.parse_usage([{"type": "result"}]),
            {"input_tokens": None, "output_tokens": None, "cached_input": None},
        )

    def test_malformed_usage_is_unknown(self):
        events = [
            {"type": "result", "usage": "nope"},
            {"type": "assistant", "message": {"usage": {"input_tokens": "lots"}}},
        ]
        self.assertEqual(
            R.parse_usage(events),
            {"input_tokens": None, "output_tokens": None, "cached_input": None},
        )

    def test_per_message_usage_is_summed_without_a_summary(self):
        events = [
            {"type": "assistant", "message": {"usage": {"input_tokens": 10, "output_tokens": 2}}},
            {"type": "assistant", "message": {"usage": {"input_tokens": 5, "output_tokens": 3}}},
        ]
        self.assertEqual(
            R.parse_usage(events),
            {"input_tokens": 15, "output_tokens": 5, "cached_input": None},
        )

    def test_cached_usage_variants_are_normalized(self):
        self.assertEqual(
            R.parse_usage(
                [{"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 1, "cached_input_tokens": 2}}]
            )["cached_input"],
            2,
        )
        self.assertEqual(
            R.parse_usage(
                [{"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 1, "prompt_tokens_details": {"cached_tokens": 3}}}]
            )["cached_input"],
            3,
        )

    def test_terminal_status(self):
        self.assertEqual(R.terminal_status(None), "unknown")
        self.assertEqual(R.terminal_status(0), "ok")
        self.assertEqual(R.terminal_status(3), "failed")
        self.assertEqual(R.terminal_status(-9), "interrupted")
        self.assertEqual(R.terminal_status(143), "interrupted")

    def test_tool_calls_are_counted(self):
        events = [
            {"type": "tool_use"},
            {"type": "assistant", "message": {"content": [{"type": "tool_use"}, {"type": "text"}]}},
            {"type": "tool_result"},
        ]
        self.assertEqual(R.count_tool_calls(events), 2)

    def test_command_output_bytes_counts_tool_results(self):
        events = [
            {"type": "tool_result", "content": "abc"},
            {"type": "tool_result", "content": "de"},
            {"type": "assistant"},
        ]
        self.assertEqual(R.command_output_bytes(events), 5)

    def test_command_output_bytes_counts_nested_stream_tool_results(self):
        events = [
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "content": [{"type": "text", "text": "abc"}]}
                    ]
                },
            }
        ]
        self.assertEqual(R.command_output_bytes(events), 3)

    def test_codex_item_events_count_tool_calls_and_output(self):
        events = [
            {"type": "item.completed", "item": {"type": "command_execution", "aggregated_output": "abc"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
        ]
        self.assertEqual(R.count_tool_calls(events), 1)
        self.assertEqual(R.command_output_bytes(events), 3)

    def test_build_metrics_carries_every_field(self):
        scenario = {"id": "s"}
        events = [{"type": "result", "model": "m", "usage": {"input_tokens": 1, "output_tokens": 2}}]
        record = R.build_metrics(scenario, events, 1.5, "ok")
        self.assertEqual(set(record), set(R.METRIC_FIELDS))
        self.assertEqual(record["scenario"], "s")
        self.assertEqual(record["model"], "m")
        self.assertEqual(record["input_tokens"], 1)
        self.assertEqual(record["wall_seconds"], 1.5)
        self.assertEqual(record["terminal_status"], "ok")


class ReadOnlyOracleTest(unittest.TestCase):
    def test_fixture_write_fails_the_read_only_scenario(self):
        repo = Path(tempfile.mkdtemp())
        declaration = scenario(artifacts={"fixtures_unchanged": True})
        entries = R.evaluate_artifacts(
            declaration, {}, {}, repo, [], fixtures_unchanged=False
        )
        self.assertFalse(entries[0]["ok"])

    def test_forge_call_fails_the_read_only_scenario(self):
        repo = Path(tempfile.mkdtemp())
        declaration = scenario(artifacts={"tree_unchanged": True})
        entries = R.evaluate_artifacts(
            declaration, {"a": "b"}, {"a": "b"}, repo, ["issue list"]
        )
        forge = next(e for e in entries if e["name"] == "no-external-forge")
        self.assertFalse(forge["ok"])

    def test_shipped_read_only_scenarios_declare_no_write_checks(self):
        matrix = R.load_matrix(R.DEFAULT_MATRIX)
        for scenario_id in ("ask-read-only", "read-only-execution"):
            declaration = next(
                s for s in matrix["scenarios"] if s["id"] == scenario_id
            )
            self.assertTrue(declaration["artifacts"].get("tree_unchanged"))
            self.assertTrue(declaration["artifacts"].get("fixtures_unchanged"))

    def test_read_only_execution_runs_a_command(self):
        matrix = R.load_matrix(R.DEFAULT_MATRIX)
        declaration = next(
            s for s in matrix["scenarios"] if s["id"] == "read-only-execution"
        )
        self.assertEqual(declaration["mode"], "offline")
        self.assertTrue(declaration["check"])


class InterruptedStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scenario = scenario()

    def test_interrupted_beats_a_failing_artifact_check(self):
        attempt = self.tmp / "attempt"
        write_attempt(
            attempt, ok=False, metrics={"terminal_status": "interrupted"}
        )
        self.assertEqual(R.evaluate(attempt, self.scenario, "abc")[0], "interrupted")

    def test_missing_metrics_is_incomplete(self):
        attempt = self.tmp / "attempt"
        write_attempt(attempt, ok=True, review=True)
        (attempt / "metrics.json").unlink()
        self.assertEqual(R.evaluate(attempt, self.scenario, "abc")[0], "incomplete")


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.scenario = scenario(id="ask-read-only")
        self.matrix = {"scenarios": [self.scenario]}
        self.digest = R.scenario_digest(self.scenario, self.tmp)

    def batch(self, side, attempts, digest=None):
        digest = digest or self.digest
        for index, spec in enumerate(attempts):
            path = self.tmp / side / self.scenario["id"] / f"a{index}-{digest[:8]}"
            write_attempt(
                path,
                digest=digest,
                ok=spec.get("ok", True),
                review=spec.get("reviewed", True),
                metrics={
                    "scenario": self.scenario["id"],
                    "model": spec.get("model"),
                    "input_tokens": spec.get("input_tokens"),
                    "output_tokens": spec.get("output_tokens"),
                    "cached_input": spec.get("cached_input"),
                    "tool_calls": spec.get("tool_calls", 0),
                    "command_output_bytes": spec.get("command_output_bytes", 0),
                    "wall_seconds": spec.get("wall_seconds", 1.0),
                    "terminal_status": spec.get("terminal", "ok"),
                },
            )

    def compare(self):
        return R.compare(
            self.tmp / "before", self.tmp / "after", self.matrix, self.tmp
        )

    def test_pass_rates_are_reported_before_efficiency(self):
        self.batch("before", [{"model": "m1", "input_tokens": 100}])
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        text = self.compare()
        self.assertLess(text.index("pass rate"), text.index("efficiency"))

    def test_failed_baseline_is_never_an_efficiency_win(self):
        self.batch("before", [{"model": "m1", "ok": False, "input_tokens": 100}])
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        text = self.compare()
        self.assertIn("no comparable pair", text)

    def test_unlike_models_are_never_pooled(self):
        self.batch("before", [{"model": "m1", "input_tokens": 100}])
        self.batch("after", [{"model": "m2", "input_tokens": 80}])
        self.assertIn("no comparable pair", self.compare())

    def test_a_single_successful_pair_is_smoke(self):
        self.batch("before", [{"model": "m1", "input_tokens": 100}])
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        self.assertIn("smoke", self.compare())

    def test_two_successful_pairs_are_not_smoke(self):
        self.batch(
            "before",
            [{"model": "m1", "input_tokens": 100}, {"model": "m2", "input_tokens": 100}],
        )
        self.batch(
            "after",
            [{"model": "m1", "input_tokens": 80}, {"model": "m2", "input_tokens": 80}],
        )
        self.assertNotIn("smoke", self.compare())

    def test_nonpassing_attempts_remain_visible(self):
        self.batch(
            "before",
            [{"model": "m1", "terminal": "interrupted"}, {"model": "m1", "reviewed": False}],
        )
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        text = self.compare()
        self.assertIn("interrupted", text)
        self.assertIn("unreviewed", text)

    def test_unavailable_scenario_is_visible(self):
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        self.assertIn("unavailable", self.compare())

    def test_cross_version_batches_still_pair(self):
        self.batch("before", [{"model": "m1", "input_tokens": 100}], digest="oldharness")
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        self.assertNotIn("no comparable pair", self.compare())

    def test_within_batch_drift_is_visible_as_stale(self):
        self.batch(
            "before",
            [{"model": "m1", "input_tokens": 100}, {"model": "m1", "input_tokens": 90}],
            digest="newharness",
        )
        drifted = self.tmp / "before" / self.scenario["id"] / "0-old"
        write_attempt(drifted, digest="oldharness", ok=True, review=True)
        self.batch("after", [{"model": "m1", "input_tokens": 80}])
        text = self.compare()
        self.assertIn("stale=1", text)
        self.assertIn("pass 2/3", text)


if __name__ == "__main__":
    unittest.main()
