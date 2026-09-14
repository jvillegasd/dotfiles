#!/usr/bin/env python3
"""Artifact-based scenarios for critical harness behavior.

Each scenario declares the artifacts and assertions it expects before any
model session runs, executes in a disposable repository with a forge shim on
PATH, and retains one attempt directory holding prompts, input provenance,
tool events, artifact results, and transcript evidence. An attempt passes only
when its artifact checks pass and a transcript review record exists. Changed
scenario or harness inputs mark an older attempt stale.

Each attempt also normalizes efficiency from its recorded events (tokens, tool
calls, command-output bytes, wall time, model, terminal status), leaving a
measurement nobody made unknown rather than zero. `compare` reports behavioral
pass rates first, then efficiency among passing runs only, one scenario and
model at a time.

Paid model execution is off unless `--allow-paid` is passed with a retained
per-batch session cap. Local tooling success is reported separately from
behavioral acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_EVIDENCE = (
    "provenance.json",
    "prompts.txt",
    "events.jsonl",
    "artifacts.json",
    "transcript.jsonl",
    "metrics.json",
)
ARTIFACT_KEYS = (
    "tree_unchanged",
    "fixtures_unchanged",
    "present",
    "absent",
    "contains",
)
METRIC_FIELDS = (
    "scenario",
    "model",
    "input_tokens",
    "output_tokens",
    "cached_input",
    "tool_calls",
    "command_output_bytes",
    "wall_seconds",
    "terminal_status",
)
STATE_ORDER = (
    "pass",
    "fail",
    "interrupted",
    "stale",
    "unreviewed",
    "incomplete",
    "unavailable",
)
BATCH = "batch.json"
HERE = Path(__file__).resolve().parent
DEFAULT_MATRIX = HERE / "matrix.json"
DEFAULT_FIXTURES = HERE / "fixtures"


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _usage_fields(usage: dict) -> dict:
    details = usage.get("input_tokens_details")
    prompt_details = usage.get("prompt_tokens_details")
    cached = usage.get("cached_input")
    for candidate in (
        cached,
        usage.get("cache_read_input_tokens"),
        details.get("cached_tokens") if isinstance(details, dict) else None,
        prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else None,
    ):
        if candidate is not None:
            cached = candidate
            break
    return {
        "input_tokens": _number(usage.get("input_tokens", usage.get("prompt_tokens"))),
        "output_tokens": _number(usage.get("output_tokens", usage.get("completion_tokens"))),
        "cached_input": _number(cached),
    }


def parse_usage(events: list) -> dict:
    """Normalize token usage, keeping an absent measurement unknown.

    A summary `result` event carries the run totals and wins; otherwise
    per-message usages are summed. A field nobody measured
    stays `None`, never `0`, because an absent measurement and a measured zero
    are different claims.
    """
    found: dict = {key: [] for key in ("input_tokens", "output_tokens", "cached_input")}
    for event in events:
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        nested = message.get("usage") if isinstance(message, dict) else None
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else nested
        if not isinstance(usage, dict):
            continue
        values = _usage_fields(usage)
        if event.get("type") == "result":
            return values
        for key, value in values.items():
            if value is not None:
                found[key].append(value)
    return {key: (sum(values) if values else None) for key, values in found.items()}


def model_from_events(events: list) -> str | None:
    for event in events:
        if not isinstance(event, dict):
            continue
        if isinstance(event.get("model"), str):
            return event["model"]
        message = event.get("message")
        if isinstance(message, dict) and isinstance(message.get("model"), str):
            return message["model"]
    return None


def count_tool_calls(events: list) -> int:
    count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") in ("tool_use", "tool_call", "function_call"):
            count += 1
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            count += sum(
                1
                for part in content
                if isinstance(part, dict) and part.get("type") == "tool_use"
            )
    return count


def _content_bytes(content: object) -> int:
    if isinstance(content, list):
        return sum(
            len(str(part.get("text", "") or "").encode())
            if isinstance(part, dict)
            else len(str(part).encode())
            for part in content
        )
    return len(str(content if content is not None else "").encode())


def command_output_bytes(events: list) -> int:
    """Bytes the run's tools returned across the recorded client shapes.

    A recorded or offline event carries one top-level `tool_result`, and a live
    Claude stream nests the same block under a `user` message's content.
    """
    total = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "tool_result":
            total += _content_bytes(event.get("content", event.get("text", "")))
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    total += _content_bytes(part.get("content", part.get("text", "")))
    return total


def terminal_status(code: int | None) -> str:
    if code is None:
        return "unknown"
    if code == 0:
        return "ok"
    if code < 0 or code >= 128:
        return "interrupted"
    return "failed"


def build_metrics(
    scenario: dict, events: list, wall_seconds: float, status: str
) -> dict:
    usage = parse_usage(events)
    values = {
        "scenario": scenario["id"],
        "model": model_from_events(events),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cached_input": usage["cached_input"],
        "tool_calls": count_tool_calls(events),
        "command_output_bytes": command_output_bytes(events),
        "wall_seconds": round(wall_seconds, 6),
        "terminal_status": status,
    }
    return {field: values[field] for field in METRIC_FIELDS}


def read_metrics(attempt: Path) -> dict:
    path = attempt / "metrics.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def recorded_digest(attempt: Path) -> str | None:
    try:
        return json.loads((attempt / "provenance.json").read_text()).get("input_digest")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def file_digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def tree_digest(root: Path) -> str:
    if not root.is_dir():
        return "missing"
    parts = [
        f"{path.relative_to(root).as_posix()}:{file_digest(path)}"
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def scenario_digest(
    scenario: dict, root: Path, fixtures_root: Path = DEFAULT_FIXTURES
) -> str:
    """Hash the declaration, its harness inputs, and its recording.

    A changed scenario, harness input, or recording changes this digest, which
    is what marks an older attempt stale instead of silently accepting it.
    """
    parts = [canonical(scenario)]
    for relative in scenario.get("harness_inputs", []):
        parts.append(f"{relative}:{file_digest(root / relative)}")
    parts.append(f"fixture:{tree_digest(fixtures_root / scenario['id'])}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    tree: dict[str, str] = {}
    if not root.exists():
        return tree
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            tree[path.relative_to(root).as_posix()] = file_digest(path)
    return tree


def validate_matrix(matrix: dict) -> list[str]:
    """Reject a declaration before any session runs."""
    errors: list[str] = []
    seen: set[str] = set()
    scenarios = matrix.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return ["matrix declares no scenarios"]
    for index, scenario in enumerate(scenarios):
        where = scenario.get("id") or f"scenario[{index}]"
        for field in ("id", "command", "prompt"):
            if not scenario.get(field):
                errors.append(f"{where}: missing {field}")
        if where in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(where)
        artifacts = scenario.get("artifacts")
        if not isinstance(artifacts, dict) or not any(
            key in artifacts for key in ARTIFACT_KEYS
        ):
            errors.append(f"{where}: declares no artifacts or assertions")
        else:
            contains = artifacts.get("contains", [])
            if not isinstance(contains, list):
                errors.append(f"{where}: contains must be a list")
            for item in contains if isinstance(contains, list) else []:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("path"), str)
                    or not isinstance(item.get("text"), str)
                ):
                    errors.append(f"{where}: contains entry needs string path and text")
        if mode(scenario) == "offline" and not scenario.get("check"):
            errors.append(f"{where}: offline scenario needs a check command")
    return errors


def mode(scenario: dict) -> str:
    return scenario.get("mode") or ("offline" if scenario.get("check") else "live")


def entry(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def evaluate_artifacts(
    scenario: dict,
    before: dict,
    after: dict,
    repo: Path,
    forge_calls: list[str],
    fixtures_unchanged: bool = True,
) -> list[dict]:
    artifacts = scenario.get("artifacts", {})
    entries: list[dict] = []
    if "tree_unchanged" in artifacts:
        expected = bool(artifacts["tree_unchanged"])
        entries.append(entry("tree_unchanged", (before == after) == expected))
    if "fixtures_unchanged" in artifacts:
        expected = bool(artifacts["fixtures_unchanged"])
        entries.append(entry("fixtures_unchanged", fixtures_unchanged == expected))
    for relative in artifacts.get("present", []):
        path = repo / relative
        entries.append(entry(f"present:{relative}", path.exists()))
    for relative in artifacts.get("absent", []):
        path = repo / relative
        entries.append(entry(f"absent:{relative}", not path.exists()))
    base = repo.resolve()
    for item in artifacts.get("contains", []):
        target = (repo / item["path"]).resolve()
        inside = target.is_relative_to(base)
        found = inside and target.is_file() and item["text"] in target.read_text(errors="replace")
        entries.append(entry(f"contains:{item['path']}:{item['text']}", found))
    entries.append(entry("no-external-forge", not forge_calls, "; ".join(forge_calls)))
    return entries


def reviewed(attempt: Path) -> bool:
    path = attempt / "review.json"
    if not path.is_file():
        return False
    try:
        return bool(json.loads(path.read_text()).get("reviewed"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def evaluate(attempt: Path, scenario: dict, current_digest: str) -> tuple[str, list[str]]:
    missing = [name for name in REQUIRED_EVIDENCE if not (attempt / name).is_file()]
    if missing:
        return "incomplete", [f"missing evidence: {', '.join(missing)}"]
    try:
        provenance = json.loads((attempt / "provenance.json").read_text())
        artifacts = json.loads((attempt / "artifacts.json").read_text())
        metrics = json.loads((attempt / "metrics.json").read_text())
    except (OSError, json.JSONDecodeError) as error:
        return "incomplete", [f"unreadable evidence: {error}"]
    if not isinstance(metrics, dict):
        return "incomplete", ["unreadable evidence: metrics is not an object"]
    if provenance.get("input_digest") != current_digest:
        return "stale", [f"inputs changed since {provenance.get('recorded_at', '')}"]
    if metrics.get("terminal_status") == "interrupted":
        return "interrupted", ["session interrupted"]
    if not artifacts.get("ok"):
        failed = [e["name"] for e in artifacts.get("results", []) if not e.get("ok")]
        return "fail", [f"artifact checks failed: {', '.join(failed) or 'none recorded'}"]
    if not reviewed(attempt):
        return "unreviewed", ["no transcript review record"]
    return "pass", []


def install_forge_guard(workspace: Path) -> tuple[Path, Path]:
    """A disposable `gh` that logs and refuses, so a scenario cannot reach a forge."""
    shim = workspace / "shim"
    shim.mkdir(parents=True, exist_ok=True)
    log = workspace / "forge.log"
    gh = shim / "gh"
    gh.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nexit 1\n')
    gh.chmod(0o755)
    return shim, log


def forge_env(shim: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{shim}{os.pathsep}{env.get('PATH', '')}"
    env["GH_CONFIG_DIR"] = str(shim.parent / "gh-config")
    env["GH_TOKEN"] = ""
    env["GITHUB_TOKEN"] = ""
    # No interactive credentials and no git transport, so a scenario that adds
    # a remote still cannot reach a forge. `gh` is already shadowed above.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "/bin/false"
    env["SSH_ASKPASS"] = "/bin/false"
    env["GIT_SSH_COMMAND"] = "/bin/false"
    env["GIT_ALLOW_PROTOCOL"] = "none"
    return env


def git_remotes(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "remote"], capture_output=True, text=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def jsonl(items: list[dict]) -> str:
    return "".join(json.dumps(item) + "\n" for item in items)


def run_check(
    scenario: dict, repo: Path, env: dict, events: list, transcript: list
) -> int:
    command = scenario["check"]
    events.append({"type": "command", "command": command})
    result = subprocess.run(
        command, shell=True, cwd=repo, env=env, capture_output=True, text=True
    )
    events.append({"type": "exit", "code": result.returncode})
    events.append({"type": "tool_result", "content": result.stdout + result.stderr})
    transcript.append({"stream": "stdout", "text": result.stdout})
    transcript.append({"stream": "stderr", "text": result.stderr})
    return result.returncode


def replay(fixture: Path, repo: Path, events: list, transcript: list) -> None:
    source = fixture / "repo"
    if source.is_dir():
        shutil.copytree(source, repo, dirs_exist_ok=True)
    for name, sink in (("events.jsonl", events), ("transcript.jsonl", transcript)):
        path = fixture / name
        if path.is_file():
            sink.extend(
                json.loads(line) for line in path.read_text().splitlines() if line.strip()
            )


def run_live(
    scenario: dict, repo: Path, env: dict, events: list, transcript: list
) -> int:
    client = scenario.get("client", "claude")
    argv = {
        "claude": ["claude", "-p", "--output-format", "stream-json", "--verbose"],
    }.get(client)
    if not argv:
        raise RuntimeError(f"unsupported client: {client}")
    events.append({"type": "session-start", "client": client})
    result = subprocess.run(
        argv + [scenario["prompt"]], cwd=repo, env=env, capture_output=True, text=True
    )
    events.append({"type": "session-end", "code": result.returncode})
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "output", "text": line})
    transcript.append({"stream": "stdout", "text": result.stdout})
    transcript.append({"stream": "stderr", "text": result.stderr})
    return result.returncode


def claim_session(out_root: Path, max_sessions: int | None) -> dict:
    """Retain a per-batch paid-session cap; refuse once it is reached."""
    path = out_root / BATCH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"cap": None, "sessions": 0}
    if path.is_file():
        data = json.loads(path.read_text())
    if data.get("cap") is None:
        if max_sessions is None:
            raise RuntimeError("paid execution needs --max-sessions to set the cap")
        data["cap"] = max_sessions
    elif max_sessions is not None and max_sessions != data["cap"]:
        raise RuntimeError(
            f"batch cap is retained at {data['cap']}; start a new batch to change it"
        )
    if data["sessions"] >= data["cap"]:
        raise RuntimeError(f"per-batch session cap reached ({data['sessions']}/{data['cap']})")
    data["sessions"] += 1
    path.write_text(json.dumps(data, indent=2) + "\n")
    return data


def attempt_paths(out_root: Path, scenario_id: str) -> list[Path]:
    root = out_root / scenario_id
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def run_one(
    scenario: dict,
    root: Path,
    out_root: Path,
    fixtures_root: Path,
    allow_paid: bool,
    max_sessions: int | None,
) -> tuple[str, str]:
    digest = scenario_digest(scenario, root, fixtures_root)
    fixture = fixtures_root / scenario["id"]
    if mode(scenario) == "live" and not fixture.is_dir() and not allow_paid:
        return "not-run", "live scenario: pass --allow-paid or provide a recording"

    workspace = Path(tempfile.mkdtemp(prefix=f"scenario-{scenario['id']}-"))
    try:
        repo = workspace / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo)
        shim, forge_log = install_forge_guard(workspace)
        env = forge_env(shim)
        env["HARNESS_ROOT"] = str(root)
        env["SCENARIO_REPO"] = str(repo)
        before = snapshot(repo)
        fixtures_before = tree_digest(fixture)
        events: list[dict] = []
        transcript: list[dict] = []
        check_code: int | None = None
        live_code: int | None = None

        started = time.monotonic()
        if mode(scenario) == "offline":
            executor = "offline"
            check_code = run_check(scenario, repo, env, events, transcript)
        elif fixture.is_dir():
            executor = "recording"
            replay(fixture, repo, events, transcript)
        else:
            executor = f"live:{scenario.get('client', 'claude')}"
            claim_session(out_root, max_sessions)
            live_code = run_live(scenario, repo, env, events, transcript)
        wall_seconds = time.monotonic() - started

        after = snapshot(repo)
        forge_calls = forge_log.read_text().splitlines() if forge_log.is_file() else []
        entries = evaluate_artifacts(
            scenario,
            before,
            after,
            repo,
            forge_calls,
            fixtures_unchanged=fixtures_before == tree_digest(fixture),
        )
        if check_code is not None:
            entries.append(entry("check-exit", check_code == 0, f"exit {check_code}"))
        if live_code is not None:
            entries.append(entry("session-exit", live_code == 0, f"exit {live_code}"))
        remotes = git_remotes(repo)
        entries.append(entry("no-git-remote", not remotes, "; ".join(remotes)))

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        attempt = out_root / scenario["id"] / f"{stamp}-{digest[:8]}"
        attempt.mkdir(parents=True, exist_ok=True)
        (attempt / "prompts.txt").write_text(scenario["prompt"].rstrip() + "\n")
        (attempt / "provenance.json").write_text(
            json.dumps(
                {
                    "scenario": scenario["id"],
                    "input_digest": digest,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "executor": executor,
                },
                indent=2,
            )
            + "\n"
        )
        (attempt / "events.jsonl").write_text(jsonl(events))
        (attempt / "artifacts.json").write_text(
            json.dumps({"ok": all(e["ok"] for e in entries), "results": entries}, indent=2) + "\n"
        )
        (attempt / "transcript.jsonl").write_text(jsonl(transcript))
        exit_code = check_code if check_code is not None else live_code
        (attempt / "metrics.json").write_text(
            json.dumps(
                build_metrics(scenario, events, wall_seconds, terminal_status(exit_code)),
                indent=2,
            )
            + "\n"
        )
        state, reasons = evaluate(attempt, scenario, digest)
        (attempt / "status.json").write_text(
            json.dumps({"state": state, "reasons": reasons}, indent=2) + "\n"
        )
        return state, str(attempt)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def load_matrix(path: Path) -> dict:
    return json.loads(path.read_text())


def report(matrix: dict, out_root: Path, root: Path) -> str:
    errors = validate_matrix(matrix)
    lines = [f"local-tooling: {'fail' if errors else 'pass'}"]
    for error in errors:
        lines.append(f"  {error}")
    lines.append("behavioral-acceptance:")
    for scenario in matrix.get("scenarios", []):
        attempts = attempt_paths(out_root, scenario["id"])
        if not attempts:
            lines.append(f"  {scenario['id']}: incomplete (no attempt)")
            continue
        state, reasons = evaluate(attempts[-1], scenario, scenario_digest(scenario, root))
        detail = f" ({'; '.join(reasons)})" if reasons else ""
        lines.append(f"  {scenario['id']}: {state}{detail}")
    return "\n".join(lines)


EFFICIENCY_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input",
    "tool_calls",
    "command_output_bytes",
    "wall_seconds",
)


def _batch(root: Path, scenario: dict, digest: str) -> tuple[dict, dict]:
    """Count a batch by its own recorded states, not the current checkout.

    A batch retained under another harness version carries a different input
    digest, so evaluating it against the current checkout would mark every
    attempt stale and make cross-version comparison impossible. Each attempt is
    read against the digest it recorded; an attempt that disagrees with the
    newest one in its own batch is the stale one, which keeps within-batch
    drift visible without hiding a whole batch. An unknown model is left out of
    efficiency pairing, since two unlabelled models are not known to match.
    """
    attempts = attempt_paths(root, scenario["id"])
    counts: dict[str, int] = {}
    passing: dict = {}
    if not attempts:
        return {"unavailable": 1}, passing
    recorded = [recorded_digest(attempt) for attempt in attempts]
    tally = Counter(value for value in recorded if value is not None)
    if digest in tally:
        reference = digest
    elif tally:
        reference = tally.most_common(1)[0][0]
    else:
        reference = digest
    for attempt, value in zip(attempts, recorded):
        if value is not None and value != reference:
            counts["stale"] = counts.get("stale", 0) + 1
            continue
        state, _ = evaluate(attempt, scenario, value or digest)
        counts[state] = counts.get(state, 0) + 1
        if state == "pass":
            metrics = read_metrics(attempt)
            if metrics.get("model") is not None:
                passing.setdefault(metrics["model"], []).append(metrics)
    return counts, passing


def _rate(counts: dict) -> str:
    if set(counts) == {"unavailable"}:
        return "unavailable"
    total = sum(counts.values())
    detail = " ".join(f"{state}={counts[state]}" for state in STATE_ORDER if counts.get(state))
    return f"pass {counts.get('pass', 0)}/{total} ({detail})"


def _median(records: list, field: str) -> int | float | None:
    values = [
        record[field]
        for record in records
        if isinstance(record.get(field), (int, float))
        and not isinstance(record.get(field), bool)
    ]
    return statistics.median(values) if values else None


def _format(value: int | float | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.3f}"
    return str(int(value))


def compare(
    before_root: Path, after_root: Path, matrix: dict, root: Path
) -> str:
    """Compare two batches: pass rates first, then efficiency among passes.

    Efficiency pairs only a passing before with a passing after of the same
    scenario and model, so unlike models or scenarios are never pooled and a
    failed baseline can never read as a win. One successful pair is a smoke
    result, not a savings claim.
    """
    lines = ["behavioral pass rates"]
    pairs: list = []
    for scenario in matrix.get("scenarios", []):
        digest = scenario_digest(scenario, root)
        before_counts, before_pass = _batch(before_root, scenario, digest)
        after_counts, after_pass = _batch(after_root, scenario, digest)
        lines.append(f"  {scenario['id']}")
        lines.append(f"    before: {_rate(before_counts)}")
        lines.append(f"    after:  {_rate(after_counts)}")
        for model in sorted(set(before_pass) & set(after_pass)):
            pairs.append((scenario["id"], model, before_pass[model], after_pass[model]))

    lines.append("")
    lines.append("efficiency (passing runs only)")
    if not pairs:
        lines.append("  no comparable pair")
        return "\n".join(lines)
    if len(pairs) == 1:
        scenario_id, model, _, _ = pairs[0]
        lines.append(
            f"  smoke: one successful pair ({scenario_id} model={model}), "
            "report as smoke rather than a savings claim"
        )
        return "\n".join(lines)
    for scenario_id, model, before_records, after_records in pairs:
        lines.append(f"  {scenario_id} model={model}")
        lines.append(f"    {'metric':<20} {'before':>10} {'after':>10} {'delta':>10}")
        for field in EFFICIENCY_FIELDS:
            before = _median(before_records, field)
            after = _median(after_records, field)
            delta = after - before if after is not None and before is not None else None
            lines.append(
                f"    {field:<20} {_format(before):>10} {_format(after):>10} {_format(delta):>10}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    common.add_argument("--out", type=Path, default=HERE / "attempts")
    common.add_argument("--root", type=Path, default=Path.cwd())
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", parents=[common])
    run_parser = sub.add_parser("run", parents=[common])
    run_parser.add_argument("--scenario")
    run_parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    run_parser.add_argument("--allow-paid", action="store_true")
    run_parser.add_argument("--max-sessions", type=int)
    sub.add_parser("report", parents=[common])
    compare_parser = sub.add_parser("compare", parents=[common])
    compare_parser.add_argument("--before", type=Path, required=True)
    compare_parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args(argv)

    matrix = load_matrix(args.matrix)
    if args.command == "compare":
        print(compare(args.before, args.after, matrix, args.root))
        return 0
    if args.command == "validate":
        errors = validate_matrix(matrix)
        for error in errors:
            print(error, file=sys.stderr)
        print("local-tooling: pass" if not errors else "local-tooling: fail")
        return 1 if errors else 0
    if args.command == "report":
        print(report(matrix, args.out, args.root))
        return 0

    errors = validate_matrix(matrix)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    exit_code = 0
    for scenario in matrix["scenarios"]:
        if args.scenario and scenario["id"] != args.scenario:
            continue
        try:
            state, where = run_one(
                scenario, args.root, args.out, args.fixtures,
                args.allow_paid, args.max_sessions,
            )
        except RuntimeError as error:
            print(f"{scenario['id']}: {error}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"{scenario['id']}: {state} -> {where}")
        if state in ("fail", "not-run", "interrupted"):
            exit_code = 1
    print(report(matrix, args.out, args.root))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
