#!/usr/bin/env python3
"""omni_team.py — WS6 team orchestrator (Copilot-native team skill only).

Manages the full lifecycle of a native Copilot team:
  create → plan → dispatch → execute → verify → collect → cleanup

NOTE: This script supports only the native `team` skill (skills/team/SKILL.md).
A prior tmux-worker skill that invoked external AI binaries was removed in
v2.1 — see docs/MIGRATION.md section 4b. Do not reintroduce external-binary
worker invocations here; the `verify_plugin_contract.py --check-external-cli`
gate now scans this file as part of the shipped plugin surface.

Run-directory layout:
  .omni/runs/team-<id>/
    manifest.json          # team definition + worker list
    status.json            # team-level status
    cancel.signal          # presence = cancel requested
    workers/
      <slug>/
        worktree/          # git worktree for this worker
        status.json        # worker status (polling target)
        stdout.log
        stderr.log
        inner/             # inner skill (ralph/autopilot) run-dir

Platform support:
  - Linux/macOS with tmux: _TmuxSession host
  - All platforms, tmux absent, or use_tmux=False: _SubprocessWorkerHost
  - Windows native tmux: gated behind OMNI_EXPERIMENTAL_TEAM=1

Stdlib only. No third-party deps.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OMNI_RUNS = _REPO_ROOT / ".omni" / "runs"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, data: dict) -> None:
    """Atomically write JSON using a .tmp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _read_json_safe(path: Path) -> Optional[dict]:
    """Read and parse a JSON file; returns None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run_dir(run_id: str) -> Path:
    return _OMNI_RUNS / run_id


def _worker_dir(run_id: str, slug: str) -> Path:
    return _run_dir(run_id) / "workers" / slug


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _slug_from_index(i: int) -> str:
    return f"worker-{i + 1}"


def _mcp_write_best_effort(mode: str, body: dict, session_id: Optional[str] = None) -> None:
    """Write to MCP state table (best-effort, never raises).

    The state table uses composite PK (mode, session_id) since schema v6.
    session_id is normalized to '' when unset so the ON CONFLICT target
    always matches a real row.
    """
    try:
        import sqlite3
        db_path = Path(os.environ.get("OMNI_HOME", str(Path.home() / ".omni"))) / "omni.db"
        if not db_path.exists():
            return
        body_str = json.dumps(body)
        now = time.time()
        sid = session_id or ""
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute(
                "INSERT INTO state(mode, body, session_id, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(mode, session_id) DO UPDATE SET"
                "  body=excluded.body,"
                "  updated_at=excluded.updated_at",
                (mode, body_str, sid, now),
            )
            conn.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# _TmuxSession: tmux-backed worker host
# ---------------------------------------------------------------------------


class _TmuxSession:
    """Manage a named tmux session for team workers.

    Each worker gets its own window. Output is captured via capture-pane.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    def create(cls, name: str) -> "_TmuxSession":
        """Create a new detached tmux session. Raises RuntimeError on failure."""
        if _is_windows():
            if os.environ.get("OMNI_EXPERIMENTAL_TEAM") != "1":
                raise RuntimeError(
                    "tmux is not supported on Windows without OMNI_EXPERIMENTAL_TEAM=1. "
                    "Options:\n"
                    "  1. Run with OMNI_EXPERIMENTAL_TEAM=1 if you have tmux "
                    "available under WSL / Cygwin / Git-Bash.\n"
                    "  2. Pass use_tmux=False to get the subprocess worker host "
                    "(no multiplexer, workers run detached).\n"
                    "  3. See docs/TEAM-WINDOWS.md for wezterm and Windows "
                    "Terminal panel fallbacks that match the tmux UX on nt."
                )
            # On Windows with guard set, attempt anyway (user opted in)

        tmux = shutil.which("tmux")
        if not tmux:
            raise RuntimeError("tmux not found on PATH; use subprocess fallback (use_tmux=False)")

        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tmux new-session failed: {result.stderr.strip()}"
            )
        return cls(name)

    def new_window(self, window_name: str, cwd: str, cmd: str) -> None:
        """Create a new window in the session running cmd in cwd."""
        subprocess.run(
            ["tmux", "new-window", "-t", self.name,
             "-n", window_name, "-c", cwd],
            capture_output=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", f"{self.name}:{window_name}", cmd, "Enter"],
            capture_output=True,
        )

    def capture_pane(self, window_name: str, *, lines: int = 50) -> str:
        """Capture the last N lines from a window's pane."""
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", f"{self.name}:{window_name}",
             "-S", f"-{lines}"],
            capture_output=True,
            text=True,
        )
        return result.stdout

    def kill(self) -> None:
        """Kill the tmux session."""
        subprocess.run(
            ["tmux", "kill-session", "-t", self.name],
            capture_output=True,
        )

    def is_alive(self) -> bool:
        """Return True if the session exists."""
        result = subprocess.run(
            ["tmux", "has-session", "-t", self.name],
            capture_output=True,
        )
        return result.returncode == 0


# ---------------------------------------------------------------------------
# Worker host interface
# ---------------------------------------------------------------------------


class _SubprocessWorkerHost:
    """Worker host that spawns each worker as a detached subprocess via subagent.py.

    Uses subagent_pool for back-pressure. Workers log to worker run-dir's
    stdout.log / stderr.log. Status is polled via status.json.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._procs: dict[str, subprocess.Popen] = {}
        self._pool = self._load_pool()

    def _load_pool(self):
        """Load SubagentPool dynamically (best-effort)."""
        pool_path = _REPO_ROOT / "scripts" / "subagent_pool.py"
        if not pool_path.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location("subagent_pool", pool_path)
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod.SubagentPool()
        except Exception:
            return None

    def launch(self, worker: dict) -> int:
        """Spawn worker via subagent.py --background.

        Acquires a pool slot before launching. Returns pid or 0 on failure.
        """
        slug = worker["slug"]
        skill = worker.get("skill", "ralph")
        prompt = worker.get("prompt", f"Execute task for team worker {slug}")
        run_dir = _worker_dir(self.run_id, slug)
        run_dir.mkdir(parents=True, exist_ok=True)
        inner_run_id = f"{self.run_id}/{slug}"

        # Acquire pool slot (non-blocking; best-effort)
        job_id = f"{self.run_id}-{slug}"
        if self._pool:
            try:
                self._pool.acquire(job_id)
            except Exception:
                pass

        subagent_path = _REPO_ROOT / "scripts" / "subagent.py"
        cmd = [
            sys.executable, str(subagent_path),
            skill, prompt,
            "--background",
            "--run-id", inner_run_id,
            "--job-id", job_id,
            "--parent-run-id", self.run_id,
        ]
        if worker.get("session_id"):
            cmd.extend(["--session-id", worker["session_id"]])

        stdout_log = run_dir / "stdout.log"
        stderr_log = run_dir / "stderr.log"

        proc_env = dict(os.environ)
        proc_env["PARENT_RUN_ID"] = self.run_id
        proc_env["PARENT_RUN_DIR"] = str(_run_dir(self.run_id))

        try:
            with open(stdout_log, "w", encoding="utf-8") as fout, \
                 open(stderr_log, "w", encoding="utf-8") as ferr:
                proc = subprocess.Popen(
                    cmd,
                    stdout=fout,
                    stderr=ferr,
                    env=proc_env,
                )
            self._procs[slug] = proc
            return proc.pid
        except Exception as exc:
            # Write failed status
            _write_json_atomic(run_dir / "status.json", {
                "state": "failed",
                "slug": slug,
                "error": str(exc),
                "started_at": _now_iso(),
                "ended_at": _now_iso(),
            })
            return None  # C4 fix (wave-3.x review): None signals failure, 0 would be truthy under `is not None`

    def is_worker_alive(self, slug: str) -> bool:
        """Return True if the worker process is still running."""
        proc = self._procs.get(slug)
        if proc is None:
            # Check status.json
            status_path = _worker_dir(self.run_id, slug) / "status.json"
            status = _read_json_safe(status_path)
            if status:
                return status.get("state") not in ("done", "failed", "cancelled")
            return False
        return proc.poll() is None

    def collect_log(self, slug: str) -> str:
        """Return last 100 lines of worker stdout.log."""
        log_path = _worker_dir(self.run_id, slug) / "stdout.log"
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            return "\n".join(lines[-100:])
        except Exception:
            return ""

    def kill_worker(self, slug: str) -> None:
        """Terminate a worker process."""
        proc = self._procs.get(slug)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
        # Release pool slot
        if self._pool:
            try:
                self._pool.release(f"{self.run_id}-{slug}")
            except Exception:
                pass


class _TmuxWorkerHost:
    """Worker host that uses a _TmuxSession for each worker window."""

    def __init__(self, run_id: str, session: _TmuxSession) -> None:
        self.run_id = run_id
        self.session = session

    def launch(self, worker: dict) -> int:
        """Spawn worker in a new tmux window. Returns 0 (no PID for tmux processes)."""
        slug = worker["slug"]
        skill = worker.get("skill", "ralph")
        prompt = worker.get("prompt", f"Execute task for team worker {slug}")
        run_dir = _worker_dir(self.run_id, slug)
        run_dir.mkdir(parents=True, exist_ok=True)
        worktree_path = worker.get("worktree_path", str(_REPO_ROOT))

        inner_run_id = f"{self.run_id}/{slug}"
        job_id = f"{self.run_id}-{slug}"

        subagent_path = _REPO_ROOT / "scripts" / "subagent.py"
        stdout_log = run_dir / "stdout.log"
        stderr_log = run_dir / "stderr.log"

        # Build the command to run in the tmux window
        session_arg = ""
        if worker.get("session_id"):
            session_arg = f"--session-id {worker['session_id']}"

        # shlex.quote() every user-controlled variable to prevent shell injection.
        # json.dumps() does NOT shell-escape; a prompt like "$(touch /tmp/pwned)"
        # would execute without quoting.
        cmd = (
            f"PARENT_RUN_ID={shlex.quote(self.run_id)} "
            f"PARENT_RUN_DIR={shlex.quote(str(_run_dir(self.run_id)))} "
            f"{shlex.quote(sys.executable)} {shlex.quote(str(subagent_path))} "
            f"{shlex.quote(skill)} {shlex.quote(prompt)} "
            f"--background "
            f"--run-id {shlex.quote(inner_run_id)} "
            f"--job-id {shlex.quote(job_id)} "
            f"--parent-run-id {shlex.quote(self.run_id)} "
            f"{session_arg} "
            f"> {shlex.quote(str(stdout_log))} 2> {shlex.quote(str(stderr_log))}"
        )

        self.session.new_window(slug, worktree_path, cmd)
        return -1  # no single PID for tmux-based processes; non-falsy sentinel

    def is_worker_alive(self, slug: str) -> bool:
        """Check by examining status.json (tmux processes don't give us a PID)."""
        status_path = _worker_dir(self.run_id, slug) / "status.json"
        status = _read_json_safe(status_path)
        if status:
            return status.get("state") not in ("done", "failed", "cancelled")
        # If no status.json yet, check if window still exists
        result = subprocess.run(
            ["tmux", "list-windows", "-t", self.session.name, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
        )
        return slug in result.stdout

    def collect_log(self, slug: str) -> str:
        """Return captured pane output plus log file content."""
        try:
            pane_output = self.session.capture_pane(slug)
        except Exception:
            pane_output = ""
        log_path = _worker_dir(self.run_id, slug) / "stdout.log"
        try:
            file_output = log_path.read_text(encoding="utf-8")[-4000:]
        except Exception:
            file_output = ""
        return pane_output + "\n---\n" + file_output

    def kill_worker(self, slug: str) -> None:
        """Kill a specific worker window."""
        subprocess.run(
            ["tmux", "kill-window", "-t", f"{self.session.name}:{slug}"],
            capture_output=True,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_team(
    name: str,
    plan: dict,
    *,
    session_id: Optional[str] = None,
    use_tmux: Optional[bool] = None,
    experimental_windows: bool = False,
) -> dict:
    """Create a team run directory and write manifest + initial status.

    Returns {run_id, manifest_path, status_path, created_at}.

    plan shape:
      {
        "workers": [
          {"slug": "...", "skill": "ralph|autopilot", "prompt": "...",
           "category": "quick|deep|ultrabrain"}
        ],
        "base_branch": "main"   # optional
      }
    """
    run_id = f"team-{uuid.uuid4().hex[:12]}"
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Resolve use_tmux
    if use_tmux is None:
        if _is_windows() and not experimental_windows:
            use_tmux = False
        else:
            use_tmux = shutil.which("tmux") is not None

    # Resolve workers from plan
    workers_spec = plan.get("workers", [])
    base_branch = plan.get("base_branch", "main")
    workers = []
    for i, spec in enumerate(workers_spec):
        slug = spec.get("slug") or _slug_from_index(i)
        workers.append({
            "slug": slug,
            "skill": spec.get("skill", "ralph"),
            "prompt": spec.get("prompt", ""),
            "category": spec.get("category", "deep"),
            "worktree_path": str(
                run_dir / "workers" / slug / "worktree"
            ),
            "branch": f"team-{run_id}/{slug}",
            "run_dir": str(run_dir / "workers" / slug),
            "status": "pending",
        })

    created_at = _now_iso()
    tmux_session_name = f"omni-team-{run_id}" if use_tmux else None

    manifest = {
        "run_id": run_id,
        "name": name,
        "session_id": session_id or "",
        "created_at": created_at,
        "tmux_session": tmux_session_name,
        "use_tmux": use_tmux,
        "base_branch": base_branch,
        "workers": workers,
    }

    manifest_path = run_dir / "manifest.json"
    status_path = run_dir / "status.json"

    _write_json_atomic(manifest_path, manifest)
    _write_json_atomic(status_path, {
        "run_id": run_id,
        "state": "created",
        "created_at": created_at,
        "updated_at": created_at,
        "worker_count": len(workers),
    })

    # Write MCP state (best-effort)
    _mcp_write_best_effort("team", {
        "run_id": run_id,
        "name": name,
        "state": "created",
        "use_tmux": use_tmux,
        "worker_count": len(workers),
    }, session_id)

    return {
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "status_path": str(status_path),
        "created_at": created_at,
    }


def dispatch_workers(run_id: str, plan: dict) -> list[dict]:
    """Spawn workers per manifest; each worker gets a worktree + slug.

    Reads the manifest from the run-dir. Creates git worktrees for each worker,
    then launches via the appropriate host (tmux or subprocess).

    Returns list of job dicts: {slug, pid, status_path, worktree_path, branch}.
    """
    manifest_path = _run_dir(run_id) / "manifest.json"
    manifest = _read_json_safe(manifest_path)
    if manifest is None:
        raise RuntimeError(f"manifest.json not found for run {run_id}")

    workers = manifest.get("workers", [])
    use_tmux = manifest.get("use_tmux", False)
    base_branch = manifest.get("base_branch", plan.get("base_branch", "main"))
    session_id = manifest.get("session_id") or None

    # Build host
    tmux_session: Optional[_TmuxSession] = None
    if use_tmux:
        tmux_name = manifest.get("tmux_session") or f"omni-team-{run_id}"
        try:
            tmux_session = _TmuxSession.create(tmux_name)
            host: _TmuxWorkerHost | _SubprocessWorkerHost = _TmuxWorkerHost(run_id, tmux_session)
        except RuntimeError:
            # Fall back to subprocess
            use_tmux = False
            host = _SubprocessWorkerHost(run_id)
    else:
        host = _SubprocessWorkerHost(run_id)

    # Load worktree module
    worktree_mod = _load_worktree_mod()

    jobs: list[dict] = []
    updated_workers = []

    for worker in workers:
        slug = worker["slug"]
        worker_dir = _worker_dir(run_id, slug)
        worker_dir.mkdir(parents=True, exist_ok=True)

        # Write initial worker status
        worker_status_path = worker_dir / "status.json"
        _write_json_atomic(worker_status_path, {
            "state": "pending",
            "slug": slug,
            "run_id": run_id,
            "started_at": None,
            "ended_at": None,
        })

        # Create worktree
        worktree_path_str = worker.get("worktree_path", str(worker_dir / "worktree"))
        if worktree_mod is not None:
            try:
                wt_info = worktree_mod.add(run_id, slug, base_branch)
                worktree_path_str = wt_info["worktree_path"]
                worker["branch"] = wt_info["branch"]
                worker["worktree_path"] = worktree_path_str
            except Exception as exc:
                # Non-fatal: worker can still run in repo root
                worktree_path_str = str(_REPO_ROOT)

        # Inject session_id and worktree_path into worker spec for host
        worker["session_id"] = session_id

        # Launch worker
        pid = host.launch(worker)

        # pid=-1 means tmux-mode (no single PID, but launch succeeded).
        # pid=None means launch failed.
        launch_ok = pid is not None
        worker_status = {
            "state": "running" if launch_ok else "failed",
            "slug": slug,
            "run_id": run_id,
            "pid": pid if (pid is not None and pid > 0) else None,
            "started_at": _now_iso(),
            "ended_at": None,
        }
        _write_json_atomic(worker_status_path, worker_status)

        worker["status"] = "running" if launch_ok else "failed"

        # Write MCP state for this worker
        _mcp_write_best_effort(f"team.{slug}", {
            "run_id": run_id,
            "slug": slug,
            "skill": worker.get("skill", "ralph"),
            "state": worker["status"],
        }, session_id)

        jobs.append({
            "slug": slug,
            "pid": pid,
            "status_path": str(worker_status_path),
            "worktree_path": worktree_path_str,
            "branch": worker.get("branch", ""),
        })
        updated_workers.append(worker)

    # Update manifest with real paths + statuses
    manifest["workers"] = updated_workers
    manifest["use_tmux"] = use_tmux
    _write_json_atomic(manifest_path, manifest)

    # Update team status
    _write_json_atomic(_run_dir(run_id) / "status.json", {
        "run_id": run_id,
        "state": "dispatched",
        "created_at": manifest.get("created_at"),
        "updated_at": _now_iso(),
        "worker_count": len(workers),
        "dispatched_count": len(jobs),
    })

    return jobs


def collect_results(run_id: str, *, timeout: int = 3600) -> dict:
    """Block until all workers reach terminal state; aggregate results.

    Uses wait_for_jobs poller. Returns aggregated summary dict.
    """
    run_dir = _run_dir(run_id)
    manifest = _read_json_safe(run_dir / "manifest.json")
    if manifest is None:
        raise RuntimeError(f"manifest.json not found for run {run_id}")

    workers = manifest.get("workers", [])
    status_paths = [
        run_dir / "workers" / w["slug"] / "status.json"
        for w in workers
    ]
    # Filter to existing paths
    status_paths = [p for p in status_paths if p.exists()]

    if not status_paths:
        return {
            "run_id": run_id,
            "state": "done",
            "workers": [],
            "summary": "no workers to collect",
        }

    # Use wait_for_jobs poller
    wait_mod = _load_wait_mod()
    if wait_mod:
        rc = wait_mod.wait_for_jobs(
            status_paths,
            timeout=float(timeout),
            poll_interval=1.0,
        )
    else:
        # Inline polling fallback
        rc = _poll_status_paths(status_paths, timeout=timeout)

    # Aggregate results
    results = []
    any_failed = False
    for w in workers:
        slug = w["slug"]
        status_path = run_dir / "workers" / slug / "status.json"
        status = _read_json_safe(status_path) or {}
        state = status.get("state", "unknown")
        if state in ("failed", "cancelled"):
            any_failed = True
        log_path = run_dir / "workers" / slug / "stdout.log"
        log_tail = ""
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            log_tail = "\n".join(lines[-20:])
        except Exception:
            pass
        results.append({
            "slug": slug,
            "state": state,
            "log_tail": log_tail,
        })

    final_state = "failed" if any_failed else "done"
    _write_json_atomic(run_dir / "status.json", {
        "run_id": run_id,
        "state": final_state,
        "created_at": manifest.get("created_at"),
        "updated_at": _now_iso(),
        "worker_count": len(workers),
        "rc": rc,
    })

    # Update MCP state
    session_id = manifest.get("session_id") or None
    _mcp_write_best_effort("team", {
        "run_id": run_id,
        "state": final_state,
        "worker_count": len(workers),
    }, session_id)

    return {
        "run_id": run_id,
        "state": final_state,
        "workers": results,
        "rc": rc,
    }


def cancel_team(run_id: str, *, reason: str = "user") -> None:
    """Cancel a team run.

    Writes cancel.signal at run-dir root AND into each worker run-dir.
    Workers (via subagent.py) poll PARENT_RUN_DIR/cancel.signal and stop.
    """
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        raise RuntimeError(f"run directory not found: {run_dir}")

    cancel_info = {
        "reason": reason,
        "requested_at": _now_iso(),
        "run_id": run_id,
    }
    cancel_text = json.dumps(cancel_info, indent=2)

    # Write team-root cancel.signal
    (run_dir / "cancel.signal").write_text(cancel_text, encoding="utf-8")

    # Read manifest to find workers
    manifest = _read_json_safe(run_dir / "manifest.json") or {}
    workers = manifest.get("workers", [])

    # Write cancel.signal into each worker run-dir
    for w in workers:
        slug = w["slug"]
        worker_dir = _worker_dir(run_id, slug)
        worker_dir.mkdir(parents=True, exist_ok=True)
        (worker_dir / "cancel.signal").write_text(cancel_text, encoding="utf-8")

        # Update worker status to cancelled if still running
        status_path = worker_dir / "status.json"
        status = _read_json_safe(status_path) or {}
        if status.get("state") not in ("done", "failed", "cancelled"):
            status["state"] = "cancelled"
            status["ended_at"] = _now_iso()
            status["cancel_reason"] = reason
            _write_json_atomic(status_path, status)

    # Update team status
    _write_json_atomic(run_dir / "status.json", {
        "run_id": run_id,
        "state": "cancelled",
        "cancelled_at": _now_iso(),
        "cancel_reason": reason,
        "updated_at": _now_iso(),
        "worker_count": len(workers),
    })

    # Kill tmux session if present
    manifest_data = manifest
    tmux_session_name = manifest_data.get("tmux_session")
    if tmux_session_name and shutil.which("tmux"):
        session = _TmuxSession(tmux_session_name)
        if session.is_alive():
            session.kill()

    # Update MCP state
    session_id = manifest_data.get("session_id") or None
    _mcp_write_best_effort("team", {
        "run_id": run_id,
        "state": "cancelled",
        "cancel_reason": reason,
    }, session_id)


def cleanup_team(run_id: str, *, force: bool = False) -> dict:
    """Remove worktrees, clear transient state. Keep logs for archaeology.

    Returns summary dict with removed_worktrees, errors.
    """
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return {"run_id": run_id, "removed_worktrees": [], "errors": [],
                "message": "run dir not found — nothing to clean"}

    manifest = _read_json_safe(run_dir / "manifest.json") or {}
    workers = manifest.get("workers", [])

    removed_worktrees: list[str] = []
    errors: list[str] = []

    worktree_mod = _load_worktree_mod()

    for w in workers:
        slug = w["slug"]
        try:
            if worktree_mod:
                result = worktree_mod.remove(run_id, slug, force=force)
                if result.get("removed"):
                    removed_worktrees.append(result.get("worktree_path", slug))
            else:
                # Fallback: manually remove the worktree dir
                wt_path = run_dir / "workers" / slug / "worktree"
                if wt_path.exists():
                    import shutil as _shutil
                    _shutil.rmtree(str(wt_path), ignore_errors=True)
                    removed_worktrees.append(str(wt_path))
        except Exception as exc:
            if force:
                errors.append(f"{slug}: {exc} (ignored, force=True)")
            else:
                errors.append(f"{slug}: {exc}")

    # Kill tmux session if present
    tmux_session_name = manifest.get("tmux_session")
    if tmux_session_name and shutil.which("tmux"):
        try:
            session = _TmuxSession(tmux_session_name)
            if session.is_alive():
                session.kill()
        except Exception as exc:
            errors.append(f"tmux kill: {exc}")

    # Update team status to cleaned
    _write_json_atomic(run_dir / "status.json", {
        "run_id": run_id,
        "state": "cleaned",
        "cleaned_at": _now_iso(),
        "updated_at": _now_iso(),
    })

    # Clear MCP state (best-effort)
    session_id = manifest.get("session_id") or None
    _mcp_write_best_effort("team", {
        "run_id": run_id,
        "state": "cleaned",
    }, session_id)
    for w in workers:
        slug = w["slug"]
        _mcp_write_best_effort(f"team.{slug}", {
            "run_id": run_id,
            "slug": slug,
            "state": "cleaned",
        }, session_id)

    return {
        "run_id": run_id,
        "removed_worktrees": removed_worktrees,
        "errors": errors,
        "message": f"cleanup complete: {len(removed_worktrees)} worktrees removed",
    }


def status_team(run_id: str) -> dict:
    """Return current team status including per-worker status."""
    run_dir = _run_dir(run_id)
    if not run_dir.exists():
        return {"run_id": run_id, "error": "run dir not found"}

    team_status = _read_json_safe(run_dir / "status.json") or {}
    manifest = _read_json_safe(run_dir / "manifest.json") or {}
    workers = manifest.get("workers", [])

    worker_statuses = []
    for w in workers:
        slug = w["slug"]
        ws_path = _worker_dir(run_id, slug) / "status.json"
        ws = _read_json_safe(ws_path) or {}
        worker_statuses.append({
            "slug": slug,
            "skill": w.get("skill", "ralph"),
            "state": ws.get("state", "unknown"),
            "started_at": ws.get("started_at"),
            "ended_at": ws.get("ended_at"),
        })

    return {
        "run_id": run_id,
        "name": manifest.get("name", ""),
        "state": team_status.get("state", "unknown"),
        "created_at": manifest.get("created_at"),
        "updated_at": team_status.get("updated_at"),
        "use_tmux": manifest.get("use_tmux", False),
        "workers": worker_statuses,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_worktree_mod():
    """Dynamically import omni_worktree (best-effort)."""
    wt_path = _REPO_ROOT / "scripts" / "omni_worktree.py"
    if not wt_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("omni_worktree", wt_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


def _load_wait_mod():
    """Dynamically import wait_for_jobs (best-effort)."""
    wj_path = _REPO_ROOT / "scripts" / "wait_for_jobs.py"
    if not wj_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("wait_for_jobs", wj_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


def _poll_status_paths(status_paths: list[Path], *, timeout: int = 3600) -> int:
    """Inline polling fallback when wait_for_jobs is unavailable."""
    terminal = frozenset({"done", "failed", "cancelled"})
    deadline = time.monotonic() + timeout
    pending = set(str(p) for p in status_paths)
    while pending and time.monotonic() < deadline:
        for path_str in list(pending):
            st = _read_json_safe(Path(path_str))
            if st and st.get("state") in terminal:
                pending.discard(path_str)
        if pending:
            time.sleep(1.0)
    if pending:
        return 124  # timeout
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_create(args: argparse.Namespace) -> int:
    plan: dict = {}
    if args.plan:
        plan_path = Path(args.plan)
        if plan_path.exists():
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"error: could not read plan file {args.plan}: {exc}", file=sys.stderr)
                return 1
        else:
            print(f"error: plan file not found: {args.plan}", file=sys.stderr)
            return 1

    result = create_team(
        args.name,
        plan,
        session_id=getattr(args, "session_id", None),
    )
    print(json.dumps(result, indent=2))
    return 0


def _cmd_dispatch(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.run_id)
    manifest = _read_json_safe(run_dir / "manifest.json")
    plan: dict = {}
    if manifest:
        plan = {"base_branch": manifest.get("base_branch", "main"),
                "workers": manifest.get("workers", [])}
    result = dispatch_workers(args.run_id, plan)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    timeout = getattr(args, "timeout", 3600)
    result = collect_results(args.run_id, timeout=int(timeout))
    print(json.dumps(result, indent=2))
    return 0 if result.get("state") == "done" else 1


def _cmd_cancel(args: argparse.Namespace) -> int:
    reason = getattr(args, "reason", "user") or "user"
    cancel_team(args.run_id, reason=reason)
    print(json.dumps({"run_id": args.run_id, "cancelled": True, "reason": reason}))
    return 0


def _cmd_cleanup(args: argparse.Namespace) -> int:
    force = getattr(args, "force", False)
    result = cleanup_team(args.run_id, force=force)
    print(json.dumps(result, indent=2))
    return 0 if not result.get("errors") else 1


def _cmd_status(args: argparse.Namespace) -> int:
    result = status_team(args.run_id)
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omni_team.py",
        description="WS6 team orchestrator — manage multi-worker team runs",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    create_p = sub.add_parser("create", help="Create a new team run")
    create_p.add_argument("name", help="Team name")
    create_p.add_argument("--plan", metavar="PLAN_JSON",
                          help="Path to plan JSON file")
    create_p.add_argument("--session-id", dest="session_id", default=None,
                          help="Session ID for MCP state scoping")
    create_p.set_defaults(func=_cmd_create)

    # dispatch
    dispatch_p = sub.add_parser("dispatch", help="Dispatch workers for a team run")
    dispatch_p.add_argument("run_id", help="Team run ID")
    dispatch_p.set_defaults(func=_cmd_dispatch)

    # collect
    collect_p = sub.add_parser("collect", help="Wait for all workers to finish")
    collect_p.add_argument("run_id", help="Team run ID")
    collect_p.add_argument("--timeout", type=int, default=3600,
                           help="Timeout in seconds (default: 3600)")
    collect_p.set_defaults(func=_cmd_collect)

    # cancel
    cancel_p = sub.add_parser("cancel", help="Cancel a team run")
    cancel_p.add_argument("run_id", help="Team run ID")
    cancel_p.add_argument("--reason", default="user",
                          help="Cancellation reason (default: user)")
    cancel_p.set_defaults(func=_cmd_cancel)

    # cleanup
    cleanup_p = sub.add_parser("cleanup", help="Clean up team run (remove worktrees)")
    cleanup_p.add_argument("run_id", help="Team run ID")
    cleanup_p.add_argument("--force", action="store_true",
                           help="Force cleanup even if errors occur")
    cleanup_p.set_defaults(func=_cmd_cleanup)

    # status
    status_p = sub.add_parser("status", help="Show team run status")
    status_p.add_argument("run_id", help="Team run ID")
    status_p.set_defaults(func=_cmd_status)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
