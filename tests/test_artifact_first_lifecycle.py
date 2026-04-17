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


class TestNoSkipThroughGates(unittest.TestCase):
    """Phase-C C34 Codex finding: `omni verify` with only plan.md present
    used to walk through plan → execute → verify silently, which was a
    bypass of the four-gate contract. Now each intermediate gate
    re-checks its artifact requirement."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.run_id = "bypass-run"
        self.run_dir = self.root / ".omni" / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_verify_without_spec_json_is_rejected(self):
        """Only plan.md present — the intermediate 'plan' gate requires
        spec.json. Walker must refuse to advance."""
        (self.run_dir / "plan.md").write_text("# Plan")
        result = _run(["verify", self.run_id], self.root)
        self.assertNotEqual(result.returncode, 0,
                            f"bypass NOT rejected; stdout={result.stdout!r}")
        self.assertIn("spec.json", result.stderr + result.stdout)

    def test_corrupt_gate_value_raises_controlled_error(self):
        """Codex P2: state.json with an unknown gate value must surface a
        StateMachineError, not a ValueError traceback from order.index."""
        (self.run_dir / "spec.json").write_text("{}")
        (self.run_dir / "plan.md").write_text("# Plan")
        (self.run_dir / "state.json").write_text(json.dumps({
            "gate": "totally-invalid-gate",
            "history": [],
        }))
        result = _run(["verify", self.run_id], self.root)
        self.assertNotEqual(result.returncode, 0)
        # The error must cite 'unknown gate', not bubble up a bare ValueError.
        combined = result.stderr + result.stdout
        self.assertIn("unknown gate", combined.lower(),
                      f"expected controlled error; got {combined!r}")
        self.assertNotIn("Traceback", combined)


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
