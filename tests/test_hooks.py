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

    def test_protected_path_unicode_nfd_is_normalised(self):
        """Phase-C C05: an NFD-encoded protected path must still be blocked.

        Writes a temporary policy with a composed (NFC) protected path, then
        submits a decomposed (NFD) candidate that is visually identical. With
        NFC normalisation wired in the hook the deny decision fires; without
        it the substring match misses and the write is allowed.
        """
        import os as _os
        import tempfile
        import unicodedata as _ud
        composed = "naïve/config.json"           # NFC
        decomposed = _ud.normalize("NFD", composed)
        self.assertNotEqual(composed, decomposed)
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            policy_path.write_text(json.dumps({
                "profile": "custom",
                "deny_commands": [],
                "protected_paths": [composed],
            }), encoding="utf-8")
            env = {**_os.environ, "OMNI_POLICY_FILE": str(policy_path)}
            result = subprocess.run(
                [sys.executable, str(HOOKS / "pre_tool_use.py")],
                input=json.dumps({
                    "tool_name": "write",
                    "tool_args": {"file_path": decomposed},
                }),
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            self.assertEqual(result.returncode, 0)
            body = json.loads(result.stdout)
            self.assertEqual(body["permissionDecision"], "deny",
                             f"NFD candidate should be blocked: {result.stdout!r}")

    def test_malformed_shell_command_denied(self):
        """C5: malformed shell input (unclosed quote) must exit with deny, not allow.

        Plan §2.WS7 contract: ValueError from shlex.split → DENY.
        Previously the hook fell through to allow after catching ValueError.
        """
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "shell",
            "tool_args": {"command": "echo 'unterminated"},
        })
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertEqual(body["permissionDecision"], "deny",
                         f"malformed shell command must be denied, got: {body}")
        self.assertIn("malformed", body.get("permissionDecisionReason", "").lower())

    def test_malformed_bash_command_denied(self):
        """C5 variant: tool_name='bash' with malformed quoting also denied."""
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "bash",
            "tool_args": {"command": 'echo "no closing quote'},
        })
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertEqual(body["permissionDecision"], "deny",
                         f"malformed bash command must be denied, got: {body}")


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
        ctx = body["additionalContext"]
        # Banner is wrapped in <omni-banner> tag; check for the tag and version
        self.assertIn("<omni-banner>", ctx)
        # Version string appears in the banner (may be "unknown" if plugin.json unreadable)
        self.assertRegex(ctx, r"copilot-omni v[\w.\-]+")


if __name__ == "__main__":
    unittest.main()
