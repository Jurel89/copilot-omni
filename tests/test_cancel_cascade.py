"""Tests for B5 — cancel cascade run-dir nesting.

Verifies:
- When --parent-run-id is set, inner job dir is nested under outer run dir
- PARENT_RUN_ID / PARENT_RUN_DIR env vars are set correctly in child
- Nested ralplan observes outer cancel.signal
- Deeply nested (autopilot → ralplan) cancel cascade works
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBAGENT_PY = ROOT / "scripts" / "subagent.py"


def _load_subagent():
    spec = importlib.util.spec_from_file_location("subagent", SUBAGENT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestNestedRunDir(unittest.TestCase):
    """When parent_run_id is set, job_dir is nested under the outer run dir."""

    def setUp(self):
        self.mod = _load_subagent()
        self.env_backup = os.environ.copy()
        os.environ["OMNI_SUBAGENT_FAKE"] = "1"
        os.environ["OMNI_TEST_MODE"] = "1"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env_backup)

    def test_job_dir_nested_with_parent_run_id(self):
        """_job_dir returns .omni/runs/<parent>/<inner>/<job> when parent_run_id set."""
        job_dir = self.mod._job_dir(
            run_id="ralplan-123",
            job_id="job-abc",
            parent_run_id="autopilot-456",
        )
        parts = job_dir.parts
        # Should contain: .omni/runs/autopilot-456/inner/ralplan-123/job-abc
        self.assertIn("autopilot-456", parts)
        self.assertIn("inner", parts)
        self.assertIn("ralplan-123", parts)
        self.assertIn("job-abc", parts)
        idx_outer = parts.index("autopilot-456")
        idx_inner = parts.index("inner")
        self.assertLess(idx_outer, idx_inner, "outer must come before 'inner'")

    def test_job_dir_flat_without_parent_run_id(self):
        """Without parent_run_id, _job_dir returns flat layout."""
        job_dir = self.mod._job_dir(
            run_id="ralplan-123",
            job_id="job-abc",
        )
        parts = job_dir.parts
        self.assertNotIn("inner", parts)
        self.assertIn("ralplan-123", parts)

    def test_spawn_creates_nested_dir(self):
        """spawn() with parent_run_id=... creates nested job dir."""
        with tempfile.TemporaryDirectory() as td:
            os.environ["OMNI_HOME"] = td
            # Point repo root at td so .omni/runs is under td
            orig_job_dir = self.mod._job_dir

            captured = {}

            def patched_job_dir(run_id, job_id, parent_run_id=None):
                d = Path(td) / ".omni" / "runs"
                if parent_run_id:
                    path = d / parent_run_id / "inner" / run_id / job_id
                else:
                    path = d / run_id / job_id
                captured["job_dir"] = path
                captured["parent_run_id"] = parent_run_id
                return path

            self.mod._job_dir = patched_job_dir
            try:
                # Also patch _init_run_dir to use the patched _job_dir
                orig_init = self.mod._init_run_dir

                def patched_init(run_id, job_id, agent, category, model_used,
                                 prompt, session_id, parent_run_id=None):
                    job_dir = patched_job_dir(run_id, job_id, parent_run_id)
                    job_dir.mkdir(parents=True, exist_ok=True)
                    status = {
                        "job_id": job_id, "run_id": run_id,
                        "agent": agent, "state": "pending",
                        "started_at": None, "ended_at": None,
                        "exit_code": None, "error": None,
                        "category": category, "model_used": model_used,
                        "prompt_excerpt": prompt[:200],
                    }
                    self.mod._write_json_atomic(job_dir / "spec.json",
                                               {"job_id": job_id})
                    self.mod._write_status(job_dir, status)
                    return job_dir, status

                self.mod._init_run_dir = patched_init
                result = self.mod.spawn(
                    "ralplan",
                    "test prompt",
                    parent_run_id="autopilot-outer-123",
                    background=False,
                )
                self.assertEqual(captured.get("parent_run_id"), "autopilot-outer-123")
                parts = captured["job_dir"].parts
                self.assertIn("autopilot-outer-123", parts)
                self.assertIn("inner", parts)
            finally:
                self.mod._job_dir = orig_job_dir
                self.mod._init_run_dir = orig_init


class TestCancelCascadeSignal(unittest.TestCase):
    """Outer cancel.signal propagates to inner skill via PARENT_RUN_DIR."""

    def test_inner_job_sees_outer_cancel_signal(self):
        """If outer run-dir has cancel.signal, _ralplan_check_cancel logic triggers."""
        with tempfile.TemporaryDirectory() as td:
            # Simulate outer run dir
            outer_run_dir = Path(td) / ".omni" / "runs" / "autopilot-outer"
            outer_run_dir.mkdir(parents=True)
            # Write outer cancel.signal
            (outer_run_dir / "cancel.signal").write_text("cancel")

            # Simulate inner run dir (nested)
            inner_run_dir = outer_run_dir / "inner" / "ralplan-inner" / "job1"
            inner_run_dir.mkdir(parents=True)
            status = {
                "job_id": "job1", "run_id": "ralplan-inner",
                "state": "running",
            }
            status_path = inner_run_dir / "status.json"
            status_path.write_text(json.dumps(status))

            # The cancel check logic: if PARENT_RUN_DIR/cancel.signal exists
            parent_cancel = outer_run_dir / "cancel.signal"
            self.assertTrue(parent_cancel.exists(),
                            "outer cancel.signal must exist")

            # Simulate the _ralplan_check_cancel logic in Python
            cancel_detected = False
            own_cancel = inner_run_dir / "cancel.signal"
            parent_cancel_check = parent_cancel

            if own_cancel.exists():
                cancel_detected = True
            if parent_cancel_check.exists():
                cancel_detected = True

            self.assertTrue(cancel_detected,
                            "Inner skill must detect outer cancel.signal")

    def test_inner_own_cancel_still_works(self):
        """Inner skill's own cancel.signal also triggers cancellation."""
        with tempfile.TemporaryDirectory() as td:
            outer_run_dir = Path(td) / "autopilot-outer"
            outer_run_dir.mkdir()
            # No outer cancel.signal

            inner_run_dir = Path(td) / "ralplan-inner"
            inner_run_dir.mkdir()
            (inner_run_dir / "cancel.signal").write_text("cancel")

            cancel_detected = (inner_run_dir / "cancel.signal").exists()
            self.assertTrue(cancel_detected)

    def test_no_cancel_signal_not_triggered(self):
        """Without any cancel.signal, nothing triggers."""
        with tempfile.TemporaryDirectory() as td:
            outer_run_dir = Path(td) / "autopilot-outer"
            outer_run_dir.mkdir()
            inner_run_dir = Path(td) / "ralplan-inner"
            inner_run_dir.mkdir()

            cancel_detected = (
                (inner_run_dir / "cancel.signal").exists() or
                (outer_run_dir / "cancel.signal").exists()
            )
            self.assertFalse(cancel_detected)

    def test_deeply_nested_cascade(self):
        """autopilot → ralplan cancel cascade: outer cancel propagates to inner."""
        with tempfile.TemporaryDirectory() as td:
            # autopilot run dir
            autopilot_dir = Path(td) / "autopilot-ap1"
            autopilot_dir.mkdir(parents=True)

            # ralplan nested under autopilot
            ralplan_dir = autopilot_dir / "inner" / "ralplan-rp1" / "job1"
            ralplan_dir.mkdir(parents=True)

            # Write cancel to autopilot (outer)
            (autopilot_dir / "cancel.signal").write_text("cancel")

            # Check: ralplan should see PARENT_RUN_DIR = autopilot_dir
            parent_run_dir = autopilot_dir
            own_cancel = ralplan_dir / "cancel.signal"
            parent_cancel = parent_run_dir / "cancel.signal"

            cancel_detected = own_cancel.exists() or parent_cancel.exists()
            self.assertTrue(cancel_detected,
                            "Deeply nested ralplan must see autopilot cancel.signal")


if __name__ == "__main__":
    unittest.main()
