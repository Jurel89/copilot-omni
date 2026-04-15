"""Unit tests for lifecycle hooks."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"


def run_hook(name, payload):
    result = subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout, result.returncode


class TestPreToolUse(unittest.TestCase):

    def test_allow_safe_command(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "shell",
            "tool_args": {"command": "ls -la"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "allow")

    def test_deny_sudo(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "shell",
            "tool_args": {"command": "sudo rm -rf /"},
        })
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertEqual(body["permissionDecision"], "deny")
        self.assertIn("sudo", body["permissionDecisionReason"])

    def test_protected_path(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "write",
            "tool_args": {"file_path": ".claude-plugin/plugin.json"},
        })
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertEqual(body["permissionDecision"], "deny")

    def test_empty_payload_fails_open(self):
        out, rc = run_hook("pre_tool_use.py", {})
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "allow")


class TestUserPromptSubmit(unittest.TestCase):

    def test_matches_autopilot_trigger(self):
        out, rc = run_hook("user_prompt_submit.py",
                           {"prompt": "autopilot build a thing"})
        self.assertEqual(rc, 0)
        self.assertIn("autopilot", out)

    def test_no_match_emits_empty(self):
        out, rc = run_hook("user_prompt_submit.py",
                           {"prompt": "hi there"})
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), {})


class TestSessionStart(unittest.TestCase):

    def test_banner_includes_version(self):
        out, rc = run_hook("session_start.py", {})
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertIn("Copilot Omni", body["additionalContext"])
        self.assertIn("1.0.0", body["additionalContext"])


if __name__ == "__main__":
    unittest.main()
