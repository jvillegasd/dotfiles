#!/usr/bin/env python3

"""What each locally authored skill body must carry."""

from __future__ import annotations

import unittest

from fixtures import SKILLS


class SkillTests(unittest.TestCase):
    def test_every_skill_declares_its_protocol(self) -> None:
        skills = {
            "setup-harness": (
                "docs/agents/harness.json",
                "docs/agents/issue-tracker.md",
                "agent-lifecycle.yml",
            ),
            "adversarial-review": (
                "Reviewer A",
                "Reviewer B",
                "Never three",
            ),
            "evidence": (
                "Kill query first",
                "falsifiable",
                "No-fabrication",
                "Source map, by capability",
                "Version history",
            ),
            "grilling": ("Mode: interactive", "Mode: self-grill", "load-bearing"),
        }
        for name, terms in skills.items():
            body = (SKILLS / name / "SKILL.md").read_text()
            for term in terms:
                self.assertIn(term, body, f"{name}: {term}")


if __name__ == "__main__":
    unittest.main()
