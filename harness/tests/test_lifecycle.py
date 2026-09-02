#!/usr/bin/env python3

"""The GitHub lifecycle reconciler that setup-harness installs."""

from __future__ import annotations

import unittest

from fixtures import SKILLS, load_module


def load_lifecycle_module():
    return load_module(
        "agent_lifecycle",
        SKILLS / "setup-harness" / "scripts" / "reconcile-agent-lifecycle.py",
    )


class FakeIssues:
    def __init__(self) -> None:
        self.issues = {
            1: {"number": 1, "state": "open", "labels": [{"name": "in-progress"}]},
            2: {"number": 2, "state": "closed", "labels": []},
            3: {"number": 3, "state": "closed", "labels": []},
            4: {"number": 4, "state": "open", "labels": [{"name": "blocked"}]},
        }
        self.parents = {2: 1, 3: 1}
        self.children = {1: [2, 3]}
        self.blocked_by = {4: [3]}
        self.blocking = {3: [4]}
        self.merged = {2, 3}

    def issue(self, number: int) -> dict:
        return self.issues[number]

    def related(self, number: int, relation: str) -> list[dict]:
        mappings = {
            "parent": {key: [value] for key, value in self.parents.items()},
            "sub_issues": self.children,
            "blocked_by": self.blocked_by,
            "blocking": self.blocking,
        }
        return [
            self.issues[related]
            for related in mappings[relation].get(number, [])
        ]

    def blocker_satisfied(self, issue: dict) -> bool:
        return issue["state"] == "closed" and issue["number"] in self.merged

    def update(self, number: int, **changes: object) -> None:
        issue = self.issues[number]
        if "state" in changes:
            issue["state"] = changes["state"]
        if "labels" in changes:
            issue["labels"] = [
                {"name": label} for label in changes["labels"]  # type: ignore[union-attr]
            ]


class LifecycleTests(unittest.TestCase):
    def test_github_close_and_reopen_reconcile_frontier(self) -> None:
        lifecycle = load_lifecycle_module()
        api = FakeIssues()
        lifecycle.reconcile(api, 3, lifecycle.DEFAULT_LABELS)
        self.assertEqual(api.issues[1]["state"], "closed")
        self.assertEqual(
            {label["name"] for label in api.issues[4]["labels"]},
            {"ready-for-agent"},
        )

        api.merged.remove(3)
        api.issues[4]["labels"] = [{"name": "ready-for-agent"}]
        lifecycle.reconcile(api, 3, lifecycle.DEFAULT_LABELS)
        self.assertEqual(
            {label["name"] for label in api.issues[4]["labels"]},
            {"blocked"},
        )
        self.assertEqual(api.issues[1]["state"], "open")
        api.issues[1]["state"] = "closed"
        lifecycle.reconcile(api, 1, lifecycle.DEFAULT_LABELS)
        self.assertEqual(api.issues[1]["state"], "open")
        api.merged.add(3)
        lifecycle.reconcile(api, 1, lifecycle.DEFAULT_LABELS, "reopened")
        self.assertEqual(api.issues[1]["state"], "closed")

        api.issues[3]["state"] = "open"
        api.issues[3]["labels"] = [{"name": "ready-for-human"}]
        lifecycle.reconcile(api, 3, lifecycle.DEFAULT_LABELS, "reopened")
        self.assertEqual(api.issues[1]["state"], "open")
        self.assertIn(
            "in-progress",
            {label["name"] for label in api.issues[1]["labels"]},
        )
        self.assertEqual(
            {label["name"] for label in api.issues[3]["labels"]},
            {"ready-for-agent"},
        )
        self.assertEqual(
            {label["name"] for label in api.issues[4]["labels"]},
            {"blocked"},
        )


if __name__ == "__main__":
    unittest.main()
