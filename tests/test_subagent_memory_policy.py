"""Phase-C C08 + C26: memory-policy tests for subagent_pool.

C08 — per-subagent cap (OMNI_SUBAGENT_MEM_CAP_MB, default 512)
C26 — cumulative pool cap (OMNI_POOL_MEM_CAP_MB, default 4096)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
POOL_PY = ROOT / "scripts" / "subagent_pool.py"


def _load():
    spec = importlib.util.spec_from_file_location("pool_mem", POOL_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMemoryPolicyBasics(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_caps(self):
        mod = _load()
        self.assertEqual(mod.DEFAULT_SUBAGENT_MEM_CAP_MB, 512)
        self.assertEqual(mod.DEFAULT_POOL_MEM_CAP_MB, 4096)

    def test_env_int_accepts_positive(self):
        mod = _load()
        os.environ["OMNI_MEMORY_TEST"] = "128"
        try:
            self.assertEqual(mod._env_int("OMNI_MEMORY_TEST", 64), 128)
        finally:
            os.environ.pop("OMNI_MEMORY_TEST", None)

    def test_env_int_rejects_zero(self):
        mod = _load()
        os.environ["OMNI_MEMORY_TEST"] = "0"
        try:
            self.assertEqual(mod._env_int("OMNI_MEMORY_TEST", 64), 64)
        finally:
            os.environ.pop("OMNI_MEMORY_TEST", None)

    def test_env_int_rejects_non_numeric(self):
        mod = _load()
        os.environ["OMNI_MEMORY_TEST"] = "huge"
        try:
            self.assertEqual(mod._env_int("OMNI_MEMORY_TEST", 64), 64)
        finally:
            os.environ.pop("OMNI_MEMORY_TEST", None)


@unittest.skipUnless(sys.platform.startswith("linux"), "rss read only on linux here")
class TestRssReading(unittest.TestCase):

    def test_self_pid_has_positive_rss(self):
        mod = _load()
        rss = mod._rss_mb(os.getpid())
        self.assertIsNotNone(rss)
        self.assertGreater(rss, 0)

    def test_nonexistent_pid_returns_none(self):
        mod = _load()
        self.assertIsNone(mod._rss_mb(99_999_999))


class TestPoolMemoryRejection(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _pool(self, mod):
        return mod.SubagentPool(cap=4, lock_dir=self.lock_dir, timeout=2.0)

    def test_acquire_under_cap_succeeds(self):
        mod = _load()
        os.environ["OMNI_POOL_MEM_CAP_MB"] = "4096"
        os.environ["OMNI_SUBAGENT_MEM_CAP_MB"] = "256"
        try:
            pool = self._pool(mod)
            pool.acquire("j1")  # first slot, rollup is self-rss only
            pool.release("j1")
        finally:
            os.environ.pop("OMNI_POOL_MEM_CAP_MB", None)
            os.environ.pop("OMNI_SUBAGENT_MEM_CAP_MB", None)

    def test_acquire_over_cap_raises(self):
        mod = _load()
        # Force the rollup to always report a huge number so the cap
        # comparison fails without having to allocate real memory.
        os.environ["OMNI_POOL_MEM_CAP_MB"] = "1024"
        os.environ["OMNI_SUBAGENT_MEM_CAP_MB"] = "256"
        try:
            pool = self._pool(mod)
            with mock.patch.object(pool, "_rollup_rss_mb", return_value=900.0):
                with self.assertRaises(mod.MemoryPolicyDenied):
                    pool.acquire("j1")
        finally:
            os.environ.pop("OMNI_POOL_MEM_CAP_MB", None)
            os.environ.pop("OMNI_SUBAGENT_MEM_CAP_MB", None)

    def test_rejection_releases_lock(self):
        """After MemoryPolicyDenied, the lock file must be releasable."""
        mod = _load()
        os.environ["OMNI_POOL_MEM_CAP_MB"] = "100"
        os.environ["OMNI_SUBAGENT_MEM_CAP_MB"] = "256"
        try:
            pool = self._pool(mod)
            with mock.patch.object(pool, "_rollup_rss_mb", return_value=50.0):
                with self.assertRaises(mod.MemoryPolicyDenied):
                    pool.acquire("j1")
            # Second attempt (still over cap) must also raise cleanly —
            # not deadlock on the lock file.
            with mock.patch.object(pool, "_rollup_rss_mb", return_value=50.0):
                with self.assertRaises(mod.MemoryPolicyDenied):
                    pool.acquire("j2")
        finally:
            os.environ.pop("OMNI_POOL_MEM_CAP_MB", None)
            os.environ.pop("OMNI_SUBAGENT_MEM_CAP_MB", None)


if __name__ == "__main__":
    unittest.main()
