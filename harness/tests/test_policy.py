#!/usr/bin/env python3

"""The policy documents read on their own: POLICY.md, which every client loads
as its global instruction file, and harness/README.md, which is its public
rendering.

Anything asserting that a policy clause also appears on a command or skill
body lives in test_consistency.py.
"""

from __future__ import annotations

import unittest

from fixtures import COMMAND_NAMES, ROOT


POLICY = ROOT / "harness" / "POLICY.md"
README = ROOT / "harness" / "README.md"


class PolicyTests(unittest.TestCase):
    def test_routing_table_names_what_is_installed(self) -> None:
        policy = POLICY.read_text()
        for name in COMMAND_NAMES:
            self.assertIn(f"`/{name}`", policy, name)
        for name in ("code-review", "to-spec", "to-tickets", "`ship`"):
            self.assertNotIn(name, policy, name)
        self.assertIn('| "mock up this ticket\'s frontend", a mockup for one ticket or spec | `/proto` |', policy)

    def test_ponytail_holds_scope_on_a_ui_surface(self) -> None:
        # `ponytail` holds scope on a UI surface by default, and the one
        # installed frontend design body is the named exception to it, with a
        # rule that decides a contested surface rather than one that only
        # excludes work neither body ever claimed. Prose nothing asserts is
        # prose that can be deleted without a test noticing.
        policy = POLICY.read_text()
        self.assertIn("`ponytail` decides a UI surface by default:", policy)
        # Every clause that bounds it is asserted, because the body is
        # description-matchable like any locked body and scope is the only
        # thing holding it. Prose nothing asserts can be deleted silently.
        for clause in (
            "One frontend design body is installed, `impeccable`, and it is the exception rather than the default: `ponytail` governs a UI surface everywhere `impeccable` is not named or matched, and `impeccable` decides nothing that is not a UI surface.",
            "its scope is frontend design broadly: landing pages, portfolios, and redesigns along with dashboards, data tables, and multi-step product UI.",
            "`/proto` and `/yolo` build from that layer whether or not this body is loaded.",
            # The body offers its own installer, updater, hook wiring, and
            # `pin` at runtime. Each one breaks something this harness holds,
            # so the ban lives where the clients actually read it.
            # Asserted through the final clause, not just up to the colon: the
            # rationale is where a wrong claim about what each command touches
            # would sit, and an assertion stopping at the colon cannot see it.
            "Never run its own installer, updater, hook wiring, or pin, whatever the body itself offers: `npx impeccable install` and `npx impeccable update` rewrite the locked directory and break its lock, `$impeccable hooks on` runs `scripts/hook-admin.mjs`, which wires `PostToolUse` and `Stop` manifests into a project's client settings, and `scripts/pin.mjs` writes a new skill directory into whichever harness skills directory it finds, which in this repository is the tracked `harness/skills` that `.agents/skills` points at.",
            "It is updated only through `harness/locked-skills.sh update`.",
        ):
            self.assertIn(clause, policy)

    def test_policy_states_the_three_contract_routes(self) -> None:
        policy = POLICY.read_text()
        self.assertIn("Three contract routes converge on `/yolo`", policy)
        self.assertIn("An approved spec continues through `/create-ticket`", policy)
        self.assertNotIn("Go straight from the approved contract to `/yolo`", policy)
        self.assertIn('"implement this" with no approved contract', policy)
        self.assertIn("agreed behavior, acceptance criteria, and verification", policy)
        self.assertIn("`/squash-land` is the only workflow that merges", policy)
        self.assertIn("`/squash-land` is the single exception", policy)

    def test_readme_describes_the_same_routes_and_landing(self) -> None:
        # Public documentation must describe the same three routes and
        # trackerless landing behavior.
        readme = README.read_text()
        self.assertIn("Three contract routes converge on `/yolo`", readme)
        self.assertIn("inline `## Contract`", readme)
        self.assertIn("ticket is optional", readme)
        self.assertIn("finding ledger remains planning input", readme)
        self.assertIn("finalized `/proto` requirements ledger is an implementation contract", readme)
        self.assertNotIn("verifies the merged state against the ticket, applies the transitions", readme)


if __name__ == "__main__":
    unittest.main()
