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
    """Return True if a process with the given PID is running.

    POSIX: ``os.kill(pid, 0)`` raises ProcessLookupError when the pid is gone,
    PermissionError when the process exists under another owner.

    Phase-C C02: on Windows, os.kill with signal 0 does not exist in the same
    form; we fall back to OpenProcess via ctypes. A failed open (with
    GetLastError() == ERROR_INVALID_PARAMETER == 87) means the pid is gone.
    """
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415 — Windows only
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong(0)
                ok = ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code)
                )
                if not ok:
                    return False
                STILL_ACTIVE = 259
                return exit_code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            # Defensive: on any error fall back to "alive" so the pool
            # errs on the side of holding the slot rather than double-issuing.
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Phase-C C08 + C26: memory policing
# ---------------------------------------------------------------------------

DEFAULT_SUBAGENT_MEM_CAP_MB = 512     # C08 — per-subagent estimate / ceiling
DEFAULT_POOL_MEM_CAP_MB = 4096        # C26 — cumulative cap across active jobs


def _rss_mb(pid: int) -> Optional[float]:
    """Return *pid*'s resident-set size in MB, or None when unreadable.

    Linux: parse /proc/<pid>/status VmRSS.
    Windows: GetProcessMemoryInfo via ctypes.
    Other platforms (macOS, BSD, …): None — caller treats that as unknown
    and skips the rollup for that pid (defensive).
    """
    if sys.platform.startswith("linux"):
        status = Path(f"/proc/{pid}/status")
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    # "VmRSS:    12345 kB"
                    if len(parts) >= 3 and parts[2].lower() == "kb":
                        return int(parts[1]) / 1024.0
        except Exception:
            return None
        return None
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415 — Windows only
            from ctypes import wintypes  # noqa: PLC0415

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if not handle:
                return None
            try:
                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                pmc = PROCESS_MEMORY_COUNTERS()
                pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                psapi = ctypes.windll.psapi
                ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb)
                if not ok:
                    return None
                return pmc.WorkingSetSize / (1024.0 * 1024.0)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return None
    return None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value <= 0:
            return default
        return value
    except ValueError:
        return default


class MemoryPolicyDenied(RuntimeError):
    """Raised by SubagentPool.acquire when a memory cap would be exceeded."""


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

    def _rollup_rss_mb(self, acquired: list) -> float:
        """Sum RSS across pids that report a reading; unknown pids contribute 0."""
        total = 0.0
        for entry in acquired:
            pid = entry.get("pid")
            if not isinstance(pid, int):
                continue
            value = _rss_mb(pid)
            if value is not None:
                total += value
        return total

    def acquire(self, job_id: str) -> None:
        """Block until a slot is free; raises TimeoutError after timeout.

        Phase-C C08 + C26: before granting a slot, enforce two memory caps:
        - OMNI_SUBAGENT_MEM_CAP_MB (default 512): minimum estimated RSS per
          subagent. Raises MemoryPolicyDenied when a subagent can't be sized
          within its share of the pool cap.
        - OMNI_POOL_MEM_CAP_MB (default 4096): cumulative across active pids.
          When the rollup (existing + per-subagent estimate) exceeds this
          budget, acquire raises MemoryPolicyDenied rather than spawning.
        """
        pid = os.getpid()
        deadline = _now() + self._timeout
        subagent_cap_mb = _env_int("OMNI_SUBAGENT_MEM_CAP_MB",
                                    DEFAULT_SUBAGENT_MEM_CAP_MB)
        pool_cap_mb = _env_int("OMNI_POOL_MEM_CAP_MB",
                               DEFAULT_POOL_MEM_CAP_MB)

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

                # C08 + C26: enforce memory caps BEFORE accepting the slot.
                current_rss = self._rollup_rss_mb(acquired)
                projected = current_rss + subagent_cap_mb
                if projected > pool_cap_mb:
                    _flock_unlock(fd)
                    os.close(fd)
                    raise MemoryPolicyDenied(
                        f"pool memory cap exceeded: current_rss={current_rss:.1f}MB "
                        f"+ per_subagent_cap={subagent_cap_mb}MB > "
                        f"pool_cap={pool_cap_mb}MB"
                    )

                if len(acquired) < cap:
                    acquired.append({
                        "job_id": job_id, "pid": pid, "ts": _now(),
                        "rss_cap_mb": subagent_cap_mb,
                    })
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
            except MemoryPolicyDenied:
                raise
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
