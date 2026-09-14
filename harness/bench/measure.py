#!/usr/bin/env python3
"""Compare the real session population before and after a harness change.

The harness is portable, so this reads both clients' own session stores:
Claude Code JSONL transcripts and the OpenCode SQLite database. Cost and
friction only. Quality stays a human read of the sessions.

A metric a client does not record is reported as `-`, never as zero.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path

METRICS = (
    "turns", "tool_calls", "minutes",
    "commands", "delegation",
    "interrupts", "denials", "errors",
)
THIN = 20

CLAUDE_INTERRUPT = "[Request interrupted by user"
# Claude Code writes one of two sentences when a human refuses a call, and
# which one depends on how the refusal arrived. Matching only the first read
# 22 of this machine's 54 refusals as zero friction.
# `has been denied` is anchored on the sentence around it: unanchored, the
# phrase matched a grep of this very file quoted back in a tool result, which
# booked a refusal that never happened and removed a real error from `errors`.
CLAUDE_DENIALS = (
    ("The user doesn't want to proceed with this tool use",),
    ("Permission to use ", " has been denied"),
)
# Injected context and client bookkeeping arrive as `user` entries, and there
# are more shapes than are obvious. A slash command is written two ways: the
# builtins lead with `<command-name>`, a custom command with the message, and
# counting only the first form made the two halves of one event disagree.
# Subagent completions arrive as `<task-notification>` with `isMeta` unset, and
# they were the largest miss of all, 422 against 1444 counted turns, which also
# tied the turn metric to the delegation metric printed two rows below it.
CLAUDE_NON_TURN = (
    CLAUDE_INTERRUPT,
    "<command-name>",
    "<command-message",
    "<local-command",
    "<system-reminder>",
    "<task-notification>",
)

HERE = Path(__file__).resolve().parent
COHORTS = "cohorts.json"


def patterns() -> list[str]:
    """The project patterns that mark a session as work.

    `cohorts.json` is gitignored, because naming a client or an employer is
    exactly what it does. The committed example names nobody, so an unconfigured
    checkout reports one population and never a misleading split.
    """
    for name in (COHORTS, "cohorts.example.json"):
        try:
            return json.loads((HERE / name).read_text()).get("work") or []
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError, AttributeError) as error:
            # Falling through silently would report every session as personal,
            # which is indistinguishable from having configured no cohorts.
            print(f"{name}: {error}", file=sys.stderr)
            return []
    return []


def canon(value: str) -> str:
    """Fold a project to one comparable shape.

    Claude Code names a project by its path with the separators rewritten as
    dashes, while OpenCode records the path itself. Folding both runs of `-`
    and `/` to a single separator on both the pattern and the project is what
    lets one pattern match a session from either client.
    """
    return re.sub(r"[-/]+", "/", value).lower()


def cohort(project: str | None, work: list[str]) -> str:
    if project is None:
        return "personal"
    folded = canon(project)
    return "work" if any(canon(p) in folded for p in work) else "personal"


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


def elapsed(first: datetime | None, last: datetime | None) -> float | None:
    if first is None or last is None:
        return None
    return round((last - first).total_seconds() / 60, 1)


def session(client: str, started: datetime, project: str | None, **counts) -> dict:
    filled = {metric: counts.get(metric) for metric in METRICS}
    return {"client": client, "date": started.date(), "project": project, **filled}


# --- Claude Code: ~/.claude/projects/<slug>/<session>.jsonl -------------------


def claude_text(block: dict) -> str:
    value = block.get("text") or block.get("content") or ""
    return value if isinstance(value, str) else json.dumps(value, default=str)


def claude_delegation(path: Path) -> int:
    """Messages in this session's subagent sidecars.

    Subagent entries moved out of the transcript into
    `<session-id>/subagents/*.jsonl`. The inline `isSidechain` flag they used
    to carry is still written on every entry and is now always false, so a
    reader that still looks there reports no delegation at all rather than
    reporting that it cannot see any.
    """
    sidecars = path.parent / path.stem / "subagents"
    return sum(
        sum(entry.get("type") in ("user", "assistant") for entry in entries(side))
        for side in sorted(sidecars.glob("*.jsonl"))
    )


def read_claude(path: Path) -> dict | None:
    first = last = None
    turns = tools = commands = interrupts = denials = errors = 0
    for entry in entries(path):
        stamp = parse_stamp(entry.get("timestamp"))
        if stamp:
            first = first or stamp
            last = stamp
        content = (entry.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else [{"text": content}]
        blocks = [b for b in blocks if isinstance(b, dict)]

        if entry.get("type") == "assistant":
            tools += sum(b.get("type") == "tool_use" for b in blocks)
            continue
        if entry.get("type") != "user":
            continue

        # An entry is a turn when it carries at least one block a human
        # actually typed. Anything the client injected can ride along in the
        # same entry, so this is per block: a real prompt arrives with its
        # system reminders attached, and one of those must not cancel it.
        typed = False
        for block in blocks:
            body = claude_text(block)
            if block.get("type") == "tool_result":
                # A tool result is the harness answering itself, never a turn.
                if any(all(part in body for part in literal)
                       for literal in CLAUDE_DENIALS):
                    denials += 1
                elif block.get("is_error"):
                    errors += 1
                continue
            commands += body.count("<command-name>")
            interrupts += body.count(CLAUDE_INTERRUPT)
            typed = typed or bool(
                body.strip()
            ) and not body.lstrip().startswith(CLAUDE_NON_TURN)
        turns += typed and not entry.get("isMeta")

    if first is None:
        return None
    return session(
        "claude", first, path.parent.name,
        turns=turns, tool_calls=tools, minutes=elapsed(first, last),
        commands=commands, delegation=claude_delegation(path),
        interrupts=interrupts, denials=denials, errors=errors,
    )


def claude_sessions(home: Path) -> list[dict]:
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return []
    # `<project>/<session>.jsonl` only. Recursing swept the subagent sidecars
    # in as sessions of their own, and on this machine that was 271 phantom
    # sessions against 209 real ones: every median was a median of the wrong
    # population.
    return [s for path in sorted(root.glob("*/*.jsonl")) if (s := read_claude(path))]


# --- OpenCode: ~/.local/share/opencode/opencode.db ---------------------------


# A row per top-level session. OpenCode gives a subagent a session of its own
# carrying the parent's id, so the parents are the population and the children
# are that population's delegation, exactly as the Claude sidecars are.
OPENCODE_QUERY = """
select s.time_created,
       s.time_updated,
       s.directory,
       (select count(*) from message m
         where m.session_id = s.id and json_extract(m.data, '$.role') = 'user'),
       (select count(*) from part p
         where p.session_id = s.id and json_extract(p.data, '$.type') = 'tool'),
       (select count(*) from message m join session c on c.id = m.session_id
         where c.parent_id = s.id)
from session s
where s.parent_id is null
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

    def moment(millis: int) -> datetime:
        return datetime.fromtimestamp(millis / 1000, timezone.utc)

    return [
        # OpenCode records no interrupt, no declined call, no failed result,
        # and no slash command durably.
        session(
            "opencode", moment(created), directory,
            turns=turns, tool_calls=tools,
            minutes=elapsed(moment(created), moment(updated)),
            delegation=delegated,
        )
        for created, updated, directory, turns, tools, delegated in rows
    ]


READERS = {
    "claude": claude_sessions,
    "opencode": opencode_sessions,
}


def collect(home: Path, clients: list[str], work: list[str] | None = None) -> list[dict]:
    # `work` is a parameter for the same reason `home` is: a caller that needs
    # a specific set passes one, rather than inheriting this machine's cohorts.json.
    work = patterns() if work is None else work
    sessions = [s for client in clients for s in READERS[client](home)]
    for entry in sessions:
        entry["cohort"] = cohort(entry["project"], work)
    return sessions


def median(sessions: list[dict], metric: str) -> float | None:
    values = [s[metric] for s in sessions if s[metric] is not None]
    return statistics.median(values) if values else None


def cell(value: float | None) -> str:
    return f"{value:>10.1f}" if value is not None else f"{'-':>10}"


def block(label: str, cohort: list[dict], split: date) -> list[str]:
    before = [s for s in cohort if s["date"] < split]
    after = [s for s in cohort if s["date"] >= split]
    lines = [
        "",
        label,
        f"  {'metric':<12}{'before':>10}{'after':>10}{'delta':>10}",
        f"  {'sessions':<12}{len(before):>10}{len(after):>10}{'':>10}",
    ]
    for metric in METRICS:
        b, a = median(before, metric), median(after, metric)
        delta = f"{a - b:>+10.1f}" if b is not None and a is not None else f"{'-':>10}"
        lines.append(f"  {metric:<12}{cell(b)}{cell(a)}{delta}")
    if len(before) < THIN or len(after) < THIN:
        lines.append(
            f"  warning: a cohort has fewer than {THIN} sessions; noise, not a result."
        )
    return lines


def report(sessions: list[dict], split: date, since: date | None) -> str:
    if since:
        sessions = [s for s in sessions if s["date"] >= since]
    lines = [
        f"split {split.isoformat()}" + (f"  since {since.isoformat()}" if since else "")
    ]
    # Split by cohort only once one is configured. Unconfigured, every session
    # is personal, and a "personal" heading would draw a distinction nobody
    # made and imply a work cohort is missing rather than undefined.
    groups = ["work", "personal"] if any(
        s["cohort"] == "work" for s in sessions
    ) else [None]
    for client in READERS:
        for group in groups:
            cohort = [
                s for s in sessions
                if s["client"] == client and group in (None, s["cohort"])
            ]
            if cohort:
                label = client if group is None else f"{client}  {group}"
                lines += block(label, cohort, split)
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
                        help="limit to one client; repeatable (default: both)")
    parser.add_argument("--home", type=Path, default=Path.home(),
                        help="session-store root (default: the current home)")
    parser.add_argument("--rows", action="store_true",
                        help="print one JSON object per session instead of the report")
    args = parser.parse_args(argv)

    sessions = collect(args.home, args.client or list(READERS))
    if args.rows:
        # The same window the report bins, or these are not the distribution
        # behind any median it printed.
        if args.since:
            sessions = [s for s in sessions if s["date"] >= args.since]
        # Project names leak here, so this output is not shareable the way the
        # aggregate report is.
        for entry in sorted(sessions, key=lambda s: (s["date"], s["client"])):
            print(json.dumps({**entry, "date": entry["date"].isoformat()}))
        return 0
    print(report(sessions, args.split, args.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
