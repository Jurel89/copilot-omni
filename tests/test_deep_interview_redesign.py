"""Phase-C C16: deep-interview redesign — challenge-agent pruning + per-axis rubric.

These tests lock in the documented contract. Implementation of the runtime
lives in the skill body (bash/python blocks under .omni/runs/) and is tested
by the e2e pipeline runner; here we only enforce the SKILL.md spec.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "deep-interview" / "SKILL.md"


class TestChallengeAgentPruning(unittest.TestCase):

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_pruning_section_present(self):
        self.assertIn("Challenge-Agent Pruning", self.text)

    def test_pruning_contract_mentions_mode_effectiveness(self):
        self.assertIn("mode_effectiveness", self.text)

    def test_pruning_rule_names_delta_threshold(self):
        # The rule uses |delta| < 0.05 for deactivation.
        self.assertIn("0.05", self.text)

    def test_revival_marker_documented(self):
        self.assertIn("--revive", self.text)


class TestPerAxisRubric(unittest.TestCase):

    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_axis_scores_are_zero_to_hundred(self):
        self.assertIn("0–100", self.text)

    def test_every_required_axis_named(self):
        for axis in ("goal_clarity", "constraint_clarity", "success_criteria",
                     "context_clarity"):
            self.assertIn(axis, self.text,
                          f"axis {axis} missing from rubric")

    def test_evidence_field_required(self):
        self.assertIn("evidence", self.text)
        self.assertIn("(no evidence yet", self.text)

    def test_normalised_score_kept_for_compat(self):
        self.assertIn("ambiguity_score_normalised", self.text)


if __name__ == "__main__":
    unittest.main()
