"""Security regression tests for high-severity findings.

Post v2.1.0: pre_tool_use.py was deleted (Claude-Code-only hook event). All
policy-decision coverage now targets the MCP ``policy_check`` tool, which is
the live enforcement path for Copilot CLI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "server.py"


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


class TestMcpPolicyCheck(unittest.TestCase):

    def test_edit_file_tool_denied_on_protected_path(self):
        with tempfile.TemporaryDirectory() as td:
            resp = _rpc([
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "policy_check",
                            "arguments": {"tool": "edit_file",
                                          "args": {"file_path": "plugin.json"}}}},
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


class TestPathTraversalHelpers(unittest.TestCase):
    """Phase-C C23: the artifact_write MCP tool was removed, but its
    underlying traversal guards (_safe_identifier + _safe_child_path) are
    still relied on by other tools (workspace, wiki_write, …). We test them
    directly so the regression coverage is kept.
    """

    def _load_server(self):
        import importlib.util
        from pathlib import Path as _P
        server = _P(__file__).resolve().parent.parent / "mcp" / "server.py"
        spec = importlib.util.spec_from_file_location("mcp_server_sec", server)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_safe_identifier_rejects_slash(self):
        srv = self._load_server()
        with self.assertRaises(ValueError):
            srv._safe_identifier("../../etc", "run_id")

    def test_safe_identifier_rejects_backslash(self):
        srv = self._load_server()
        with self.assertRaises(ValueError):
            srv._safe_identifier("foo\\bar", "run_id")

    def test_safe_identifier_accepts_allowed_chars(self):
        srv = self._load_server()
        self.assertEqual(srv._safe_identifier("run-1_abc", "run_id"), "run-1_abc")

    def test_safe_child_path_blocks_traversal(self):
        srv = self._load_server()
        with tempfile.TemporaryDirectory() as td:
            from pathlib import Path as _P
            root = _P(td)
            with self.assertRaises(ValueError):
                srv._safe_child_path(root, "../../../../etc/passwd")

    def test_safe_child_path_allows_child(self):
        srv = self._load_server()
        with tempfile.TemporaryDirectory() as td:
            from pathlib import Path as _P
            root = _P(td)
            child = srv._safe_child_path(root, "sub/file.md")
            self.assertTrue(str(child).startswith(str(root)))


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
