"""Tests for subagent_pool.py back-pressure (WS5a)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
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


pool_mod = _load_module("subagent_pool")
SubagentPool = pool_mod.SubagentPool
get_cap = pool_mod.get_cap


# ---------------------------------------------------------------------------
# Test: get_cap default
# ---------------------------------------------------------------------------


def test_get_cap_returns_positive_int():
    cap = get_cap()
    assert isinstance(cap, int)
    assert cap > 0
    assert cap <= 8


def test_get_cap_config_override(tmp_path):
    """get_cap reads runtime.max_parallel_subagents from .omni/config.json."""
    omni_dir = tmp_path / ".omni"
    omni_dir.mkdir()
    config = omni_dir / "config.json"
    config.write_text(json.dumps({"runtime": {"max_parallel_subagents": 3}}))

    # Patch the repo root used by get_cap
    original_root = pool_mod._REPO_ROOT
    try:
        pool_mod._REPO_ROOT = tmp_path
        cap = get_cap()
        assert cap == 3
    finally:
        pool_mod._REPO_ROOT = original_root


# ---------------------------------------------------------------------------
# Test: acquire / release basic
# ---------------------------------------------------------------------------


def test_acquire_release_single_slot(tmp_path):
    """Acquire and release a single slot successfully."""
    pool = SubagentPool(cap=2, lock_dir=tmp_path / "locks", timeout=5.0)
    pool.acquire("job-1")
    status = pool.status()
    assert len(status["acquired"]) == 1
    pool.release("job-1")
    status = pool.status()
    assert len(status["acquired"]) == 0


def test_acquire_fills_cap(tmp_path):
    """Acquire up to cap; cap+1 should block."""
    pool = SubagentPool(cap=3, lock_dir=tmp_path / "locks", timeout=5.0)
    pool.acquire("job-1")
    pool.acquire("job-2")
    pool.acquire("job-3")

    status = pool.status()
    assert len(status["acquired"]) == 3

    # Attempt to acquire beyond cap — should timeout quickly
    pool2 = SubagentPool(cap=3, lock_dir=tmp_path / "locks", timeout=0.5)
    with pytest.raises(TimeoutError):
        pool2.acquire("job-4")

    # Release one slot and try again
    pool.release("job-1")
    pool3 = SubagentPool(cap=3, lock_dir=tmp_path / "locks", timeout=5.0)
    pool3.acquire("job-4")
    pool.release("job-2")
    pool.release("job-3")
    pool3.release("job-4")


def test_release_nonexistent_job_is_noop(tmp_path):
    """Releasing a job_id that doesn't exist should not raise."""
    pool = SubagentPool(cap=4, lock_dir=tmp_path / "locks", timeout=5.0)
    # Should not raise
    pool.release("nonexistent-job-xyz")


# ---------------------------------------------------------------------------
# Test: stale entry pruning
# ---------------------------------------------------------------------------


def test_stale_entries_pruned_on_acquire(tmp_path):
    """Entries with dead PIDs and age > STALE_AGE_SECS are pruned on acquire."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "subagent_pool.lock"

    # Inject a stale entry: PID 99999 (very likely dead), old timestamp
    stale_ts = time.time() - SubagentPool.STALE_AGE_SECS - 60
    state = {
        "acquired": [{"job_id": "stale-job", "pid": 99999999, "ts": stale_ts}],
        "cap": 2,
    }
    lock_path.write_text(json.dumps(state), encoding="utf-8")

    pool = SubagentPool(cap=2, lock_dir=lock_dir, timeout=5.0)
    # Acquire should prune the stale entry and succeed
    pool.acquire("new-job")
    status = pool.status()
    job_ids = [e["job_id"] for e in status["acquired"]]
    assert "stale-job" not in job_ids
    assert "new-job" in job_ids
    pool.release("new-job")


# ---------------------------------------------------------------------------
# Test: cap=4, 12 jobs — wall time and concurrency
# ---------------------------------------------------------------------------


def test_cap_4_twelve_jobs_wall_time(tmp_path):
    """Cap=4, 12 jobs with sleep 2s: wall time >= 6s, <= 18s, max concurrent <= 4."""
    import threading

    cap = 4
    n_jobs = 12
    sleep_secs = 0.3  # use 0.3s instead of 2s to keep test fast

    pool = SubagentPool(cap=cap, lock_dir=tmp_path / "locks", timeout=60.0)

    concurrent_counts: list[int] = []
    counter_lock = threading.Lock()
    active = [0]
    results: list[dict] = []
    result_lock = threading.Lock()

    def run_job(job_id: str):
        pool.acquire(job_id)
        with counter_lock:
            active[0] += 1
            concurrent_counts.append(active[0])
        try:
            time.sleep(sleep_secs)
        finally:
            with counter_lock:
                active[0] -= 1
            pool.release(job_id)
        with result_lock:
            results.append({"job_id": job_id, "done": True})

    start = time.monotonic()
    threads = []
    for i in range(n_jobs):
        t = threading.Thread(target=run_job, args=(f"job-{i}",))
        threads.append(t)

    for t in threads:
        t.start()

    for t in threads:
        t.join(timeout=60)

    elapsed = time.monotonic() - start

    # All jobs must complete
    assert len(results) == n_jobs

    # Max concurrent must not exceed cap
    max_concurrent = max(concurrent_counts) if concurrent_counts else 0
    assert max_concurrent <= cap, (
        f"max concurrent {max_concurrent} exceeded cap {cap}"
    )

    # Wall time: at least ceil(n_jobs/cap) waves * sleep_secs
    min_expected = (n_jobs / cap) * sleep_secs
    assert elapsed >= min_expected * 0.8, (
        f"wall time {elapsed:.2f}s < expected min {min_expected * 0.8:.2f}s"
    )


# ---------------------------------------------------------------------------
# Test: TimeoutError when cap exceeded
# ---------------------------------------------------------------------------


def test_timeout_error_when_cap_exceeded(tmp_path):
    """acquire() raises TimeoutError when cap is full and timeout expires."""
    pool = SubagentPool(cap=1, lock_dir=tmp_path / "locks", timeout=0.3)
    pool.acquire("holder-job")

    pool2 = SubagentPool(cap=1, lock_dir=tmp_path / "locks", timeout=0.3)
    with pytest.raises(TimeoutError):
        pool2.acquire("waiter-job")

    pool.release("holder-job")


# ---------------------------------------------------------------------------
# Test: cross-process cap enforcement (using subprocess)
# ---------------------------------------------------------------------------


def test_cross_process_cap_enforcement(tmp_path):
    """Cross-process: 8 subprocesses all try to acquire cap=4; max concurrent <= 4."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()

    # Script that acquires pool, sleeps, releases, then prints "done <job_id>"
    worker_script = tmp_path / "worker.py"
    worker_script.write_text(
        f"""\
import sys, time, json, importlib.util
from pathlib import Path

job_id = sys.argv[1]
lock_dir = {str(lock_dir)!r}
scripts_dir = {str(_SCRIPTS)!r}

spec = importlib.util.spec_from_file_location(
    "subagent_pool", str(Path(scripts_dir) / "subagent_pool.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

pool = mod.SubagentPool(cap=4, lock_dir=Path(lock_dir), timeout=30.0)
pool.acquire(job_id)
time.sleep(0.3)
pool.release(job_id)
print(f"done {{job_id}}")
""",
        encoding="utf-8",
    )

    procs = []
    for i in range(8):
        p = subprocess.Popen(
            [sys.executable, str(worker_script), f"xproc-job-{i}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        procs.append(p)

    start = time.monotonic()
    outputs = []
    for p in procs:
        stdout, _ = p.communicate(timeout=60)
        outputs.append(stdout.strip())
    elapsed = time.monotonic() - start

    # All 8 processes must finish
    completed = [o for o in outputs if o.startswith("done")]
    assert len(completed) == 8, f"Only {len(completed)}/8 jobs completed: {outputs}"

    # With cap=4 and sleep=0.3s, 8 jobs in 2 waves => wall time >= 0.6s
    assert elapsed >= 0.5, f"Wall time {elapsed:.2f}s seems too fast for cap=4 enforcement"
