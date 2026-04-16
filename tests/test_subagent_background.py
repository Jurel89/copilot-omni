"""Tests for subagent.py background mode and run-directory artifacts (WS5a)."""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from unittest import mock

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


subagent = _load_module("subagent")

# Required status.json fields
STATUS_REQUIRED_FIELDS = frozenset({
    "job_id", "run_id", "agent", "category", "state",
    "started_at", "ended_at", "exit_code", "error",
    "model_used", "prompt_excerpt",
})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_terminal(status_path: Path, *, timeout: float = 30.0) -> dict:
    """Poll status.json until state is terminal. Returns final status dict."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            if data.get("state") in ("done", "failed", "cancelled"):
                return data
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"Job did not reach terminal state within {timeout}s")


# ---------------------------------------------------------------------------
# Test: single background job round-trip
# ---------------------------------------------------------------------------


def test_background_spawn_returns_immediately(tmp_path, monkeypatch):
    """spawn(..., background=True) returns a dict with pid, job_id, run_id, status_path."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.2")

    result = subagent.spawn(
        "general-purpose", "echo test",
        background=True,
    )

    assert "job_id" in result
    assert "run_id" in result
    assert "pid" in result
    assert "status_path" in result
    assert "error" not in result


def test_background_status_json_exists(tmp_path, monkeypatch):
    """status.json must exist at the announced path immediately after spawn."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.1")

    result = subagent.spawn(
        "general-purpose", "echo test",
        background=True,
    )

    status_path = Path(result["status_path"])
    assert status_path.exists(), "status.json must exist right after spawn"

    # spec.json must also exist
    spec_path = status_path.parent / "spec.json"
    assert spec_path.exists(), "spec.json must exist right after spawn"


def test_background_status_schema(monkeypatch):
    """status.json must contain all required fields after job terminates."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.1")

    result = subagent.spawn(
        "general-purpose", "check schema",
        background=True,
    )

    status_path = Path(result["status_path"])
    final = _wait_for_terminal(status_path, timeout=30.0)

    missing = STATUS_REQUIRED_FIELDS - set(final.keys())
    assert not missing, f"status.json missing required fields: {missing}"
    assert final["state"] == "done"
    assert final["exit_code"] == 0


# ---------------------------------------------------------------------------
# Test: 3 parallel background jobs
# ---------------------------------------------------------------------------


def test_three_parallel_background_jobs(monkeypatch):
    """Spawn 3 background jobs; all must complete as 'done' within 30s."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "1")

    results = []
    for i in range(3):
        r = subagent.spawn(
            "general-purpose", f"parallel job {i}",
            background=True,
        )
        assert "error" not in r, f"spawn failed: {r}"
        results.append(r)

    # Wait for all to finish
    final_statuses = []
    for r in results:
        status_path = Path(r["status_path"])
        final = _wait_for_terminal(status_path, timeout=30.0)
        final_statuses.append(final)

    # All must be done
    for i, fs in enumerate(final_statuses):
        assert fs["state"] == "done", f"job {i} ended in {fs['state']}"

    # All must have unique job_ids
    job_ids = [r["job_id"] for r in results]
    assert len(set(job_ids)) == 3, "job_ids must be unique"


# ---------------------------------------------------------------------------
# Test: foreground mode with fake
# ---------------------------------------------------------------------------


def test_foreground_spawn_returns_exit_code(monkeypatch):
    """spawn(..., background=False) blocks and returns exit_code=0 for fake."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0")

    result = subagent.spawn(
        "general-purpose", "foreground test",
        background=False,
    )

    assert result["exit_code"] == 0
    assert "status_path" in result
    assert "stdout" in result

    # Verify status.json shows done
    status_path = Path(result["status_path"])
    final = json.loads(status_path.read_text(encoding="utf-8"))
    assert final["state"] == "done"
    assert final["exit_code"] == 0


def test_foreground_log_files_written(monkeypatch):
    """stdout.log and stderr.log must exist after foreground spawn."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0")

    result = subagent.spawn(
        "general-purpose", "log file test",
        background=False,
    )

    job_dir = Path(result["status_path"]).parent
    assert (job_dir / "stdout.log").exists()
    assert (job_dir / "stderr.log").exists()


# ---------------------------------------------------------------------------
# Test: run-directory structure
# ---------------------------------------------------------------------------


def test_run_directory_layout(monkeypatch):
    """Run directory must follow .omni/runs/<run-id>/<job-id>/ layout."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0")

    run_id = "test-run-layout-001"
    job_id = "test-job-layout-001"

    result = subagent.spawn(
        "general-purpose", "layout test",
        background=False,
        run_id=run_id,
        job_id=job_id,
    )

    status_path = Path(result["status_path"])
    assert status_path.parent.name == job_id
    assert status_path.parent.parent.name == run_id
    assert "runs" in str(status_path)


# ---------------------------------------------------------------------------
# Test: CLI --background flag
# ---------------------------------------------------------------------------


def test_cli_background_flag(monkeypatch, capsys):
    """CLI --background should print JSON with run_id, job_id, pid, status_path."""
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE", "1")
    monkeypatch.setenv("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "0.1")

    # We call main() directly with sys.argv patched
    import sys
    old_argv = sys.argv
    try:
        sys.argv = [
            "subagent.py",
            "general-purpose",
            "cli background test",
            "--background",
        ]
        rc = subagent.main()
    finally:
        sys.argv = old_argv

    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert "job_id" in data
    assert "run_id" in data
    assert "pid" in data
    assert "status_path" in data


def test_cli_help_shows_new_flags(capsys):
    """--help output must show --background, --session-id, --run-id, --job-id."""
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["subagent.py", "--help"]
        with pytest.raises(SystemExit) as exc_info:
            subagent.main()
    finally:
        sys.argv = old_argv

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--background" in captured.out
    assert "--session-id" in captured.out
    assert "--run-id" in captured.out
    assert "--job-id" in captured.out
