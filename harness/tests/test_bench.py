#!/usr/bin/env python3

"""The session-population measurement in harness/bench, and its manual."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from fixtures import ROOT, load_module


BENCH = ROOT / "harness" / "bench"


class BenchTests(unittest.TestCase):
    def test_bench_reads_every_client_session_store(self) -> None:
        measure = load_module("measure", BENCH / "measure.py")

        def lines(*records: dict) -> str:
            return "\n".join(json.dumps(record) for record in records)

        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)

            claude = home / ".claude" / "projects" / "repo"
            claude.mkdir(parents=True)
            (claude / "old.jsonl").write_text(lines(
                {"type": "user", "timestamp": "2026-01-01T00:00:00Z",
                 "message": {"content": [{"type": "text", "text": "go"}]}},
                {"type": "assistant",
                 "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
                {"type": "user",
                 "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
                {"type": "user", "message": {"content": [
                    {"type": "text", "text": "[Request interrupted by user]"}]}},
            ))
            (claude / "new.jsonl").write_text(lines(
                {"type": "user", "timestamp": "2026-03-01T00:00:00Z",
                 "message": {"content": [{"type": "text", "text": "go"}]}},
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Bash"},
                    {"type": "tool_use", "name": "Read"}]}},
            ))
            (claude / "junk.jsonl").write_text("not json\n")

            codex = home / ".codex" / "sessions" / "2026" / "03" / "01"
            codex.mkdir(parents=True)
            (codex / "rollout-2026-03-01T00-00-00-abc.jsonl").write_text(lines(
                {"type": "session_meta", "timestamp": "2026-03-01T00:00:00Z"},
                {"type": "response_item", "payload": {"type": "message", "role": "user"}},
                {"type": "response_item", "payload": {"type": "message", "role": "developer"}},
                {"type": "response_item", "payload": {"type": "function_call"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call"}},
                {"type": "event_msg",
                 "payload": {"type": "turn_aborted", "reason": "interrupted"}},
            ))

            opencode = home / ".local" / "share" / "opencode"
            opencode.mkdir(parents=True)
            connection = sqlite3.connect(opencode / "opencode.db")
            connection.executescript(
                "create table session (id text, time_created integer);"
                "create table message (id text, session_id text, data text);"
                "create table part (id text, session_id text, data text);"
            )
            created = int(
                datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000
            )
            connection.execute("insert into session values ('s1', ?)", (created,))
            connection.executemany(
                "insert into message values (?, 's1', ?)",
                [("m1", '{"role": "user"}'), ("m2", '{"role": "assistant"}')],
            )
            connection.executemany(
                "insert into part values (?, 's1', ?)",
                [("p1", '{"type": "tool"}'), ("p2", '{"type": "text"}')],
            )
            connection.commit()
            connection.close()

            sessions = measure.collect(home, ["claude", "codex", "opencode"])
            by_client: dict[str, list[dict]] = {}
            for entry in sessions:
                by_client.setdefault(entry["client"], []).append(entry)

            self.assertEqual(len(by_client["claude"]), 2)
            self.assertEqual(
                [s["tool_calls"] for s in by_client["claude"]], [2, 1]
            )
            self.assertEqual(sum(s["turns"] for s in by_client["claude"]), 3)
            self.assertEqual(sum(s["interrupts"] for s in by_client["claude"]), 1)

            self.assertEqual(len(by_client["codex"]), 1)
            self.assertEqual(
                by_client["codex"][0]
                | {"client": "codex", "date": date(2026, 3, 1)},
                {"client": "codex", "date": date(2026, 3, 1), "turns": 1,
                 "tool_calls": 2, "interrupts": 1, "denials": None},
            )

            self.assertEqual(len(by_client["opencode"]), 1)
            self.assertEqual(by_client["opencode"][0]["turns"], 1)
            self.assertEqual(by_client["opencode"][0]["tool_calls"], 1)
            self.assertIsNone(by_client["opencode"][0]["interrupts"])

            text = measure.report(sessions, date(2026, 2, 1), None)
            self.assertRegex(text, r"tool_calls\s+1\.0\s+2\.0\s+\+1\.0")
            # A metric a client never records is reported as absent, not zero.
            self.assertRegex(text, r"denials\s+-\s+-\s+-")
            self.assertIn("fewer than", text)

    def test_manual_documents_every_metric_and_flag(self) -> None:
        # The manual is the only place the metrics are explained, so it is the
        # place that goes stale when one is renamed.
        measure = load_module("measure", BENCH / "measure.py")
        manual = (BENCH / "README.md").read_text()
        for metric in measure.METRICS:
            self.assertIn(f"`{metric}`", manual, metric)
        for flag in ("--split", "--since", "--client", "--home"):
            self.assertIn(flag, manual, flag)
        self.assertIn(str(measure.THIN), manual)


if __name__ == "__main__":
    unittest.main()
