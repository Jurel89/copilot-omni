"""Phase-C C19: four-gate state machine tests."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SM = ROOT / "scripts" / "state_machine.py"


def _load():
    spec = importlib.util.spec_from_file_location("state_machine", SM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestStateMachine(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name) / "run"

    def tearDown(self):
        self.tmp.cleanup()

    def test_initial_gate_is_discuss(self):
        sm = _load()
        self.assertEqual(sm.read_state(self.run)["gate"], "discuss")

    def test_forward_through_all_gates(self):
        sm = _load()
        for target in ("plan", "execute", "verify", "done"):
            state = sm.advance(self.run, target)
            self.assertEqual(state["gate"], target)

    def test_skip_is_rejected(self):
        sm = _load()
        with self.assertRaises(sm.StateMachineError):
            sm.advance(self.run, "execute")

    def test_same_gate_is_idempotent(self):
        sm = _load()
        sm.advance(self.run, "plan")
        state = sm.advance(self.run, "plan")
        self.assertEqual(state["gate"], "plan")

    def test_rewind_one_step_ok(self):
        sm = _load()
        sm.advance(self.run, "plan")
        state = sm.advance(self.run, "discuss")
        self.assertEqual(state["gate"], "discuss")

    def test_rewind_twice_in_a_row_rejected(self):
        """Two consecutive rewinds surface a StateMachineError — thrashing."""
        sm = _load()
        sm.advance(self.run, "plan")
        sm.advance(self.run, "execute")
        sm.advance(self.run, "plan")  # first rewind, OK
        with self.assertRaises(sm.StateMachineError):
            sm.advance(self.run, "discuss")  # second rewind in a row

    def test_require_gate(self):
        sm = _load()
        sm.advance(self.run, "plan")
        sm.require_gate(self.run, "plan")  # passes
        with self.assertRaises(sm.StateMachineError):
            sm.require_gate(self.run, "execute")

    def test_cli_require_exits_nonzero_on_mismatch(self):
        run = self.run
        run.mkdir(parents=True)
        (run / "state.json").write_text(json.dumps({"gate": "discuss", "history": []}))
        proc = subprocess.run(
            [sys.executable, str(SM), "require", str(run), "execute"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("gate check failed", proc.stderr)

    def test_cli_advance_success(self):
        proc = subprocess.run(
            [sys.executable, str(SM), "advance", str(self.run), "plan"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        body = json.loads(proc.stdout)
        self.assertEqual(body["gate"], "plan")


class TestDocs(unittest.TestCase):

    def test_doc_exists(self):
        doc = ROOT / "docs" / "STATE-MACHINE.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        for token in ("discuss", "plan", "execute", "verify", "done"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
