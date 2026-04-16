#!/usr/bin/env python3
"""Pipeline-state reader — reads live state via MCP for all known modes.

Public API
----------
    read_pipeline_state(session_id=None, mode="router") -> dict | None

Attempts to read the given mode's state from MCP (via state_read JSON-RPC).
Returns the stored body dict on success.

Falls back to scanning `.omni/runs/<run-prefix>-*/status.json` for the most
recent terminal state when MCP is unavailable.

Returns None if no state is found (callers must handle None — never returns
the old WS5 stub).

CLI
---
    python3 scripts/router_state.py --read [--mode router] [--session-id <id>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def read_pipeline_state(
    session_id: str | None = None,
    mode: str = "router",
) -> dict | None:
    """Read pipeline state for the given mode.

    Tries MCP first; falls back to filesystem scan; returns None if nothing found.
    Never returns the old WS5 stub.
    """
    # Try MCP read
    try:
        result = _read_via_mcp(mode=mode, session_id=session_id)
        if result is not None:
            return result
    except Exception as exc:
        print(
            f"[router_state] warn: MCP read failed for mode={mode!r}: {exc}",
            file=sys.stderr,
        )

    # Fallback: scan filesystem run dirs for most recent terminal status
    try:
        return _read_filesystem_fallback(mode=mode, session_id=session_id)
    except Exception as exc:
        print(
            f"[router_state] warn: filesystem fallback failed for mode={mode!r}: {exc}",
            file=sys.stderr,
        )
    return None


def _read_filesystem_fallback(
    mode: str,
    session_id: str | None = None,
) -> dict | None:
    """Scan .omni/runs/<mode>-*/status.json for the most recent terminal state.

    Returns the status dict from the most recently modified terminal-state file,
    or None if no matching run dirs exist.
    """
    # Resolve .omni/runs relative to the repo root (two levels up from scripts/)
    here = Path(__file__).resolve().parent.parent
    runs_dir = here / ".omni" / "runs"
    if not runs_dir.exists():
        return None

    terminal_states = {"done", "failed", "cancelled", "completed"}
    best_mtime = -1.0
    best_status: dict | None = None

    # Match run dirs prefixed with the mode name
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        if not run_dir.name.startswith(mode):
            continue
        # Scan all job subdirectories for status.json
        for status_file in run_dir.rglob("status.json"):
            try:
                mtime = status_file.stat().st_mtime
                if mtime <= best_mtime:
                    continue
                data = json.loads(status_file.read_text(encoding="utf-8"))
                state = data.get("state", "")
                if state in terminal_states:
                    best_mtime = mtime
                    best_status = data
            except Exception:
                continue

    return best_status


def _read_via_mcp(mode: str, session_id: str | None) -> dict | None:
    """Send a state_read JSON-RPC request to the MCP server subprocess."""
    import subprocess
    import uuid

    server_py = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
    if not server_py.exists():
        raise FileNotFoundError(f"MCP server not found at {server_py}")

    args: dict[str, Any] = {"mode": mode}
    if session_id:
        args["session_id"] = session_id

    rpc_request = json.dumps({
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {
            "name": "state_read",
            "arguments": args,
        },
    })

    proc = subprocess.run(
        [sys.executable, str(server_py)],
        input=rpc_request,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"MCP server exited {proc.returncode}: {proc.stderr[:200]}"
        )

    # Parse the JSON-RPC response
    try:
        resp = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise RuntimeError(f"Malformed MCP response: {exc}") from exc

    result = resp.get("result", {})
    # MCP state_read returns {"content": [{"type": "text", "text": "<json>"}]}
    content = result.get("content", [])
    if not content:
        return None
    text = content[0].get("text", "")
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WS3 stub pipeline-state reader."
    )
    parser.add_argument(
        "--read", action="store_true", required=True,
        help="Read state for the given mode",
    )
    parser.add_argument(
        "--mode", default="router",
        help="State mode to read (default: router)",
    )
    parser.add_argument(
        "--session-id", default=None,
        help="Optional session ID to scope the read",
    )
    args = parser.parse_args(argv)

    result = read_pipeline_state(session_id=args.session_id, mode=args.mode)
    if result is None:
        print(json.dumps({"status": "none", "reason": "no state found"}))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
