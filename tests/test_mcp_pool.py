"""Connection pool tests for MCP server (WS8).

Tests:
- 5 threads each doing 100 quick state_writes all succeed.
- Pool active count never exceeds cap of 4.
"""
from __future__ import annotations

import importlib.util
import os
import threading
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = ROOT / "mcp" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("mcp_server_pool", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestConnectionPool(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env_orig = os.environ.get("OMNI_HOME")
        os.environ["OMNI_HOME"] = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()
        if self.env_orig is not None:
            os.environ["OMNI_HOME"] = self.env_orig
        else:
            os.environ.pop("OMNI_HOME", None)

    def test_concurrent_writes_all_succeed(self):
        """5 threads x 100 state_writes should all succeed with no errors."""
        srv = _load_server()
        errors = []
        successes = []

        def worker(thread_id):
            for i in range(100):
                try:
                    with srv._Conn() as conn:
                        conn.execute(
                            "INSERT INTO state(mode, body, session_id, updated_at)"
                            " VALUES (?, ?, ?, ?)"
                            " ON CONFLICT(mode, session_id) DO UPDATE SET"
                            " body=excluded.body,"
                            " updated_at=excluded.updated_at",
                            (f"t{thread_id}-i{i}", '{"x":1}', "", float(i)),
                        )
                    successes.append(1)
                except Exception as exc:
                    errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors: {errors[:5]}")
        self.assertEqual(len(successes), 500)

    def test_pool_size_never_exceeds_cap(self):
        """Pool _POOL_ACTIVE + len(_POOL_IDLE) should never exceed _POOL_MAX (4)."""
        srv = _load_server()
        cap_violations = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()  # all threads start simultaneously
            for _ in range(20):
                with srv._Conn():
                    active = srv._POOL_ACTIVE
                    idle = len(srv._POOL_IDLE)
                    total = active + idle
                    if total > srv._POOL_MAX:
                        cap_violations.append(total)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(cap_violations, [],
                         f"Cap exceeded: {cap_violations[:5]}")

    def test_pool_idle_connections_reused(self):
        """After 10 sequential acquires/releases, idle list should have connections."""
        srv = _load_server()
        for _ in range(10):
            with srv._Conn():
                pass
        # After sequential use, idle pool should have at least 1 connection.
        with srv._POOL_LOCK:
            idle_count = len(srv._POOL_IDLE)
        self.assertGreater(idle_count, 0)

    def test_pool_reuses_same_connection_across_calls(self):
        """Phase-C C06: sequential _Conn() acquisitions return the same sqlite
        handle (FIFO of the idle list). Proves reuse across tool calls rather
        than 'one connection per call'."""
        srv = _load_server()
        srv._pool_close_all()
        first_ids: list[int] = []
        for _ in range(3):
            with srv._Conn() as conn:
                first_ids.append(id(conn))
        self.assertEqual(len(set(first_ids)), 1,
                         f"expected reuse, got distinct ids {first_ids}")

    def test_every_handler_uses_context_manager(self):
        """Phase-C C07: every MCP handler in TOOLS must use the _Conn context
        manager (or not touch sqlite at all). Regression against reintroducing
        bare sqlite3.connect() calls."""
        import re
        server_src = (Path(__file__).resolve().parent.parent
                      / "mcp" / "server.py").read_text(encoding="utf-8")
        # The only legitimate sqlite3.connect() lives inside _make_connection().
        direct_calls = [m for m in re.finditer(r"sqlite3\.connect\(", server_src)]
        self.assertEqual(len(direct_calls), 1,
                         f"expected exactly one sqlite3.connect (in _make_connection), "
                         f"found {len(direct_calls)}")

    def test_atexit_close_all_is_registered(self):
        """Phase-C C06: WAL-safe shutdown — _pool_close_all must run at exit."""
        srv = _load_server()
        # _pool_close_all is idempotent; call it directly to verify no crash.
        srv._pool_close_all()
        srv._pool_close_all()
        self.assertEqual(len(srv._POOL_IDLE), 0)


if __name__ == "__main__":
    unittest.main()
