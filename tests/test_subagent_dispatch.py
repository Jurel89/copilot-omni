"""Tests for B1 — skill-vs-agent dispatcher in subagent.py.

Verifies:
- Known skill names route to /copilot-omni:<name> (not --agent)
- Real agent names route to --agent <name>
- --is-skill CLI subcommand returns 0/1 correctly
- No name collision between skills and agents produces wrong routing
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBAGENT_PY = ROOT / "scripts" / "subagent.py"


def _load_subagent():
    spec = importlib.util.spec_from_file_location("subagent", SUBAGENT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestKnownSkillsSet(unittest.TestCase):
    """_KNOWN_SKILLS contains the expected names."""

    def setUp(self):
        self.mod = _load_subagent()

    def test_known_skills_nonempty(self):
        self.assertGreater(len(self.mod._KNOWN_SKILLS), 0)

    def test_ralplan_is_skill(self):
        self.assertIn("ralplan", self.mod._KNOWN_SKILLS)

    def test_ralph_is_skill(self):
        self.assertIn("ralph", self.mod._KNOWN_SKILLS)

    def test_ultrawork_is_skill(self):
        self.assertIn("ultrawork", self.mod._KNOWN_SKILLS)

    def test_autopilot_is_skill(self):
        self.assertIn("autopilot", self.mod._KNOWN_SKILLS)

    def test_team_is_skill(self):
        self.assertIn("team", self.mod._KNOWN_SKILLS)

    def test_plan_is_skill(self):
        # "plan" is both a skill and could be confused with an agent
        self.assertIn("plan", self.mod._KNOWN_SKILLS)

    def test_executor_is_not_skill(self):
        # Real agents must not be in _KNOWN_SKILLS
        self.assertNotIn("executor", self.mod._KNOWN_SKILLS)

    def test_architect_is_not_skill(self):
        self.assertNotIn("architect", self.mod._KNOWN_SKILLS)


class TestBuildCmdDispatch(unittest.TestCase):
    """_build_cmd routes skills to /copilot-omni: and agents to --agent."""

    def setUp(self):
        self.env_backup = os.environ.copy()
        # Ensure FAKE is off so we reach the real dispatch logic
        os.environ.pop("OMNI_SUBAGENT_FAKE", None)
        os.environ.pop("PYTEST_CURRENT_TEST", None)
        os.environ.pop("OMNI_TEST_MODE", None)
        self.mod = _load_subagent()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)

    def _build(self, agent: str, prompt: str = "test", model=None, allow_all=False):
        """Call _build_cmd with a fake copilot path so it doesn't return None."""
        import shutil
        orig = shutil.which
        # Patch shutil.which to return a fake copilot path
        self.mod._build_cmd.__globals__["shutil"] = type(
            "shutil", (), {"which": staticmethod(lambda n: "/fake/copilot" if n == "copilot" else None)}
        )()
        try:
            return self.mod._build_cmd(agent, prompt, model, allow_all)
        finally:
            import shutil as _shutil
            self.mod._build_cmd.__globals__["shutil"] = _shutil

    def test_skill_routes_to_slash_command(self):
        cmd = self._build("ralplan")
        self.assertIsNotNone(cmd)
        # Should contain /copilot-omni:ralplan, NOT --agent
        joined = " ".join(cmd)
        self.assertIn("/copilot-omni:ralplan", joined)
        self.assertNotIn("--agent", joined)

    def test_agent_routes_to_agent_flag(self):
        cmd = self._build("executor")
        self.assertIsNotNone(cmd)
        joined = " ".join(cmd)
        self.assertIn("--agent", joined)
        self.assertIn("executor", joined)
        self.assertNotIn("/copilot-omni:", joined)

    def test_plan_skill_routes_correctly(self):
        # "plan" name collision: must route as skill
        cmd = self._build("plan")
        self.assertIsNotNone(cmd)
        joined = " ".join(cmd)
        self.assertIn("/copilot-omni:plan", joined)
        self.assertNotIn("--agent", joined)

    def test_ultraqa_routes_to_slash_command(self):
        cmd = self._build("ultraqa")
        self.assertIsNotNone(cmd)
        self.assertIn("/copilot-omni:ultraqa", " ".join(cmd))


class TestIsSkillCLI(unittest.TestCase):
    """--is-skill CLI subcommand exits 0 for known skills, 1 for unknowns."""

    def _run_is_skill(self, name: str):
        return subprocess.run(
            [sys.executable, str(SUBAGENT_PY), "--is-skill", name],
            capture_output=True,
            text=True,
        )

    def test_known_skill_exits_zero(self):
        proc = self._run_is_skill("ralplan")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "1")

    def test_unknown_skill_exits_one(self):
        proc = self._run_is_skill("executor")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout.strip(), "0")

    def test_real_agent_exits_one(self):
        proc = self._run_is_skill("architect")
        self.assertEqual(proc.returncode, 1)

    def test_plan_is_skill(self):
        # "plan" skill/agent collision — must be 0
        proc = self._run_is_skill("plan")
        self.assertEqual(proc.returncode, 0)

    def test_ultrawork_is_skill(self):
        proc = self._run_is_skill("ultrawork")
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
