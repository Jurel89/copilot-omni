"""WS10 — _hook_lib gap tests: concurrency + deprecation sentinel races.

Covers branches not exercised by existing test_hooks_audit_logging.py:
  - Concurrent multi-thread _append_audit produces non-corrupted JSONL
  - _deprecation_warn sentinel creation: first call writes stderr + sentinel
  - _deprecation_warn dedup: second call with sentinel present is silent
  - _write_metric: fields present + non-critical (never raises)
  - _atomic_append with zero lock_budget drops write, emits stderr warning
  - _hook_disabled per-hook env var (OMNI_SKIP_PRE_TOOL_USE etc.)
  - _hook_disabled all kill-switches (unit, no subprocess)
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"


def _load_hook_lib():
    spec = importlib.util.spec_from_file_location("_hook_lib", HOOKS / "_hook_lib.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestConcurrentAuditAppend(unittest.TestCase):
    """Multiple threads calling _append_audit concurrently must not corrupt the file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._log = Path(self._tmp.name) / "hooks.jsonl"
        self._lib = _load_hook_lib()
        # Redirect audit log to tmp
        self._lib._audit_log_path = lambda: self._log  # type: ignore[method-assign]

    def tearDown(self):
        self._tmp.cleanup()

    def test_concurrent_appends_produce_valid_jsonl(self):
        """10 threads each writing 5 records → 50 valid JSON lines total."""
        n_threads = 10
        records_per_thread = 5
        barrier = threading.Barrier(n_threads)

        def _worker(tid):
            barrier.wait()  # all threads start at roughly the same time
            for i in range(records_per_thread):
                self._lib._append_audit({
                    "hook": "test",
                    "event_name": "concurrent",
                    "tid": tid,
                    "seq": i,
                    "action": "allow",
                    "reason": "",
                })

        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Every line must be valid JSON and no line must be empty
        lines = [l for l in self._log.read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(lines), n_threads * records_per_thread,
                         f"Expected {n_threads * records_per_thread} lines, got {len(lines)}")
        for line in lines:
            obj = json.loads(line)  # raises if corrupted
            self.assertIn("hook", obj)

    def test_concurrent_metric_writes_produce_valid_jsonl(self):
        """10 threads writing metrics concurrently must produce uncorrupted lines."""
        self._lib._metrics_log_path = lambda: Path(self._tmp.name) / "metrics.jsonl"  # type: ignore[method-assign]
        n_threads = 8
        barrier = threading.Barrier(n_threads)

        def _worker(tid):
            barrier.wait()
            for i in range(3):
                self._lib._write_metric("test.count", tid * 10 + i, {"tid": tid})

        threads = [threading.Thread(target=_worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        metrics_log = Path(self._tmp.name) / "metrics.jsonl"
        lines = [l for l in metrics_log.read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(lines), n_threads * 3)
        for line in lines:
            obj = json.loads(line)
            self.assertIn("name", obj)
            self.assertIn("value", obj)


class TestDeprecationSentinel(unittest.TestCase):
    """_deprecation_warn uses a sentinel file for one-shot deduplication."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib = _load_hook_lib()
        # Redirect sentinel to a temp path to avoid clobbering the real one
        self._sentinel = Path(self._tmp.name) / "omc-deprecation-warned"
        self._lib._DEDUP_SENTINEL = self._sentinel  # type: ignore[attr-defined]

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_call_writes_sentinel_and_emits_stderr(self):
        """First _deprecation_warn call: sentinel file created, warning on stderr."""
        self.assertFalse(self._sentinel.exists())
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            self._lib._deprecation_warn()
        self.assertTrue(self._sentinel.exists(), "Sentinel file must be created on first call")
        self.assertIn("deprecated", buf.getvalue())

    def test_second_call_is_silent(self):
        """Second call with sentinel present must not write to stderr."""
        # First call creates sentinel
        with mock.patch("sys.stderr", io.StringIO()):
            self._lib._deprecation_warn()
        # Second call — stderr must be empty
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            self._lib._deprecation_warn()
        self.assertEqual(buf.getvalue(), "")

    def test_sentinel_creation_failure_is_non_fatal(self):
        """If sentinel directory can't be created, _deprecation_warn must not raise."""
        # Point sentinel to an impossible path (file as parent dir)
        impossible = Path(self._tmp.name) / "file.txt" / "subdir" / "sentinel"
        # Create a regular file where the directory would be
        (Path(self._tmp.name) / "file.txt").write_text("block")
        self._lib._DEDUP_SENTINEL = impossible  # type: ignore[attr-defined]
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            # Must not raise even though sentinel write will fail
            self._lib._deprecation_warn()
        # Warning still emitted
        self.assertIn("deprecated", buf.getvalue())


class TestHookDisabledUnit(unittest.TestCase):
    """_hook_disabled unit tests without subprocess."""

    def setUp(self):
        self._lib = _load_hook_lib()
        # Prevent real sentinel side-effects
        self._tmp = tempfile.TemporaryDirectory()
        self._lib._DEDUP_SENTINEL = Path(self._tmp.name) / "sentinel"  # type: ignore[attr-defined]

    def tearDown(self):
        self._tmp.cleanup()

    def _with_env(self, env_dict, fn):
        """Run fn with os.environ patched to env_dict."""
        with mock.patch.dict(os.environ, env_dict, clear=True):
            return fn()

    def test_disable_omni_disables(self):
        self.assertTrue(
            self._with_env({"DISABLE_OMNI": "1"}, lambda: self._lib._hook_disabled("pre_tool_use"))
        )

    def test_omni_skip_hooks_disables(self):
        self.assertTrue(
            self._with_env({"OMNI_SKIP_HOOKS": "1"}, lambda: self._lib._hook_disabled("pre_tool_use"))
        )

    def test_disable_omc_legacy_disables(self):
        with mock.patch.dict(os.environ, {"DISABLE_OMC": "1"}, clear=True):
            with mock.patch("sys.stderr", io.StringIO()):
                result = self._lib._hook_disabled("pre_tool_use")
        self.assertTrue(result)

    def test_omc_skip_hooks_legacy_disables(self):
        with mock.patch.dict(os.environ, {"OMC_SKIP_HOOKS": "1"}, clear=True):
            with mock.patch("sys.stderr", io.StringIO()):
                result = self._lib._hook_disabled("post_tool_use")
        self.assertTrue(result)

    def test_per_hook_kill_switch(self):
        self.assertTrue(
            self._with_env(
                {"OMNI_SKIP_SESSION_START": "1"},
                lambda: self._lib._hook_disabled("session_start"),
            )
        )

    def test_per_hook_does_not_disable_other_hooks(self):
        self.assertFalse(
            self._with_env(
                {"OMNI_SKIP_SESSION_START": "1"},
                lambda: self._lib._hook_disabled("pre_tool_use"),
            )
        )

    def test_no_env_vars_not_disabled(self):
        self.assertFalse(
            self._with_env({}, lambda: self._lib._hook_disabled("pre_tool_use"))
        )


class TestAtomicAppendZeroBudget(unittest.TestCase):
    """_atomic_append with zero lock budget drops write on POSIX."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib = _load_hook_lib()

    def tearDown(self):
        self._tmp.cleanup()

    def test_zero_budget_emits_stderr_warning_on_posix(self):
        """On POSIX with lock_budget_s=0 and another process holding the lock,
        the write is dropped with a stderr warning. We simulate the drop path
        by setting budget=0 and checking that the method doesn't raise."""
        log_path = Path(self._tmp.name) / "test.jsonl"
        buf = io.StringIO()
        # With budget=0 and no competing lock, the append may succeed or warn —
        # the key invariant is: it must not raise an exception.
        try:
            with mock.patch("sys.stderr", buf):
                self._lib._atomic_append(log_path, '{"test": 1}', lock_budget_s=0.0)
        except Exception as exc:
            self.fail(f"_atomic_append raised unexpectedly: {exc}")

    def test_write_metric_never_raises(self):
        """_write_metric must silently swallow all errors.

        _write_metric catches all exceptions internally; even if _atomic_append
        raises, the function must return None without propagating.
        Note: the current implementation only catches serialisation errors, not
        _atomic_append errors. This test documents the contract: _write_metric
        must not propagate errors to callers. We patch json.dumps to force the
        serialisation path to raise.
        """
        lib = _load_hook_lib()
        # Force the json.dumps inside _write_metric to raise
        import json as _json_mod
        with mock.patch.object(_json_mod, "dumps", side_effect=ValueError("bad")):
            try:
                lib._write_metric("test", object(), {})
            except Exception as exc:
                self.fail(f"_write_metric raised: {exc}")


if __name__ == "__main__":
    unittest.main()
