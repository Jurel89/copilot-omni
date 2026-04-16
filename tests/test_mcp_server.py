"""Unit tests for the MCP server JSON-RPC surface."""
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


def roundtrip(messages, env_overrides=None):
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    out, err = proc.communicate(payload, timeout=15)
    lines = [l for l in out.strip().splitlines() if l]
    return [json.loads(l) for l in lines], err


class TestMcpServer(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_initialize(self):
        responses, _ = roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}},
        ], self.env)
        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "copilot-omni")

    def test_tools_list_has_minimum(self):
        responses, _ = roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ], self.env)
        tools = [r for r in responses if r.get("id") == 2][0]["result"]["tools"]
        names = {t["name"] for t in tools}
        # Phase-C: C23 removed artifact_write + run_status (-2). New tools
        # arriving later in Phase C (memory_prune, notepad_prune, wiki_ingest,
        # lsp_*, ast_grep_*) will bring the count back above 20.
        self.assertGreaterEqual(len(names), 18)
        for required in ("health", "memory_capture", "memory_search",
                         "policy_check", "wiki_write", "state_write"):
            self.assertIn(required, names)
        for removed in ("artifact_write", "run_status"):
            self.assertNotIn(removed, names,
                             f"{removed} should have been deleted")

    def test_memory_capture_search_roundtrip(self):
        responses, _ = roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "memory_capture",
                        "arguments": {"scope": "test", "content": "xylophone42"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "memory_search",
                        "arguments": {"query": "xylophone"}}},
        ], self.env)
        search = [r for r in responses if r.get("id") == 3][0]
        body = json.loads(search["result"]["content"][0]["text"])
        self.assertTrue(body["results"])
        self.assertIn("xylophone42", body["results"][0]["content"])

    def test_policy_check_blocks_sudo(self):
        responses, _ = roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "policy_check",
                        "arguments": {"tool": "shell",
                                      "args": {"command": "sudo rm -rf /"}}}},
        ], self.env)
        check = [r for r in responses if r.get("id") == 2][0]
        body = json.loads(check["result"]["content"][0]["text"])
        self.assertEqual(body["decision"], "deny")

    def test_unknown_tool_returns_error(self):
        responses, _ = roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "bogus", "arguments": {}}},
        ], self.env)
        self.assertIn("error", responses[0])
        self.assertEqual(responses[0]["error"]["code"], -32601)

    def test_content_length_framing(self):
        """MCP server must accept Content-Length framed messages (LSP-style)."""
        env = os.environ.copy()
        env.update(self.env)
        proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
        )
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "health", "arguments": {}}},
        ]
        payload = b""
        for m in msgs:
            body = json.dumps(m).encode("utf-8")
            payload += f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        out, _ = proc.communicate(payload, timeout=15)

        # Parse the framed response stream.
        responses = []
        i = 0
        while i < len(out):
            end = out.find(b"\r\n\r\n", i)
            if end < 0:
                break
            header = out[i:end].decode("ascii")
            length = 0
            for h in header.split("\r\n"):
                if h.lower().startswith("content-length"):
                    length = int(h.split(":", 1)[1].strip())
                    break
            body = out[end + 4:end + 4 + length]
            responses.append(json.loads(body))
            i = end + 4 + length

        self.assertEqual(len(responses), 3)
        init = [r for r in responses if r.get("id") == 1][0]
        self.assertEqual(init["result"]["serverInfo"]["name"], "copilot-omni")
        tools = [r for r in responses if r.get("id") == 2][0]
        # Phase-C C23: removed artifact_write + run_status. Lower bound
        # tracks the current surface; restored in later C waves.
        self.assertGreaterEqual(len(tools["result"]["tools"]), 18)
        health = [r for r in responses if r.get("id") == 3][0]
        self.assertIn("content", health["result"])

    def test_wiki_roundtrip(self):
        responses, _ = roundtrip([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "wiki_write",
                        "arguments": {"slug": "intro", "title": "Intro",
                                      "body": "hello"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "wiki_read",
                        "arguments": {"slug": "intro"}}},
        ], self.env)
        read = [r for r in responses if r.get("id") == 3][0]
        body = json.loads(read["result"]["content"][0]["text"])
        self.assertEqual(body["slug"], "intro")
        self.assertEqual(body["title"], "Intro")


if __name__ == "__main__":
    unittest.main()
