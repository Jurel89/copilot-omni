"""Phase-C C33: structured cancel reasons + partial-cancel tests."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CS = ROOT / "scripts" / "cancel_signal.py"


def _load():
    spec = importlib.util.spec_from_file_location("cancel_signal", CS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestStructuredCancel(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_signal_returns_none(self):
        mod = _load()
        self.assertIsNone(mod.read_cancel(self.run))
        self.assertFalse(mod.should_cancel(self.run))

    def test_legacy_empty_file_still_cancels(self):
        mod = _load()
        path = self.run / "cancel.signal"
        path.touch()
        record = mod.read_cancel(self.run)
        self.assertIsNotNone(record)
        self.assertIn("legacy", record["reason"])
        self.assertTrue(mod.should_cancel(self.run))

    def test_structured_cancel_writes_and_reads(self):
        mod = _load()
        mod.write_cancel(self.run, reason="user stop")
        record = mod.read_cancel(self.run)
        self.assertEqual(record["reason"], "user stop")
        self.assertGreater(record["ts"], 0)

    def test_full_run_cancel_applies_to_any_scope(self):
        mod = _load()
        mod.write_cancel(self.run, reason="global stop")
        self.assertTrue(mod.should_cancel(self.run))
        self.assertTrue(mod.should_cancel(self.run, scope="branch:a"))

    def test_scoped_cancel_only_applies_to_matching_branch(self):
        mod = _load()
        mod.write_cancel(self.run, reason="branch stop", scope="branch:a")
        self.assertTrue(mod.should_cancel(self.run, scope="branch:a"))
        self.assertFalse(mod.should_cancel(self.run, scope="branch:b"))
        # An unscoped caller is NOT forced to cancel by a scoped signal.
        self.assertFalse(mod.should_cancel(self.run))

    def test_non_json_content_still_treated_as_cancel(self):
        mod = _load()
        path = self.run / "cancel.signal"
        path.write_text("old-style reason text")
        record = mod.read_cancel(self.run)
        self.assertEqual(record["reason"], "old-style reason text")
        self.assertTrue(mod.should_cancel(self.run))


class TestCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv):
        return subprocess.run(
            [sys.executable, str(CS), *argv],
            capture_output=True, text=True, timeout=10,
        )

    def test_write_and_read(self):
        w = self._run("write", str(self.run), "--reason", "abc",
                      "--scope", "branch:x")
        self.assertEqual(w.returncode, 0)
        r = self._run("read", str(self.run))
        self.assertEqual(r.returncode, 0)
        body = json.loads(r.stdout)
        self.assertEqual(body["reason"], "abc")
        self.assertEqual(body["scope"], "branch:x")

    def test_should_cancel_exit_codes(self):
        self._run("write", str(self.run), "--scope", "branch:a")
        r = self._run("should-cancel", str(self.run), "--scope", "branch:a")
        self.assertEqual(r.returncode, 0)
        r = self._run("should-cancel", str(self.run), "--scope", "branch:b")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
