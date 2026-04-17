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

WS5d additions
--------------
OMNI_SUBAGENT_FAKE_RESPONSE_FILE=<path>  (default: "")
    Path to a JSON file mapping agent_name → list_of_responses_in_order.
    When set (and OMNI_SUBAGENT_FAKE=1), each call to agent X pops the next
    response string from responses[X] and writes it to stdout instead of "OK".
    Responses are consumed in order; once the list is exhausted the fake falls
    back to "OK". Invocation counts are tracked in a sidecar file at
    <response_file>.counts.json (agent_name → int) using atomic writes so
    parallel invocations are safe within a single test process.

    Format of the JSON file:
    {
      "planner": ["plan text cycle 1", "plan text cycle 2"],
      "critic":  ["VERDICT: REVISE", "VERDICT: APPROVE"],
      "architect": ["arch review cycle 1"]
    }

    Each string becomes the full stdout of the fake subagent for that invocation.
    The response file is read-only; counts are written to the sidecar.

All vars are read at command-build time in _build_cmd(). They are ignored
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


# ---------------------------------------------------------------------------
# Skill vs. agent dispatcher (B1)
# ---------------------------------------------------------------------------

# Known skill names — these map to `/copilot-omni:<name>` invocations rather
# than `--agent <name>`.  ADR-0006 §2: subprocess-only composition.
_KNOWN_SKILLS: frozenset[str] = frozenset(
    {
        "ralplan",
        "ralph",
        "ralph-prd",
        "ultrawork",
        "ultraqa",
        "autopilot",
        "team",
        "deep-interview",
        "plan",
        "cancel",
    }
)

# ---------------------------------------------------------------------------
# T4 / B4 — Production guard on OMNI_SUBAGENT_FAKE
# ---------------------------------------------------------------------------
# FAKE mode is honored ONLY when running under pytest (PYTEST_CURRENT_TEST is
# set by pytest automatically) OR when OMNI_TEST_MODE=1 is explicitly set.
# If someone sets OMNI_SUBAGENT_FAKE in a real shell session without one of
# these guards, we refuse to fake and emit a loud warning instead.
_warned_fake_misuse: list = [False]


def _compute_fake() -> bool:
    if not _env_bool("OMNI_SUBAGENT_FAKE", False):
        return False
    in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    in_test_mode = _env_bool("OMNI_TEST_MODE", False)
    if in_pytest or in_test_mode:
        return True
    # FAKE set but not in a test context — refuse with loud warning (once).
    if not _warned_fake_misuse[0]:
        print(
            "WARNING: OMNI_SUBAGENT_FAKE=1 is set outside of a test context "
            "(PYTEST_CURRENT_TEST and OMNI_TEST_MODE are both unset). "
            "Fake mode REFUSED — real copilot will be invoked. "
            "Set OMNI_TEST_MODE=1 to allow fake mode in non-pytest scripts.",
            file=sys.stderr,
        )
        _warned_fake_misuse[0] = True
    return False


_FAKE: bool = _compute_fake()


def _is_fake() -> bool:
    """Re-evaluate FAKE-mode at each call site.

    Necessary because pytest sets PYTEST_CURRENT_TEST AFTER this module is
    imported, so the eager `_FAKE` constant above evaluates to False during
    the import even when running under pytest. Call sites that need the
    runtime view (rather than the import-time view) use this function.
    """
    return _compute_fake()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _omni_home() -> Path:
    root = os.environ.get("OMNI_HOME")
    if root:
        return Path(root)
    return Path.home() / ".omni"


def _current_project() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


def _load_resolver():
    """Dynamically import category_resolver from the scripts/ directory."""
    here = Path(__file__).resolve().parent
    resolver_path = here / "category_resolver.py"
    if not resolver_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "category_resolver", resolver_path
        )
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


def _mcp_memory_capture_best_effort(
    scope: str,
    content: str,
    key: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> None:
    """Write a row to MCP memory table (best-effort; never raises)."""
    try:
        import sqlite3

        db_path = _omni_home() / "omni.db"
        if not db_path.exists():
            return
        now = time.time()
        project = _current_project()
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute(
                "INSERT INTO memory(id, scope, key, content, tags, project, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    scope,
                    key,
                    content,
                    ",".join(tags or []),
                    project,
                    now,
                    now,
                ),
            )
    except Exception as exc:
        print(f"warning: MCP memory capture failed (non-fatal): {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Run-directory helpers
# ---------------------------------------------------------------------------


def _job_dir(run_id: str, job_id: str, parent_run_id: Optional[str] = None) -> Path:
    """Return path to the job directory.

    B5 (cancel cascade): if parent_run_id is set AND the agent is a known skill,
    nest the job under .omni/runs/<parent_run_id>/inner/<run-id>/<job-id>/ so that
    cancel.signal written to the outer run-dir is visible to the inner skill.
    Otherwise use the flat layout .omni/runs/<run-id>/<job-id>/.
    """
    here = Path(__file__).resolve().parent.parent
    if parent_run_id:
        return here / ".omni" / "runs" / parent_run_id / "inner" / run_id / job_id
    return here / ".omni" / "runs" / run_id / job_id


def _init_run_dir(
    run_id: str,
    job_id: str,
    agent: str,
    category: Optional[str],
    model_used: Optional[str],
    prompt: str,
    session_id: Optional[str],
    parent_run_id: Optional[str] = None,
) -> tuple[Path, dict]:
    """Create run-directory, write spec.json + initial status.json.

    Returns (job_dir, status_dict).
    """
    job_dir = _job_dir(run_id, job_id, parent_run_id=parent_run_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    spec = {
        "job_id": job_id,
        "run_id": run_id,
        "agent": agent,
        "category": category,
        "model_used": model_used,
        "session_id": session_id,
        "parent_run_id": parent_run_id,
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
    parent_run_id: Optional[str] = None,
) -> dict:
    """Spawn a subagent.

    Parameters
    ----------
    parent_run_id:
        B5 (cancel cascade): when set, the inner skill's run-dir is nested
        under the outer run-dir as .omni/runs/<parent_run_id>/inner/<agent>-<job_id>/.
        The PARENT_RUN_ID env var is passed to the inner process so it can
        check <parent_run_dir>/cancel.signal.

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
            return {
                "job_id": job_id,
                "run_id": run_id,
                "exit_code": 1,
                "error": f"unknown category: {category}",
            }
        model_used = effective_model

    if allow_all is None:
        allow_all = _env_bool("OMNI_SUBAGENT_ALLOW_ALL", False)

    # Create run-dir + write spec.json + pending status.json BEFORE spawn
    job_dir, status = _init_run_dir(
        run_id,
        job_id,
        agent,
        category,
        model_used,
        prompt,
        session_id,
        parent_run_id=parent_run_id,
    )
    status_path = str(job_dir / "status.json")

    # Acquire pool slot (best-effort; if pool unavailable, proceed anyway).
    # Phase-C C08/C26: MemoryPolicyDenied is NOT best-effort — it is a hard
    # reject that surfaces to the caller as an error result so memory caps
    # are actually enforced, not silently ignored.
    pool_mod = _load_pool()
    pool = None
    if pool_mod is not None:
        try:
            cap = pool_mod.get_cap()
            pool = pool_mod.SubagentPool(cap=cap)
            pool.acquire(job_id)
        except Exception as exc:
            mem_denied_cls = getattr(pool_mod, "MemoryPolicyDenied", None)
            if mem_denied_cls is not None and isinstance(exc, mem_denied_cls):
                status.update(
                    state="failed",
                    ended_at=_now_iso(),
                    exit_code=77,
                    error=f"memory-policy: {exc}",
                )
                _write_status(job_dir, status)
                return {
                    "job_id": job_id,
                    "run_id": run_id,
                    "exit_code": 77,
                    "error": f"memory-policy: {exc}",
                    "status_path": status_path,
                }
            print(f"warning: pool acquire failed (non-fatal): {exc}", file=sys.stderr)
            pool = None

    try:
        if background:
            return _spawn_background(
                agent,
                prompt,
                effective_model,
                allow_all,
                timeout,
                job_id,
                run_id,
                job_dir,
                status,
                status_path,
                session_id,
                pool,
                parent_run_id=parent_run_id,
            )
        else:
            return _spawn_foreground(
                agent,
                prompt,
                effective_model,
                allow_all,
                timeout,
                job_id,
                run_id,
                job_dir,
                status,
                status_path,
                session_id,
                pool,
                parent_run_id=parent_run_id,
            )
    finally:
        # For foreground: pool is released inside _spawn_foreground via try/finally
        # For background: pool release is handled by the spawned process wrapper
        pass


def _get_fake_response(agent: str) -> str:
    """Return the next scripted response for *agent* from OMNI_SUBAGENT_FAKE_RESPONSE_FILE.

    Reads the JSON response file, looks up responses[agent], pops the first
    entry, persists the updated counts to a sidecar file, and returns the
    response string.  Falls back to "OK" when the file is absent, the agent
    has no entry, or the list is exhausted.
    """
    response_file = os.environ.get("OMNI_SUBAGENT_FAKE_RESPONSE_FILE", "")
    if not response_file:
        return "OK"

    import json as _json

    rf = Path(response_file)
    if not rf.exists():
        return "OK"

    try:
        responses: dict = _json.loads(rf.read_text(encoding="utf-8"))
    except Exception:
        return "OK"

    agent_responses = responses.get(agent, [])
    if not agent_responses:
        return "OK"

    # Track invocation count via sidecar file (atomic read-modify-write)
    counts_file = rf.with_suffix(".counts.json")
    try:
        counts: dict = (
            _json.loads(counts_file.read_text(encoding="utf-8"))
            if counts_file.exists()
            else {}
        )
    except Exception:
        counts = {}

    idx = counts.get(agent, 0)
    if idx >= len(agent_responses):
        return "OK"

    response_text = agent_responses[idx]
    counts[agent] = idx + 1
    try:
        tmp = counts_file.with_suffix(".tmp")
        tmp.write_text(_json.dumps(counts, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(counts_file))
    except Exception:
        pass  # sidecar write failure is non-fatal

    return response_text


def _fake_env(agent: str) -> dict:
    """Return an os.environ copy with _F_* vars set for the fake subprocess.

    B2 fix: values are passed via environment variables, never interpolated
    into source code.
    """
    env = dict(os.environ)
    env["_F_SLEEP"] = os.environ.get("OMNI_SUBAGENT_FAKE_SLEEP_SECS", "1")
    env["_F_EXIT"] = os.environ.get("OMNI_SUBAGENT_FAKE_EXIT_CODE", "0")
    env["_F_STDERR"] = os.environ.get("OMNI_SUBAGENT_FAKE_STDERR", "")
    env["_F_STDOUT"] = _get_fake_response(agent)
    return env


def _build_cmd(
    agent: str,
    prompt: str,
    effective_model: Optional[str],
    allow_all: bool,
) -> Optional[list]:
    """Build the copilot command. Returns None if copilot not found.

    Dispatch: if *agent* is a known skill name, build
    ``copilot -p <prompt> /copilot-omni:<agent>`` (skill invocation).
    Otherwise build ``copilot -p <prompt> --agent <agent>`` (agent invocation).
    """
    # OMNI_SUBAGENT_FAKE=1: bypass real copilot, use synthetic exit.
    # B4 guard: FAKE is only honored inside pytest or when OMNI_TEST_MODE=1.
    if _is_fake():
        inline = (
            "import os, sys, time; "
            "time.sleep(float(os.environ['_F_SLEEP'])); "
            "sys.stderr.write(os.environ.get('_F_STDERR', '')); "
            "print(os.environ.get('_F_STDOUT', 'OK')); "
            "sys.exit(int(os.environ['_F_EXIT']))"
        )
        return [sys.executable, "-c", inline]

    copilot = shutil.which("copilot")
    if not copilot:
        return None

    # B1 fix: skill-vs-agent dispatcher
    if agent in _KNOWN_SKILLS:
        cmd = [copilot, "-p", prompt, f"/copilot-omni:{agent}"]
    else:
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
    pool=None,
    parent_run_id: Optional[str] = None,
) -> dict:
    """Run synchronously, tee stdout/stderr to logs + terminal."""
    cmd = _build_cmd(agent, prompt, effective_model, allow_all)
    if cmd is None:
        status.update(
            state="failed",
            ended_at=_now_iso(),
            exit_code=2,
            error="copilot CLI not found on PATH",
        )
        _write_status(job_dir, status)
        _mcp_write_best_effort(f"subagent:{job_id}", status, session_id)
        _mcp_memory_capture_best_effort(
            scope="subagent",
            content=json.dumps(
                {
                    "agent": agent,
                    "exit_code": 2,
                    "error": "copilot CLI not found on PATH"[:500],
                    "prompt_excerpt": prompt[:200],
                    "run_id": run_id,
                }
            ),
            key=f"subagent:{agent}:{run_id}",
            tags=["subagent", agent],
        )
        _release_pool_safe(pool, job_id)
        return {
            "job_id": job_id,
            "run_id": run_id,
            "exit_code": 2,
            "error": "copilot CLI not found",
            "status_path": status_path,
        }

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

    # B5: build subprocess env with PARENT_RUN_ID so inner skills can find
    # the outer cancel.signal.
    proc_env = _fake_env(agent) if _is_fake() else dict(os.environ)
    if parent_run_id:
        proc_env["PARENT_RUN_ID"] = parent_run_id
        here = Path(__file__).resolve().parent.parent
        proc_env["PARENT_RUN_DIR"] = str(here / ".omni" / "runs" / parent_run_id)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=proc_env if (_is_fake() or parent_run_id) else None,
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
    _mcp_memory_capture_best_effort(
        scope="subagent",
        content=json.dumps(
            {
                "agent": agent,
                "exit_code": exit_code,
                "error": (error_text or "")[:500],
                "prompt_excerpt": prompt[:200],
                "run_id": run_id,
            }
        ),
        key=f"subagent:{agent}:{run_id}",
        tags=["subagent", agent],
    )
    _release_pool_safe(pool, job_id)

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
    parent_run_id: Optional[str] = None,
) -> dict:
    """Spawn detached; return immediately with pid."""
    cmd = _build_cmd(agent, prompt, effective_model, allow_all)
    if cmd is None:
        status.update(
            state="failed",
            ended_at=_now_iso(),
            exit_code=2,
            error="copilot CLI not found on PATH",
        )
        _write_status(job_dir, status)
        _mcp_write_best_effort(f"subagent:{job_id}", status, session_id)
        _mcp_memory_capture_best_effort(
            scope="subagent",
            content=json.dumps(
                {
                    "agent": agent,
                    "exit_code": 2,
                    "error": "copilot CLI not found on PATH"[:500],
                    "prompt_excerpt": prompt[:200],
                    "run_id": run_id,
                }
            ),
            key=f"subagent:{agent}:{run_id}",
            tags=["subagent", agent],
        )
        if pool is not None:
            try:
                pool.release(job_id)
            except Exception:
                pass
        return {
            "job_id": job_id,
            "run_id": run_id,
            "exit_code": 2,
            "error": "copilot CLI not found",
            "status_path": status_path,
        }

    # T9: write config JSON sidecar and invoke static wrapper module.
    # This eliminates f-string interpolation of dynamic values into Python source.
    wrapper_script = _wrapper_module_path()
    here = Path(__file__).resolve().parent.parent
    config = {
        "cmd": cmd,
        "status_path": str(job_dir / "status.json"),
        "stdout_log": str(job_dir / "stdout.log"),
        "stderr_log": str(job_dir / "stderr.log"),
        "job_id": job_id,
        "run_id": run_id,
        "agent": agent,
        "session_id": session_id,
        "prompt_excerpt": prompt[:200],
        "timeout_secs": timeout,
        "scripts_dir": str(Path(__file__).resolve().parent),
        # B5: cancel cascade
        "parent_run_id": parent_run_id,
        "parent_run_dir": str(here / ".omni" / "runs" / parent_run_id)
        if parent_run_id
        else None,
    }
    config_path = job_dir / "_wrapper_config.json"
    _write_json_atomic(config_path, config)

    # B2: for fake mode, pass values via environment, not source interpolation
    # B5: pass PARENT_RUN_ID / PARENT_RUN_DIR so inner skills can check outer cancel.signal
    spawn_env = _fake_env(agent) if _is_fake() else dict(os.environ)
    if parent_run_id:
        spawn_env["PARENT_RUN_ID"] = parent_run_id
        spawn_env["PARENT_RUN_DIR"] = config["parent_run_dir"] or ""
    elif not _is_fake():
        spawn_env = None  # no override needed; inherit parent env

    # Transition status to running immediately (wrapper will update too)
    # We leave it as "pending" — the wrapper transitions to "running" when it starts.

    # Launch wrapper detached (T9: passes config_path as arg, no f-string source).
    # Phase-C C02: on Windows start_new_session is silently ignored; use
    # CREATE_NEW_PROCESS_GROUP so Ctrl-C in the parent does not cascade into
    # the background subagent, and add DETACHED_PROCESS to fully decouple.
    popen_kwargs: dict = dict(
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=spawn_env,
    )
    if sys.platform == "win32":
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen_kwargs["creationflags"] = detached | new_group
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            [sys.executable, str(wrapper_script), str(config_path)],
            **popen_kwargs,
        )
        pid = proc.pid
    except Exception as exc:
        status.update(state="failed", ended_at=_now_iso(), exit_code=1, error=str(exc))
        _write_status(job_dir, status)
        _mcp_memory_capture_best_effort(
            scope="subagent",
            content=json.dumps(
                {
                    "agent": agent,
                    "exit_code": 1,
                    "error": str(exc)[:500],
                    "prompt_excerpt": prompt[:200],
                    "run_id": run_id,
                }
            ),
            key=f"subagent:{agent}:{run_id}",
            tags=["subagent", agent],
        )
        if pool is not None:
            try:
                pool.release(job_id)
            except Exception:
                pass
        return {
            "job_id": job_id,
            "run_id": run_id,
            "exit_code": 1,
            "error": str(exc),
            "status_path": status_path,
        }

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


def _wrapper_module_path() -> Path:
    """Return path to the static wrapper module (scripts/_subagent_wrapper.py)."""
    return Path(__file__).resolve().parent / "_subagent_wrapper.py"


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
    if not _is_fake() and not copilot:
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
        result = subprocess.run(
            cmd,
            timeout=timeout,
            check=False,
            env=_fake_env(name) if _is_fake() else None,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"error: agent {name!r} timed out after {timeout}s", file=sys.stderr)
        return 124


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    # B1: --is-skill <name> subcommand — returns 0 if name is a known skill, 1 otherwise
    if len(sys.argv) == 3 and sys.argv[1] == "--is-skill":
        name = sys.argv[2]
        print("1" if name in _KNOWN_SKILLS else "0")
        return 0 if name in _KNOWN_SKILLS else 1

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
    parser.add_argument(
        "--allow-all",
        dest="allow_all",
        action="store_true",
        help="Pass --allow-all to the spawned copilot session",
    )
    parser.add_argument(
        "--no-allow-all",
        dest="allow_all",
        action="store_false",
        help="Require the spawned session to ask for permissions (default)",
    )
    parser.set_defaults(allow_all=None)
    parser.add_argument(
        "--background",
        action="store_true",
        help="Spawn detached; print {run_id, job_id, pid, status_path} to stdout and exit 0",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        dest="session_id",
        help="Session ID passed through to MCP state writes (FK to state.session_id)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        dest="run_id",
        help="Explicit run ID; if omitted, a UUID4 is generated",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        dest="job_id",
        help="Explicit job ID; if omitted, a UUID4 is generated",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--parent-run-id",
        default=None,
        dest="parent_run_id",
        help=(
            "B5 cancel cascade: outer run-id. When set, this inner skill's "
            "run-dir is nested under .omni/runs/<parent-run-id>/inner/. "
            "PARENT_RUN_ID and PARENT_RUN_DIR env vars are set in the child."
        ),
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
            parent_run_id=args.parent_run_id,
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
        parent_run_id=args.parent_run_id,
    )
    return result.get("exit_code", 1)


if __name__ == "__main__":
    sys.exit(main())
