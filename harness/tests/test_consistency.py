#!/usr/bin/env python3

"""Clauses that must say the same thing on more than one surface.

Every assertion here reads two or more files at once, which is the whole
point: the policy, the command bodies, and the public README each restate the
same contract, and a restatement that drifts is the failure this file exists
to catch. Splitting one of these by target would leave two assertions that
each prove a file contains a string and neither that the two agree.
"""

from __future__ import annotations

import json
import re
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
        for name in ("impeccable", "frontend-design", "DESIGN.md", "/design"):
            for label, path in bodies.items():
                self.assertNotIn(name, path.read_text(), f"{label}: {name}")
        policy = POLICY.read_text()
        for name in ("frontend-design", "DESIGN.md", "/design"):
            self.assertNotIn(name, policy, name)

    def test_no_surface_grants_a_skill_scope_over_a_ui_surface(self) -> None:
        # `ponytail` claims no UI authority upstream, so nothing here grants
        # it any. One file is not enough to hold that: the clause outlived its
        # removal from `POLICY.md` once already, in `adversarial-review`, where
        # it ran on every review round while the policy said it did not exist.
        surfaces = {"harness/POLICY.md": POLICY, "harness/README.md": README}
        surfaces.update({f"commands/{name}.md": COMMANDS / f"{name}.md" for name in COMMAND_NAMES})
        surfaces.update({f"skills/{name}": SKILLS / name / "SKILL.md" for name in LOCAL_SKILLS})
        for phrasing in ("decides a UI surface", "governs a UI surface", "scope on a UI surface"):
            for label, path in surfaces.items():
                self.assertNotIn(phrasing, path.read_text(), f"{label}: {phrasing}")

    def test_the_frontend_design_body_policy_names_is_installed(self) -> None:
        # Without this, `POLICY.md` can name a body nobody installed and every
        # other test still passes: the lock and the policy are checked apart.
        lock = json.loads((ROOT / "skills-lock.json").read_text())["skills"]
        named = re.search(
            r"One frontend design body is installed, `([^`]+)`", POLICY.read_text()
        )
        self.assertIsNotNone(named)
        name = named.group(1)  # type: ignore[union-attr]
        self.assertIn(name, lock)
        self.assertTrue((SKILLS / name / "SKILL.md").is_file(), name)
    def test_the_commit_rule_delegates_to_the_locked_body(self) -> None:
        # The policy states the rule and names the body carrying its worked
        # examples; the workflow that commits names it at the commit step. A
        # pointer to a body nobody installed is the failure mode here, so the
        # lockfile is checked rather than the prose alone.
        lock = json.loads((ROOT / "skills-lock.json").read_text())["skills"]
        self.assertIn("caveman-commit", lock)
        self.assertIn(
            "When writing any git commit message, follow the `caveman-commit` skill",
            POLICY.read_text(),
        )
        self.assertIn("written per `caveman-commit`", command("yolo"))

    def test_the_default_branch_fast_forward_names_its_worktree(self) -> None:
        # Both retirement paths fast-forward the default branch, and the way to
        # get it wrong is dropping `-C`: the command then advances whatever
        # branch the current worktree holds, silently when it has not diverged.
        # The failure modes are asserted too, not just the instruction, or they
        # could be deleted from both files with this test still green.
        for name in ("land", "squash-land"):
            text = command(name)
            self.assertIn("in the worktree that has it checked out", text, name)
            self.assertIn("`git -C <that path> merge --ff-only origin/<default>`", text, name)
            self.assertIn("Always pass `-C`", text, name)
            self.assertIn("silently fast-forwards that branch", text, name)
            self.assertIn("exits 128", text, name)

    def test_three_contract_routes_converge_on_yolo(self) -> None:
        # All three contract routes must converge on the only delivery workflow.
        policy = POLICY.read_text()
        yolo = command("yolo")
        for route in ("`/spec` plus `/create-ticket`", "approved in-conversation contract", "`/proto`"):
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

    def test_the_prose_rule_has_an_enforcement_point(self) -> None:
        # A concision rule nothing checks is inert, and a reviewer lens with no
        # rule behind it is a reviewer inventing a standard. Both halves are
        # asserted here so neither can be deleted while the other still passes.
        policy = POLICY.read_text()
        self.assertIn("Write prose a human reads once", policy)
        self.assertIn("never a locked third-party body", policy)
        review = (SKILLS / "adversarial-review" / "SKILL.md").read_text()
        self.assertIn("docstring longer than what it documents", review)

    def test_the_commit_body_wrap_belongs_to_the_locked_body(self) -> None:
        # The no-hard-wrap rule claimed commit bodies while the locked body the
        # policy delegates commit writing to wraps them at 72. The policy drops
        # the claim rather than restating the skill's rule: a restatement that
        # agrees with the body it delegates to buys nothing and adds a second
        # place to drift. That leaves the wrap stated in exactly one place, so
        # both ends are pinned here: the rule no longer reaches a commit body,
        # and the skill still says what the policy now relies on it to say.
        policy = POLICY.read_text()
        wrap_rule = [line for line in policy.splitlines() if line.startswith("- Never hard-wrap prose")]
        self.assertEqual(len(wrap_rule), 1)
        self.assertNotIn("commit bodies", wrap_rule[0])
        self.assertIn("Wrap at 72 chars", (SKILLS / "caveman-commit" / "SKILL.md").read_text())

    def test_every_other_pull_request_workflow_refuses_to_merge(self) -> None:
        # /squash-land is the one workflow that merges, and only because a
        # human typed its name. Every other pull-request workflow still refuses.
        for name in ("yolo", "feedback", "address-review"):
            self.assertIn("Never merge", command(name), name)


if __name__ == "__main__":
    unittest.main()
