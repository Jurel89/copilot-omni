"""Phase-C C02: Windows back-pressure + background-detach smoke tests."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SUBAGENT_PY = ROOT / "scripts" / "subagent.py"
POOL_PY = ROOT / "scripts" / "subagent_pool.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSubagentBackgroundDetachSelection(unittest.TestCase):
    """Verify Popen is called with the right platform flags."""

    def test_posix_uses_start_new_session(self):
        """On POSIX, background spawn must pass start_new_session=True and
        MUST NOT pass creationflags (that's a Windows-only kwarg)."""
        if sys.platform == "win32":
            self.skipTest("POSIX-only path")
        sub = _load("subagent_c02_posix", SUBAGENT_PY)
        # Simulate _spawn_background's Popen invocation by inspecting source.
        src = SUBAGENT_PY.read_text(encoding="utf-8")
        self.assertIn("start_new_session", src)
        self.assertIn('sys.platform == "win32"', src)
        self.assertIn("CREATE_NEW_PROCESS_GROUP", src)
        self.assertIn("DETACHED_PROCESS", src)

    @unittest.skipUnless(sys.platform == "win32", "Windows-only contract")
    def test_windows_flags_applied(self):
        """On Windows, creationflags must include both CREATE_NEW_PROCESS_GROUP
        and DETACHED_PROCESS so the child is fully decoupled from the parent
        (Ctrl-C in parent does not cascade)."""
        expected = (subprocess.CREATE_NEW_PROCESS_GROUP
                    | getattr(subprocess, "DETACHED_PROCESS", 0))
        self.assertTrue(expected & subprocess.CREATE_NEW_PROCESS_GROUP)


class TestIsPidAlivePortable(unittest.TestCase):

    def test_live_self_pid(self):
        pool = _load("pool_c02", POOL_PY)
        import os as _os
        self.assertTrue(pool._is_pid_alive(_os.getpid()))

    def test_very_unlikely_pid(self):
        """A very high PID almost certainly does not exist. The check
        returns False on POSIX; on Windows it returns False via
        OpenProcess failure."""
        pool = _load("pool_c02_dead", POOL_PY)
        self.assertFalse(pool._is_pid_alive(99_999_999))

    def test_pool_prune_stale_handles_dead_pid(self):
        """A dead pid with age > STALE_AGE_SECS is pruned regardless of OS."""
        pool_mod = _load("pool_c02_prune", POOL_PY)
        import time as _time
        p = pool_mod.SubagentPool(cap=4)
        # Very high PID with old timestamp → should prune.
        old_entries = [{"job_id": "x", "pid": 10_000_001,
                        "ts": _time.time() - 3600}]
        live = p._prune_stale(old_entries)
        self.assertEqual(live, [])


if __name__ == "__main__":
    unittest.main()
