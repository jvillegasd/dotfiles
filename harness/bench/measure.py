#!/usr/bin/env python3
"""Compare the real session population before and after a harness change.

The harness is portable, so this reads all three clients' own session stores:
Claude Code JSONL transcripts, Codex rollout JSONL, and the OpenCode SQLite
database. Cost and friction only. Quality stays a human read of the sessions.

A metric a client does not record is reported as `-`, never as zero.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

METRICS = ("turns", "tool_calls", "interrupts", "denials")
THIN = 20

CLAUDE_INTERRUPT = "[Request interrupted by user"
CLAUDE_DENIAL = "The user doesn't want to proceed with this tool use"
CODEX_TOOL_CALLS = {"function_call", "custom_tool_call"}


def entries(path: Path):
    """Yield the parsed dict lines of a JSONL transcript, skipping damage."""
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield entry


def parse_stamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def session(client: str, started: datetime, **counts) -> dict:
    return {"client": client, "date": started.date(), **counts}


# --- Claude Code: ~/.claude/projects/<slug>/<session>.jsonl -------------------


def claude_text(block: dict) -> str:
    value = block.get("text") or block.get("content") or ""
    return value if isinstance(value, str) else json.dumps(value)


def read_claude(path: Path) -> dict | None:
    started = None
    turns = tools = interrupts = denials = 0
    for entry in entries(path):
        started = started or parse_stamp(entry.get("timestamp"))
        content = (entry.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if entry.get("type") == "user":
            # A tool result is the harness answering itself, not a human turn.
            if not any(b.get("type") == "tool_result" for b in blocks):
                turns += 1
            for block in blocks:
                body = claude_text(block)
                interrupts += body.count(CLAUDE_INTERRUPT)
                denials += body.count(CLAUDE_DENIAL)
        elif entry.get("type") == "assistant":
            tools += sum(b.get("type") == "tool_use" for b in blocks)
    if started is None:
        return None
    return session(
        "claude", started,
        turns=turns, tool_calls=tools, interrupts=interrupts, denials=denials,
    )


def claude_sessions(home: Path) -> list[dict]:
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return []
    return [s for path in sorted(root.rglob("*.jsonl")) if (s := read_claude(path))]


# --- Codex: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl ----------------------


def read_codex(path: Path) -> dict | None:
    started = None
    turns = tools = interrupts = 0
    for entry in entries(path):
        started = started or parse_stamp(entry.get("timestamp"))
        payload = entry.get("payload") or {}
        kind = payload.get("type")
        if entry.get("type") == "response_item":
            if kind == "message" and payload.get("role") == "user":
                turns += 1
            elif kind in CODEX_TOOL_CALLS:
                tools += 1
        elif kind == "turn_aborted" and payload.get("reason") == "interrupted":
            interrupts += 1
    if started is None:
        return None
    # Codex does not record a declined tool call distinguishably.
    return session(
        "codex", started,
        turns=turns, tool_calls=tools, interrupts=interrupts, denials=None,
    )


def codex_sessions(home: Path) -> list[dict]:
    root = home / ".codex" / "sessions"
    if not root.is_dir():
        return []
    return [s for path in sorted(root.rglob("rollout-*.jsonl")) if (s := read_codex(path))]


# --- OpenCode: ~/.local/share/opencode/opencode.db ---------------------------


OPENCODE_QUERY = """
select s.time_created,
       (select count(*) from message m
         where m.session_id = s.id and json_extract(m.data, '$.role') = 'user'),
       (select count(*) from part p
         where p.session_id = s.id and json_extract(p.data, '$.type') = 'tool')
from session s
"""


def opencode_sessions(home: Path) -> list[dict]:
    db = home / ".local" / "share" / "opencode" / "opencode.db"
    if not db.is_file():
        return []
    # Read-only: the database may belong to a running client.
    connection = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    try:
        rows = connection.execute(OPENCODE_QUERY).fetchall()
    except sqlite3.DatabaseError as error:
        print(f"opencode: {error}", file=sys.stderr)
        return []
    finally:
        connection.close()
    return [
        # OpenCode records neither interrupts nor tool denials durably.
        session(
            "opencode",
            datetime.fromtimestamp(created / 1000, timezone.utc),
            turns=turns, tool_calls=tools, interrupts=None, denials=None,
        )
        for created, turns, tools in rows
    ]


READERS = {
    "claude": claude_sessions,
    "codex": codex_sessions,
    "opencode": opencode_sessions,
}


def collect(home: Path, clients: list[str]) -> list[dict]:
    return [s for client in clients for s in READERS[client](home)]


def median(sessions: list[dict], metric: str) -> float | None:
    values = [s[metric] for s in sessions if s[metric] is not None]
    return statistics.median(values) if values else None


def cell(value: float | None) -> str:
    return f"{value:>10.1f}" if value is not None else f"{'-':>10}"


def report(sessions: list[dict], split: date, since: date | None) -> str:
    if since:
        sessions = [s for s in sessions if s["date"] >= since]
    lines = [
        f"split {split.isoformat()}" + (f"  since {since.isoformat()}" if since else "")
    ]
    for client in READERS:
        cohort = [s for s in sessions if s["client"] == client]
        if not cohort:
            continue
        before = [s for s in cohort if s["date"] < split]
        after = [s for s in cohort if s["date"] >= split]
        lines += [
            "",
            client,
            f"  {'metric':<12}{'before':>10}{'after':>10}{'delta':>10}",
            f"  {'sessions':<12}{len(before):>10}{len(after):>10}{'':>10}",
        ]
        for metric in METRICS:
            b, a = median(before, metric), median(after, metric)
            delta = f"{a - b:>+10.1f}" if b is not None and a is not None else f"{'-':>10}"
            lines.append(f"  {metric:<12}{cell(b)}{cell(a)}{delta}")
        if len(before) < THIN or len(after) < THIN:
            lines.append(f"  warning: a cohort has fewer than {THIN} sessions; noise, not a result.")
    if len(lines) == 1:
        lines.append("no sessions found")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, type=date.fromisoformat,
                        help="commit date of the harness change under test")
    parser.add_argument("--since", type=date.fromisoformat,
                        help="ignore sessions older than this date")
    parser.add_argument("--client", action="append", choices=sorted(READERS),
                        help="limit to one client; repeatable (default: all three)")
    parser.add_argument("--home", type=Path, default=Path.home(),
                        help="session-store root (default: the current home)")
    args = parser.parse_args(argv)

    print(report(collect(args.home, args.client or list(READERS)), args.split, args.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
