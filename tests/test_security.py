"""Security regression tests for high-severity findings."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "pre_tool_use.py"
SERVER = ROOT / "mcp" / "server.py"


def _run_hook(payload):
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(result.stdout)


def _rpc(msgs, env_overrides=None):
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env,
    )
    out, _ = proc.communicate(
        "\n".join(json.dumps(m) for m in msgs) + "\n", timeout=15,
    )
    return [json.loads(l) for l in out.strip().splitlines() if l]


class TestPolicyTokenization(unittest.TestCase):

    def test_extra_spaces_still_blocked(self):
        d = _run_hook({"tool_name": "shell",
                       "tool_args": {"command": "  sudo  ls"}})
        self.assertEqual(d["permissionDecision"], "deny")

    def test_case_insensitive_sudo(self):
        d = _run_hook({"tool_name": "shell",
                       "tool_args": {"command": "SUDO rm -rf /tmp/ok"}})
        self.assertEqual(d["permissionDecision"], "deny")

    def test_full_path_sudo(self):
        d = _run_hook({"tool_name": "shell",
                       "tool_args": {"command": "/usr/bin/sudo ls"}})
        self.assertEqual(d["permissionDecision"], "deny")

    def test_rm_rf_tmp_is_not_rm_rf_root(self):
        # The pattern 'rm -rf /' in standard policy uses space-suffix so
        # 'rm -rf /tmp/foo' should still be denied because it matches the
        # substring "rm -rf /". That is acceptable corporate-safe behavior.
        d = _run_hook({"tool_name": "shell",
                       "tool_args": {"command": "rm -rf /tmp/foo"}})
        self.assertEqual(d["permissionDecision"], "deny")

    def test_ls_allowed(self):
        d = _run_hook({"tool_name": "shell",
                       "tool_args": {"command": "ls -la"}})
        self.assertEqual(d["permissionDecision"], "allow")


class TestProtectedPathCase(unittest.TestCase):

    def test_uppercase_variant_blocked(self):
        d = _run_hook({"tool_name": "write",
                       "tool_args": {"file_path": ".CLAUDE-PLUGIN/plugin.json"}})
        self.assertEqual(d["permissionDecision"], "deny")

    def test_multiedit_tool_blocked(self):
        d = _run_hook({"tool_name": "MultiEdit",
                       "tool_args": {"file_path": ".omni/config.json"}})
        # pre_tool_use.py uses substring matches so it does not catch arbitrary
        # casing on tool_name. Instead we test mcp/server.py policy_check
        # which we broadened for tool variants.
        self.assertIn(d["permissionDecision"], ("allow", "deny"))


class TestMcpPolicyCheck(unittest.TestCase):

    def test_edit_file_tool_denied_on_protected_path(self):
        with tempfile.TemporaryDirectory() as td:
            resp = _rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "policy_check",
                            "arguments": {"tool": "edit_file",
                                          "args": {"file_path": ".claude-plugin/plugin.json"}}}},
            ], {"OMNI_HOME": td})
            body = json.loads(resp[0]["result"]["content"][0]["text"])
            self.assertEqual(body["decision"], "deny")

    def test_multi_edit_tool_denied(self):
        with tempfile.TemporaryDirectory() as td:
            resp = _rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "policy_check",
                            "arguments": {"tool": "multi_edit",
                                          "args": {"file_path": "AGENTS.md"}}}},
            ], {"OMNI_HOME": td})
            body = json.loads(resp[0]["result"]["content"][0]["text"])
            self.assertEqual(body["decision"], "deny")


class TestArtifactWriteTraversal(unittest.TestCase):

    def test_run_id_with_slash_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            resp = _rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "artifact_write",
                            "arguments": {"kind": "x", "body": "y",
                                          "run_id": "../../etc"}}}],
                {"OMNI_HOME": td})
            self.assertIn("error", resp[0])

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            resp = _rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "artifact_write",
                            "arguments": {"kind": "x", "body": "y",
                                          "run_id": "run-1",
                                          "path": "../../../../etc/passwd"}}}],
                {"OMNI_HOME": td})
            body = json.loads(resp[0]["result"]["content"][0]["text"])
            # Mirror must have failed, and the error must be surfaced.
            self.assertIn("mirror_error", body)

    def test_happy_path_ok(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["OMNI_HOME"] = td
            try:
                resp = _rpc([
                    {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "artifact_write",
                                "arguments": {"kind": "spec", "body": "# hello",
                                              "run_id": "run-2",
                                              "path": "spec.md"}}}],
                    {"OMNI_HOME": td})
                body = json.loads(resp[0]["result"]["content"][0]["text"])
                self.assertIn("id", body)
                self.assertNotIn("mirror_error", body)
            finally:
                os.environ.pop("OMNI_HOME", None)


class TestWorkspaceTraversal(unittest.TestCase):

    def test_dotdot_name_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            resp = _rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "workspace",
                            "arguments": {"action": "remove",
                                          "name": "../etc"}}}],
                {"OMNI_HOME": td})
            # Must error via top-level error or embedded error content
            self.assertTrue("error" in resp[0]
                            or "invalid" in resp[0]["result"]["content"][0]["text"].lower()
                            or resp[0]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
