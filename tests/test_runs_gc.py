"""Phase-C C32: .omni/runs/<run-id>/ TTL-based garbage collector."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GC_SCRIPT = ROOT / "scripts" / "runs_gc.py"
OMNI_SCRIPT = ROOT / "scripts" / "omni.py"


def _load_gc():
    spec = importlib.util.spec_from_file_location("runs_gc", GC_SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestRunsGC(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.runs = self.repo / ".omni" / "runs"
        self.runs.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _mk(self, name: str, age_days: float):
        d = self.runs / name
        d.mkdir()
        f = d / "status.json"
        f.write_text("{}")
        past = time.time() - age_days * 86400
        os.utime(f, (past, past))
        os.utime(d, (past, past))
        return d

    def test_stale_dirs_identified(self):
        mod = _load_gc()
        new = self._mk("run-new", age_days=1)
        stale = self._mk("run-stale", age_days=30)
        results = list(mod.collect_stale(self.runs, ttl_days=14))
        paths = [p for p, _ in results]
        self.assertIn(stale, paths)
        self.assertNotIn(new, paths)

    def test_dry_run_does_not_delete(self):
        mod = _load_gc()
        stale = self._mk("run-stale", age_days=30)
        found, deleted = mod.run_gc(self.repo, ttl_days=14, apply_=False)
        self.assertGreaterEqual(found, 1)
        self.assertEqual(deleted, 0)
        self.assertTrue(stale.exists())

    def test_apply_deletes_stale(self):
        mod = _load_gc()
        stale = self._mk("run-stale", age_days=30)
        new = self._mk("run-new", age_days=1)
        found, deleted = mod.run_gc(self.repo, ttl_days=14, apply_=True)
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(stale.exists())
        self.assertTrue(new.exists())

    def test_ttl_env_override(self):
        self._mk("run-mid", age_days=10)
        env = {**os.environ, "OMNI_RUNS_TTL_DAYS": "5"}
        result = subprocess.run(
            [sys.executable, str(GC_SCRIPT), "--repo-root", str(self.repo)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("DRY", result.stdout)

    @unittest.skipIf(sys.platform == "win32",
                     "utime(follow_symlinks=False) unavailable on Windows")
    def test_symlinks_are_skipped(self):
        mod = _load_gc()
        target = Path(self._tmp.name) / "outside"
        target.mkdir()
        link = self.runs / "link-stale"
        try:
            os.symlink(str(target), str(link))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported on this platform")
        past = time.time() - 30 * 86400
        os.utime(link, (past, past), follow_symlinks=False)
        results = list(mod.collect_stale(self.runs, ttl_days=14))
        paths = [p for p, _ in results]
        self.assertNotIn(link, paths, "symlinks must not be GC targets")

    def test_doctor_gc_flag_registered(self):
        """`omni doctor --help` must advertise the --gc flag."""
        result = subprocess.run(
            [sys.executable, str(OMNI_SCRIPT), "doctor", "--help"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--gc", result.stdout)
        self.assertIn("--gc-apply", result.stdout)

    def test_gc_script_cli_dry_run(self):
        """`python scripts/runs_gc.py --repo-root <tmp>` must exit 0 and
        print a DRY-RUN line even when there is a stale run to report.
        This replaces the previous end-to-end doctor test which was
        brittle on Windows when an unrelated doctor subroutine errored
        before the gc block ran."""
        self._mk("run-stale", age_days=30)
        result = subprocess.run(
            [sys.executable, str(GC_SCRIPT), "--repo-root", str(self.repo)],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("DRY-RUN", result.stdout)
        self.assertIn("DRY", result.stdout)


if __name__ == "__main__":
    unittest.main()
