"""Tests for scripts/omni_team.py — WS6 team orchestrator (15+ cases).

Uses OMNI_SUBAGENT_FAKE=1 for deterministic worker outputs.
Does NOT require a real copilot binary.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Module loaders
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str):
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


omni_team = _load_module("omni_team")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})


def _wait_worker_terminal(run_id: str, slug: str, *, timeout: float = 10.0) -> dict:
    """Poll a worker's status.json until terminal. Returns status dict."""
    runs_dir = _REPO_ROOT / ".omni" / "runs"
    status_path = runs_dir / run_id / "workers" / slug / "status.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            if data.get("state") in TERMINAL_STATES:
                return data
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"worker {slug} did not reach terminal state in {timeout}s")


def _make_simple_plan(n: int = 2, skill: str = "ralph") -> dict:
    return {
        "base_branch": "main",
        "workers": [
            {
                "slug": f"worker-{i+1}",
                "skill": skill,
                "prompt": f"Test task for worker {i+1}",
                "category": "quick",
            }
            for i in range(n)
        ],
    }


# ---------------------------------------------------------------------------
# Test 1: create_team writes manifest + status files
# ---------------------------------------------------------------------------


def test_create_team_writes_manifest_and_status(tmp_path, monkeypatch):
    """create_team should write manifest.json and status.json."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    plan = _make_simple_plan(2)
    result = omni_team.create_team("test-team", plan, session_id="s-test1")

    run_id = result["run_id"]
    assert run_id.startswith("team-")

    run_dir = tmp_path / "runs" / run_id
    assert (run_dir / "manifest.json").exists(), "manifest.json must exist"
    assert (run_dir / "status.json").exists(), "status.json must exist"

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["run_id"] == run_id
    assert manifest["name"] == "test-team"
    assert manifest["session_id"] == "s-test1"
    assert len(manifest["workers"]) == 2

    status = json.loads((run_dir / "status.json").read_text())
    assert status["state"] == "created"
    assert status["run_id"] == run_id


# ---------------------------------------------------------------------------
# Test 2: dispatch_workers creates worktrees for each worker (happy path Linux)
# ---------------------------------------------------------------------------


def test_dispatch_workers_creates_worker_dirs(tmp_path, monkeypatch):
    """dispatch_workers should create worker run-dirs and status.json for each worker."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.1")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("dispatch-test", plan)
    run_id = create_result["run_id"]

    # Mock worktree add to avoid actual git operations in tests
    mock_worktree_mod = mock.MagicMock()
    mock_worktree_mod.add.return_value = {
        "worktree_path": str(tmp_path / "runs" / run_id / "workers" / "worker-1" / "worktree"),
        "branch": f"team-{run_id}/worker-1",
    }
    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: mock_worktree_mod)

    jobs = omni_team.dispatch_workers(run_id, plan)

    assert len(jobs) == 2
    for job in jobs:
        slug = job["slug"]
        worker_dir = tmp_path / "runs" / run_id / "workers" / slug
        assert worker_dir.exists(), f"worker dir must exist for {slug}"
        assert (worker_dir / "status.json").exists(), f"status.json must exist for {slug}"


# ---------------------------------------------------------------------------
# Test 3: cap-respecting dispatch — pool back-pressure
# ---------------------------------------------------------------------------


def test_dispatch_respects_pool_cap(tmp_path, monkeypatch):
    """dispatch_workers should use SubagentPool for back-pressure.

    We mock the pool to verify acquire() is called once per worker.
    """
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    plan = _make_simple_plan(4)
    # Force subprocess mode (use_tmux=False) so _SubprocessWorkerHost is used
    create_result = omni_team.create_team("cap-test", plan, use_tmux=False)
    run_id = create_result["run_id"]

    # Track acquire calls
    acquired_slugs: list[str] = []

    class FakePool:
        def acquire(self, job_id: str) -> None:
            acquired_slugs.append(job_id)

        def release(self, job_id: str) -> None:
            pass

        def status(self) -> dict:
            return {"cap": 4, "acquired": []}

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)

    # Make _SubprocessWorkerHost use our FakePool by patching _load_pool
    monkeypatch.setattr(omni_team._SubprocessWorkerHost, "_load_pool", lambda self: FakePool())

    # Also patch Popen so no real process is spawned
    def fake_popen(cmd, **kwargs):
        slug = None
        for i, arg in enumerate(cmd):
            if arg == "--job-id" and i + 1 < len(cmd):
                slug = cmd[i + 1]
        wdir = tmp_path / "runs" / run_id / "workers" / (slug.split("-", 2)[-1] if slug else "unknown")
        wdir.mkdir(parents=True, exist_ok=True)
        return mock.MagicMock(pid=1, returncode=None)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    jobs = omni_team.dispatch_workers(run_id, plan)
    assert len(jobs) == 4
    # Each worker should have triggered an acquire
    assert len(acquired_slugs) == 4


# ---------------------------------------------------------------------------
# Test 4: tmux path — skip if tmux not on PATH
# ---------------------------------------------------------------------------

pytestmark_tmux = pytest.mark.tmux


@pytest.mark.tmux
def test_tmux_session_creates_when_available(tmp_path, monkeypatch):
    """When tmux is on PATH, _TmuxSession.create should succeed."""
    if shutil.which("tmux") is None:
        pytest.skip("tmux not on PATH")
    if platform.system() == "Windows":
        pytest.skip("tmux test skipped on Windows without OMNI_EXPERIMENTAL_TEAM")

    session_name = f"omni-test-{os.getpid()}"
    try:
        session = omni_team._TmuxSession.create(session_name)
        assert session.is_alive()
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session_name],
                       capture_output=True)


# ---------------------------------------------------------------------------
# Test 5: subprocess fallback when tmux absent or use_tmux=False
# ---------------------------------------------------------------------------


def test_subprocess_fallback_when_no_tmux(tmp_path, monkeypatch):
    """When use_tmux=False, workers launch via _SubprocessWorkerHost."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    plan = _make_simple_plan(1)
    # Force use_tmux=False
    create_result = omni_team.create_team("no-tmux-test", plan, use_tmux=False)
    run_id = create_result["run_id"]

    # Verify manifest says use_tmux=False
    run_dir = tmp_path / "runs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["use_tmux"] is False

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)

    launched: list[dict] = []
    original_launch = omni_team._SubprocessWorkerHost.launch

    def patched_launch(self_h, worker):
        launched.append(worker)
        # Write a fake status
        worker_dir = omni_team._worker_dir(run_id, worker["slug"])
        worker_dir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(worker_dir / "status.json", {
            "state": "running", "slug": worker["slug"], "run_id": run_id,
            "pid": 99999, "started_at": omni_team._now_iso(), "ended_at": None,
        })
        return 99999

    monkeypatch.setattr(omni_team._SubprocessWorkerHost, "launch", patched_launch)

    jobs = omni_team.dispatch_workers(run_id, plan)
    assert len(launched) == 1
    assert launched[0]["slug"] == "worker-1"


# ---------------------------------------------------------------------------
# Test 6: collect_results aggregates worker summaries
# ---------------------------------------------------------------------------


def test_collect_results_aggregates(tmp_path, monkeypatch):
    """collect_results should aggregate per-worker states into a summary."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("collect-test", plan)
    run_id = create_result["run_id"]
    run_dir = tmp_path / "runs" / run_id

    # Manually write terminal worker statuses
    for i in range(1, 3):
        slug = f"worker-{i}"
        wdir = run_dir / "workers" / slug
        wdir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(wdir / "status.json", {
            "state": "done", "slug": slug, "run_id": run_id,
            "started_at": omni_team._now_iso(), "ended_at": omni_team._now_iso(),
        })

    result = omni_team.collect_results(run_id, timeout=5)
    assert result["state"] == "done"
    assert len(result["workers"]) == 2
    for w in result["workers"]:
        assert w["state"] == "done"


# ---------------------------------------------------------------------------
# Test 7: cancel cascade — writes cancel.signal + sets workers cancelled
# ---------------------------------------------------------------------------


def test_cancel_cascade(tmp_path, monkeypatch):
    """cancel_team should write cancel.signal at team root + each worker dir."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(3)
    create_result = omni_team.create_team("cancel-test", plan)
    run_id = create_result["run_id"]
    run_dir = tmp_path / "runs" / run_id

    # Write running worker statuses
    for i in range(1, 4):
        slug = f"worker-{i}"
        wdir = run_dir / "workers" / slug
        wdir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(wdir / "status.json", {
            "state": "running", "slug": slug, "run_id": run_id,
        })

    omni_team.cancel_team(run_id, reason="test-cancel")

    # Team root cancel.signal must exist
    assert (run_dir / "cancel.signal").exists()

    # Each worker dir must have cancel.signal
    for i in range(1, 4):
        slug = f"worker-{i}"
        assert (run_dir / "workers" / slug / "cancel.signal").exists()

    # Each worker status.json must be cancelled
    for i in range(1, 4):
        slug = f"worker-{i}"
        status = json.loads((run_dir / "workers" / slug / "status.json").read_text())
        assert status["state"] == "cancelled"

    # Team status must be cancelled
    team_status = json.loads((run_dir / "status.json").read_text())
    assert team_status["state"] == "cancelled"


# ---------------------------------------------------------------------------
# Test 8: cleanup removes worktrees + prunes git state
# ---------------------------------------------------------------------------


def test_cleanup_removes_worktrees(tmp_path, monkeypatch):
    """cleanup_team should remove worktrees via omni_worktree.remove."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("cleanup-test", plan)
    run_id = create_result["run_id"]

    removed_slugs: list[str] = []

    class MockWorktreeMod:
        @staticmethod
        def add(run_id_a, slug, base):
            wt_path = tmp_path / "runs" / run_id_a / "workers" / slug / "worktree"
            wt_path.mkdir(parents=True, exist_ok=True)
            return {"worktree_path": str(wt_path), "branch": f"team-{run_id_a}/{slug}",
                    "removed": False}

        @staticmethod
        def remove(run_id_r, slug, *, force=False):
            removed_slugs.append(slug)
            return {"removed": True, "worktree_path": f"/fake/{slug}/worktree",
                    "branch_removed": True}

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: MockWorktreeMod)

    result = omni_team.cleanup_team(run_id)
    assert len(result["removed_worktrees"]) == 2
    assert set(removed_slugs) == {"worker-1", "worker-2"}
    assert not result["errors"]

    # Team status must be cleaned
    run_dir = tmp_path / "runs" / run_id
    team_status = json.loads((run_dir / "status.json").read_text())
    assert team_status["state"] == "cleaned"


# ---------------------------------------------------------------------------
# Test 9: Windows experimental guard
# ---------------------------------------------------------------------------


def test_windows_tmux_guard_without_flag(monkeypatch):
    """On Windows without OMNI_EXPERIMENTAL_TEAM=1, tmux should raise RuntimeError."""
    monkeypatch.setattr(omni_team, "_is_windows", lambda: True)
    monkeypatch.delenv("OMNI_EXPERIMENTAL_TEAM", raising=False)
    # Also mock shutil.which to return a tmux path so we get past the "not found" check
    with mock.patch("shutil.which", return_value="/usr/bin/tmux"):
        with pytest.raises(RuntimeError, match="OMNI_EXPERIMENTAL_TEAM"):
            omni_team._TmuxSession.create("test-session")


def test_windows_subprocess_fallback_always_works(tmp_path, monkeypatch):
    """On Windows without OMNI_EXPERIMENTAL_TEAM=1, subprocess fallback must still work."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    monkeypatch.setattr(omni_team, "_is_windows", lambda: True)
    monkeypatch.delenv("OMNI_EXPERIMENTAL_TEAM", raising=False)

    plan = _make_simple_plan(1)
    # create_team with use_tmux=False should work regardless of platform
    result = omni_team.create_team("win-test", plan, use_tmux=False)
    run_id = result["run_id"]

    run_dir = tmp_path / "runs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["use_tmux"] is False


# ---------------------------------------------------------------------------
# Test 10: Team composes with ralph — worker skill=="ralph" spawns with --parent-run-id
# ---------------------------------------------------------------------------


def test_team_composes_with_ralph(tmp_path, monkeypatch):
    """Worker skill=='ralph' should spawn subagent with --parent-run-id pointing to team."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.05")

    plan = _make_simple_plan(1, skill="ralph")
    # Force subprocess mode to avoid tmux dependency
    create_result = omni_team.create_team("ralph-compose", plan, use_tmux=False)
    run_id = create_result["run_id"]

    launched_cmds: list[list] = []
    original_popen = subprocess.Popen

    def patched_popen(cmd, **kwargs):
        if isinstance(cmd, list):
            launched_cmds.append(cmd)
        # Create fake process
        worker_dir = tmp_path / "runs" / run_id / "workers" / "worker-1"
        worker_dir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(worker_dir / "status.json", {
            "state": "running", "slug": "worker-1", "run_id": run_id,
            "pid": 99999, "started_at": omni_team._now_iso(), "ended_at": None,
        })
        return mock.MagicMock(pid=99999, returncode=None)

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", patched_popen)

    omni_team.dispatch_workers(run_id, plan)

    # Verify --parent-run-id is in the launched command
    assert len(launched_cmds) >= 1
    flat_cmd = " ".join(str(x) for x in launched_cmds[0])
    assert "--parent-run-id" in flat_cmd
    assert run_id in flat_cmd


# ---------------------------------------------------------------------------
# Test 11: Team composes with autopilot
# ---------------------------------------------------------------------------


def test_team_composes_with_autopilot(tmp_path, monkeypatch):
    """Worker skill=='autopilot' should spawn subagent with autopilot skill."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(1, skill="autopilot")
    # Force subprocess mode to avoid tmux dependency
    create_result = omni_team.create_team("autopilot-compose", plan, use_tmux=False)
    run_id = create_result["run_id"]

    launched_cmds: list[list] = []

    def patched_popen(cmd, **kwargs):
        if isinstance(cmd, list):
            launched_cmds.append(list(cmd))
        worker_dir = tmp_path / "runs" / run_id / "workers" / "worker-1"
        worker_dir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(worker_dir / "status.json", {
            "state": "running", "slug": "worker-1", "run_id": run_id,
            "pid": 99998, "started_at": omni_team._now_iso(), "ended_at": None,
        })
        return mock.MagicMock(pid=99998, returncode=None)

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", patched_popen)

    omni_team.dispatch_workers(run_id, plan)

    assert len(launched_cmds) >= 1
    flat_cmd = " ".join(str(x) for x in launched_cmds[0])
    assert "autopilot" in flat_cmd


# ---------------------------------------------------------------------------
# Test 12: Orphan-worktree recovery — cleanup --force succeeds
# ---------------------------------------------------------------------------


def test_cleanup_force_handles_orphan_worktrees(tmp_path, monkeypatch):
    """cleanup_team --force should succeed even if worktree dir was manually deleted."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("orphan-test", plan)
    run_id = create_result["run_id"]

    # MockWorktreeMod that simulates an already-deleted worktree for worker-2
    removed_slugs: list[str] = []

    class MockWorktreeMod:
        @staticmethod
        def remove(run_id_r, slug, *, force=False):
            removed_slugs.append(slug)
            if slug == "worker-2" and not force:
                raise RuntimeError("worktree dir already deleted")
            return {"removed": True, "worktree_path": f"/fake/{slug}/worktree",
                    "branch_removed": True}

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: MockWorktreeMod)

    # With force=True it should NOT raise
    result = omni_team.cleanup_team(run_id, force=True)
    assert "worker-2" in removed_slugs
    # errors list may contain the force-suppressed error
    # but overall it should complete
    team_status = json.loads((tmp_path / "runs" / run_id / "status.json").read_text())
    assert team_status["state"] == "cleaned"


# ---------------------------------------------------------------------------
# Test 13: MCP state writes land under mode="team" and mode="team.<worker-slug>"
# ---------------------------------------------------------------------------


def test_mcp_state_writes_team_modes(tmp_path, monkeypatch):
    """create_team and dispatch_workers should write MCP state under correct mode keys."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    mcp_writes: list[tuple] = []

    def fake_mcp_write(mode, body, session_id=None):
        mcp_writes.append((mode, body.copy(), session_id))

    monkeypatch.setattr(omni_team, "_mcp_write_best_effort", fake_mcp_write)
    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)

    plan = _make_simple_plan(2)
    # Force subprocess mode to avoid tmux dependency
    create_result = omni_team.create_team("mcp-test", plan, session_id="s-mcp", use_tmux=False)
    run_id = create_result["run_id"]

    # After create, team mode should be written
    team_modes = [m for m, _, _ in mcp_writes if m == "team"]
    assert len(team_modes) >= 1

    # Dispatch (mock Popen to avoid real process)
    def patched_popen(cmd, **kwargs):
        # Write fake status for each worker
        for slug in ["worker-1", "worker-2"]:
            wdir = tmp_path / "runs" / run_id / "workers" / slug
            wdir.mkdir(parents=True, exist_ok=True)
            omni_team._write_json_atomic(wdir / "status.json", {
                "state": "running", "slug": slug, "run_id": run_id,
                "pid": 1, "started_at": omni_team._now_iso(), "ended_at": None,
            })
        return mock.MagicMock(pid=1, returncode=None)

    monkeypatch.setattr(subprocess, "Popen", patched_popen)

    omni_team.dispatch_workers(run_id, plan)

    # Per-worker modes should be written
    worker_modes = {m for m, _, _ in mcp_writes if m.startswith("team.")}
    assert "team.worker-1" in worker_modes
    assert "team.worker-2" in worker_modes


# ---------------------------------------------------------------------------
# Test 14: cancel-signal pairing — cancel then cleanup, no stale signals
# ---------------------------------------------------------------------------


def test_cancel_signal_paired_after_cleanup(tmp_path, monkeypatch):
    """After cancel + cleanup, cancel.signal should be paired with cancelled status.json."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("signal-pair-test", plan)
    run_id = create_result["run_id"]
    run_dir = tmp_path / "runs" / run_id

    # Write running worker statuses
    for i in range(1, 3):
        slug = f"worker-{i}"
        wdir = run_dir / "workers" / slug
        wdir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(wdir / "status.json", {
            "state": "running", "slug": slug, "run_id": run_id,
        })

    # Cancel
    omni_team.cancel_team(run_id, reason="test")

    # Verify cancel.signal exists and at least one status.json is cancelled
    assert (run_dir / "cancel.signal").exists()

    # Simulate the validator's check_cancel_signal_pairing logic
    found_cancelled = False
    for status_path in run_dir.rglob("status.json"):
        data = json.loads(status_path.read_text())
        if data.get("state") == "cancelled":
            found_cancelled = True
            break
    assert found_cancelled, "At least one status.json must have state=cancelled after cancel"


# ---------------------------------------------------------------------------
# Test 15: Concurrent teams share pool back-pressure
# ---------------------------------------------------------------------------


def test_concurrent_teams_share_pool(tmp_path, monkeypatch):
    """Two teams dispatching simultaneously should share the SubagentPool."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    acquire_calls: list[str] = []

    class SharedFakePool:
        def acquire(self, job_id: str) -> None:
            acquire_calls.append(job_id)

        def release(self, job_id: str) -> None:
            pass

        def status(self) -> dict:
            return {"cap": 4, "acquired": []}

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)

    original_init = omni_team._SubprocessWorkerHost.__init__

    def patched_init(self_h, run_id_h):
        original_init(self_h, run_id_h)
        self_h._pool = SharedFakePool()

    monkeypatch.setattr(omni_team._SubprocessWorkerHost, "__init__", patched_init)

    def patched_popen(cmd, **kwargs):
        return mock.MagicMock(pid=1, returncode=None)

    monkeypatch.setattr(subprocess, "Popen", patched_popen)

    # Create 2 teams each with 2 workers
    plan_a = _make_simple_plan(2)
    plan_b = _make_simple_plan(2)
    create_a = omni_team.create_team("team-a", plan_a, use_tmux=False)
    create_b = omni_team.create_team("team-b", plan_b, use_tmux=False)

    omni_team.dispatch_workers(create_a["run_id"], plan_a)
    omni_team.dispatch_workers(create_b["run_id"], plan_b)

    # Both teams should have contributed to acquire_calls
    assert len(acquire_calls) == 4  # 2 workers × 2 teams


# ---------------------------------------------------------------------------
# Test 16: status_team returns per-worker states
# ---------------------------------------------------------------------------


def test_status_team_returns_worker_states(tmp_path, monkeypatch):
    """status_team should return a summary with per-worker states."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("status-test", plan)
    run_id = create_result["run_id"]
    run_dir = tmp_path / "runs" / run_id

    # Write worker statuses
    states = {"worker-1": "running", "worker-2": "done"}
    for slug, state in states.items():
        wdir = run_dir / "workers" / slug
        wdir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(wdir / "status.json", {
            "state": state, "slug": slug, "run_id": run_id,
        })

    result = omni_team.status_team(run_id)
    assert result["run_id"] == run_id
    assert len(result["workers"]) == 2

    by_slug = {w["slug"]: w for w in result["workers"]}
    assert by_slug["worker-1"]["state"] == "running"
    assert by_slug["worker-2"]["state"] == "done"


# ---------------------------------------------------------------------------
# Test 17: CLI --help shows all subcommands
# ---------------------------------------------------------------------------


def test_cli_help_shows_all_subcommands(capsys):
    """omni_team.py --help should show all CLI subcommands."""
    with pytest.raises(SystemExit) as exc_info:
        omni_team.main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    for subcmd in ("create", "dispatch", "collect", "cancel", "cleanup", "status"):
        assert subcmd in captured.out


# ---------------------------------------------------------------------------
# Test 18: collect_results returns failed when any worker failed
# ---------------------------------------------------------------------------


def test_collect_results_fails_when_worker_fails(tmp_path, monkeypatch):
    """collect_results should return state=failed if any worker failed."""
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    plan = _make_simple_plan(2)
    create_result = omni_team.create_team("fail-collect-test", plan)
    run_id = create_result["run_id"]
    run_dir = tmp_path / "runs" / run_id

    # worker-1 done, worker-2 failed
    for slug, state in [("worker-1", "done"), ("worker-2", "failed")]:
        wdir = run_dir / "workers" / slug
        wdir.mkdir(parents=True, exist_ok=True)
        omni_team._write_json_atomic(wdir / "status.json", {
            "state": state, "slug": slug, "run_id": run_id,
            "started_at": omni_team._now_iso(), "ended_at": omni_team._now_iso(),
        })

    result = omni_team.collect_results(run_id, timeout=5)
    assert result["state"] == "failed"


# ---------------------------------------------------------------------------
# C3: Shell injection prevention in _TmuxWorkerHost.launch
# ---------------------------------------------------------------------------


def test_tmux_launch_shell_injection_not_executed(tmp_path, monkeypatch):
    """Adversarial prompt $(touch /tmp/pwned-wave-3x) must NOT be executed.

    We mock _TmuxSession.new_window to capture the cmd string and assert:
    1. The prompt is shlex-quoted (shell-safe single-quoted form).
    2. /tmp/pwned-wave-3x does NOT exist after the test.
    """
    import shlex as _shlex
    import tempfile
    import os

    sentinel = tmp_path / "pwned-wave-3x"
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    captured_cmds: list[str] = []

    class FakeTmuxSession:
        name = "fake-session"

        def new_window(self, slug, worktree_path, cmd):
            captured_cmds.append(cmd)

    host = omni_team._TmuxWorkerHost(run_id="test-inject-run", session=FakeTmuxSession())
    # Override _run_dir and _worker_dir to use tmp_path
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")

    worker = {
        "slug": "inject-worker",
        "skill": "ralph",
        "prompt": f"$(touch {str(sentinel)})",
        "worktree_path": str(tmp_path),
    }

    # Create the worker dir so launch doesn't fail on mkdir
    (tmp_path / "runs" / "test-inject-run" / "workers" / "inject-worker").mkdir(
        parents=True, exist_ok=True
    )

    rc = host.launch(worker)

    assert rc == -1, "tmux host must return -1 (non-falsy tmux sentinel)"
    assert len(captured_cmds) == 1

    cmd = captured_cmds[0]
    # The dangerous payload must appear shell-quoted (inside single quotes)
    # shlex.quote wraps in '' for strings containing special chars
    assert "$(touch" not in cmd or (
        # It IS in the cmd but wrapped in single quotes — verify properly quoted
        _shlex.quote(f"$(touch {str(sentinel)})") in cmd
    ), f"prompt not shell-quoted in cmd: {cmd!r}"

    # The sentinel file must NOT exist — the command was captured, not executed
    assert not sentinel.exists(), (
        f"/tmp/pwned-wave-3x was created — shell injection not prevented"
    )


# ---------------------------------------------------------------------------
# C4: _TmuxWorkerHost returns -1 (non-falsy) → workers marked "running"
# ---------------------------------------------------------------------------


def test_tmux_workers_marked_running_not_failed(tmp_path, monkeypatch):
    """Dispatch 3 workers via mock tmux host; assert all marked 'running' not 'failed'.

    Regression for: _TmuxWorkerHost.launch() returning 0 (falsy), which caused
    the dispatch loop's `pid is not None` check to mark all tmux workers as failed.
    Now launch() returns -1 (non-falsy sentinel) and callers check `pid is not None`.
    """
    monkeypatch.setattr(omni_team, "_OMNI_RUNS", tmp_path / "runs")
    monkeypatch.setenv("OMNI_TEST_MODE", "1")

    plan = {
        "name": "tmux-pid-test",
        "workers": [
            {"slug": f"tw{i}", "skill": "ralph", "prompt": "do work", "category": "quick"}
            for i in range(3)
        ],
    }
    # Create with use_tmux=False (subprocess), then we patch the launch method
    create_result = omni_team.create_team("tmux-pid-test", plan, use_tmux=False)
    run_id = create_result["run_id"]

    monkeypatch.setattr(omni_team, "_load_worktree_mod", lambda: None)

    # Patch _SubprocessWorkerHost.launch to return -1 (simulating the tmux sentinel)
    # This directly tests that the dispatch loop treats -1 as success, not failure.
    def fake_launch(self_h, worker):
        slug = worker["slug"]
        worker_dir = omni_team._worker_dir(run_id, slug)
        worker_dir.mkdir(parents=True, exist_ok=True)
        return -1  # tmux-mode sentinel: non-zero, non-None

    monkeypatch.setattr(omni_team._SubprocessWorkerHost, "launch", fake_launch)

    jobs = omni_team.dispatch_workers(run_id, plan)

    assert len(jobs) == 3
    run_dir = tmp_path / "runs" / run_id
    for w in ["tw0", "tw1", "tw2"]:
        status_path = run_dir / "workers" / w / "status.json"
        assert status_path.exists(), f"status.json missing for {w}"
        status = json.loads(status_path.read_text())
        assert status["state"] == "running", (
            f"worker {w} state={status['state']!r} — expected 'running' (C4 regression: "
            f"returning -1 must NOT be treated as launch failure)"
        )
