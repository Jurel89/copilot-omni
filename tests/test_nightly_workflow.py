"""Phase-C C28: contract test for .github/workflows/copilot-nightly.yml.

We can't run the workflow from the test suite, but we can lock in the
invariants that keep it safe to add: scheduled cron, manual dispatch,
secret guard, plugin install + two smoke turns.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows" / "copilot-nightly.yml"


class TestNightlyWorkflow(unittest.TestCase):

    def setUp(self):
        self.text = WF.read_text(encoding="utf-8")

    def test_file_exists(self):
        self.assertTrue(WF.exists())

    def test_scheduled(self):
        self.assertIn("schedule:", self.text)
        self.assertIn("cron:", self.text)

    def test_manual_dispatch(self):
        self.assertIn("workflow_dispatch:", self.text)

    def test_guarded_on_missing_secret(self):
        """Job must skip (not fail) when COPILOT_TOKEN is absent."""
        self.assertIn("COPILOT_TOKEN", self.text)
        self.assertIn("secret_check", self.text)
        self.assertIn("has_token=false", self.text)
        self.assertIn("if: steps.secret_check.outputs.has_token == 'true'",
                      self.text)

    def test_installs_copilot_cli(self):
        self.assertIn("npm install -g @github/copilot", self.text)

    def test_installs_plugin(self):
        self.assertIn("copilot plugin install", self.text)

    def test_two_turn_smoke(self):
        self.assertIn("Turn 1", self.text)
        self.assertIn("Turn 2", self.text)

    def test_timeout_guard(self):
        self.assertIn("timeout-minutes:", self.text)


if __name__ == "__main__":
    unittest.main()
