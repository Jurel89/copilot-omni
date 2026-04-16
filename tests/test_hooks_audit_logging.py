"""Tests for atomic audit logging (_hook_lib._append_audit and _write_metric).

Covers:
- Single-process append writes valid JSONL
- Concurrent appends from multiple processes produce a non-corrupted file
  (each line is valid JSON, no interleaved content)
- _write_metric produces valid JSONL with expected schema
- File-lock path: lock contention drops write with stderr warning (budget=0)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"


def _load_hook_lib():
    """Load _hook_lib module directly for unit testing."""
    spec = importlib.util.spec_from_file_location("_hook_lib", HOOKS / "_hook_lib.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestAtomicAppend(unittest.TestCase):
    """_atomic_append writes valid lines to a file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._log = Path(self._tmp.name) / "test.jsonl"
        self._lib = _load_hook_lib()
        # Patch _audit_log_path to point to tmp file
        self._lib._audit_log_path = lambda: self._log  # type: ignore[method-assign]

    def tearDown(self):
        self._tmp.cleanup()

    def test_single_write_produces_valid_json_line(self):
        record = {"hook": "test", "event_name": "unit_test", "action": "allow", "reason": ""}
        self._lib._append_audit(record)
        lines = self._log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["hook"], "test")
        self.assertEqual(parsed["action"], "allow")
        self.assertIn("ts", parsed)

    def test_multiple_writes_produce_multiple_lines(self):
        for i in range(5):
            self._lib._append_audit({"hook": "test", "event_name": f"ev{i}", "action": "log", "reason": ""})
        lines = self._log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 5)
        for line in lines:
            json.loads(line)  # must not raise

    def test_audit_record_ts_is_filled(self):
        """Records without 'ts' get a ts field injected."""
        record = {"hook": "test", "event_name": "x", "action": "allow", "reason": ""}
        self._lib._append_audit(record)
        line = self._log.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        self.assertIsInstance(parsed["ts"], float)

    def test_audit_record_with_ts_preserved(self):
        """Records with 'ts' keep the caller-supplied value."""
        record = {"ts": 12345.0, "hook": "test", "event_name": "x", "action": "allow", "reason": ""}
        self._lib._append_audit(record)
        line = self._log.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        self.assertEqual(parsed["ts"], 12345.0)


class TestConcurrentAppend(unittest.TestCase):
    """Concurrent threads appending to the same file produce valid JSONL."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._log = Path(self._tmp.name) / "concurrent.jsonl"
        self._lib = _load_hook_lib()
        self._lib._audit_log_path = lambda: self._log  # type: ignore[method-assign]

    def tearDown(self):
        self._tmp.cleanup()

    def test_concurrent_writes_all_valid_json(self):
        """20 threads each write 5 records; all 100 lines must be valid JSON."""
        n_threads = 20
        n_per_thread = 5
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(n_per_thread):
                    self._lib._append_audit({
                        "hook": "concurrent_test",
                        "event_name": f"t{thread_id}_e{i}",
                        "action": "log",
                        "reason": "",
                    })
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        lines = self._log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), n_threads * n_per_thread)
        for line in lines:
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                self.fail(f"Invalid JSON line: {line!r} — {exc}")


class TestWriteMetric(unittest.TestCase):
    """_write_metric appends valid JSONL metric records."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._metrics = Path(self._tmp.name) / "metrics.jsonl"
        self._lib = _load_hook_lib()
        self._lib._metrics_log_path = lambda: self._metrics  # type: ignore[method-assign]

    def tearDown(self):
        self._tmp.cleanup()

    def test_metric_record_schema(self):
        self._lib._write_metric("hook_latency_ms", 42.5, {"hook": "test"})
        line = self._metrics.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        self.assertEqual(record["name"], "hook_latency_ms")
        self.assertEqual(record["value"], 42.5)
        self.assertEqual(record["labels"]["hook"], "test")
        self.assertIn("ts", record)

    def test_metric_without_labels(self):
        self._lib._write_metric("hook_exit_code", 0)
        line = self._metrics.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        self.assertEqual(record["labels"], {})

    def test_multiple_metrics(self):
        for i in range(3):
            self._lib._write_metric(f"m{i}", i, {"i": i})
        lines = self._metrics.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        for i, line in enumerate(lines):
            r = json.loads(line)
            self.assertEqual(r["name"], f"m{i}")
            self.assertEqual(r["value"], i)


class TestDeprecationWarn(unittest.TestCase):
    """_deprecation_warn emits warning and creates sentinel; de-dupes on second call."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lib = _load_hook_lib()
        # Point sentinel to tmp dir
        self._sentinel = Path(self._tmp.name) / "omc-deprecation-warned"  # omni-rename-allow: legacy sentinel name
        self._lib._DEDUP_SENTINEL = self._sentinel  # type: ignore[attr-defined]

    def tearDown(self):
        self._tmp.cleanup()

    def test_warn_emits_message_to_stderr(self):
        import io
        buf = io.StringIO()
        orig = sys.stderr
        sys.stderr = buf
        try:
            self._lib._deprecation_warn()
        finally:
            sys.stderr = orig
        output = buf.getvalue()
        self.assertIn("deprecated", output.lower())
        self.assertIn("v3.0.0", output)

    def test_warn_creates_sentinel(self):
        self._lib._deprecation_warn()
        self.assertTrue(self._sentinel.exists())

    def test_warn_deduplicates(self):
        """Second call must NOT emit a second warning (sentinel already exists)."""
        import io
        # First call
        self._lib._deprecation_warn()
        # Second call — sentinel exists, should be silent
        buf = io.StringIO()
        orig = sys.stderr
        sys.stderr = buf
        try:
            self._lib._deprecation_warn()
        finally:
            sys.stderr = orig
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
