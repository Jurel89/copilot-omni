"""Unit tests for the live lifecycle hooks.

v2.1.0 restored ``hooks/pre_tool_use.py`` as the corporate policy guard
(Copilot CLI fires the ``preToolUse`` event before every tool call). This
module regression-tests the hook's decision surface: deny-commands matching,
protected-path blocking, and safe-command allow-through. ``session_start.py``
is covered by its own banner test and the MCP smoke suite.
"""
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

    def test_handles_copilot_cli_payload_shape(self):
        # Regression: Copilot CLI emits `toolName` + `toolArgs` where
        # `toolArgs` is a JSON-encoded STRING (per the hooks-configuration
        # reference). The hook must decode it; naïve `.get()` against a
        # string would raise AttributeError on the first live tool event.
        out, rc = run_hook("pre_tool_use.py", {
            "timestamp": 1704614600000,
            "cwd": "/tmp",
            "toolName": "bash",
            "toolArgs": json.dumps({"command": "sudo rm -rf /"}),
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "deny")

    def test_deny_create_tool_on_protected_path(self):
        # Regression: Copilot CLI's `create` tool name was previously not in
        # the file-modification set, so `create plugin.json` silently slipped
        # through the protected-path check.
        out, rc = run_hook("pre_tool_use.py", {
            "toolName": "create",
            "toolArgs": json.dumps({"path": "plugin.json",
                                    "file_text": "bogus"}),
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "deny")

    def test_malformed_toolargs_string_allows_through(self):
        # If `toolArgs` is a string but not valid JSON, treat args as empty
        # rather than crashing. Downstream checks fall through to allow
        # when no command / file_path is present.
        out, rc = run_hook("pre_tool_use.py", {
            "toolName": "bash",
            "toolArgs": "{not-json",
        })
        self.assertEqual(rc, 0)
        # No command argument means no deny pattern matches → allow.
        self.assertEqual(json.loads(out)["permissionDecision"], "allow")

    def test_deny_sudo(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "shell",
            "tool_args": {"command": "sudo rm -rf /"},
        })
        self.assertEqual(rc, 0)
        body = json.loads(out)
        self.assertEqual(body["permissionDecision"], "deny")

    def test_deny_fork_bomb(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "shell",
            "tool_args": {"command": ":(){ :|:& };:"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "deny")

    def test_protected_root_plugin_json(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "write",
            "tool_args": {"file_path": "plugin.json"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "deny")

    def test_protected_mcp_json(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "edit_file",
            "tool_args": {"file_path": ".mcp.json"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "deny")

    def test_protected_hooks_json(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "write",
            "tool_args": {"file_path": "hooks/hooks.json"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "deny")

    def test_unrelated_file_allowed(self):
        out, rc = run_hook("pre_tool_use.py", {
            "tool_name": "write",
            "tool_args": {"file_path": "src/app.py"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
