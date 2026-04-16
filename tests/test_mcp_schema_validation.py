"""Schema validation tests for MCP tools/call dispatch (WS8).

Tests that the server returns -32602 on bad inputs and that good inputs
pass through to the handler without false-positive validation errors.
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
        "\n".join(json.dumps(m) for m in msgs) + "\n", timeout=15
    )
    return [json.loads(l) for l in out.strip().splitlines() if l]


def _call(tool_name, arguments, env):
    return _rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": tool_name, "arguments": arguments}},
    ], env)[0]


class TestBadInputsReturnInvalidParams(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    # --- type violations ---

    def test_memory_capture_content_wrong_type(self):
        """content must be string, not integer."""
        resp = _call("memory_capture", {"content": 42}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        errors = resp["error"]["data"]["errors"]
        self.assertTrue(any("type" in e["message"] for e in errors))

    def test_memory_search_limit_wrong_type(self):
        """limit must be integer, not string."""
        resp = _call("memory_search", {"query": "x", "limit": "ten"}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_wiki_write_body_wrong_type(self):
        """body must be string, not list."""
        resp = _call("wiki_write", {"slug": "test", "body": [1, 2, 3]}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_notepad_write_body_wrong_type(self):
        """body must be string, not dict."""
        resp = _call("notepad_write", {"body": {"nested": "dict"}}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    # --- required field violations ---

    def test_memory_capture_missing_content(self):
        """content is required for memory_capture."""
        resp = _call("memory_capture", {"scope": "test"}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)
        errors = resp["error"]["data"]["errors"]
        self.assertTrue(any("content" in e["message"] for e in errors))

    def test_wiki_write_missing_slug(self):
        """slug is required for wiki_write."""
        resp = _call("wiki_write", {"body": "hello"}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_wiki_read_missing_slug(self):
        """slug is required for wiki_read."""
        resp = _call("wiki_read", {}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_state_write_missing_mode(self):
        """mode is required for state_write."""
        resp = _call("state_write", {"body": {"x": 1}}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    # --- additionalProperties violations ---

    def test_health_extra_property(self):
        """health schema has additionalProperties: false."""
        resp = _call("health", {"unexpected": "field"}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_doctor_extra_property(self):
        """doctor schema has additionalProperties: false."""
        resp = _call("doctor", {"extra": True}, self.env)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32602)


class TestGoodInputsPassThrough(unittest.TestCase):
    """Good inputs must not be rejected by the validator (no false positives)."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_memory_family_happy_path(self):
        """memory_capture + memory_search succeed with valid inputs."""
        resp = _call("memory_capture",
                     {"scope": "test", "content": "hello world", "tags": ["a", "b"]},
                     self.env)
        self.assertNotIn("error", resp)
        self.assertIn("result", resp)

        resp2 = _call("memory_search", {"query": "hello", "limit": 5}, self.env)
        self.assertNotIn("error", resp2)
        body = json.loads(resp2["result"]["content"][0]["text"])
        self.assertIn("results", body)

    def test_state_family_happy_path(self):
        """state_write + state_read + state_clear work with valid inputs."""
        resp = _call("state_write", {"mode": "router", "body": {"decision": "go"}}, self.env)
        self.assertNotIn("error", resp)

        resp2 = _call("state_read", {"mode": "router"}, self.env)
        self.assertNotIn("error", resp2)
        body = json.loads(resp2["result"]["content"][0]["text"])
        self.assertEqual(body["mode"], "router")
        self.assertEqual(body["body"]["decision"], "go")

        resp3 = _call("state_clear", {"mode": "router"}, self.env)
        self.assertNotIn("error", resp3)

    def test_wiki_family_happy_path(self):
        """wiki_write + wiki_read + wiki_query succeed with valid inputs."""
        resp = _call("wiki_write",
                     {"slug": "gs-intro", "title": "Intro", "body": "# Hello", "tags": ["intro"]},
                     self.env)
        self.assertNotIn("error", resp)

        resp2 = _call("wiki_read", {"slug": "gs-intro"}, self.env)
        self.assertNotIn("error", resp2)
        body = json.loads(resp2["result"]["content"][0]["text"])
        self.assertEqual(body["slug"], "gs-intro")

        resp3 = _call("wiki_query", {"query": "Hello"}, self.env)
        self.assertNotIn("error", resp3)

    def test_health_no_args(self):
        """health accepts empty args."""
        resp = _call("health", {}, self.env)
        self.assertNotIn("error", resp)


if __name__ == "__main__":
    unittest.main()
