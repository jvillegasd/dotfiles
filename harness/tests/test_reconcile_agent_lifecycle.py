"""Regression checks for frontier promotion in reconcile-agent-lifecycle.

Planning-only tickets carry no lifecycle label and must stay off the ready
frontier until explicit promotion labels them. Each case below mirrors a
real reconcile path with an in-memory fake of the GitHub API.
"""

import importlib.util
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1]
_SCRIPT = _HARNESS / "skills/setup-harness/scripts/reconcile-agent-lifecycle.py"
_SPEC = importlib.util.spec_from_file_location("reconcile_agent_lifecycle", _SCRIPT)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


def issue(number, labels=(), state="open"):
    return {
        "number": number,
        "state": state,
        "labels": [{"name": label} for label in labels],
    }


class FakeAPI:
    def __init__(self, issues, satisfied=(), blocked_by=None, blocking=None, parent=None):
        self.issues = issues
        self.satisfied = set(satisfied)
        self.blocked_by = blocked_by or {}
        self.blocking = blocking or {}
        self.parent = parent or {}
        self.updated = []

    def issue(self, number):
        return self.issues[number]

    def related(self, number, relation):
        relations = {
            "blocked_by": self.blocked_by,
            "blocking": self.blocking,
            "parent": self.parent,
        }
        return [self.issues[n] for n in relations[relation].get(number, ())]

    def blocker_satisfied(self, blocker):
        return blocker["number"] in self.satisfied

    def update(self, number, **changes):
        self.updated.append((number, changes))
        self.issues[number].update(changes)


class FrontierPromotionTest(unittest.TestCase):
    def setUp(self):
        self.labels = R.DEFAULT_LABELS

    def test_planning_only_ticket_not_promoted(self):
        api = FakeAPI({1: issue(1)})
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [])

    def test_planning_only_ticket_not_promoted_on_reopen(self):
        api = FakeAPI({1: issue(1)})
        R.reconcile_frontier(api, 1, self.labels, reset_active=True)
        self.assertEqual(api.updated, [])

    def test_planning_only_dependent_not_promoted_when_blocker_closes(self):
        api = FakeAPI(
            {1: issue(1, state="closed"), 2: issue(2)},
            satisfied={1},
            blocked_by={2: [1]},
            blocking={1: [2]},
        )
        R.reconcile(api, 1, self.labels)
        self.assertEqual(api.updated, [])

    def test_blocked_ticket_becomes_ready_when_blocker_closes(self):
        api = FakeAPI(
            {1: issue(1, state="closed"), 2: issue(2, labels=(self.labels["blocked"],))},
            satisfied={1},
            blocked_by={2: [1]},
            blocking={1: [2]},
        )
        R.reconcile(api, 1, self.labels)
        self.assertEqual(
            api.updated, [(2, {"labels": [self.labels["ready_for_agent"]]})]
        )

    def test_ready_ticket_becomes_blocked_while_blocker_open(self):
        api = FakeAPI(
            {1: issue(1, labels=(self.labels["ready_for_agent"],)), 2: issue(2)},
            blocked_by={1: [2]},
        )
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [(1, {"labels": [self.labels["blocked"]]})])

    def test_reopened_in_progress_ticket_resets_to_ready(self):
        api = FakeAPI({1: issue(1, labels=(self.labels["in_progress"],))})
        R.reconcile_frontier(api, 1, self.labels, reset_active=True)
        self.assertEqual(api.updated, [(1, {"labels": [self.labels["ready_for_agent"]]})])

    def test_active_ticket_with_no_blockers_untouched(self):
        api = FakeAPI({1: issue(1, labels=(self.labels["in_progress"],))})
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [])

    def test_released_pair_keeps_ready_over_ready_for_human(self):
        api = FakeAPI(
            {1: issue(1, labels=(self.labels["ready_for_agent"], self.labels["ready_for_human"]))}
        )
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [(1, {"labels": [self.labels["ready_for_agent"]]})])

    def test_released_pair_keeps_ready_over_in_progress(self):
        api = FakeAPI(
            {1: issue(1, labels=(self.labels["ready_for_agent"], self.labels["in_progress"]))}
        )
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [(1, {"labels": [self.labels["ready_for_agent"]]})])

    def test_released_pair_keeps_blocked_over_ready_for_human(self):
        api = FakeAPI(
            {1: issue(1, labels=(self.labels["blocked"], self.labels["ready_for_human"])), 2: issue(2)},
            blocked_by={1: [2]},
        )
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [(1, {"labels": [self.labels["blocked"]]})])

    def test_released_pair_keeps_blocked_over_in_progress(self):
        api = FakeAPI(
            {1: issue(1, labels=(self.labels["blocked"], self.labels["in_progress"])), 2: issue(2)},
            blocked_by={1: [2]},
        )
        R.reconcile_frontier(api, 1, self.labels)
        self.assertEqual(api.updated, [(1, {"labels": [self.labels["blocked"]]})])

    def test_deployed_copy_matches_harness_copy(self):
        root = _HARNESS.parent
        deployed_copy = root / ".github/scripts/reconcile-agent-lifecycle.py"
        self.assertEqual(_SCRIPT.read_bytes(), deployed_copy.read_bytes())


if __name__ == "__main__":
    unittest.main()
