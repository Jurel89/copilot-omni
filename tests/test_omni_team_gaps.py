"""WS10 — omni_team.py gap tests: cleanup edge cases + Windows guard branches.

Covers branches not exercised by existing test_omni_team.py:
  - cleanup_team with nonexistent run_id returns graceful dict
  - cleanup_team with no workers in manifest produces clean result
  - cleanup_team fallback path (worktree mod unavailable) removes dir manually
  - cleanup_team force=True suppresses errors
  - cleanup_team updates status.json to 'cleaned'
  - _TmuxSession.create Windows guard: raises without OMNI_EXPERIMENTAL_TEAM
  - _TmuxSession.create Windows guard: does not raise with flag set (mocked tmux)
  - _is_windows returns bool
  - _write_json_atomic uses tmp + replace (atomic write)
  - _read_json_safe returns None on missing / corrupted file
  - status_team for missing run returns error dict
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load_omni_team():
    spec = importlib.util.spec_from_file_location("omni_team", SCRIPTS / "omni_team.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestCleanupTeamEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._mod = _load_omni_team()
        self._mod._OMNI_RUNS = Path(self._tmp.name) / "runs"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_run(self, run_id: str, workers=None) -> Path:
        """Create a minimal run directory with manifest + status."""
        run_dir = self._mod._OMNI_RUNS / run_id
        run_dir.mkdir(parents=True)
        manifest = {
            "run_id": run_id,
            "name": "test-team",
            "workers": workers or [],
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (run_dir / "status.json").write_text(
            json.dumps({"run_id": run_id, "state": "done"}), encoding="utf-8"
        )
        return run_dir

    # ------------------------------------------------------------------
    # cleanup_team: nonexistent run
    # ------------------------------------------------------------------

    def test_cleanup_nonexistent_run_returns_graceful_dict(self):
        result = self._mod.cleanup_team("team-does-not-exist-xyz")
        self.assertEqual(result["run_id"], "team-does-not-exist-xyz")
        self.assertIn("nothing to clean", result.get("message", ""))
        self.assertEqual(result["removed_worktrees"], [])
        self.assertEqual(result["errors"], [])

    # ------------------------------------------------------------------
    # cleanup_team: run with no workers
    # ------------------------------------------------------------------

    def test_cleanup_no_workers_succeeds(self):
        run_id = "team-no-workers-ws10"
        self._make_run(run_id, workers=[])
        result = self._mod.cleanup_team(run_id)
        self.assertEqual(result["run_id"], run_id)
        self.assertEqual(result["removed_worktrees"], [])
        self.assertEqual(result["errors"], [])
        # Status must be updated to 'cleaned'
        run_dir = self._mod._OMNI_RUNS / run_id
        status = json.loads((run_dir / "status.json").read_text())
        self.assertEqual(status["state"], "cleaned")

    # ------------------------------------------------------------------
    # cleanup_team: fallback path when worktree mod unavailable
    # ------------------------------------------------------------------

    def test_cleanup_fallback_removes_worktree_dir(self):
        """When worktree mod returns None, cleanup must manually shutil.rmtree the dir."""
        run_id = "team-fallback-ws10"
        workers = [{"slug": "worker-1"}]
        run_dir = self._make_run(run_id, workers=workers)

        # Create a fake worktree directory for worker-1
        wt_path = run_dir / "workers" / "worker-1" / "worktree"
        wt_path.mkdir(parents=True)
        (wt_path / "somefile.txt").write_text("data")

        # Make _load_worktree_mod return None to force the fallback path
        with mock.patch.object(self._mod, "_load_worktree_mod", return_value=None):
            result = self._mod.cleanup_team(run_id)

        self.assertFalse(wt_path.exists(), "Fallback must remove the worktree directory")
        self.assertEqual(len(result["removed_worktrees"]), 1)
        self.assertEqual(result["errors"], [])

    # ------------------------------------------------------------------
    # cleanup_team: force=True suppresses per-worker errors
    # ------------------------------------------------------------------

    def test_cleanup_force_suppresses_errors(self):
        """cleanup_team(force=True) must record errors but not raise."""
        run_id = "team-force-ws10"
        workers = [{"slug": "worker-err"}]
        self._make_run(run_id, workers=workers)

        def _bad_worktree_mod():
            m = mock.MagicMock()
            m.remove.side_effect = RuntimeError("simulated worktree error")
            return m

        with mock.patch.object(self._mod, "_load_worktree_mod", side_effect=_bad_worktree_mod):
            result = self._mod.cleanup_team(run_id, force=True)

        # Errors recorded but method did not raise
        self.assertTrue(len(result["errors"]) > 0)
        self.assertIn("ignored, force=True", result["errors"][0])

    # ------------------------------------------------------------------
    # cleanup_team: status updated to 'cleaned'
    # ------------------------------------------------------------------

    def test_cleanup_updates_status_to_cleaned(self):
        run_id = "team-status-ws10"
        self._make_run(run_id, workers=[])
        self._mod.cleanup_team(run_id)
        run_dir = self._mod._OMNI_RUNS / run_id
        status = json.loads((run_dir / "status.json").read_text())
        self.assertEqual(status["state"], "cleaned")
        self.assertIn("cleaned_at", status)


class TestWindowsGuardBranches(unittest.TestCase):
    """_TmuxSession.create Windows guard logic."""

    def setUp(self):
        self._mod = _load_omni_team()

    def test_is_windows_returns_bool(self):
        result = self._mod._is_windows()
        self.assertIsInstance(result, bool)
        self.assertEqual(result, platform.system() == "Windows")

    def test_tmux_create_windows_without_flag_raises(self):
        """On Windows without OMNI_EXPERIMENTAL_TEAM=1, create must raise RuntimeError."""
        with mock.patch.object(self._mod, "_is_windows", return_value=True):
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(RuntimeError) as ctx:
                    self._mod._TmuxSession.create("test-session")
        self.assertIn("OMNI_EXPERIMENTAL_TEAM", str(ctx.exception))

    def test_tmux_create_windows_with_flag_proceeds_to_which(self):
        """On Windows with flag, code must NOT raise the guard error (may fail at which())."""
        with mock.patch.object(self._mod, "_is_windows", return_value=True):
            with mock.patch.dict(os.environ, {"OMNI_EXPERIMENTAL_TEAM": "1"}):
                # tmux won't be found in CI, expect RuntimeError about tmux not found
                # NOT the Windows guard error
                with self.assertRaises(RuntimeError) as ctx:
                    with mock.patch.object(self._mod.shutil, "which", return_value=None):
                        self._mod._TmuxSession.create("test-session")
        self.assertNotIn("OMNI_EXPERIMENTAL_TEAM", str(ctx.exception))
        self.assertIn("tmux not found", str(ctx.exception))

    def test_tmux_create_no_tmux_on_path_raises(self):
        """Without tmux on PATH (non-Windows), create raises about tmux not found."""
        with mock.patch.object(self._mod, "_is_windows", return_value=False):
            with mock.patch.object(self._mod.shutil, "which", return_value=None):
                with self.assertRaises(RuntimeError) as ctx:
                    self._mod._TmuxSession.create("test-session")
        self.assertIn("tmux not found", str(ctx.exception))


class TestHelperFunctions(unittest.TestCase):
    """_write_json_atomic, _read_json_safe, status_team missing run."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._mod = _load_omni_team()
        self._mod._OMNI_RUNS = Path(self._tmp.name) / "runs"

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_json_atomic_creates_file(self):
        target = Path(self._tmp.name) / "subdir" / "out.json"
        self._mod._write_json_atomic(target, {"key": "value"})
        self.assertTrue(target.exists())
        data = json.loads(target.read_text())
        self.assertEqual(data["key"], "value")

    def test_write_json_atomic_no_tmp_leftover(self):
        target = Path(self._tmp.name) / "out.json"
        self._mod._write_json_atomic(target, {"x": 1})
        tmp = target.with_suffix(".tmp")
        self.assertFalse(tmp.exists(), ".tmp file must not remain after atomic write")

    def test_read_json_safe_returns_none_on_missing(self):
        result = self._mod._read_json_safe(Path(self._tmp.name) / "no_such_file.json")
        self.assertIsNone(result)

    def test_read_json_safe_returns_none_on_corrupt(self):
        bad = Path(self._tmp.name) / "corrupt.json"
        bad.write_text("{ not valid json }", encoding="utf-8")
        result = self._mod._read_json_safe(bad)
        self.assertIsNone(result)

    def test_read_json_safe_returns_dict_on_valid(self):
        good = Path(self._tmp.name) / "good.json"
        good.write_text('{"a": 1}', encoding="utf-8")
        result = self._mod._read_json_safe(good)
        self.assertEqual(result, {"a": 1})

    def test_status_team_missing_run(self):
        result = self._mod.status_team("team-nonexistent-xyz")
        self.assertEqual(result["run_id"], "team-nonexistent-xyz")
        self.assertIn("error", result)

    def test_slug_from_index(self):
        self.assertEqual(self._mod._slug_from_index(0), "worker-1")
        self.assertEqual(self._mod._slug_from_index(2), "worker-3")


if __name__ == "__main__":
    unittest.main()
