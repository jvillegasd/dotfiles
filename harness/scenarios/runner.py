#!/usr/bin/env python3
"""Artifact-based scenarios for critical harness behavior.

Each scenario declares the artifacts and assertions it expects before any
model session runs, executes in a disposable repository with a forge shim on
PATH, and retains one attempt directory holding prompts, input provenance,
tool events, artifact results, and transcript evidence. An attempt passes only
when its artifact checks pass and a transcript review record exists. Changed
scenario or harness inputs mark an older attempt stale.

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
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_EVIDENCE = (
    "provenance.json",
    "prompts.txt",
    "events.jsonl",
    "artifacts.json",
    "transcript.jsonl",
)
ARTIFACT_KEYS = ("tree_unchanged", "present", "absent", "contains")
BATCH = "batch.json"
HERE = Path(__file__).resolve().parent
DEFAULT_MATRIX = HERE / "matrix.json"
DEFAULT_FIXTURES = HERE / "fixtures"


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
    scenario: dict, before: dict, after: dict, repo: Path, forge_calls: list[str]
) -> list[dict]:
    artifacts = scenario.get("artifacts", {})
    entries: list[dict] = []
    if "tree_unchanged" in artifacts:
        expected = bool(artifacts["tree_unchanged"])
        entries.append(entry("tree_unchanged", (before == after) == expected))
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
    except (OSError, json.JSONDecodeError) as error:
        return "incomplete", [f"unreadable evidence: {error}"]
    if provenance.get("input_digest") != current_digest:
        return "stale", [f"inputs changed since {provenance.get('recorded_at', '')}"]
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
        "codex": ["codex", "exec", "--json"],
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
        events: list[dict] = []
        transcript: list[dict] = []
        check_code: int | None = None
        live_code: int | None = None

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

        after = snapshot(repo)
        forge_calls = forge_log.read_text().splitlines() if forge_log.is_file() else []
        entries = evaluate_artifacts(scenario, before, after, repo, forge_calls)
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
    args = parser.parse_args(argv)

    matrix = load_matrix(args.matrix)
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
        if state in ("fail", "not-run"):
            exit_code = 1
    print(report(matrix, args.out, args.root))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
