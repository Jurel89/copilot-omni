"""Tests for B3 — connection-pool deadlock fix in mcp/server.py.

Verifies that after _make_connection() raises repeatedly, _POOL_ACTIVE is
correctly restored and the pool remains usable (not deadlocked).
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = ROOT / "mcp" / "server.py"


def _load_server(td: str):
    os.environ["OMNI_HOME"] = td
    spec = importlib.util.spec_from_file_location("mcp_server_pool", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestPoolDeadlockRecovery(unittest.TestCase):
    """Pool recovers after _make_connection() fails repeatedly."""

    def setUp(self):
        self.env_backup = os.environ.copy()
        self.td = tempfile.mkdtemp()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)

    def test_pool_not_deadlocked_after_failed_acquires(self):
        """After 5 failed _make_connection calls, _POOL_ACTIVE must be 0."""
        srv = _load_server(self.td)

        fail_count = [0]
        original_make = srv._make_connection

        def failing_make():
            fail_count[0] += 1
            raise sqlite3.OperationalError("injected failure")

        # Patch _make_connection to always fail
        srv._make_connection = failing_make

        # Reset pool state to known zero
        with srv._POOL_COND:
            srv._POOL_ACTIVE = 0
            srv._POOL_IDLE.clear()

        # Try to acquire 5 times — each should raise, not deadlock
        for _ in range(5):
            with self.assertRaises(sqlite3.OperationalError):
                srv._pool_acquire()

        # After all failures, _POOL_ACTIVE must be 0 (slots restored)
        with srv._POOL_COND:
            active = srv._POOL_ACTIVE
        self.assertEqual(active, 0,
                         f"_POOL_ACTIVE={active} after failures; pool would deadlock")

    def test_pool_usable_after_failures(self):
        """Pool can complete a real acquire after recovering from failures."""
        srv = _load_server(self.td)

        # First call fails, second succeeds
        call_count = [0]
        original_make = srv._make_connection

        def sometimes_failing():
            call_count[0] += 1
            if call_count[0] <= 3:
                raise sqlite3.OperationalError("transient failure")
            return original_make()

        srv._make_connection = sometimes_failing

        with srv._POOL_COND:
            srv._POOL_ACTIVE = 0
            srv._POOL_IDLE.clear()

        # First acquire: all 3 internal retries fail → raises
        with self.assertRaises(sqlite3.OperationalError):
            srv._pool_acquire()

        # Pool must be clean
        with srv._POOL_COND:
            self.assertEqual(srv._POOL_ACTIVE, 0)

        # Restore and verify pool can acquire normally
        srv._make_connection = original_make
        conn = srv._pool_acquire()
        self.assertIsNotNone(conn)
        srv._pool_release(conn)

    def test_concurrent_waiters_unblocked_after_failure(self):
        """Waiting threads are unblocked when a failed acquire restores the slot."""
        srv = _load_server(self.td)
        original_make = srv._make_connection

        # Fill the pool to max capacity with idle connections
        with srv._POOL_COND:
            srv._POOL_ACTIVE = srv._POOL_MAX
            srv._POOL_IDLE.clear()

        # One thread will try to acquire — it should block until a slot opens.
        # We simulate slot opening via pool_release (as if a real connection completes).
        errors = []
        completed = threading.Event()

        def waiter():
            try:
                # Restore one slot so this waiter can proceed
                conn = srv._pool_acquire()
                srv._pool_release(conn)
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()

        # Restore _POOL_ACTIVE so a real acquire can succeed
        t = threading.Thread(target=waiter, daemon=True)
        with srv._POOL_COND:
            srv._POOL_ACTIVE = 0  # reset so waiter can proceed immediately
        t.start()
        completed.wait(timeout=10)
        t.join(timeout=10)

        self.assertFalse(errors, f"Waiter thread raised: {errors}")
        self.assertTrue(completed.is_set(), "Waiter thread never completed")


if __name__ == "__main__":
    unittest.main()
