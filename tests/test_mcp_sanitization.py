"""Exception-sanitization tests for MCP server (WS8).

Verifies that tool failures do NOT leak filesystem paths, env vars, or
traceback strings into JSON-RPC error responses.
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
    out, err = proc.communicate(
        "\n".join(json.dumps(m) for m in msgs) + "\n", timeout=15
    )
    responses = [json.loads(l) for l in out.strip().splitlines() if l]
    return responses, err


def _call(tool_name, arguments, env):
    responses, err = _rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": tool_name, "arguments": arguments}},
    ], env)
    return responses[0], err


class TestErrorSanitization(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_error_response_no_traceback(self):
        """A handler failure must not include 'Traceback' in the JSON-RPC response."""
        # Trigger a ValueError from state_clear (no mode or all provided).
        resp, _ = _call("state_clear", {}, self.env)
        self.assertIn("error", resp)
        error_str = json.dumps(resp["error"])
        self.assertNotIn("Traceback", error_str)
        self.assertNotIn("traceback", error_str)

    def test_error_response_no_filesystem_path(self):
        """A path-traversal failure from artifact_write must not leak cwd in mirror_error."""
        resp, _ = _call("artifact_write", {
            "kind": "x", "body": "y",
            "run_id": "run-safe",
            "path": "../../../../etc/passwd"
        }, self.env)
        # The result should have a mirror_error about path escaping.
        result_text = resp.get("result", {}).get("content", [{}])[0].get("text", "")
        body = json.loads(result_text) if result_text else {}
        mirror_error = body.get("mirror_error", "")
        # mirror_error should NOT contain the real tmpdir path (a filesystem path).
        self.assertNotIn(self.tmpdir.name, mirror_error)
        # mirror_error should not contain a real absolute path from the system.
        self.assertNotIn("/home/", mirror_error)
        self.assertNotIn("/var/", mirror_error)
        self.assertNotIn("/tmp/tmp", mirror_error)

    def test_error_code_is_32000(self):
        """Handler exceptions must return error code -32000."""
        # state_clear with no args raises ValueError.
        resp, _ = _call("state_clear", {}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32000)

    def test_error_has_tool_name_in_data(self):
        """Sanitized error must include the tool name in data.tool."""
        resp, _ = _call("state_clear", {}, self.env)
        self.assertIn("error", resp)
        data = resp["error"].get("data", {})
        self.assertEqual(data.get("tool"), "state_clear")

    def test_stderr_has_full_detail(self):
        """Full exception info should appear in stderr (for operator logs)."""
        resp, err = _call("state_clear", {}, self.env)
        self.assertIn("error", resp)
        # stderr must contain something (the log line)
        self.assertTrue(len(err) > 0, "Expected stderr output for tool failure")

    def test_unknown_tool_not_sanitized_as_handler_error(self):
        """Unknown tool returns -32601 (method not found), not -32000."""
        resp, _ = _call("no_such_tool", {}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_invalid_params_not_sanitized_as_handler_error(self):
        """Schema validation returns -32602, not -32000."""
        resp, _ = _call("memory_capture", {"content": 999}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)


class TestSanitizeErrorHelper(unittest.TestCase):
    """Unit-test _sanitize_error() directly."""

    def _load_server(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("mcp_server_san", SERVER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_sanitize_hides_path_in_exception(self):
        srv = self._load_server()
        exc = ValueError("/home/user/secret/file.db: something failed")
        result = srv._sanitize_error(exc, "my_tool")
        self.assertEqual(result["code"], -32000)
        self.assertNotIn("/home/user/secret/file.db", result["message"])
        self.assertEqual(result["data"]["tool"], "my_tool")

    def test_sanitize_allows_safe_message(self):
        srv = self._load_server()
        exc = ValueError("mode or all=true required")
        result = srv._sanitize_error(exc, "state_clear")
        self.assertEqual(result["code"], -32000)
        self.assertIn("state_clear", result["message"])
        # Safe message should be included
        self.assertIn("mode or all=true required", result["message"])


if __name__ == "__main__":
    unittest.main()
