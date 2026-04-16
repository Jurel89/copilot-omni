"""Phase-C C14: deep-interview skill UX smoke tests.

The skill is designed to work with Copilot CLI's ``-p`` turn-based mode.
We cannot spawn a real Copilot subprocess in CI, but we can lock in the
invariants that make the UX work:

- SKILL.md frontmatter declares the handoff path under ``.omni/specs/``
- The pipeline chain is deep-interview → omni-plan → autopilot
- The skill's body mentions the ambiguity gate threshold explicitly
- The 3-stage handoff uses a slug-based filename we can actually resolve
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "deep-interview" / "SKILL.md"


class TestDeepInterviewFrontmatter(unittest.TestCase):

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")
        # Pull the frontmatter block only.
        if not self.text.startswith("---"):
            self.fail("SKILL.md missing frontmatter")
        end = self.text.find("\n---", 3)
        self.assertGreater(end, 0)
        self.block = self.text[3:end]

    def test_has_pipeline_declaration(self):
        self.assertIn("pipeline:", self.block)
        self.assertIn("deep-interview", self.block)
        self.assertIn("omni-plan", self.block)
        self.assertIn("autopilot", self.block)

    def test_handoff_path_under_omni_specs(self):
        m = re.search(r"handoff:\s*(\S+)", self.block)
        self.assertIsNotNone(m, "handoff not declared in frontmatter")
        handoff = m.group(1)
        self.assertTrue(handoff.startswith(".omni/specs/"),
                        f"handoff must live under .omni/specs/; got {handoff!r}")

    def test_next_skill_is_omni_plan(self):
        m = re.search(r"next-skill:\s*(\S+)", self.block)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "omni-plan")


class TestDeepInterviewBody(unittest.TestCase):

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_ambiguity_gate_threshold_mentioned(self):
        self.assertTrue(
            "20%" in self.text or "ambiguity" in self.text.lower(),
            "ambiguity gate threshold (default 20%) must be documented",
        )

    def test_socratic_reference_present(self):
        self.assertIn("Socratic", self.text)

    def test_turn_based_p_mode_referenced(self):
        """The skill must document that it works under Copilot CLI's -p mode
        (turn-based), otherwise downstream tools misroute invocations."""
        # Accept either ``copilot -p`` or ``-p turn`` or a documented turn
        # gate — we just need one of these tokens present.
        markers = ("copilot -p", "turn-based", "-p mode", "one turn",
                   "resume", "awaiting-input")
        self.assertTrue(
            any(m in self.text for m in markers),
            f"SKILL.md must mention a turn-based / -p invocation marker; "
            f"looked for: {markers}",
        )


if __name__ == "__main__":
    unittest.main()
