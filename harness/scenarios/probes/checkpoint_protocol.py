#!/usr/bin/env python3
"""Exercise the workflow-checkpoint protocol's declared rules.

Reads the canonical protocol block from the workflow-checkpoint skill and
interprets it: the topic-key format, the schema field names and shapes, the
state set, the non-empty requirements, and what a stale tip invalidates. One
store, serialized at its boundary, is driven through recovery so the rules,
not a parallel copy of them, decide each outcome. The outcomes are written to
`artifacts/checkpoint.json` in the disposable repository the scenario runner
provides.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[2] / "skills/workflow-checkpoint/SKILL.md"
)
_TYPES = {
    "string": str,
    "array": list,
    "object": dict,
    "number": (int, float),
    "boolean": bool,
}


def protocol() -> dict:
    text = _SKILL.read_text()
    for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if (
            isinstance(data, dict)
            and isinstance(data.get("fields"), dict)
            and "states" in data
        ):
            return data
    raise SystemExit("workflow-checkpoint skill carries no canonical protocol block")


def schema_fields() -> tuple:
    return tuple(protocol()["fields"])


def shapes() -> dict:
    return protocol()["fields"]


def topic_key_prefix() -> str:
    return protocol()["topic_key"].split("/<branch>")[0]


def topic_key(branch: str) -> str:
    return protocol()["topic_key"].replace("<branch>", branch)


def states() -> tuple:
    return tuple(protocol()["states"])


def terminal_states() -> tuple:
    return tuple(protocol()["terminal_states"])


def save(store, branch, tip, state, contract, checks, rationale, next_action):
    record = {
        "state": state,
        "branch_tip": tip,
        "contract": contract,
        "checks": checks,
        "rationale": rationale,
        "next_action": next_action,
    }
    if set(record) != set(schema_fields()):
        raise SystemExit("probe record does not match the skill schema")
    store[topic_key(branch)] = json.dumps(record, sort_keys=True)
    return record


def load(store, branch):
    raw = store.get(topic_key(branch))
    return json.loads(raw) if raw is not None else None


def mutate(store, branch, **changes):
    record = load(store, branch)
    record.update(changes)
    store[topic_key(branch)] = json.dumps(record, sort_keys=True)


def valid_shapes(record):
    return all(
        field in record and isinstance(record[field], _TYPES[shape])
        for field, shape in shapes().items()
    )


def recover(store, branch, current_tip, resolve_contract):
    rules = protocol()
    record = load(store, branch)
    if record is None:
        return None, ["no checkpoint for branch"]
    state = record.get("state")
    if state in rules["terminal_states"]:
        return None, [f"terminal state {state} is excluded"]
    if state not in rules["states"]:
        return None, [f"unknown state {state} is excluded"]
    if not valid_shapes(record):
        return None, ["a field is missing or has the wrong shape"]
    for field in rules["require_non_empty"]:
        if not record.get(field):
            return None, [f"required field {field} is empty"]
    resolved = [ref for ref in record["contract"] if resolve_contract(ref)]
    if not resolved:
        return None, ["no contract reference resolves"]

    usable = dict(record, contract=resolved)
    notes = [
        f"contract reference {ref} did not resolve"
        for ref in record["contract"]
        if ref not in resolved
    ]
    if record["branch_tip"] != current_tip:
        for field in rules["stale_invalidates"]:
            usable[field] = [] if shapes()[field] == "array" else ""
        notes.append(
            "stale tip; " + ", ".join(rules["stale_invalidates"]) + " not reused"
        )
    return usable, notes


def read_back(store, branch, written):
    return load(store, branch) == written


def run(store=None):
    store = {} if store is None else store
    branch = "feat/83-centralize-checkpoint-protocol"
    tip = "abc123"
    contract = ["https://github.com/jvillegasd/dotfiles/issues/83"]
    resolve = lambda ref: ref.startswith("https://")
    active = protocol()["active_state"]

    written = save(
        store,
        branch,
        tip,
        active,
        contract,
        ["typecheck: pass", "lint: pass"],
        "the skill is the single schema source",
        "wire the commands at their return boundaries (#77)",
    )
    snapshot = json.loads(json.dumps(written))
    read_back_ok = read_back(store, branch, snapshot)

    store[topic_key(branch)] = json.dumps(
        {**snapshot, "branch_tip": "corrupted"}, sort_keys=True
    )
    detects_corruption = not read_back(store, branch, snapshot)
    save(store, branch, tip, active, contract, ["typecheck: pass"], "why", "wire (#77)")

    other, other_reasons = recover(store, "feat/99-other", tip, resolve)
    isolation = other is None and other_reasons == ["no checkpoint for branch"]

    stale, stale_notes = recover(store, branch, "def456", resolve)
    stale_checks_dropped = (
        stale is not None
        and stale["checks"] == []
        and stale["next_action"] == ""
        and stale["contract"] == contract
        and any("stale tip" in note for note in stale_notes)
    )

    mutate(store, branch, state="paused")
    unknown, unknown_reasons = recover(store, branch, tip, resolve)
    invalid_state_rejected = unknown is None and unknown_reasons == [
        "unknown state paused is excluded"
    ]
    mutate(store, branch, state=active)

    terminal_excluded = True
    for state in terminal_states():
        mutate(store, branch, state=state)
        record, reasons = recover(store, branch, tip, resolve)
        terminal_excluded = terminal_excluded and record is None and reasons == [
            f"terminal state {state} is excluded"
        ]
    mutate(store, branch, state=active)

    mutate(store, branch, contract=[])
    empty, empty_reasons = recover(store, branch, tip, resolve)
    empty_contract_rejected = empty is None and empty_reasons == [
        "required field contract is empty"
    ]

    mutate(store, branch, contract="https://github.com/jvillegasd/dotfiles/issues/83")
    bad_shape, shape_reasons = recover(store, branch, tip, resolve)
    shape_rejected = bad_shape is None and shape_reasons == [
        "a field is missing or has the wrong shape"
    ]

    mutate(store, branch, contract=contract)
    expired, expired_reasons = recover(store, branch, tip, lambda ref: False)
    contract_rejected = expired is None and expired_reasons == [
        "no contract reference resolves"
    ]

    mutate(store, branch, contract=["https://good", "https://gone"])
    partial, partial_notes = recover(
        store, branch, tip, lambda ref: ref == "https://good"
    )
    contract_partial = (
        partial is not None
        and partial["contract"] == ["https://good"]
        and any("did not resolve" in note for note in partial_notes)
    )

    return {
        "isolation": isolation,
        "stale_checks_dropped": stale_checks_dropped,
        "invalid_state_rejected": invalid_state_rejected,
        "terminal_excluded": terminal_excluded,
        "empty_contract_rejected": empty_contract_rejected,
        "shape_rejected": shape_rejected,
        "contract_rejected": contract_rejected,
        "contract_partial": contract_partial,
        "read_back": read_back_ok,
        "read_back_detects_corruption": detects_corruption,
    }


def main() -> None:
    repo = Path(os.environ.get("SCENARIO_REPO", "."))
    out = repo / "artifacts" / "checkpoint.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(), indent=2) + "\n")


if __name__ == "__main__":
    main()
