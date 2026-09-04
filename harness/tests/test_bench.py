#!/usr/bin/env python3

"""The session-population measurement in harness/bench, and its manual."""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from fixtures import ROOT, load_module


BENCH = ROOT / "harness" / "bench"


def lines(*records: dict) -> str:
    return "\n".join(json.dumps(record) for record in records)


def build_home(home: Path) -> None:
    """One session per client, each carrying every quirk the readers handle."""
    claude = home / ".claude" / "projects" / "repo"
    claude.mkdir(parents=True)
    (claude / "old.jsonl").write_text(lines(
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": [{"type": "text", "text": "go"}]}},
        {"type": "assistant", "timestamp": "2026-01-01T00:06:00Z",
         "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
        {"type": "user", "timestamp": "2026-01-01T00:06:30Z",
         "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        # Neither literal is optional: the client writes one or the other.
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True,
             "content": "The user doesn't want to proceed with this tool use"}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True,
             "content": "Permission to use Bash ... has been denied"}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": "boom"}]}},
        # A tool result that merely quotes the phrase is an error, not a
        # refusal: unanchored, this booked a denial that never happened.
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True,
             "content": "grep hit: the build has been denied by nobody"}]}},
        # Injected context and client bookkeeping are not human turns, and
        # there is one entry here per shape the reader has to recognise. A
        # builtin slash command leads with the name, a custom one with the
        # message, and counting only the first made one event count twice.
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "<command-name>/yolo</command-name>"}]}},
        {"type": "user", "message": {"content": [
            {"type": "text",
             "text": "<command-message>spec</command-message>\n"
                     "<command-name>/spec</command-name>"}]}},
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "<task-notification>done</task-notification>"}]}},
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "<local-command-stdout>out</local-command-stdout>"}]}},
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "<system-reminder>ping</system-reminder>"}]}},
        {"type": "user", "isMeta": True,
         "message": {"content": [{"type": "text", "text": "caveat"}]}},
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "[Request interrupted by user]"}]}},
        # A real prompt arrives with its reminders attached, and one of those
        # riding along must not cancel the turn.
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "and again"},
            {"type": "text", "text": "<system-reminder>ping</system-reminder>"}]}},
    ))
    # A subagent sidecar is this session's delegation, never a session itself.
    sidecar = claude / "old" / "subagents"
    sidecar.mkdir(parents=True)
    (sidecar / "agent-1.jsonl").write_text(lines(
        {"type": "user", "timestamp": "2026-01-01T00:01:00Z",
         "message": {"content": [{"type": "text", "text": "sub"}]}},
        {"type": "assistant", "message": {"content": []}},
        # Not a message, so it is not delegation either.
        {"type": "summary", "summary": "ignored"},
    ))
    (claude / "new.jsonl").write_text(lines(
        {"type": "user", "timestamp": "2026-03-01T00:00:00Z",
         "message": {"content": [{"type": "text", "text": "go"}]}},
        {"type": "assistant", "timestamp": "2026-03-01T00:01:00Z",
         "message": {"content": [
             {"type": "tool_use", "name": "Bash"},
             {"type": "tool_use", "name": "Read"}]}},
    ))
    (claude / "junk.jsonl").write_text("not json\n")

    codex = home / ".codex" / "sessions" / "2026" / "03" / "01"
    codex.mkdir(parents=True)
    (codex / "rollout-2026-03-01T00-00-00-abc.jsonl").write_text(lines(
        {"type": "session_meta", "timestamp": "2026-03-01T00:00:00Z",
         "payload": {"cwd": "/Users/me/projects/hobby"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user"}},
        {"type": "response_item", "payload": {"type": "message", "role": "developer"}},
        {"type": "response_item", "payload": {"type": "function_call"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call"}},
        {"type": "event_msg", "timestamp": "2026-03-01T00:02:00Z",
         "payload": {"type": "turn_aborted", "reason": "interrupted"}},
    ))

    opencode = home / ".local" / "share" / "opencode"
    opencode.mkdir(parents=True)
    connection = sqlite3.connect(opencode / "opencode.db")
    connection.executescript(
        "create table session (id text, parent_id text, directory text,"
        " time_created integer, time_updated integer);"
        "create table message (id text, session_id text, data text);"
        "create table part (id text, session_id text, data text);"
    )
    created = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000)
    connection.executemany(
        "insert into session values (?, ?, ?, ?, ?)",
        # `s2` is a subagent of `s1`: delegation, not a second session.
        [("s1", None, "/Users/me/projects/hobby", created, created + 180_000),
         ("s2", "s1", "/Users/me/projects/hobby", created, created + 60_000)],
    )
    connection.executemany(
        "insert into message values (?, ?, ?)",
        [("m1", "s1", '{"role": "user"}'), ("m2", "s1", '{"role": "assistant"}'),
         ("m3", "s2", '{"role": "user"}')],
    )
    connection.executemany(
        "insert into part values (?, ?, ?)",
        [("p1", "s1", '{"type": "tool"}'), ("p2", "s1", '{"type": "text"}')],
    )
    connection.commit()
    connection.close()


class BenchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.measure = load_module("measure", BENCH / "measure.py")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        build_home(self.home)
        self.sessions = self.measure.collect(
            self.home, ["claude", "codex", "opencode"], work=[]
        )
        self.by_client: dict[str, list[dict]] = {}
        # By date, not by filename: `new.jsonl` sorts before `old.jsonl`.
        for entry in sorted(self.sessions, key=lambda s: s["date"]):
            self.by_client.setdefault(entry["client"], []).append(entry)

    def test_claude_counts_only_human_turns(self) -> None:
        old, new = self.by_client["claude"]
        # Only `go` and `and again`. A tool result, both slash-command shapes,
        # a task notification, local-command stdout, a system reminder, an
        # isMeta caveat and an interrupt marker all arrive as `user` entries.
        self.assertEqual((old["turns"], new["turns"]), (2, 1))
        self.assertEqual((old["tool_calls"], new["tool_calls"]), (1, 2))
        # Both shapes of one event count once each, never differently.
        self.assertEqual(old["commands"], 2)
        self.assertEqual(old["interrupts"], 1)
        self.assertEqual(old["minutes"], 6.5)

    def test_each_injected_shape_alone_is_not_a_turn(self) -> None:
        # One entry per literal, so dropping any single one from
        # `CLAUDE_NON_TURN` fails rather than leaving the suite green.
        for text in ("<command-name>/x</command-name>",
                     "<command-message>x</command-message>\n<command-name>/x</command-name>",
                     "<task-notification>done</task-notification>",
                     "<local-command-stdout>out</local-command-stdout>",
                     "<system-reminder>ping</system-reminder>",
                     "[Request interrupted by user]"):
            path = self.home / ".claude" / "projects" / "repo" / "solo.jsonl"
            path.write_text(lines(
                {"type": "user", "timestamp": "2026-03-01T00:00:00Z",
                 "message": {"content": [{"type": "text", "text": text}]}},
            ))
            self.assertEqual(self.measure.read_claude(path)["turns"], 0, text)

    def test_claude_separates_a_refusal_from_a_failure(self) -> None:
        old = self.by_client["claude"][0]
        # Both refusal sentences count and neither is also an error, while a
        # result that merely quotes `has been denied` is an error only.
        self.assertEqual((old["denials"], old["errors"]), (2, 2))

    def test_a_subagent_is_delegation_not_a_session(self) -> None:
        claude = self.by_client["claude"]
        self.assertEqual([s["turns"] for s in claude], [2, 1])
        # The sidecar holds two messages and one non-message entry.
        self.assertEqual([s["delegation"] for s in claude], [2, 0])

        opencode = self.by_client["opencode"]
        self.assertEqual(len(opencode), 1)
        self.assertEqual(opencode[0]["turns"], 1)
        self.assertEqual(opencode[0]["tool_calls"], 1)
        self.assertEqual(opencode[0]["delegation"], 1)
        self.assertEqual(opencode[0]["minutes"], 3.0)
        self.assertIsNone(opencode[0]["interrupts"])

    def test_codex_reads_its_own_rollout_format(self) -> None:
        self.assertEqual(
            self.by_client["codex"],
            [{"client": "codex", "date": date(2026, 3, 1),
              "project": "/Users/me/projects/hobby", "cohort": "personal",
              "turns": 1, "tool_calls": 2, "minutes": 2.0, "commands": None,
              "delegation": None, "interrupts": 1, "denials": None,
              "errors": None}],
        )

    def test_report_marks_an_absent_metric_and_a_thin_cohort(self) -> None:
        text = self.measure.report(self.sessions, date(2026, 2, 1), None)
        self.assertRegex(text, r"tool_calls\s+1\.0\s+2\.0\s+\+1\.0")
        # A metric a client never records is reported as absent, not zero.
        self.assertRegex(text, r"denials\s+-\s+-\s+-")
        self.assertIn("fewer than", text)

    def test_rows_emit_one_json_object_per_session(self) -> None:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = self.measure.main(
                ["--split", "2026-02-01", "--home", str(self.home), "--rows"]
            )
        self.assertEqual(code, 0)
        rows = [json.loads(line) for line in captured.getvalue().splitlines()]
        self.assertEqual(len(rows), len(self.sessions))
        # The date has to survive the round trip, or a row cannot be binned.
        self.assertEqual(rows[0]["date"], "2026-01-01")

    def test_rows_honour_the_same_window_as_the_report(self) -> None:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            self.measure.main(["--split", "2026-02-01", "--home", str(self.home),
                               "--since", "2026-02-01", "--rows"])
        dates = {json.loads(l)["date"] for l in captured.getvalue().splitlines()}
        # Rows outside the window are not the distribution behind any median.
        self.assertNotIn("2026-01-01", dates)

    def test_one_pattern_matches_every_client_project_format(self) -> None:
        # Claude names a project by its path with the separators rewritten as
        # dashes; Codex and OpenCode record the path. One pattern has to reach
        # all three or a cohort is silently client-shaped.
        self.assertEqual(
            self.measure.canon("-Users-me-projects-sir-backoffice-laravel"),
            self.measure.canon("/Users/me/projects/sir/backoffice/laravel"),
        )
        for project in ("-Users-me-projects-acme", "/Users/me/projects/acme",
                        "/Users/me/orca/workspaces/acme/issue-12"):
            self.assertEqual(self.measure.cohort(project, ["acme"]), "work")
        self.assertEqual(self.measure.cohort("/Users/me/hobby", ["acme"]), "personal")
        # A session whose client records no project cannot be called work.
        self.assertEqual(self.measure.cohort(None, ["acme"]), "personal")

    def test_report_splits_by_cohort_only_once_one_is_configured(self) -> None:
        plain = self.measure.report(self.sessions, date(2026, 2, 1), None)
        self.assertIn("\nclaude\n", plain)
        self.assertNotIn("personal", plain)

        split = self.measure.collect(
            self.home, ["claude", "codex", "opencode"], work=["repo"]
        )
        text = self.measure.report(split, date(2026, 2, 1), None)
        # The Claude fixture lives in a project named `repo`; the others do not.
        self.assertIn("claude  work", text)
        self.assertIn("codex  personal", text)
        self.assertNotIn("claude  personal", text)

    def test_manual_documents_every_metric_and_flag(self) -> None:
        # The manual is the only place the metrics are explained, so it is the
        # place that goes stale when one is renamed.
        manual = (BENCH / "README.md").read_text()
        for metric in self.measure.METRICS:
            self.assertIn(f"`{metric}`", manual, metric)
        for flag in ("--split", "--since", "--client", "--home", "--rows"):
            self.assertIn(flag, manual, flag)
        self.assertIn(str(self.measure.THIN), manual)


if __name__ == "__main__":
    unittest.main()
