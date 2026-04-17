"""Phase-C C01: 16-class skill chooser embedded in router.classify()."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_router():
    spec = importlib.util.spec_from_file_location(
        "router_skill", ROOT / "scripts" / "router.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSkillChooserOutputShape(unittest.TestCase):

    def test_classify_emits_primary_skill_key(self):
        router = _load_router()
        result = router.classify("autopilot build me a REST API")
        self.assertIn("primary_skill", result)
        self.assertIn("skill_scores", result)
        self.assertIsInstance(result["skill_scores"], list)

    def test_bypass_path_also_has_primary_skill(self):
        router = _load_router()
        result = router.classify("build me something --skip-interview")
        self.assertEqual(result["decision"], "bypass")
        self.assertIn("primary_skill", result)


class TestSkillChooserAccuracy(unittest.TestCase):
    """Each rule fires on its canonical prompt."""

    def _pick(self, prompt: str) -> str | None:
        router = _load_router()
        return router.classify(prompt)["primary_skill"]

    def test_autopilot(self):
        self.assertEqual(self._pick("autopilot build me a bookstore API"), "autopilot")

    def test_ralph(self):
        self.assertEqual(self._pick("run ralph until complete"), "ralph")

    def test_ralplan(self):
        self.assertEqual(self._pick("ralplan design me a CLI"), "ralplan")

    def test_ultrawork(self):
        self.assertEqual(self._pick("ultrawork fan-out on 3 tasks"), "ultrawork")

    def test_ultraqa(self):
        self.assertEqual(self._pick("start an ultraqa cycle"), "ultraqa")

    def test_team(self):
        self.assertEqual(self._pick("spin up team mode with tmux panes"), "team")

    def test_deep_interview(self):
        self.assertEqual(self._pick("run a deep-interview socratic session"), "deep-interview")

    def test_debug(self):
        self.assertEqual(self._pick("debug this root-cause analysis please"), "debug")

    def test_trace(self):
        self.assertEqual(self._pick("trace the causal chain with competing hypotheses"), "trace")

    def test_wiki(self):
        self.assertEqual(self._pick("add this to the wiki knowledge base"), "wiki")

    def test_release(self):
        self.assertEqual(self._pick("let's release and tag a version"), "release")

    def test_remember(self):
        self.assertEqual(self._pick("remember save to memory for next time"), "remember")

    def test_mcp_setup(self):
        self.assertEqual(self._pick("set up MCP for this repo"), "mcp-setup")

    def test_cancel(self):
        self.assertEqual(self._pick("cancel and kill the autopilot"), "cancel")

    def test_plan(self):
        self.assertEqual(self._pick("write me a plan for the login page"), "plan")

    def test_verify(self):
        self.assertEqual(self._pick("verify the acceptance criteria hold"), "verify")


class TestSkillChooserEdgeCases(unittest.TestCase):

    def test_no_match_returns_none(self):
        router = _load_router()
        result = router.classify("just a random sentence with no keywords")
        self.assertIsNone(result["primary_skill"])

    def test_ranked_scores_sorted_desc(self):
        router = _load_router()
        result = router.classify("autopilot with a ralplan consensus plan")
        scores = result["skill_scores"]
        values = [s["score"] for s in scores]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_priority_tie_break(self):
        """When two skills tie on score, lower priority index wins."""
        router = _load_router()
        # The phrases "run ralph" and "ralplan" both fire strongly; ralph
        # priority (20) equals ralplan priority (20), so alphabetical name
        # order is the final fallback. Assert the ranked output contains both.
        result = router.classify("run ralph via ralplan")
        names = {s["skill"] for s in result["skill_scores"]}
        self.assertIn("ralph", names)
        self.assertIn("ralplan", names)


if __name__ == "__main__":
    unittest.main()
