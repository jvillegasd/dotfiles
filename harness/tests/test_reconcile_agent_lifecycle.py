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
        self.history = {
            n: [
                {"event": "labeled", "label": {"name": label}}
                for label in R.label_names(value)
            ]
            for n, value in issues.items()
        }

    def issue(self, number):
        return self.issues[number]

    def related(self, number, relation):
        if relation == "sub_issues":
            return [
                self.issues[n] for n, parents in self.parent.items() if number in parents
            ]
        relations = {
            "blocked_by": self.blocked_by,
            "blocking": self.blocking,
            "parent": self.parent,
        }
        return [self.issues[n] for n in relations[relation].get(number, ())]

    def events(self, number):
        return self.history[number]

    def blocker_satisfied(self, blocker):
        return blocker["state"] == "closed" and blocker["number"] in self.satisfied

    def update(self, number, **changes):
        self.updated.append((number, changes))
        before = R.label_names(self.issue(number))
        self.issues[number].update(changes)
        after = R.label_names(self.issue(number))
        for event, labels in (("labeled", after - before), ("unlabeled", before - after)):
            self.history[number].extend(
                {"event": event, "label": {"name": label}} for label in labels
            )


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


class ParentLifecycleTest(unittest.TestCase):
    def test_completed_parent_loses_lifecycle_labels(self):
        api = FakeAPI(
            {1: issue(1, state="closed"), 2: issue(2, labels=("in-progress", "feature"))},
            satisfied={1},
            parent={1: [2]},
        )
        R.reconcile(api, 1, R.DEFAULT_LABELS, "closed")
        self.assertEqual(api.issue(2)["state"], "closed")
        self.assertEqual(R.label_names(api.issue(2)), {"feature"})

    def test_already_closed_parent_repairs_labels_once(self):
        labels = {
            "blocked": "waiting",
            "ready_for_agent": "queued",
            "in_progress": "working",
            "ready_for_human": "review",
        }
        api = FakeAPI(
            {
                1: issue(1, state="closed"),
                2: issue(2, state="closed", labels=("waiting", "queued", "working", "review", "feature")),
            },
            satisfied={1},
            parent={1: [2]},
        )
        R.reconcile(api, 2, labels, "closed")
        self.assertEqual(api.issue(2)["state"], "closed")
        self.assertEqual(R.label_names(api.issue(2)), {"feature"})
        updates = list(api.updated)
        R.reconcile(api, 2, labels, "closed")
        self.assertEqual(api.updated, updates)

    def test_cleaned_parent_reopens_when_child_reopens(self):
        custom = {
            "blocked": "waiting",
            "ready_for_agent": "queued",
            "in_progress": "working",
            "ready_for_human": "review",
        }
        for labels in (R.DEFAULT_LABELS, custom):
            with self.subTest(labels=labels):
                api = FakeAPI(
                    {
                        1: issue(1, state="closed", labels=(labels["ready_for_human"],)),
                        2: issue(2, labels=(labels["in_progress"], "feature")),
                    },
                    satisfied={1},
                    parent={1: [2]},
                )
                R.reconcile(api, 1, labels, "closed")
                self.assertEqual(R.label_names(api.issue(2)), {"feature"})
                api.update(1, state="open")
                api.satisfied.clear()
                R.reconcile(api, 1, labels, "reopened")
                self.assertEqual(api.issue(2)["state"], "open")
                self.assertEqual(
                    R.label_names(api.issue(2)), {labels["in_progress"], "feature"}
                )
                updates = list(api.updated)
                R.reconcile(api, 1, labels, "reopened")
                self.assertEqual(api.updated, updates)

    def test_already_reopened_parent_recovers_lifecycle_label(self):
        for event_number in (1, 2):
            with self.subTest(event_number=event_number):
                api = FakeAPI(
                    {
                        1: issue(1, state="closed", labels=("ready-for-human",)),
                        2: issue(2, labels=("in-progress", "feature")),
                    },
                    satisfied={1},
                    parent={1: [2]},
                )
                R.reconcile(api, 1, R.DEFAULT_LABELS, "closed")
                api.update(2, state="open")
                api.update(1, state="open")
                R.reconcile(api, event_number, R.DEFAULT_LABELS, "reopened")
                self.assertEqual(api.issue(2)["state"], "open")
                self.assertEqual(R.label_names(api.issue(2)), {"in-progress", "feature"})
                updates = list(api.updated)
                R.reconcile(api, 1, R.DEFAULT_LABELS)
                self.assertEqual(api.updated, updates)

    def test_reopened_parent_still_respects_its_blockers(self):
        api = FakeAPI(
            {
                1: issue(1, state="closed"),
                2: issue(2, labels=("in-progress", "feature")),
                3: issue(3),
            },
            satisfied={1},
            parent={1: [2]},
            blocked_by={2: [3]},
        )
        R.reconcile(api, 1, R.DEFAULT_LABELS, "closed")
        api.update(2, state="open")
        api.update(1, state="open")
        R.reconcile(api, 2, R.DEFAULT_LABELS, "reopened")
        self.assertEqual(api.issue(2)["state"], "open")
        self.assertEqual(R.label_names(api.issue(2)), {"blocked", "feature"})

    def test_planning_only_parent_stays_unmanaged(self):
        for state in ("open", "closed"):
            with self.subTest(state=state):
                api = FakeAPI(
                    {
                        1: issue(1, state="closed", labels=("ready-for-human",)),
                        2: issue(2, state=state, labels=("feature",)),
                    },
                    satisfied={1},
                    parent={1: [2]},
                )
                R.reconcile(api, 1, R.DEFAULT_LABELS, "closed")
                self.assertEqual(api.updated, [])
                api.update(1, state="open")
                updates = list(api.updated)
                R.reconcile(api, 1, R.DEFAULT_LABELS)
                self.assertEqual(api.updated, updates)
                self.assertEqual(api.issue(2)["state"], state)
                self.assertEqual(R.label_names(api.issue(2)), {"feature"})

    def test_parent_waits_for_every_child_merge(self):
        api = FakeAPI(
            {
                1: issue(1, state="closed"),
                2: issue(2, labels=("in-progress", "feature")),
                3: issue(3, state="closed"),
            },
            satisfied={1},
            parent={1: [2], 3: [2]},
        )
        R.reconcile(api, 1, R.DEFAULT_LABELS, "closed")
        self.assertEqual(api.updated, [])
        api.satisfied.add(3)
        R.reconcile(api, 3, R.DEFAULT_LABELS, "closed")
        self.assertEqual(api.issue(2)["state"], "closed")
        self.assertEqual(R.label_names(api.issue(2)), {"feature"})

    def test_closed_standalone_ticket_keeps_labels(self):
        api = FakeAPI(
            {1: issue(1, state="closed", labels=("ready-for-human", "feature"))}
        )
        R.reconcile(api, 1, R.DEFAULT_LABELS, "closed")
        self.assertEqual(api.updated, [])


if __name__ == "__main__":
    unittest.main()
