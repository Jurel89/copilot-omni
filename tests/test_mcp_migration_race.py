"""Phase-C C30: multi-process migration race.

N subprocesses boot the MCP server simultaneously against the same empty
database. All must complete without corruption, and only one schema_version
row must exist at steady state.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("mcp_srv_race", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bootstrap_server(home: str) -> int:
    """Spawn a fresh mcp/server.py process and execute a tool call that touches
    the DB (memory_capture). Returns the subprocess exit code.

    memory_capture triggers _Conn() → _pool_acquire() → _make_connection() →
    _migrate(), which is the sequence that races between processes.
    """
    env = {**os.environ, "OMNI_HOME": home}
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "memory_capture",
                    "arguments": {"scope": "race",
                                  "content": f"race-marker-{os.getpid()}"}}},
    ]
    payload = "\n".join(json.dumps(m) for m in msgs) + "\n"
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload, capture_output=True, text=True, env=env, timeout=30,
    )
    return proc.returncode


class TestMultiProcessMigrationRace(unittest.TestCase):

    def test_n_processes_all_succeed(self):
        """8 subprocesses racing on a fresh DB all exit cleanly."""
        n = 8
        with tempfile.TemporaryDirectory() as td:
            # Sanity: starting with no db
            db = Path(td) / "omni.db"
            self.assertFalse(db.exists())
            with cf.ThreadPoolExecutor(max_workers=n) as ex:
                rcs = list(ex.map(_bootstrap_server, [td] * n))
            self.assertEqual(rcs, [0] * n,
                             f"some bootstraps failed: {rcs}")

    def test_single_schema_version_row_after_race(self):
        """After the race, schema_version has exactly one row at the
        current SCHEMA_VERSION — no duplicates, no stale rows."""
        n = 6
        with tempfile.TemporaryDirectory() as td:
            with cf.ThreadPoolExecutor(max_workers=n) as ex:
                list(ex.map(_bootstrap_server, [td] * n))
            # Inspect the DB directly.
            srv = _load_server()
            db = Path(td) / "omni.db"
            self.assertTrue(db.exists(), "DB was not created")
            with sqlite3.connect(str(db)) as conn:
                rows = conn.execute("SELECT version FROM schema_version").fetchall()
            self.assertEqual(len(rows), 1, f"expected exactly one schema_version row, got {rows}")
            self.assertEqual(rows[0][0], srv.SCHEMA_VERSION)

    def test_tables_intact_after_race(self):
        """Core tables (memory, state, wiki, notepad) all exist after the race."""
        n = 5
        expected_tables = {"memory", "state", "wiki", "notepad",
                           "shared_memory", "trace", "sessions",
                           "artifacts", "runs"}
        with tempfile.TemporaryDirectory() as td:
            with cf.ThreadPoolExecutor(max_workers=n) as ex:
                list(ex.map(_bootstrap_server, [td] * n))
            db = Path(td) / "omni.db"
            with sqlite3.connect(str(db)) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            found = {r[0] for r in rows}
            missing = expected_tables - found
            self.assertEqual(missing, set(),
                             f"tables missing after race: {missing}")


if __name__ == "__main__":
    unittest.main()
