#!/usr/bin/env python3
"""Subagent pool — cross-process semaphore for subagent back-pressure.

Uses a file-lock (fcntl.flock on POSIX, msvcrt on Windows) plus a JSON
token-bucket so the concurrency cap is enforced ACROSS processes.

Per ADR-0010: default cap = min(8, os.cpu_count() or 4).
Overridable via .omni/config.json > runtime.max_parallel_subagents.

Stdlib only. No third-party deps.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Platform file-locking
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    try:
        import msvcrt as _msvcrt  # type: ignore[import]

        def _flock_exclusive(fd: int) -> None:
            _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)

        def _flock_unlock(fd: int) -> None:
            _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)

        _FLOCK_AVAILABLE = True
    except ImportError:
        _FLOCK_AVAILABLE = False

        def _flock_exclusive(fd: int) -> None:
            pass

        def _flock_unlock(fd: int) -> None:
            pass
else:
    try:
        import fcntl as _fcntl

        def _flock_exclusive(fd: int) -> None:
            _fcntl.flock(fd, _fcntl.LOCK_EX)

        def _flock_unlock(fd: int) -> None:
            _fcntl.flock(fd, _fcntl.LOCK_UN)

        _FLOCK_AVAILABLE = True
    except ImportError:
        _FLOCK_AVAILABLE = False

        def _flock_exclusive(fd: int) -> None:
            pass

        def _flock_unlock(fd: int) -> None:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_cap() -> int:
    """Read .omni/config.json > runtime.max_parallel_subagents OR
    fall back to min(8, os.cpu_count() or 4).
    """
    config_path = _REPO_ROOT / ".omni" / "config.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        cap = data.get("runtime", {}).get("max_parallel_subagents")
        if isinstance(cap, int) and cap > 0:
            return cap
    except Exception:
        pass
    return min(8, os.cpu_count() or 4)


def _is_pid_alive(pid: int) -> bool:
    """Return True if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't have permission to signal it
        return True
    except Exception:
        return False


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# SubagentPool
# ---------------------------------------------------------------------------


class SubagentPool:
    """Cross-process semaphore backed by a JSON file under a file-lock.

    Lock file path: <lock_dir>/subagent_pool.lock
    Token bucket JSON: {"acquired": [{"job_id", "pid", "ts"}], "cap": N}

    Stale entries (pid not alive AND age > 5 min) are pruned on acquire.
    """

    STALE_AGE_SECS = 300  # 5 minutes

    def __init__(
        self,
        *,
        cap: Optional[int] = None,
        lock_dir: Optional[Path] = None,
        timeout: float = 60.0,
    ) -> None:
        self._cap = cap if cap is not None else get_cap()
        if lock_dir is None:
            omni_home = os.environ.get("OMNI_HOME")
            if omni_home:
                lock_dir = Path(omni_home) / "locks"
            else:
                lock_dir = Path.home() / ".omni" / "locks"
        self._lock_dir = lock_dir
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._lock_dir / "subagent_pool.lock"
        self._timeout = timeout

    def _read_state(self, fd: int) -> dict:
        """Read and parse the lock file state. Must be called with lock held."""
        os.lseek(fd, 0, os.SEEK_SET)
        raw = b""
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            raw += chunk
        if not raw.strip():
            return {"acquired": [], "cap": self._cap}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {"acquired": [], "cap": self._cap}

    def _write_state(self, fd: int, state: dict) -> None:
        """Write state to the lock file. Must be called with lock held."""
        data = json.dumps(state).encode("utf-8")
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, data)

    def _prune_stale(self, acquired: list) -> list:
        """Remove entries whose pid is dead and whose age exceeds STALE_AGE_SECS."""
        now = _now()
        live = []
        for entry in acquired:
            pid = entry.get("pid", 0)
            ts = entry.get("ts", 0)
            age = now - ts
            if not _is_pid_alive(pid) and age > self.STALE_AGE_SECS:
                continue  # prune
            live.append(entry)
        return live

    def acquire(self, job_id: str) -> None:
        """Block until a slot is free; raises TimeoutError after timeout."""
        pid = os.getpid()
        deadline = _now() + self._timeout

        if not _FLOCK_AVAILABLE:
            # Best-effort: no locking available, proceed
            return

        while True:
            if _now() > deadline:
                raise TimeoutError(
                    f"SubagentPool.acquire: timed out after {self._timeout}s "
                    f"waiting for a free slot (cap={self._cap})"
                )

            fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o600)
            try:
                _flock_exclusive(fd)
                state = self._read_state(fd)
                acquired = self._prune_stale(state.get("acquired", []))
                cap = state.get("cap", self._cap)

                if len(acquired) < cap:
                    acquired.append({"job_id": job_id, "pid": pid, "ts": _now()})
                    state["acquired"] = acquired
                    state["cap"] = cap
                    self._write_state(fd, state)
                    _flock_unlock(fd)
                    os.close(fd)
                    return
                else:
                    # Slot not free; release lock and wait
                    _flock_unlock(fd)
                    os.close(fd)
                    time.sleep(0.1)
            except Exception:
                try:
                    _flock_unlock(fd)
                except Exception:
                    pass
                try:
                    os.close(fd)
                except Exception:
                    pass
                raise

    def release(self, job_id: str) -> None:
        """Remove job_id from the acquired list."""
        if not _FLOCK_AVAILABLE:
            return

        if not self._lock_path.exists():
            return

        fd = os.open(str(self._lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _flock_exclusive(fd)
            state = self._read_state(fd)
            acquired = [e for e in state.get("acquired", [])
                        if e.get("job_id") != job_id]
            state["acquired"] = acquired
            self._write_state(fd, state)
            _flock_unlock(fd)
        except Exception:
            try:
                _flock_unlock(fd)
            except Exception:
                pass
            raise
        finally:
            try:
                os.close(fd)
            except Exception:
                pass

    def status(self) -> dict:
        """Return current pool state (cap, acquired list). Read-only."""
        if not self._lock_path.exists():
            return {"cap": self._cap, "acquired": []}

        fd = os.open(str(self._lock_path), os.O_RDONLY | os.O_CREAT, 0o600)
        try:
            _flock_exclusive(fd)
            state = self._read_state(fd)
            _flock_unlock(fd)
        except Exception:
            try:
                _flock_unlock(fd)
            except Exception:
                pass
            return {"cap": self._cap, "acquired": []}
        finally:
            try:
                os.close(fd)
            except Exception:
                pass

        acquired = self._prune_stale(state.get("acquired", []))
        return {"cap": state.get("cap", self._cap), "acquired": acquired}


# ---------------------------------------------------------------------------
# CLI (for diagnostics)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Subagent pool diagnostics")
    parser.add_argument("--status", action="store_true", help="Show pool status")
    parser.add_argument("--cap", action="store_true", help="Print configured cap")
    args = parser.parse_args()

    if args.cap:
        print(get_cap())
    else:
        pool = SubagentPool()
        st = pool.status()
        print(json.dumps(st, indent=2))
