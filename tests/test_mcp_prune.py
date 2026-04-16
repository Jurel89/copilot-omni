"""Phase-C C24: memory_prune + notepad_prune TTL tests."""
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


def _load():
    spec = importlib.util.spec_from_file_location("mcp_server_prune", SERVER)
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
    out, _err = proc.communicate(
        "\n".join(json.dumps(m) for m in msgs) + "\n", timeout=15
    )
    return [json.loads(l) for l in out.strip().splitlines() if l]


class TestMemoryPrune(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed_memory(self, age_days: float, content: str, scope: str = "project"):
        """Directly write a memory row with a backdated updated_at."""
        srv = _load()
        os.environ["OMNI_HOME"] = self.tmpdir.name
        try:
            import time
            past = time.time() - age_days * 86400
            mem_id = srv._new_id()
            with srv._Conn() as conn:
                conn.execute(
                    "INSERT INTO memory(id, scope, key, content, tags, created_at, updated_at)"
                    " VALUES (?, ?, NULL, ?, '', ?, ?)",
                    (mem_id, scope, content, past, past),
                )
        finally:
            pass

    def test_prune_deletes_stale_entries(self):
        self._seed_memory(age_days=60, content="ancient")
        self._seed_memory(age_days=5, content="recent")
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "memory_prune",
                                 "arguments": {"ttl_days": 30}}}], self.env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["ttl_days"], 30)
        self.assertFalse(body["dry_run"])

    def test_dry_run_returns_count_no_deletion(self):
        self._seed_memory(age_days=60, content="one")
        self._seed_memory(age_days=60, content="two")
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "memory_prune",
                                 "arguments": {"ttl_days": 30, "dry_run": True}}}],
                    self.env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 2)
        self.assertTrue(body["dry_run"])
        # Confirm rows still there: second call with dry_run still counts 2.
        resp2 = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "memory_prune",
                                  "arguments": {"ttl_days": 30, "dry_run": True}}}],
                     self.env)
        body2 = json.loads(resp2[0]["result"]["content"][0]["text"])
        self.assertEqual(body2["deleted"], 2)

    def test_scope_filter(self):
        self._seed_memory(age_days=60, content="proj", scope="project")
        self._seed_memory(age_days=60, content="user", scope="user")
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "memory_prune",
                                 "arguments": {"ttl_days": 30, "scope": "project"}}}],
                    self.env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["scope"], "project")

    def test_ttl_days_env_override(self):
        self._seed_memory(age_days=10, content="x")
        env = {**self.env, "OMNI_MEM_TTL_DAYS": "5"}
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "memory_prune",
                                 "arguments": {}}}], env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["ttl_days"], 5.0)

    def test_ttl_days_must_be_positive(self):
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "memory_prune",
                                 "arguments": {"ttl_days": 0}}}], self.env)
        self.assertIn("error", resp[0])


class TestNotepadPrune(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env = {"OMNI_HOME": self.tmpdir.name}

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed_notepad(self, age_days: float, body: str, kind: str = "working"):
        srv = _load()
        os.environ["OMNI_HOME"] = self.tmpdir.name
        import time
        past = time.time() - age_days * 86400
        note_id = srv._new_id()
        with srv._Conn() as conn:
            conn.execute(
                "INSERT INTO notepad(id, kind, body, created_at) VALUES (?, ?, ?, ?)",
                (note_id, kind, body, past),
            )

    def test_prune_deletes_stale(self):
        self._seed_notepad(age_days=60, body="old")
        self._seed_notepad(age_days=1, body="fresh")
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "notepad_prune",
                                 "arguments": {"ttl_days": 30}}}], self.env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 1)

    def test_kind_filter(self):
        self._seed_notepad(age_days=60, body="w", kind="working")
        self._seed_notepad(age_days=60, body="p", kind="priority")
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "notepad_prune",
                                 "arguments": {"ttl_days": 30, "kind": "working"}}}],
                    self.env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["kind"], "working")

    def test_env_override(self):
        self._seed_notepad(age_days=10, body="x")
        env = {**self.env, "OMNI_NOTEPAD_TTL_DAYS": "5"}
        resp = _rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                      "params": {"name": "notepad_prune",
                                 "arguments": {}}}], env)
        body = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["ttl_days"], 5.0)


if __name__ == "__main__":
    unittest.main()
