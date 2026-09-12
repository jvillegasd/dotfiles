#!/usr/bin/env python3
"""Recover a branch checkpoint in a later session through its topic key.

Session one records a deferred requirement and the rationale that exists
nowhere else, then serializes the store as it would survive a context reset.
Session two retrieves the checkpoint by the branch topic key, not from recent
memory, and recovers exactly that requirement, its rationale, and the contract
reference. The same run proves two branches cannot consume each other's
checkpoint, that the topic key upserts one record, that a moved tip drops the
resolved checks and next action while keeping the rationale and contract, and
that terminal records are excluded from ordinary continuation. The outcomes are
written to `artifacts/checkpoint.json` in the disposable repository the
scenario runner provides.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import checkpoint_protocol as P

BRANCH = "docs/77-engram-workflow-checkpoints"
OTHER = "feat/99-unrelated-work"
DEFERRED_REQUIREMENT = "wire /ship continuation retrieval at its worktree step"
RATIONALE = "the branch, not the ticket, scopes recovery across sessions"
TICKET = "https://github.com/jvillegasd/dotfiles/issues/77"


def resolves(ref: str) -> bool:
    return ref.startswith("https://")


def run() -> dict:
    store: dict = {}

    # Session one: record the deferred requirement with the rationale that is
    # not yet durable anywhere else, then persist the store across the reset.
    P.save(
        store,
        BRANCH,
        "abc1234",
        "active",
        [TICKET],
        ["tests: pass"],
        RATIONALE,
        DEFERRED_REQUIREMENT,
    )
    persisted = json.loads(json.dumps(store))

    # Session two: retrieve by the branch topic key, never from recent memory.
    record, _ = P.recover(persisted, BRANCH, "abc1234", resolves)
    recovers_requirement = (
        record is not None and record["next_action"] == DEFERRED_REQUIREMENT
    )
    recovers_rationale = record is not None and record["rationale"] == RATIONALE
    recovers_contract = record is not None and record["contract"] == [TICKET]

    # Two branches hold separate checkpoints; neither reads the other's.
    P.save(persisted, OTHER, "abc1234", "active", [TICKET], [], "", "a different next action")
    mine, _ = P.recover(persisted, BRANCH, "abc1234", resolves)
    theirs, _ = P.recover(persisted, OTHER, "abc1234", resolves)
    isolation = (
        mine is not None
        and theirs is not None
        and mine["next_action"] == DEFERRED_REQUIREMENT
        and theirs["next_action"] == "a different next action"
        and mine["next_action"] != theirs["next_action"]
    )

    # The topic key is stable: a later save upserts the one branch record.
    P.save(store, BRANCH, "def5678", "active", [TICKET], ["lint: pass"], RATIONALE, "next")
    saved = P.load(store, BRANCH)
    stable_key = (
        list(store) == [P.topic_key(BRANCH)] and saved["branch_tip"] == "def5678"
    )

    # A moved tip drops the resolved checks and the next action but keeps the
    # rationale and the contract reference, which a later session re-derives from.
    stale, stale_notes = P.recover(persisted, BRANCH, "def5678", resolves)
    stale_tip = (
        stale is not None
        and stale["checks"] == []
        and stale["next_action"] == ""
        and stale["rationale"] == RATIONALE
        and stale["contract"] == [TICKET]
        and any("stale tip" in note for note in stale_notes)
    )

    # Terminal records are excluded from ordinary continuation.
    terminal_excluded = True
    for state in P.terminal_states():
        P.mutate(persisted, BRANCH, state=state)
        record, reasons = P.recover(persisted, BRANCH, "abc1234", resolves)
        terminal_excluded = terminal_excluded and record is None and reasons == [
            f"terminal state {state} is excluded"
        ]

    return {
        "two_session_recovers_requirement": recovers_requirement,
        "two_session_recovers_rationale": recovers_rationale,
        "two_session_recovers_contract": recovers_contract,
        "branch_isolation": isolation,
        "stable_topic_key_upserts": stable_key,
        "stale_tip_keeps_rationale": stale_tip,
        "terminal_excluded": terminal_excluded,
    }


def main() -> None:
    repo = Path(os.environ.get("SCENARIO_REPO", "."))
    out = repo / "artifacts" / "checkpoint.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run(), indent=2) + "\n")


if __name__ == "__main__":
    main()
