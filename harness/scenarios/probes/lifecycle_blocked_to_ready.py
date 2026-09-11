#!/usr/bin/env python3
"""Replay one existing lifecycle decision into an artifact.

A blocked ticket becomes ready-for-agent when its blocker is closed by a merged
pull request. This runs the shipped reconciler against an in-memory API and
writes the resulting transitions to `artifacts/labels.json` in the disposable
repository the scenario runner provides.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

_RECONCILER = (
    Path(__file__).resolve().parents[2]
    / "skills/setup-harness/scripts/reconcile-agent-lifecycle.py"
)


def load_reconciler():
    spec = importlib.util.spec_from_file_location("reconcile_agent_lifecycle", _RECONCILER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAPI:
    def __init__(self, issues, satisfied, blocked_by, blocking):
        self.issues = issues
        self.satisfied = set(satisfied)
        self.blocked_by = blocked_by
        self.blocking = blocking
        self.updated: list = []

    def issue(self, number):
        return self.issues[number]

    def related(self, number, relation):
        table = {"blocked_by": self.blocked_by, "blocking": self.blocking}
        return [self.issues[n] for n in table.get(relation, {}).get(number, ())]

    def blocker_satisfied(self, issue):
        return issue["number"] in self.satisfied

    def update(self, number, **changes):
        self.updated.append([number, changes])
        self.issues[number].update(changes)


def main() -> None:
    reconciler = load_reconciler()
    labels = reconciler.DEFAULT_LABELS
    issues = {
        1: {"number": 1, "state": "closed", "labels": []},
        2: {"number": 2, "state": "open", "labels": [{"name": labels["blocked"]}]},
    }
    api = FakeAPI(issues, satisfied={1}, blocked_by={2: [1]}, blocking={1: [2]})
    reconciler.reconcile(api, 1, labels)

    repo = Path(os.environ["SCENARIO_REPO"])
    out = repo / "artifacts" / "labels.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(api.updated, indent=2) + "\n")


if __name__ == "__main__":
    main()
