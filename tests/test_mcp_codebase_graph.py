"""Tests for the MCP codebase graph and impact tools."""
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


def _rpc(messages, env_overrides=None):
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
    out, _ = proc.communicate(
        "\n".join(json.dumps(message) for message in messages) + "\n", timeout=15
    )
    return [json.loads(line) for line in out.strip().splitlines() if line]


def _call(name, args, env):
    response = _rpc(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            }
        ],
        env,
    )
    return json.loads(response[0]["result"]["content"][0]["text"])


class TestMcpCodebaseGraph(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.omni_home = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.env = {"OMNI_HOME": self.omni_home.name}
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "helper.py").write_text(
            "def helper():\n    return 1\n", encoding="utf-8"
        )
        (self.root / "pkg" / "main.py").write_text(
            "from pkg.helper import helper\n\n\ndef run():\n    return helper()\n",
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            "See [helper](./pkg/helper.py).\n", encoding="utf-8"
        )

    def tearDown(self):
        self.tmpdir.cleanup()
        self.omni_home.cleanup()

    def test_codebase_graph_returns_file_and_symbol_edges(self):
        body = _call("codebase_graph", {"root": str(self.root)}, self.env)
        self.assertEqual(body["file_count"], 3)
        edge_types = {
            (edge["source"], edge["target"], edge["type"]) for edge in body["edges"]
        }
        self.assertIn(("pkg/main.py", "pkg/helper.py", "imports"), edge_types)
        self.assertIn(("README.md", "pkg/helper.py", "references"), edge_types)
        symbol_nodes = {
            node["symbol"]
            for node in body["nodes"]
            if node["kind"] == "symbol" and node["path"] == "pkg/helper.py"
        }
        self.assertIn("helper", symbol_nodes)

    def test_codebase_impact_reports_dependents(self):
        body = _call(
            "codebase_impact",
            {"root": str(self.root), "path": "pkg/helper.py"},
            self.env,
        )
        self.assertIn("pkg/main.py", body["imported_by"])
        self.assertIn("README.md", body["imported_by"])
        self.assertIn("helper", body["defines"])

    def test_codebase_impact_captures_dynamic_loader_in_repo(self):
        body = _call(
            "codebase_impact",
            {"root": str(ROOT), "path": "scripts/category_resolver.py"},
            self.env,
        )
        self.assertIn("scripts/subagent.py", body["imported_by"])


if __name__ == "__main__":
    unittest.main()
