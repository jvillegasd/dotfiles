#!/usr/bin/env python3
"""Exercise the recon citation check declared by `/triage` and `/research`.

The commands carry the canonical `## Recon citations` section and this probe reads the finding shape's field count from `/triage`'s copy; the regression suite asserts both copies agree. It applies the check to a valid citation, a missing file, a path outside the repository, a stale line, a wrong or partial symbol, absent fields, and a subagent that ended on a tool result, which is no data rather than a refutation. A location check grounds only the location, never the claimed mechanism, so the probe verifies nothing past the cited line. Outcomes land in `artifacts/recon.json` in the disposable repository the scenario runner provides.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_COMMAND = _ROOT / "harness/commands/triage.md"


def fields() -> list:
    match = re.search(r"^## Recon citations\n.*?in the shape `([^`]+)`", _COMMAND.read_text(), re.M | re.S)
    if not match:
        raise SystemExit("triage command carries no recon citation shape")
    return match.group(1).split(" | ")


def verify(final: dict, root: Path) -> dict:
    """Split a recon subagent's final message into grounded and refuted citations."""
    if final.get("type") != "text":
        return {"grounded": [], "refuted": [], "no_data": "no text report"}
    result = {"grounded": [], "refuted": []}
    root = root.resolve()
    count = len(fields())
    for citation in filter(str.strip, final["text"].splitlines()):
        parts = [part.strip() for part in citation.split(" | ", count - 1)]
        location = re.fullmatch(r"(.+):(\d+)", parts[0])
        if len(parts) < count or not all(parts) or not location:
            result["refuted"].append({"citation": citation, "reason": "missing field"})
            continue
        path = (root / location[1]).resolve()
        if not path.is_relative_to(root):
            reason = "outside repository"
        elif not path.is_file():
            reason = "missing file"
        else:
            lines = path.read_text(errors="replace").split("\n")
            number = int(location[2])
            symbol = rf"(?<!\w){re.escape(parts[1])}(?!\w)"
            if 0 < number <= len(lines) and re.search(symbol, lines[number - 1]):
                result["grounded"].append(citation)
                continue
            reason = "symbol not at line"
        result["refuted"].append({"citation": citation, "reason": reason})
    return result


def run() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "app.py").write_text("def load_config(path):\n    return parse(path)\n")
        valid = "app.py:1 | load_config | defines the loader"
        invalid = {
            "missing_file_refuted": ("gone.py:1 | load_config | defines the loader", "missing file"),
            "outside_repository_refuted": ("../app.py:1 | load_config | defines the loader", "outside repository"),
            "stale_line_refuted": ("app.py:9 | load_config | defines the loader", "symbol not at line"),
            "wrong_symbol_refuted": ("app.py:2 | load_config | defines the loader", "symbol not at line"),
            "partial_symbol_refuted": ("app.py:1 | load | defines the loader", "symbol not at line"),
            "absent_field_refuted": ("app.py:1 | load_config", "missing field"),
        }

        def refuted(citation, reason):
            return verify({"type": "text", "text": citation}, root) == {
                "grounded": [],
                "refuted": [{"citation": citation, "reason": reason}],
            }

        mixed = verify({"type": "text", "text": "\n".join([valid] + [c for c, _ in invalid.values()])}, root)
        outcomes = {
            "valid_citation_grounded": verify({"type": "text", "text": valid}, root)
            == {"grounded": [valid], "refuted": []},
        }
        outcomes.update({key: refuted(*case) for key, case in invalid.items()})
        outcomes["refuted_never_grounded"] = mixed["grounded"] == [valid] and [
            entry["citation"] for entry in mixed["refuted"]
        ] == [c for c, _ in invalid.values()]
        outcomes["trailing_tool_result_no_data"] = verify({"type": "tool_result", "text": valid}, root) == {
            "grounded": [],
            "refuted": [],
            "no_data": "no text report",
        }
        return outcomes


def main() -> None:
    repo = Path(os.environ.get("SCENARIO_REPO") or tempfile.mkdtemp(prefix="recon-citations-scenario-"))
    out = repo / "artifacts" / "recon.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(), indent=2) + "\n")


if __name__ == "__main__":
    main()
