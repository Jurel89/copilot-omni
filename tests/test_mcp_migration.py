"""Migration framework tests for MCP server (WS8).

Tests:
- v1 -> v2 migration produces correct schema_version and session_id column.
- Newer-DB guard raises on a synthetic v3 database.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = ROOT / "mcp" / "server.py"


def _load_server():
    """Load mcp.server as a module (works whether installed as package or not)."""
    spec = importlib.util.spec_from_file_location("mcp_server", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_v1_db(path: str) -> sqlite3.Connection:
    """Create a fresh v1 database at *path* without running v2 migration."""
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS memory (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, key TEXT,
            content TEXT NOT NULL, tags TEXT,
            created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS state (
            mode TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wiki (
            slug TEXT PRIMARY KEY, title TEXT NOT NULL,
            body TEXT NOT NULL, tags TEXT, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notepad (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL,
            body TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shared_memory (
            key TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trace (
            id TEXT PRIMARY KEY, observation TEXT NOT NULL,
            hypothesis TEXT, evidence TEXT, verdict TEXT, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, started_at REAL NOT NULL, tags TEXT, summary TEXT
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY, run_id TEXT, kind TEXT NOT NULL,
            path TEXT NOT NULL, body TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, phase TEXT NOT NULL, status TEXT NOT NULL,
            meta TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
    """)
    conn.execute("INSERT INTO schema_version(version) VALUES (1)")
    return conn


class TestMigrationV1ToV2(unittest.TestCase):

    def test_v1_to_v2_migration(self):
        """Starting from v1 DB, _migrate() should bump to v2 and add session_id."""
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "omni.db")
            # Create v1 DB manually.
            conn = _make_v1_db(db_path)
            conn.close()

            # Now open via server _migrate().
            srv = _load_server()
            import os
            os.environ["OMNI_HOME"] = td
            try:
                conn2 = sqlite3.connect(db_path, isolation_level=None)
                conn2.row_factory = sqlite3.Row
                conn2.execute("PRAGMA foreign_keys=ON")
                srv._migrate(conn2)

                # Version must be 2.
                row = conn2.execute("SELECT version FROM schema_version").fetchone()
                self.assertEqual(row["version"], 2)

                # session_id column must exist on state table.
                cols = {r["name"] for r in conn2.execute("PRAGMA table_info(state)").fetchall()}
                self.assertIn("session_id", cols)

                conn2.close()
            finally:
                os.environ.pop("OMNI_HOME", None)

    def test_fresh_db_ends_at_v2(self):
        """A brand-new DB migrated from scratch reaches SCHEMA_VERSION=2."""
        with tempfile.TemporaryDirectory() as td:
            import os
            os.environ["OMNI_HOME"] = td
            try:
                srv = _load_server()
                db_path = str(Path(td) / "omni.db")
                conn = sqlite3.connect(db_path, isolation_level=None)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                srv._migrate(conn)

                row = conn.execute("SELECT version FROM schema_version").fetchone()
                self.assertEqual(row["version"], srv.SCHEMA_VERSION)
                self.assertEqual(srv.SCHEMA_VERSION, 2)
                conn.close()
            finally:
                os.environ.pop("OMNI_HOME", None)


class TestNewerDbGuard(unittest.TestCase):

    def test_newer_db_raises(self):
        """If DB schema_version > SCHEMA_VERSION, _migrate must raise RuntimeError."""
        with tempfile.TemporaryDirectory() as td:
            db_path = str(Path(td) / "omni.db")
            # Synthesize a v3 DB.
            conn = sqlite3.connect(db_path, isolation_level=None)
            conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO schema_version(version) VALUES (3)")
            conn.close()

            import os
            os.environ["OMNI_HOME"] = td
            try:
                srv = _load_server()
                conn2 = sqlite3.connect(db_path, isolation_level=None)
                conn2.row_factory = sqlite3.Row
                with self.assertRaises(RuntimeError) as ctx:
                    srv._migrate(conn2)
                self.assertIn("newer plugin version", str(ctx.exception))
                conn2.close()
            finally:
                os.environ.pop("OMNI_HOME", None)


if __name__ == "__main__":
    unittest.main()
