"""Phase-C C17: wiki_ingest (SHA dedupe) + wiki_graph (knowledge graph)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("mcp_srv_wiki", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def _call(name, args, env):
    resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": name, "arguments": args}}], env)
    return json.loads(resp[0]["result"]["content"][0]["text"])


class TestWikiIngestDedupe(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_first_ingest_writes(self):
        body = _call("wiki_ingest", {
            "slug": "alpha", "body": "hello world"
        }, self.env)
        self.assertTrue(body["ok"])
        self.assertFalse(body["deduped"])
        self.assertEqual(len(body["sha256"]), 64)

    def test_same_body_deduped(self):
        _call("wiki_ingest", {"slug": "alpha", "body": "hello world"}, self.env)
        body = _call("wiki_ingest", {"slug": "alpha", "body": "hello world"}, self.env)
        self.assertTrue(body["deduped"])

    def test_different_body_updates(self):
        _call("wiki_ingest", {"slug": "alpha", "body": "v1"}, self.env)
        body = _call("wiki_ingest", {"slug": "alpha", "body": "v2"}, self.env)
        self.assertFalse(body["deduped"])

    def test_auto_slug_from_title(self):
        body = _call("wiki_ingest", {"title": "Hello, World!", "body": "x"}, self.env)
        self.assertEqual(body["slug"], "hello-world")

    def test_empty_body_rejected(self):
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "wiki_ingest",
                                 "arguments": {"slug": "x", "body": ""}}}],
                    self.env)
        self.assertIn("error", resp[0])


class TestWikiGraph(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_empty_graph(self):
        body = _call("wiki_graph", {}, self.env)
        self.assertEqual(body["nodes"], [])
        self.assertEqual(body["edges"], [])

    def test_wiki_link_syntax(self):
        _call("wiki_ingest", {"slug": "home", "body": "see [[about]]"}, self.env)
        _call("wiki_ingest", {"slug": "about", "body": "back to [[home]]"}, self.env)
        body = _call("wiki_graph", {}, self.env)
        slugs = {n["slug"] for n in body["nodes"]}
        self.assertEqual(slugs, {"home", "about"})
        edge_pairs = {(e["source"], e["target"]) for e in body["edges"]}
        self.assertIn(("home", "about"), edge_pairs)
        self.assertIn(("about", "home"), edge_pairs)

    def test_md_link_recognised(self):
        _call("wiki_ingest", {"slug": "readme", "body": "[docs](./notes.md)"}, self.env)
        _call("wiki_ingest", {"slug": "notes", "body": "body"}, self.env)
        body = _call("wiki_graph", {}, self.env)
        edges = [(e["source"], e["target"]) for e in body["edges"]]
        self.assertIn(("readme", "notes"), edges)

    def test_dangling_targets_separated(self):
        _call("wiki_ingest", {"slug": "root", "body": "see [[missing]]"}, self.env)
        body = _call("wiki_graph", {}, self.env)
        self.assertEqual(body["edges"], [])
        dangling = [(e["source"], e["target"]) for e in body["dangling"]]
        self.assertIn(("root", "missing"), dangling)

    def test_external_urls_ignored(self):
        _call("wiki_ingest", {"slug": "root",
                              "body": "link [x](https://example.com)"}, self.env)
        body = _call("wiki_graph", {}, self.env)
        self.assertEqual(body["edges"], [])
        self.assertEqual(body["dangling"], [])


if __name__ == "__main__":
    unittest.main()
