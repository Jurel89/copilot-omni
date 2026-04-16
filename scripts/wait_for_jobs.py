#!/usr/bin/env python3
"""wait_for_jobs — poll subagent status.json files until all jobs terminate.

CLI:
    python3 scripts/wait_for_jobs.py <status_path> [<status_path>...]
    python3 scripts/wait_for_jobs.py --run-id <id>
    python3 scripts/wait_for_jobs.py --session-id <id>

Exit codes:
    0   all jobs ended in "done"
    1   at least one job ended in "failed" or "cancelled"
    124 timeout elapsed before all jobs terminated
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OMNI_RUNS = _REPO_ROOT / ".omni" / "runs"

TERMINAL_STATES = frozenset({"done", "failed", "cancelled"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _omni_home() -> Path:
    root = os.environ.get("OMNI_HOME")
    if root:
        return Path(root)
    return Path.home() / ".omni"


def _read_status(path: Path, *, retries: int = 3) -> dict | None:
    """Read and parse a status.json. Retries up to `retries` times on JSONDecodeError."""
    for attempt in range(retries):
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            if attempt < retries - 1:
                time.sleep(0.05)
            else:
                return None
        except Exception:
            return None
    return None


def _find_status_paths_for_run(run_id: str) -> list[Path]:
    """Return all status.json paths under .omni/runs/<run-id>/*/status.json."""
    run_dir = _OMNI_RUNS / run_id
    if not run_dir.exists():
        return []
    paths = []
    for job_dir in sorted(run_dir.iterdir()):
        if job_dir.is_dir():
            sp = job_dir / "status.json"
            if sp.exists():
                paths.append(sp)
    return paths


def _find_status_paths_for_session(session_id: str) -> list[Path]:
    """Scan all run-dirs for status.json files matching session_id."""
    paths = []
    if not _OMNI_RUNS.exists():
        return paths
    for run_dir in sorted(_OMNI_RUNS.iterdir()):
        if not run_dir.is_dir():
            continue
        for job_dir in sorted(run_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            sp = job_dir / "status.json"
            if not sp.exists():
                continue
            status = _read_status(sp)
            if status is None:
                continue
            # Check spec.json for session_id
            spec_path = job_dir / "spec.json"
            if spec_path.exists():
                spec = _read_status(spec_path)
                if spec and spec.get("session_id") == session_id:
                    paths.append(sp)
            elif status.get("session_id") == session_id:
                paths.append(sp)
    return paths


# ---------------------------------------------------------------------------
# Core poll loop
# ---------------------------------------------------------------------------


def wait_for_jobs(
    status_paths: list[Path],
    *,
    timeout: float = 1800.0,
    poll_interval: float = 1.0,
) -> int:
    """Poll status_paths until all jobs reach a terminal state.

    Emits one JSONL line per job at terminal state:
        {job_id, run_id, state, exit_code, duration_s, stdout_path, stderr_path}

    Returns:
        0  — all done
        1  — any failed/cancelled
        124 — timeout
    """
    if not status_paths:
        print("wait_for_jobs: no status paths provided", file=sys.stderr)
        return 1

    pending = {str(p): p for p in status_paths}
    terminal_states: dict[str, dict] = {}  # path -> status dict
    start = time.monotonic()

    while pending:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            remaining = list(pending.keys())
            print(
                f"wait_for_jobs: timeout after {timeout:.0f}s; "
                f"{len(remaining)} job(s) still pending",
                file=sys.stderr,
            )
            return 124

        for path_str, path in list(pending.items()):
            status = _read_status(path)
            if status is None:
                continue
            state = status.get("state", "")
            if state in TERMINAL_STATES:
                terminal_states[path_str] = status
                del pending[path_str]

                # Compute duration
                started_at = status.get("started_at")
                ended_at = status.get("ended_at")
                duration_s: float | None = None
                if started_at and ended_at:
                    try:
                        from datetime import datetime, timezone
                        fmt = "%Y-%m-%dT%H:%M:%SZ"
                        t0 = datetime.strptime(started_at, fmt).replace(
                            tzinfo=timezone.utc)
                        t1 = datetime.strptime(ended_at, fmt).replace(
                            tzinfo=timezone.utc)
                        duration_s = (t1 - t0).total_seconds()
                    except Exception:
                        pass

                job_dir = path.parent
                summary = {
                    "job_id": status.get("job_id"),
                    "run_id": status.get("run_id"),
                    "state": state,
                    "exit_code": status.get("exit_code"),
                    "duration_s": duration_s,
                    "stdout_path": str(job_dir / "stdout.log"),
                    "stderr_path": str(job_dir / "stderr.log"),
                }
                print(json.dumps(summary), flush=True)

        if pending:
            time.sleep(poll_interval)

    # Determine exit code
    any_failed = any(
        s.get("state") in ("failed", "cancelled")
        for s in terminal_states.values()
    )
    return 1 if any_failed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll subagent status.json paths until all jobs terminate"
    )
    parser.add_argument(
        "status_paths",
        nargs="*",
        metavar="STATUS_PATH",
        help="Path(s) to status.json file(s)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        help="Wait for ALL jobs under .omni/runs/<id>/",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        metavar="ID",
        help="Wait for ALL jobs in a session (scans all run dirs)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1800.0,
        metavar="SECS",
        help="Timeout in seconds (default: 1800); exits 124 on timeout",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        metavar="SECS",
        help="Poll interval in seconds (default: 1.0)",
    )
    args = parser.parse_args()

    paths: list[Path] = [Path(p) for p in args.status_paths]

    if args.run_id:
        extra = _find_status_paths_for_run(args.run_id)
        if not extra:
            print(
                f"wait_for_jobs: no jobs found for run-id {args.run_id!r}",
                file=sys.stderr,
            )
            return 1
        paths.extend(extra)

    if args.session_id:
        extra = _find_status_paths_for_session(args.session_id)
        if not extra:
            print(
                f"wait_for_jobs: no jobs found for session-id {args.session_id!r}",
                file=sys.stderr,
            )
            return 1
        paths.extend(extra)

    if not paths:
        parser.print_help()
        return 2

    return wait_for_jobs(
        paths,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    sys.exit(main())
