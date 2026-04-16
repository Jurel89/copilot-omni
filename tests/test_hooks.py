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
    """WS3: user_prompt_submit emits structured <router-decision> blocks."""

    def _get_context(self, prompt: str) -> str:
        out, rc = run_hook("user_prompt_submit.py", {"prompt": prompt})
        self.assertEqual(rc, 0)
        body = json.loads(out)
        return body.get("additionalContext", "")

    def test_vague_prompt_emits_redirect_tag(self):
        ctx = self._get_context("build me something")
        self.assertIn('<router-decision', ctx)
        self.assertIn('redirect="deep-interview"', ctx)
        self.assertIn('reason="vague-prompt"', ctx)

    def test_concrete_prompt_emits_proceed_tag(self):
        ctx = self._get_context("fix scripts/router.py:10 — parse() fails")
        self.assertIn('<router-decision', ctx)
        self.assertIn('proceed="true"', ctx)

    def test_bypass_prompt_emits_bypass_tag(self):
        ctx = self._get_context("do something --skip-interview")
        self.assertIn('<router-decision', ctx)
        self.assertIn('bypass="true"', ctx)

    def test_redirect_tag_includes_signals(self):
        ctx = self._get_context("i want a website")
        self.assertIn('"signals"', ctx)
        self.assertIn('bypass', ctx)

    def test_proceed_tag_includes_score(self):
        ctx = self._get_context("fix hooks/pre_tool_use.py:42")
        self.assertIn('score=', ctx)

    def test_kill_switch_omni_skip_hooks(self):
        import os
        import subprocess
        env = os.environ.copy()
        env["OMNI_SKIP_HOOKS"] = "1"
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "user_prompt_submit.py")],
            input=json.dumps({"prompt": "build me something"}),
            capture_output=True, text=True, timeout=10, env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {})

    def test_kill_switch_disable_omni(self):
        import os
        import subprocess
        env = os.environ.copy()
        env["DISABLE_OMNI"] = "1"
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "user_prompt_submit.py")],
            input=json.dumps({"prompt": "fix hooks/pre_tool_use.py:10"}),
            capture_output=True, text=True, timeout=10, env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {})

    def test_kill_switch_omc_compat_alias(self):
        import os
        import subprocess
        env = os.environ.copy()
        env["OMC_SKIP_HOOKS"] = "1"
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "user_prompt_submit.py")],
            input=json.dumps({"prompt": "do something"}),
            capture_output=True, text=True, timeout=10, env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {})

    def test_empty_prompt_emits_redirect(self):
        ctx = self._get_context("")
        self.assertIn('<router-decision', ctx)
        self.assertIn('redirect="deep-interview"', ctx)

    def test_bypass_tag_no_redirect_attr(self):
        ctx = self._get_context("migrate db --skip-interview")
        self.assertNotIn('redirect="deep-interview"', ctx)
        self.assertIn('bypass="true"', ctx)


class TestSessionStart(unittest.TestCase):

    def test_banner_includes_version(self):
        out, rc = run_hook("session_start.py", {})
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertIn("Copilot Omni", body["additionalContext"])
        self.assertIn("1.0.0", body["additionalContext"])


if __name__ == "__main__":
    unittest.main()
