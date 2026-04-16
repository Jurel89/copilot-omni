#!/usr/bin/env python3
"""Static background-job wrapper for subagent.py (WS5a/T9).

Reads all job configuration from a JSON sidecar file passed as the first
command-line argument.  This eliminates f-string interpolation of dynamic
values into Python source code.

Usage (internal — called by subagent._spawn_background):
    python3 scripts/_subagent_wrapper.py <job_dir>/_wrapper_config.json

Config JSON schema:
    {
        "cmd":          list[str],   # command to run
        "status_path":  str,         # path to status.json
        "stdout_log":   str,         # path to stdout.log
        "stderr_log":   str,         # path to stderr.log
        "job_id":       str,
        "run_id":       str,
        "agent":        str,
        "session_id":   str | null,
        "timeout_secs": int,
        "scripts_dir":  str          # path to scripts/ directory
    }

For OMNI_SUBAGENT_FAKE mode the invoker sets _F_SLEEP/_F_STDERR/_F_STDOUT/_F_EXIT
env vars; the cmd already contains the inline Python that reads those vars.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2))
    os.replace(tmp, path)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: _subagent_wrapper.py <config.json>", file=sys.stderr)
        return 1

    config_path = sys.argv[1]
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as exc:
        print(f"_subagent_wrapper: failed to read config {config_path!r}: {exc}",
              file=sys.stderr)
        return 1

    cmd: list = cfg["cmd"]
    status_path: str = cfg["status_path"]
    stdout_log: str = cfg["stdout_log"]
    stderr_log: str = cfg["stderr_log"]
    job_id: str = cfg["job_id"]
    run_id: str = cfg["run_id"]
    agent: str = cfg["agent"]
    session_id: str | None = cfg.get("session_id")
    timeout_secs: int = cfg.get("timeout_secs", 1800)
    scripts_dir: str = cfg.get("scripts_dir", "")

    # Load current status and transition to running
    with open(status_path, encoding="utf-8") as f:
        status = json.load(f)

    status.update(state="running", started_at=_now_iso())
    _write_json_atomic(status_path, status)

    exit_code = 1
    error_text = None
    try:
        with open(stdout_log, "w", encoding="utf-8") as fout, \
             open(stderr_log, "w", encoding="utf-8") as ferr:
            proc = subprocess.run(
                cmd,
                stdout=fout,
                stderr=ferr,
                timeout=timeout_secs,
                check=False,
            )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        error_text = f"agent timed out after {timeout_secs}s"
        exit_code = 124
    except Exception as exc:
        error_text = str(exc)
        exit_code = 1

    final_state = "done" if exit_code == 0 else "failed"
    status.update(state=final_state, ended_at=_now_iso(),
                  exit_code=exit_code, error=error_text)
    _write_json_atomic(status_path, status)

    # Release pool slot
    if scripts_dir:
        try:
            pool_path = Path(scripts_dir) / "subagent_pool.py"
            if pool_path.exists():
                spec = importlib.util.spec_from_file_location(
                    "subagent_pool", str(pool_path))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
                    p = mod.SubagentPool(cap=mod.get_cap())
                    p.release(job_id)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
