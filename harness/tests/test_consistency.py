#!/usr/bin/env python3

"""Clauses that must say the same thing on more than one surface.

Every assertion here reads two or more files at once, which is the whole
point: the policy, the command bodies, and the public README each restate the
same contract, and a restatement that drifts is the failure this file exists
to catch. Splitting one of these by target would leave two assertions that
each prove a file contains a string and neither that the two agree.
"""

from __future__ import annotations

import unittest

from fixtures import (
    COMMANDS,
    COMMAND_NAMES,
    LOCAL_SKILLS,
    ROOT,
    SKILLS,
)


def command(name: str) -> str:
    return (COMMANDS / f"{name}.md").read_text()


POLICY = (ROOT / "harness" / "POLICY.md")
README = (ROOT / "harness" / "README.md")


class ConsistencyTests(unittest.TestCase):
    def test_a_workflow_is_never_also_a_skill(self) -> None:
        # A workflow is never also a skill, and no skill outranks a command by
        # answering to the same name.
        self.assertTrue(set(COMMAND_NAMES).isdisjoint(
            path.name for path in SKILLS.iterdir() if path.is_dir()
        ))

    def test_architecture_rule_reads_the_same_everywhere(self) -> None:
        architecture_rule = "`improve-codebase-architecture` produces planning input, never a change contract: keep its report and grilling read-only, do not edit `CONTEXT.md` or ADRs inline, and route a selected candidate through native plan mode, `/spec`, or `/proto` before changing files."
        for body in (POLICY.read_text(), README.read_text()):
            self.assertIn(architecture_rule, body)

    def test_no_surface_loads_the_frontend_design_body_implicitly(self) -> None:
        # Nothing loads it implicitly. A command or a local skill that named it
        # would pull it into every run of that workflow, which is the one
        # entry path scope alone cannot close.
        bodies = {f"commands/{name}.md": (COMMANDS / f"{name}.md") for name in COMMAND_NAMES}
        bodies.update({f"skills/{name}": (SKILLS / name / "SKILL.md") for name in LOCAL_SKILLS})
        for name in ("design-taste-frontend", "frontend-design", "DESIGN.md", "/design"):
            for label, path in bodies.items():
                self.assertNotIn(name, path.read_text(), f"{label}: {name}")
        policy = POLICY.read_text()
        for name in ("frontend-design", "DESIGN.md", "/design"):
            self.assertNotIn(name, policy, name)

    def test_three_contract_routes_converge_on_yolo(self) -> None:
        # All three contract routes must converge on the only delivery workflow.
        policy = POLICY.read_text()
        yolo = command("yolo")
        for route in ("`/spec` plus `/create-ticket`", "approved native plan", "`/proto`"):
            self.assertIn(route, policy)
            self.assertIn(route, yolo)

    def test_research_readiness_rule_reads_the_same_everywhere(self) -> None:
        # A confirmed research batch becomes a ticket contract only after
        # /create-ticket publishes it.
        readiness_rule = "Publication confirmation alone does not make a research ticket implementation-ready; agreed behavior, acceptance criteria, and verification or test seams are also required."
        for body in (POLICY.read_text(), README.read_text()):
            self.assertIn(readiness_rule, body)

    def test_tracker_binding_reads_the_same_everywhere(self) -> None:
        # Tracker binding changes the branch and pull-request metadata, not the
        # delivery pipeline.
        policy = POLICY.read_text()
        readme = README.read_text()
        yolo = command("yolo")
        proto = command("proto")
        for body in (policy, yolo, proto):
            self.assertIn("`<type>/<tracker-id>-<short-slug>`", body)
            self.assertIn("`<type>/<short-slug>`", body)
        for body in (policy, yolo, readme):
            self.assertIn("Contract source and tracker binding are independent", body)
        for body in (policy, readme):
            self.assertIn("tracker-bound only when a tracker exists", body)

    def test_every_other_pull_request_workflow_refuses_to_merge(self) -> None:
        # /squash-land is the one workflow that merges, and only because a
        # human typed its name. Every other pull-request workflow still refuses.
        for name in ("yolo", "feedback", "address-review"):
            self.assertIn("Never merge", command(name), name)


if __name__ == "__main__":
    unittest.main()
