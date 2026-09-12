#!/usr/bin/env python3
"""Exercise the spec-slicing routes declared by `/create-ticket`.

The command carries the canonical route table and this probe reads it from
there rather than a parallel copy, so a change to the table changes the probe's
behavior. It applies the table to zero-, one-, and many-slice spec fixtures: an
empty spec publishes nothing, a one-slice spec is promoted in place as the
single implementation contract with no child, a many-slice spec keeps its
parent, children, native dependency edges, and ready frontier, and a research
finding batch resolves its own parent and never collapses. Tracker labels come
from the repository manifest, so the probe models the mapped values the command
actually applies, and a trackerless or local-markdown binding changes where the
one artifact lives, not how many there are. Outcomes land in
`artifacts/slicing.json` in the disposable repository the scenario runner
provides.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_COMMAND = _ROOT / "harness/commands/create-ticket.md"
_MANIFEST = _ROOT / "docs/agents/harness.json"
_ROUTE_KEYS = (
    "empty_spec_route",
    "single_slice_route",
    "multi_slice_route",
    "research_input_route",
    "projection_fields",
)


def block() -> dict:
    text = _COMMAND.read_text()
    for candidate in re.findall(r"```json\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict) and all(key in data for key in _ROUTE_KEYS):
            return data
    raise SystemExit("create-ticket command carries no canonical slicing block")


def labels() -> dict:
    mapped = json.loads(_MANIFEST.read_text()).get("labels")
    required = {"blocked", "ready_for_agent", "in_progress"}
    if not isinstance(mapped, dict) or not required <= set(mapped):
        raise SystemExit("docs/agents/harness.json carries no usable label mapping")
    return mapped


def route(slices, kind="spec") -> str:
    rules = block()
    if kind == "research":
        return rules["research_input_route"]
    if not slices:
        return rules["empty_spec_route"]
    if len(slices) == 1:
        return rules["single_slice_route"]
    return rules["multi_slice_route"]


def projection_fields() -> tuple:
    return tuple(block()["projection_fields"])


def plan(parent, slices, kind="spec", binding="github") -> dict:
    """Return the publication plan the route selected by the table produces.

    The mechanics are keyed off the route name the command declares, so a
    command that repoints a cardinality at another route changes the plan and
    fails the outcome that expected the old shape.
    """
    mapped = labels()
    chosen = route(slices, kind)
    address = parent["id"] if binding == "github" else parent["path"]
    result = {
        "route": chosen,
        "artifacts": [],
        "parent": None,
        "children": [],
        "edges": [],
        "frontier": [],
        "labels": {},
        "projection": {},
    }
    if chosen == "publish_nothing":
        return result
    if chosen == "promote_spec_in_place":
        blocked = any(s.get("blocked_by") for s in slices)
        result["artifacts"] = [address]
        result["labels"] = {
            address: mapped["blocked"] if blocked else mapped["ready_for_agent"]
        }
        result["projection"] = {field: True for field in projection_fields()}
        return result
    result["parent"] = address
    result["artifacts"] = [address] + [s["id"] for s in slices]
    result["children"] = [s["id"] for s in slices]
    result["edges"] = [(s["id"], blocker) for s in slices for blocker in s.get("blocked_by", [])]
    result["frontier"] = [s["id"] for s in slices if not s.get("blocked_by")]
    result["labels"] = {address: mapped["in_progress"]}
    result["labels"].update(
        {
            s["id"]: mapped["blocked"] if s.get("blocked_by") else mapped["ready_for_agent"]
            for s in slices
        }
    )
    return result


def run() -> dict:
    mapped = labels()
    spec = {"id": "issue-74", "path": "docs/specs/continuity/spec.md"}
    research_parent = {"id": "issue-70", "path": "docs/specs/research/spec.md"}
    empty: list = []
    one = [{"id": "issue-74", "blocked_by": []}]
    many = [
        {"id": "issue-101", "blocked_by": []},
        {"id": "issue-102", "blocked_by": ["issue-101"]},
        {"id": "issue-103", "blocked_by": []},
    ]
    research = [{"id": "issue-104", "blocked_by": []}]

    zero_plan = plan(spec, empty)
    one_plan = plan(spec, one)
    many_plan = plan(spec, many)
    research_plan = plan(research_parent, research, kind="research")
    local_plan = plan(spec, one, binding="local-markdown")

    return {
        "zero_slice_publishes_nothing": zero_plan["artifacts"] == [],
        "one_slice_creates_no_child": (
            one_plan["children"] == [] and one_plan["artifacts"] == [spec["id"]]
        ),
        "one_slice_implementation_label": (
            one_plan["labels"][spec["id"]] == mapped["ready_for_agent"]
        ),
        "multi_slice_preserves_parent": many_plan["parent"] == spec["id"],
        "multi_slice_preserves_children": many_plan["children"]
        == ["issue-101", "issue-102", "issue-103"],
        "multi_slice_preserves_edges": many_plan["edges"] == [("issue-102", "issue-101")],
        "multi_slice_preserves_frontier": many_plan["frontier"]
        == ["issue-101", "issue-103"],
        "research_batch_uses_child_dag": (
            research_plan["parent"] == research_parent["id"]
            and research_plan["artifacts"][0] == research_parent["id"]
            and research_plan["children"] == ["issue-104"]
        ),
        "single_slice_binding_is_one_artifact": (
            local_plan["artifacts"] == [spec["path"]]
            and local_plan["children"] == []
            and local_plan["labels"][spec["path"]] == mapped["ready_for_agent"]
        ),
    }


def main() -> None:
    repo = Path(os.environ.get("SCENARIO_REPO", "."))
    out = repo / "artifacts" / "slicing.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(), indent=2) + "\n")


if __name__ == "__main__":
    main()
