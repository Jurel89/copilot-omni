"""Phase-C C20: artifact-first lifecycle enforcement on `omni execute`/`verify`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMNI = ROOT / "scripts" / "omni.py"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(OMNI), *cmd],
        capture_output=True, text=True, timeout=15, cwd=str(cwd),
        env={**os.environ, "OMNI_HOME": str(cwd / ".omni")},
    )


class TestExecuteGate(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run_id = "test-run"
        self.run_dir = self.root / ".omni" / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_execute_fails_without_spec_json(self):
        result = _run(["execute", self.run_id], self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("spec.json", result.stderr)
        self.assertIn("missing required artifacts", result.stderr)

    def test_execute_succeeds_with_spec_json(self):
        (self.run_dir / "spec.json").write_text(json.dumps({"name": "x"}))
        result = _run(["execute", self.run_id], self.root)
        self.assertEqual(result.returncode, 0,
                         f"stderr={result.stderr!r}")
        self.assertIn("gate=execute", result.stdout)
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(state["gate"], "execute")

    def test_unknown_run_dir_errors(self):
        result = _run(["execute", "nonexistent-run"], self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run-dir not found", result.stderr)


class TestVerifyGate(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run_id = "test-run"
        self.run_dir = self.root / ".omni" / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)
        # Pre-advance through execute so verify can follow.
        (self.run_dir / "spec.json").write_text(json.dumps({"name": "x"}))
        _run(["execute", self.run_id], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_verify_fails_without_plan_md(self):
        result = _run(["verify", self.run_id], self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plan.md", result.stderr)

    def test_verify_succeeds_with_plan_md(self):
        (self.run_dir / "plan.md").write_text("# Plan\nbody")
        result = _run(["verify", self.run_id], self.root)
        self.assertEqual(result.returncode, 0,
                         f"stderr={result.stderr!r}")
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(state["gate"], "verify")


if __name__ == "__main__":
    unittest.main()
