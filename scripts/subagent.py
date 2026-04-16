#!/usr/bin/env python3
"""Subagent helper — invoke a specialized agent via `copilot -p ... --agent <name>`.

This is the Copilot-CLI equivalent of Claude Code's `Task(subagent_type=...)`.
Ported skills call this module to spawn an agent and capture its output.

WS5a additions
--------------
- background mode (--background / background=True)
- run-directory artifacts: .omni/runs/<run-id>/<job-id>/{spec.json,status.json,stdout.log,stderr.log}
- JSON status protocol with atomic os.replace writes
- pool back-pressure (subagent_pool.py)
- MCP state write (best-effort, mode="subagent")
- OMNI_SUBAGENT_FAKE=1 test hook — bypasses real copilot exec

WS5c additions (OMNI_SUBAGENT_FAKE_* env-var contract)
-------------------------------------------------------
OMNI_SUBAGENT_FAKE=1
    Bypass real copilot execution. Runs a synthetic Python one-liner instead.

OMNI_SUBAGENT_FAKE_SLEEP_SECS=<float>  (default: 1.0)
    How long the fake subagent sleeps before exiting. Keep tiny in tests (0.05).

OMNI_SUBAGENT_FAKE_EXIT_CODE=<int>  (default: 0)
    Exit code the fake subagent returns. Set to non-zero to simulate failures.
    Example: OMNI_SUBAGENT_FAKE_EXIT_CODE=1 causes the job to end in state="failed".

OMNI_SUBAGENT_FAKE_STDERR=<string>  (default: "")
    Text written to stderr by the fake subagent. Used to simulate error messages
    for same-error-signature detection in ultraqa tests.
    Example: OMNI_SUBAGENT_FAKE_STDERR="AssertionError: expected True got False"

All three vars are read at command-build time in _build_cmd(). They are ignored
when OMNI_SUBAGENT_FAKE is not set. The contract is additive: existing tests that
only set OMNI_SUBAGENT_FAKE=1 continue to work unchanged (exit_code=0, stderr="").
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off", "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _omni_home() -> Path:
    root = os.environ.get("OMNI_HOME")
    if root:
        return Path(root)
    return Path.home() / ".omni"


def _load_resolver():
    """Dynamically import category_resolver from the scripts/ directory."""
    here = Path(__file__).resolve().parent
    resolver_path = here / "category_resolver.py"
    if not resolver_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("category_resolver", resolver_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


def _load_pool():
    """Dynamically import SubagentPool from subagent_pool.py (best-effort)."""
    here = Path(__file__).resolve().parent
    pool_path = here / "subagent_pool.py"
    if not pool_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("subagent_pool", pool_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception:
        return None


def _resolve_category(category: str) -> Optional[str]:
    """Resolve a semantic category to a concrete model string."""
    resolver = _load_resolver()
    if resolver is None:
        print(
            f"warning: category_resolver not found; ignoring --category {category!r}",
            file=sys.stderr,
        )
        return None
    known = resolver.known_categories()
    if category not in known:
        print(
            f"error: unknown category '{category}'. Known: {', '.join(sorted(known))}",
            file=sys.stderr,
        )
        return None
    res = resolver.resolve(category)
    return res["model"]


def _write_json_atomic(path: Path, data: dict) -> None:
    """Atomically write JSON to path using a temp file + os.replace."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _write_status(job_dir: Path, status_dict: dict) -> None:
    """Write status.json to the job directory atomically."""
    _write_json_atomic(job_dir / "status.json", status_dict)


def _mcp_write_best_effort(mode: str, body: dict, session_id: Optional[str]) -> None:
    """Write a row to MCP state table (best-effort; never raises)."""
    try:
        here = Path(__file__).resolve().parent
        server_path = here.parent / "mcp" / "server.py"
        if not server_path.exists():
            return
        # Use subprocess to call the MCP write tool via stdin JSON-RPC
        # This is best-effort; if it fails we log and continue.
        # We use a direct sqlite3 write approach to avoid JSON-RPC overhead.
        import sqlite3
        home = _omni_home()
        db_path = home / "omni.db"
        if not db_path.exists():
            return
        body_str = json.dumps(body)
        now = time.time()
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            # Use UPSERT by mode key — session_id column added in SCHEMA_VERSION=2
            try:
                conn.execute(
                    "INSERT INTO state(mode, body, session_id, updated_at)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, session_id=excluded.session_id,"
                    " updated_at=excluded.updated_at",
                    (mode, body_str, session_id, now),
                )
            except Exception:
                # Fallback: without session_id column (older schema)
                conn.execute(
                    "INSERT INTO state(mode, body, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(mode) DO UPDATE SET"
                    " body=excluded.body, updated_at=excluded.updated_at",
                    (mode, body_str, now),
                )
    except Exception as exc:
        print(f"warning: MCP state write failed (non-fatal): {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Run-directory helpers
# ---------------------------------------------------------------------------


def _job_dir(run_id: str, job_id: str) -> Path:
    """Return path to .omni/runs/<run-id>/<job-id>/"""
    here = Path(__file__).resolve().parent.parent
    return here / ".omni" / "runs" / run_id / job_id


def _init_run_dir(
    run_id: str,
    job_id: str,
    agent: str,
    category: Optional[str],
    model_used: Optional[str],
    prompt: str,
    session_id: Optional[str],
) -> tuple[Path, dict]:
    """Create run-directory, write spec.json + initial status.json.

    Returns (job_dir, status_dict).
    """
    job_dir = _job_dir(run_id, job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    spec = {
        "job_id": job_id,
        "run_id": run_id,
        "agent": agent,
        "category": category,
        "model_used": model_used,
        "session_id": session_id,
        "prompt_excerpt": prompt[:200],
    }
    _write_json_atomic(job_dir / "spec.json", spec)

    status: dict = {
        "job_id": job_id,
        "run_id": run_id,
        "agent": agent,
        "category": category,
        "state": "pending",
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "error": None,
        "model_used": model_used,
        "prompt_excerpt": prompt[:200],
    }
    _write_status(job_dir, status)
    return job_dir, status


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def spawn(
    agent: str,
    prompt: str,
    *,
    category: Optional[str] = None,
    model: Optional[str] = None,
    allow_all: Optional[bool] = None,
    background: bool = False,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    job_id: Optional[str] = None,
    timeout: int = 1800,
) -> dict:
    """Spawn a subagent.

    Returns:
    - foreground: {job_id, run_id, exit_code, stdout, stderr, status_path}
    - background: {job_id, run_id, pid, status_path} (returns immediately)
    """
    run_id = run_id or str(uuid.uuid4())
    job_id = job_id or str(uuid.uuid4())

    # Resolve model
    effective_model = model
    model_used: Optional[str] = model
    if effective_model is None and category is not None:
        effective_model = _resolve_category(category)
        if effective_model is None:
            return {"job_id": job_id, "run_id": run_id, "exit_code": 1,
                    "error": f"unknown category: {category}"}
        model_used = effective_model

    if allow_all is None:
        allow_all = _env_bool("OMNI_SUBAGENT_ALLOW_ALL", False)

    # Create run-dir + write spec.json + pending status.json BEFORE spawn
    job_dir, status = _init_run_dir(
        run_id, job_id, agent, category, model_used, prompt, session_id
    )
    status_path = str(job_dir / "status.json")

    # Acquire pool slot (best-effort; if pool unavailable, proceed anyway)
    pool_mod = _load_pool()
    pool = None
    if pool_mod is not None:
        try:
            cap = pool_mod.get_cap()
            pool = pool_mod.SubagentPool(cap=cap)
            pool.acquire(job_id)
        except Exception as exc:
            print(f"warning: pool acquire failed (non-fatal): {exc}", file=sys.stderr)
            pool = None

    try:
        if background:
            return _spawn_background(
                agent, prompt, effective_model, allow_all, timeout,
                job_id, run_id, job_dir, status, status_path, session_id, pool
            )
        else:
            return _spawn_foreground(
                agent, prompt, effective_model, allow_all, timeout,
                job_id, run_id, job_dir, status, status_path, session_id
            )
    finally:
        # For foreground: pool is released inside _spawn_foreground
        # For background: pool release is handled by the spawned process wrapper
        # If background, we already returned above so this only runs on exception path
        pass


def _build_cmd(
    agent: str,
    prompt: str,
    effective_model: Optional[str],
    allow_all: bool,
) -> Optional[list]:
    """Build the copilot command. Returns None if copilot not found."""
    # OMNI_SUBAGENT_FAKE=1: bypass real copilot, use synthetic exit
    if _env_bool("OMNI_SUBAGENT_FAKE", False):
        sleep_secs = float(os.environ.get("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "1"))
        exit_code = int(os.environ.get("OMNI_SUBAGENT_FAKE_EXIT_CODE", "0"))
        fake_stderr = os.environ.get("OMNI_SUBAGENT_FAKE_STDERR", "")
        # Build a one-liner: sleep, optionally write stderr, then exit
        stderr_part = ""
        if fake_stderr:
            escaped = fake_stderr.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            stderr_part = f"import sys; sys.stderr.write('{escaped}\\n'); "
        return [sys.executable, "-c",
                f"import time; time.sleep({sleep_secs}); {stderr_part}print('OK'); exit({exit_code})"]

    copilot = shutil.which("copilot")
    if not copilot:
        return None

    cmd = [copilot, "-p", prompt, "--agent", agent]
    if allow_all:
        cmd.append("--allow-all")
    if effective_model:
        cmd.extend(["--model", effective_model])
    return cmd


def _spawn_foreground(
    agent: str,
    prompt: str,
    effective_model: Optional[str],
    allow_all: bool,
    timeout: int,
    job_id: str,
    run_id: str,
    job_dir: Path,
    status: dict,
    status_path: str,
    session_id: Optional[str],
) -> dict:
    """Run synchronously, tee stdout/stderr to logs + terminal."""
    pool_mod = _load_pool()

    cmd = _build_cmd(agent, prompt, effective_model, allow_all)
    if cmd is None:
        status.update(state="failed", ended_at=_now_iso(), exit_code=2,
                      error="copilot CLI not found on PATH")
        _write_status(job_dir, status)
        _mcp_write_best_effort(f"subagent:{job_id}", status, session_id)
        _release_pool_safe(pool_mod, job_id)
        return {"job_id": job_id, "run_id": run_id, "exit_code": 2,
                "error": "copilot CLI not found", "status_path": status_path}

    # Transition: pending → running
    started_at = _now_iso()
    status.update(state="running", started_at=started_at)
    _write_status(job_dir, status)
    _mcp_write_best_effort(f"subagent:{job_id}", status, session_id)

    stdout_log = job_dir / "stdout.log"
    stderr_log = job_dir / "stderr.log"
    collected_stdout: list[str] = []
    collected_stderr: list[str] = []
    exit_code = 1
    error_text: Optional[str] = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Tee stdout/stderr: relay to terminal AND write to log files
        def _relay(pipe, log_path: Path, collect: list, dest_stream):
            with open(log_path, "w", encoding="utf-8") as f:
                for line in pipe:
                    dest_stream.write(line)
                    dest_stream.flush()
                    f.write(line)
                    collect.append(line)

        t_out = threading.Thread(
            target=_relay,
            args=(proc.stdout, stdout_log, collected_stdout, sys.stdout),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_relay,
            args=(proc.stderr, stderr_log, collected_stderr, sys.stderr),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            error_text = f"agent {agent!r} timed out after {timeout}s"
            print(f"error: {error_text}", file=sys.stderr)

        t_out.join()
        t_err.join()
        exit_code = proc.returncode if error_text is None else 124

    except Exception as exc:
        error_text = str(exc)
        exit_code = 1

    # Transition: running → done|failed
    ended_at = _now_iso()
    final_state = "done" if exit_code == 0 else "failed"
    status.update(
        state=final_state,
        ended_at=ended_at,
        exit_code=exit_code,
        error=error_text,
    )
    _write_status(job_dir, status)
    _mcp_write_best_effort(f"subagent:{job_id}", status, session_id)
    _release_pool_safe(pool_mod, job_id)

    return {
        "job_id": job_id,
        "run_id": run_id,
        "exit_code": exit_code,
        "stdout": "".join(collected_stdout),
        "stderr": "".join(collected_stderr),
        "status_path": status_path,
    }


def _spawn_background(
    agent: str,
    prompt: str,
    effective_model: Optional[str],
    allow_all: bool,
    timeout: int,
    job_id: str,
    run_id: str,
    job_dir: Path,
    status: dict,
    status_path: str,
    session_id: Optional[str],
    pool,
) -> dict:
    """Spawn detached; return immediately with pid."""
    cmd = _build_cmd(agent, prompt, effective_model, allow_all)
    if cmd is None:
        status.update(state="failed", ended_at=_now_iso(), exit_code=2,
                      error="copilot CLI not found on PATH")
        _write_status(job_dir, status)
        _mcp_write_best_effort(f"subagent:{job_id}", status, session_id)
        if pool is not None:
            try:
                pool.release(job_id)
            except Exception:
                pass
        return {"job_id": job_id, "run_id": run_id, "exit_code": 2,
                "error": "copilot CLI not found", "status_path": status_path}

    # Write a small wrapper script into the run-dir that:
    # 1. Updates status to running
    # 2. Runs the real command
    # 3. Updates status to done/failed
    # 4. Releases the pool slot
    wrapper_script = job_dir / "_wrapper.py"
    cmd_json = json.dumps(cmd)
    status_json_path = str(job_dir / "status.json")
    stdout_log_path = str(job_dir / "stdout.log")
    stderr_log_path = str(job_dir / "stderr.log")

    wrapper_src = f"""\
#!/usr/bin/env python3
import json, os, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _write_json_atomic(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        f.write(json.dumps(data, indent=2))
    os.replace(tmp, str(path))

status_path = {status_json_path!r}
stdout_log = {stdout_log_path!r}
stderr_log = {stderr_log_path!r}
cmd = {cmd_json}
job_id = {job_id!r}
run_id = {run_id!r}
agent = {agent!r}
session_id = {session_id!r}
timeout_secs = {timeout}
pool_dir = {str(job_dir.parent.parent.parent / "locks")!r}

# Load current status
with open(status_path) as f:
    status = json.load(f)

# running
status.update(state="running", started_at=_now_iso())
_write_json_atomic(status_path, status)

exit_code = 1
error_text = None
try:
    with open(stdout_log, "w") as fout, open(stderr_log, "w") as ferr:
        proc = subprocess.run(cmd, stdout=fout, stderr=ferr,
                               timeout=timeout_secs, check=False)
    exit_code = proc.returncode
except subprocess.TimeoutExpired:
    error_text = f"agent timed out after {{timeout_secs}}s"
    exit_code = 124
except Exception as e:
    error_text = str(e)
    exit_code = 1

final_state = "done" if exit_code == 0 else "failed"
status.update(state=final_state, ended_at=_now_iso(),
              exit_code=exit_code, error=error_text)
_write_json_atomic(status_path, status)

# Release pool slot
try:
    here = Path(__file__).resolve().parent.parent.parent / "scripts"
    pool_path = here / "subagent_pool.py"
    if pool_path.exists():
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("subagent_pool", str(pool_path))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        p = mod.SubagentPool(cap=mod.get_cap())
        p.release(job_id)
except Exception:
    pass
"""

    wrapper_script.write_text(wrapper_src, encoding="utf-8")

    # Transition status to running immediately (wrapper will update too)
    # We leave it as "pending" — the wrapper transitions to "running" when it starts.

    # Launch wrapper detached
    try:
        proc = subprocess.Popen(
            [sys.executable, str(wrapper_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        pid = proc.pid
    except Exception as exc:
        status.update(state="failed", ended_at=_now_iso(), exit_code=1,
                      error=str(exc))
        _write_status(job_dir, status)
        if pool is not None:
            try:
                pool.release(job_id)
            except Exception:
                pass
        return {"job_id": job_id, "run_id": run_id, "exit_code": 1,
                "error": str(exc), "status_path": status_path}

    # Pool release for background: wrapper handles it on exit.
    # Parent atexit: release if parent dies before wrapper finishes.
    if pool is not None:
        import atexit
        atexit.register(_release_pool_safe, pool, job_id)

    return {
        "job_id": job_id,
        "run_id": run_id,
        "pid": pid,
        "status_path": status_path,
    }


def _release_pool_safe(pool_or_mod, job_id: str) -> None:
    """Release pool slot, ignoring all errors."""
    if pool_or_mod is None:
        return
    try:
        if hasattr(pool_or_mod, "release"):
            pool_or_mod.release(job_id)
        elif hasattr(pool_or_mod, "SubagentPool"):
            p = pool_or_mod.SubagentPool(cap=pool_or_mod.get_cap())
            p.release(job_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Legacy API (kept for backward compat with WS4 tests)
# ---------------------------------------------------------------------------


def run_agent(
    name: str,
    prompt: str,
    allow_all: Optional[bool] = None,
    model: Optional[str] = None,
    category: Optional[str] = None,
    timeout: int = 1800,
) -> int:
    """Invoke a Copilot subagent (legacy foreground-only API).

    Category resolution
    -------------------
    If *category* is given and *model* is not, the category is resolved to a
    concrete model via category_resolver.resolve() and passed as --model.
    If both *category* and *model* are given, *model* wins.
    """
    copilot = shutil.which("copilot")
    if not _env_bool("OMNI_SUBAGENT_FAKE", False) and not copilot:
        print("error: `copilot` CLI not found on PATH", file=sys.stderr)
        return 2
    if allow_all is None:
        allow_all = _env_bool("OMNI_SUBAGENT_ALLOW_ALL", False)

    effective_model = model
    if effective_model is None and category is not None:
        effective_model = _resolve_category(category)
        if effective_model is None:
            return 1

    cmd = _build_cmd(name, prompt, effective_model, bool(allow_all))
    if cmd is None:
        print("error: `copilot` CLI not found on PATH", file=sys.stderr)
        return 2

    try:
        result = subprocess.run(cmd, timeout=timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"error: agent {name!r} timed out after {timeout}s", file=sys.stderr)
        return 124


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Copilot Omni subagent")
    parser.add_argument("name", help="Agent name (matches agents/<name>.md)")
    parser.add_argument("prompt", help="Task prompt to send the agent")
    parser.add_argument(
        "--model",
        default=None,
        help="Concrete model name to pass to copilot --model. Overrides --category.",
    )
    parser.add_argument(
        "--category",
        default=None,
        metavar="CATEGORY",
        help=(
            "Semantic model category (quick|deep|ultrabrain). "
            "Resolved to a concrete model via category_resolver. "
            "Ignored when --model is also given."
        ),
    )
    parser.add_argument("--allow-all", dest="allow_all", action="store_true",
                        help="Pass --allow-all to the spawned copilot session")
    parser.add_argument("--no-allow-all", dest="allow_all", action="store_false",
                        help="Require the spawned session to ask for permissions (default)")
    parser.set_defaults(allow_all=None)
    parser.add_argument(
        "--background", action="store_true",
        help="Spawn detached; print {run_id, job_id, pid, status_path} to stdout and exit 0",
    )
    parser.add_argument(
        "--session-id", default=None, dest="session_id",
        help="Session ID passed through to MCP state writes (FK to state.session_id)",
    )
    parser.add_argument(
        "--run-id", default=None, dest="run_id",
        help="Explicit run ID; if omitted, a UUID4 is generated",
    )
    parser.add_argument(
        "--job-id", default=None, dest="job_id",
        help="Explicit job ID; if omitted, a UUID4 is generated",
    )
    parser.add_argument(
        "--timeout", type=int, default=1800,
        help="Timeout in seconds (default: 1800)",
    )
    args = parser.parse_args()

    if args.background:
        result = spawn(
            args.name,
            args.prompt,
            category=args.category,
            model=args.model,
            allow_all=args.allow_all,
            background=True,
            session_id=args.session_id,
            run_id=args.run_id,
            job_id=args.job_id,
            timeout=args.timeout,
        )
        print(json.dumps(result))
        return 0 if "error" not in result else 1

    result = spawn(
        args.name,
        args.prompt,
        category=args.category,
        model=args.model,
        allow_all=args.allow_all,
        background=False,
        session_id=args.session_id,
        run_id=args.run_id,
        job_id=args.job_id,
        timeout=args.timeout,
    )
    return result.get("exit_code", 1)


if __name__ == "__main__":
    sys.exit(main())
