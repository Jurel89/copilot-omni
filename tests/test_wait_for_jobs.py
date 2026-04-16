"""Tests for scripts/wait_for_jobs.py (WS5a)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_module(name: str):
    path = _SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


wfj = _load_module("wait_for_jobs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_status(
    job_id: str,
    run_id: str,
    state: str,
    exit_code: int | None = None,
    started_at: str | None = "2026-01-01T00:00:00Z",
    ended_at: str | None = "2026-01-01T00:00:01Z",
) -> dict:
    return {
        "job_id": job_id,
        "run_id": run_id,
        "agent": "general-purpose",
        "category": None,
        "state": state,
        "started_at": started_at,
        "ended_at": ended_at,
        "exit_code": exit_code,
        "error": None,
        "model_used": None,
        "prompt_excerpt": "test prompt",
    }


def _write_status(path: Path, status: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test: single done job -> exit 0
# ---------------------------------------------------------------------------


def test_single_done_job(tmp_path, capsys):
    status_path = tmp_path / "run1" / "job1" / "status.json"
    _write_status(status_path, _make_status("job1", "run1", "done", exit_code=0))

    rc = wfj.wait_for_jobs([status_path], timeout=5.0, poll_interval=0.1)
    assert rc == 0

    captured = capsys.readouterr()
    line = json.loads(captured.out.strip())
    assert line["state"] == "done"
    assert line["job_id"] == "job1"
    assert line["exit_code"] == 0


# ---------------------------------------------------------------------------
# Test: mixed done + failed -> exit 1
# ---------------------------------------------------------------------------


def test_mixed_done_and_failed(tmp_path, capsys):
    p1 = tmp_path / "run1" / "job1" / "status.json"
    p2 = tmp_path / "run1" / "job2" / "status.json"
    _write_status(p1, _make_status("job1", "run1", "done", exit_code=0))
    _write_status(p2, _make_status("job2", "run1", "failed", exit_code=1))

    rc = wfj.wait_for_jobs([p1, p2], timeout=5.0, poll_interval=0.1)
    assert rc == 1


# ---------------------------------------------------------------------------
# Test: timeout -> exit 124
# ---------------------------------------------------------------------------


def test_timeout_returns_124(tmp_path, capsys):
    # Create a status.json stuck in "running" state
    p = tmp_path / "run1" / "job1" / "status.json"
    _write_status(p, _make_status("job1", "run1", "running"))

    rc = wfj.wait_for_jobs([p], timeout=0.3, poll_interval=0.05)
    assert rc == 124


# ---------------------------------------------------------------------------
# Test: cancelled job -> exit 1
# ---------------------------------------------------------------------------


def test_cancelled_job_exits_1(tmp_path, capsys):
    p = tmp_path / "run1" / "job1" / "status.json"
    _write_status(p, _make_status("job1", "run1", "cancelled", exit_code=None))

    rc = wfj.wait_for_jobs([p], timeout=5.0, poll_interval=0.1)
    assert rc == 1


# ---------------------------------------------------------------------------
# Test: mid-write (truncated JSON) -> retry succeeds
# ---------------------------------------------------------------------------


def test_mid_write_retry_succeeds(tmp_path, capsys):
    """Truncated JSON on first read should retry and succeed."""
    p = tmp_path / "run1" / "job1" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)

    good_status = _make_status("job1", "run1", "done", exit_code=0)

    # Write truncated JSON first
    p.write_text('{"job_id": "job1", "state": "don', encoding="utf-8")

    # After 0.15s, overwrite with valid status
    def _write_good():
        time.sleep(0.15)
        _write_status(p, good_status)

    t = threading.Thread(target=_write_good, daemon=True)
    t.start()

    rc = wfj.wait_for_jobs([p], timeout=5.0, poll_interval=0.05)
    t.join()

    assert rc == 0


# ---------------------------------------------------------------------------
# Test: status transitions pending -> running -> done
# ---------------------------------------------------------------------------


def test_waits_for_transition_to_terminal(tmp_path, capsys):
    """wait_for_jobs should keep polling until state is terminal."""
    p = tmp_path / "run1" / "job1" / "status.json"
    _write_status(p, _make_status("job1", "run1", "pending"))

    def _progress():
        time.sleep(0.1)
        _write_status(p, _make_status("job1", "run1", "running"))
        time.sleep(0.1)
        _write_status(p, _make_status("job1", "run1", "done", exit_code=0))

    t = threading.Thread(target=_progress, daemon=True)
    t.start()

    rc = wfj.wait_for_jobs([p], timeout=5.0, poll_interval=0.05)
    t.join()

    assert rc == 0


# ---------------------------------------------------------------------------
# Test: duration_s computed correctly
# ---------------------------------------------------------------------------


def test_duration_computed(tmp_path, capsys):
    """duration_s should be 1.0 for started/ended 1 second apart."""
    p = tmp_path / "run1" / "job1" / "status.json"
    _write_status(p, _make_status(
        "job1", "run1", "done", exit_code=0,
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
    ))

    wfj.wait_for_jobs([p], timeout=5.0, poll_interval=0.1)
    captured = capsys.readouterr()
    line = json.loads(captured.out.strip())
    assert line["duration_s"] == 1.0


# ---------------------------------------------------------------------------
# Test: missing status file -> handled gracefully
# ---------------------------------------------------------------------------


def test_missing_status_file_times_out(tmp_path, capsys):
    """A path that never exists should result in timeout (exit 124)."""
    p = tmp_path / "nonexistent" / "status.json"

    rc = wfj.wait_for_jobs([p], timeout=0.2, poll_interval=0.05)
    assert rc == 124


# ---------------------------------------------------------------------------
# Test: stdout_path and stderr_path in output
# ---------------------------------------------------------------------------


def test_output_includes_log_paths(tmp_path, capsys):
    """Output JSONL should include stdout_path and stderr_path."""
    p = tmp_path / "run1" / "job1" / "status.json"
    _write_status(p, _make_status("job1", "run1", "done", exit_code=0))

    wfj.wait_for_jobs([p], timeout=5.0, poll_interval=0.1)
    captured = capsys.readouterr()
    line = json.loads(captured.out.strip())
    assert "stdout_path" in line
    assert "stderr_path" in line
    assert line["stdout_path"].endswith("stdout.log")
    assert line["stderr_path"].endswith("stderr.log")


# ---------------------------------------------------------------------------
# Test: multiple jobs, all done
# ---------------------------------------------------------------------------


def test_multiple_done_jobs_all_exit_0(tmp_path, capsys):
    """Three done jobs should all be reported and exit 0."""
    paths = []
    for i in range(3):
        p = tmp_path / f"run{i}" / f"job{i}" / "status.json"
        _write_status(p, _make_status(f"job{i}", f"run{i}", "done", exit_code=0))
        paths.append(p)

    rc = wfj.wait_for_jobs(paths, timeout=5.0, poll_interval=0.1)
    assert rc == 0

    captured = capsys.readouterr()
    lines = [json.loads(ln) for ln in captured.out.strip().splitlines()]
    assert len(lines) == 3
    assert all(ln["state"] == "done" for ln in lines)


# ---------------------------------------------------------------------------
# Test: CLI --help
# ---------------------------------------------------------------------------


def test_cli_help(capsys):
    """--help should show --timeout and --poll-interval."""
    old_argv = sys.argv
    try:
        sys.argv = ["wait_for_jobs.py", "--help"]
        with pytest.raises(SystemExit) as exc_info:
            wfj.main()
    finally:
        sys.argv = old_argv

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--timeout" in captured.out
    assert "--poll-interval" in captured.out
    assert "--run-id" in captured.out
    assert "--session-id" in captured.out


# ---------------------------------------------------------------------------
# Test: no args -> exit 2
# ---------------------------------------------------------------------------


def test_cli_no_args_exit_2(capsys):
    old_argv = sys.argv
    try:
        sys.argv = ["wait_for_jobs.py"]
        rc = wfj.main()
    finally:
        sys.argv = old_argv

    assert rc == 2


# ---------------------------------------------------------------------------
# T6: exit-code semantics — 2 for config errors, 1 only for job failures
# ---------------------------------------------------------------------------


def test_empty_status_paths_returns_2(capsys):
    """T6: wait_for_jobs([]) returns 2 (config error), not 1."""
    rc = wfj.wait_for_jobs([], timeout=5)
    assert rc == 2, f"Expected 2 for no paths, got {rc}"


def test_failed_job_returns_1_not_2(tmp_path):
    """T6: a failed job returns 1 (job failure), not 2."""
    p = tmp_path / "status.json"
    _write_status(p, _make_status("job1", "run1", "failed", exit_code=1))
    rc = wfj.wait_for_jobs([p], timeout=5)
    assert rc == 1, f"Expected 1 for failed job, got {rc}"


def test_succeeded_job_returns_0(tmp_path):
    """T6: all done jobs returns 0."""
    p = tmp_path / "status.json"
    _write_status(p, _make_status("job1", "run1", "done", exit_code=0))
    rc = wfj.wait_for_jobs([p], timeout=5)
    assert rc == 0, f"Expected 0 for all-done, got {rc}"
