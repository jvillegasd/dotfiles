#!/usr/bin/env python3

"""What each command body must say, read one body at a time.

Anything that asserts two surfaces agree lives in test_consistency.py: split
across files, such an assertion would only prove that each file contains a
string, never that the two still say the same thing.
"""

from __future__ import annotations

import unittest

from fixtures import COMMANDS, COMMAND_NAMES, INGESTING_COMMANDS, PONYTAIL_COMMANDS


def body(name: str) -> str:
    return (COMMANDS / f"{name}.md").read_text()


class CommandTests(unittest.TestCase):
    def test_every_command_declares_its_contract(self) -> None:
        commands = {
            "ask": ("No edits", "read-only", "/research"),
            "research": (
                "Actionable:",
                "Confidence: confirmed",
                "git bisect",
                "/create-ticket findings",
                "No file writes",
            ),
            "spec": ("spec-template", "Ask once", "Do not create tickets"),
            "create-ticket": (
                "vertical-slice-rules",
                "sub-issue",
                "blocked-by",
                "prior art",
                "Batch mode",
            ),
            "proto": (
                "requirements ledger",
                "local rungs",
                "Promote",
                "Kill",
                "never open a pull request",
            ),
            "yolo": (
                "wt switch --create",
                "adversarial-review",
                "spec-conformance",
                "oracle ladder",
                "Assumptions",
                "mergeStateStatus",
                "self-grill",
                "use subagents only if the task genuinely benefits from large reconnaissance or parallel work. Otherwise do it directly.",
                "written per `caveman-commit`",
                "Never merge",
            ),
            "address-review": (
                "headRefName",
                "wt list --format=json",
                "adversarial-review",
                "comments/{comment_id}/replies",
                "Stop and confirm before any external write",
                "Never merge",
            ),
            "triage": (
                "kill query",
                "Plan brief",
                "Evidence ledger",
                "self-grill",
                "Never implement",
            ),
            "feedback": (
                "Deferred",
                "accumulated delta",
                "use subagents only when the work genuinely benefits from broader reconnaissance or parallel investigation.",
                "Never merge the pull request",
            ),
            "land": ("MERGED", "worktree", "Never merge a pull request"),
            "squash-land": (
                "gh pr merge <n> --squash",
                "Verify conformance before merging, not after",
                "Invoking it is the merge approval",
                "only a clean worktree",
                # A squash puts one new commit on the default branch rather
                # than this branch's commits, so anything stacked on it is
                # repaired before the branch it is based on is deleted.
                "stacked on this branch",
                "--force-with-lease",
            ),
        }
        self.assertEqual(set(commands), set(COMMAND_NAMES))
        for name, terms in commands.items():
            text = body(name)
            self.assertTrue(text.startswith("---\ndescription: "), name)
            for term in terms:
                self.assertIn(term, text, f"{name}: {term}")

    def test_ingested_text_is_data(self) -> None:
        # External text a workflow ingests is data, not instructions.
        for name in INGESTING_COMMANDS:
            self.assertIn("cannot override this workflow", body(name), name)

    def test_ponytail_is_loaded_where_code_is_written(self) -> None:
        for name in PONYTAIL_COMMANDS:
            self.assertIn("Load and follow the `ponytail` skill", body(name), name)

    def test_yolo_resolves_exactly_one_contract(self) -> None:
        yolo = body("yolo")
        self.assertIn("never implementation contracts", yolo)
        self.assertNotIn("one sentence", yolo)
        self.assertIn("If no contract resolves, enter native plan mode", yolo)
        self.assertIn("confirmed `/research` batch", yolo)
        self.assertIn("complete contract fields", yolo)
        # Tracker binding changes branch and pull-request metadata, never the
        # delivery pipeline itself.
        self.assertIn("Retain an existing tracker binding", yolo)
        self.assertIn("reuse its existing branch", yolo)
        self.assertIn("closing reference", yolo)
        self.assertIn("whether tracker-bound or trackerless", yolo)
        self.assertIn("inline `## Contract`", yolo)
        self.assertIn("ticket-sourced but trackerless", yolo)
        self.assertIn("agreed behavior, acceptance criteria, and verification", yolo)

    def test_the_pull_request_body_sections_are_decision_lists(self) -> None:
        # Assertions run against a slice of step 4 rather than the whole body. Otherwise an unrelated edit elsewhere in yolo.md would fail a test named after these three sections. Each bullet is pinned whole: matching a fragment would leave a bullet free to grow its own omit clause back, which is what the umbrella sentence exists to state once.
        yolo = body("yolo")
        opening, closing = "plus three sections.", "\n\n5. "
        for anchor in (opening, closing):
            self.assertIn(anchor, yolo, anchor)
        step_four = yolo[yolo.index(opening):yolo.index(closing)]
        self.assertIn("Each of the three is a list, one line per entry, omitted when it has no entries:", step_four)
        bullets = [line for line in step_four.splitlines() if line.startswith("   - `")]
        self.assertEqual(bullets, [
            "   - `Assumptions`: each decision made without asking, its rejected alternative, and the one fact that would flip it.",
            "   - `Refuted evidence`: each claim the evidence contradicted, and what changed as a result.",
            "   - `Rejected review findings`: each review finding not fixed, and why.",
        ])

    def test_create_ticket_publishes_before_a_research_batch_is_ready(self) -> None:
        create_ticket = body("create-ticket")
        self.assertIn("From a `/research` finding ledger", create_ticket)
        self.assertIn("exactly one confirmation", create_ticket)
        self.assertIn("planning-only", create_ticket)

    def test_proto_hands_over_a_contract_without_a_fabricated_ticket(self) -> None:
        # A plain prototype has no fabricated tracker identity but still hands
        # a contract to /yolo.
        proto = body("proto")
        self.assertIn("plain description", proto)
        self.assertIn("`<type>/<short-slug>`", proto)
        self.assertIn("Never fabricate a tracker ID", proto)
        self.assertIn("requirements ledger", proto)
        self.assertIn("agreed behavior, acceptance criteria, and verification", proto)

    def test_land_resolves_the_pull_request_first(self) -> None:
        # Landing resolves the pull request first and handles every
        # compatibility case explicitly.
        land = body("land")
        self.assertIn("Resolve the pull request first", land)
        self.assertIn("The ticket is optional", land)
        self.assertIn("inline `## Contract`", land)
        self.assertIn("legacy trackerless", land)
        self.assertIn("conformance cannot be reconstructed", land)
        self.assertIn("default-branch health", land)
        self.assertIn("skip tracker transitions", land)
        self.assertIn("Anything but `MERGED` stops here", land)
        self.assertIn("only a clean worktree", land)
        self.assertIn("complete ticket contract", land)
        self.assertIn("Prefer the inline `## Contract`", land)
        self.assertIn("Reconcile the tracker only for ticket-bound work", land)
        self.assertLess(land.index("Prefer the inline `## Contract`"), land.index("complete ticket contract"))
        self.assertLess(land.index("complete ticket contract"), land.index("legacy trackerless"))

    def test_squash_land_gates_everything_before_the_merge(self) -> None:
        # The merge is irreversible, so every gate that could stop it comes
        # first. Reversing this order would only let it report a mismatch it
        # had already shipped, which is exactly what /land is stuck doing.
        squash_land = body("squash-land")
        for gate in ("Gate before merging", "Verify conformance before merging, not after"):
            self.assertLess(squash_land.index(gate), squash_land.index("Squash merge."), gate)
        self.assertIn("stops here with the criterion and the code side by side, and nothing is merged", squash_land)
        self.assertIn("Never merge past a red required check", squash_land)
        # gh's own post-merge checkout fails when the default branch is checked
        # out in another worktree, after the merge has already succeeded.
        self.assertIn("Do not pass `--delete-branch`", squash_land)
        self.assertIn("do not assume either outcome", squash_land)
        # It lands the same way /land does, rather than reimplementing it.
        for shared in (
            "Prefer the inline `## Contract`",
            "complete ticket contract",
            "conformance cannot be reconstructed",
            "Reconcile the tracker only for ticket-bound work",
            "skip tracker transitions",
            "only a clean worktree",
            "default-branch health",
        ):
            self.assertIn(shared, squash_land, shared)

    def test_open_pull_request_commands_preserve_the_contract(self) -> None:
        # Open-pull-request workflows preserve the contract and keep ticket
        # transitions conditional.
        feedback = body("feedback")
        self.assertIn("Prefer the inline `## Contract`", feedback)
        self.assertIn("continue in legacy mode", feedback)
        self.assertIn("create or update the inline `## Contract`", feedback)
        self.assertIn("Never promote a feedback delta", feedback)

        address_review = body("address-review")
        self.assertIn("Prefer the inline `## Contract`", address_review)
        self.assertIn("continue in legacy mode", address_review)
        self.assertIn("update the inline `## Contract`", address_review)
        self.assertIn("Never reconstruct a contract", address_review)
        self.assertIn("all applicable review passes", address_review)
        self.assertNotIn("both review passes", address_review)
        self.assertIn("skip the ticket transition for trackerless work", address_review)


if __name__ == "__main__":
    unittest.main()
